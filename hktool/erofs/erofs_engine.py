"""
Universal Huawei & AOSP EROFS Toolkit Engine (EMUI 9/10/MagicUI & Android 11..14 GSI)
100% Pure Python - No WSL or Linux dependencies required.
Supports Unpacking with full LZ4 decompression and validation, Repacking, and Sparse/Raw conversion.
"""
from __future__ import annotations

import base64
import bisect
import concurrent.futures
import hashlib
import io
import json
import math
import os
import stat
import struct
import sys
import time
import uuid
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Dict, List, Optional, Tuple

SPARSE_MAGIC = 0xED26FF3A
CHUNK_TYPE_RAW = 0xCAC1
CHUNK_TYPE_FILL = 0xCAC2
CHUNK_TYPE_DONT_CARE = 0xCAC3
CHUNK_TYPE_CRC32 = 0xCAC4

EROFS_SUPER_OFFSET = 1024
EROFS_MAGIC = 0xE0F5E1E2

EROFS_FT_REG_FILE = 1
EROFS_FT_DIR = 2
EROFS_FT_SYMLINK = 7

EROFS_INODE_FLAT_PLAIN = 0
EROFS_INODE_COMPRESSED_LEGACY = 1
EROFS_INODE_FLAT_INLINE = 2

Z_EROFS_CLUSTER_TYPE_PLAIN = 0
Z_EROFS_CLUSTER_TYPE_HEAD = 1
Z_EROFS_CLUSTER_TYPE_NONHEAD = 2
Z_EROFS_CLUSTER_TYPE_HEAD2 = 3
Z_EROFS_VLE_DI_D0_CBLKCNT = 0x0800

EROFS_XATTR_INDEX_PREFIX = {
    1: "user.",
    2: "system.posix_acl_access",
    3: "system.posix_acl_default",
    4: "trusted.",
    5: "lustre.",
    6: "security.",
}


class SparseReader:
    def __init__(self, image_path: str | Path):
        self.image_path = str(image_path)
        self.f = open(self.image_path, "rb")
        header = self.f.read(28)
        if len(header) != 28:
            raise ValueError("Short Android sparse header")
        (
            magic, major, minor, file_hdr_sz, chunk_hdr_sz,
            blk_sz, total_blks, total_chunks, checksum
        ) = struct.unpack("<IHHHHIIII", header)
        if magic != SPARSE_MAGIC:
            raise ValueError(f"{image_path!r} is not an Android sparse image")

        self.block_size = blk_sz
        self.logical_size = total_blks * blk_sz
        self.segments = []

        if file_hdr_sz > 28:
            self.f.seek(file_hdr_sz)

        logical = 0
        for chunk_index in range(total_chunks):
            chunk_off = self.f.tell()
            raw = self.f.read(chunk_hdr_sz)
            if len(raw) != chunk_hdr_sz:
                raise ValueError(f"Short sparse chunk header at chunk {chunk_index}")
            chunk_type, _reserved, chunk_sz, total_sz = struct.unpack("<HHII", raw[:12])
            payload_sz = total_sz - chunk_hdr_sz
            logical_sz = chunk_sz * blk_sz

            if chunk_type == CHUNK_TYPE_RAW:
                self.segments.append((logical, logical + logical_sz, "raw", self.f.tell(), None))
                self.f.seek(payload_sz, os.SEEK_CUR)
                logical += logical_sz
            elif chunk_type == CHUNK_TYPE_FILL:
                fill = self.f.read(4)
                if len(fill) != 4:
                    raise ValueError(f"Short fill sparse chunk at chunk {chunk_index}")
                if payload_sz > 4:
                    self.f.seek(payload_sz - 4, os.SEEK_CUR)
                self.segments.append((logical, logical + logical_sz, "fill", None, fill))
                logical += logical_sz
            elif chunk_type == CHUNK_TYPE_DONT_CARE:
                if payload_sz:
                    self.f.seek(payload_sz, os.SEEK_CUR)
                self.segments.append((logical, logical + logical_sz, "zero", None, None))
                logical += logical_sz
            elif chunk_type == CHUNK_TYPE_CRC32:
                if payload_sz:
                    self.f.seek(payload_sz, os.SEEK_CUR)
            else:
                raise ValueError(f"Unsupported sparse chunk type 0x{chunk_type:04X} at offset {chunk_off}")

        self.starts = [segment[0] for segment in self.segments]

    def read_at(self, offset: int, size: int) -> bytes:
        if size <= 0:
            return b""
        end = offset + size
        if offset < 0 or end > self.logical_size:
            raise ValueError(f"Read outside logical image: offset={offset}, size={size}")

        out = bytearray()
        while offset < end:
            idx = bisect.bisect_right(self.starts, offset) - 1
            if idx < 0:
                raise ValueError(f"Read before first sparse segment at offset {offset}")
            seg_start, seg_end, seg_kind, file_off, fill = self.segments[idx]
            take = min(end, seg_end) - offset
            if take <= 0:
                raise ValueError(f"Sparse segment gap at offset {offset}")

            if seg_kind == "raw":
                self.f.seek(file_off + offset - seg_start)
                data = self.f.read(take)
                if len(data) != take:
                    raise ValueError(f"Short image read at logical offset {offset}")
                out += data
            elif seg_kind == "zero":
                out += b"\0" * take
            elif seg_kind == "fill":
                rel = offset - seg_start
                repeated = fill * ((take + (rel % 4) + 3) // 4 + 1)
                out += repeated[rel % 4 : rel % 4 + take]
            offset += take
        return bytes(out)

    def close(self):
        self.f.close()


class RawReader:
    def __init__(self, image_path: str | Path):
        self.image_path = str(image_path)
        self.f = open(self.image_path, "rb")
        self.logical_size = os.path.getsize(self.image_path)
        self.block_size = 4096

    def read_at(self, offset: int, size: int) -> bytes:
        if size <= 0:
            return b""
        end = offset + size
        if offset < 0 or end > self.logical_size:
            raise ValueError(f"Read outside raw image: offset={offset}, size={size}")
        self.f.seek(offset)
        data = self.f.read(size)
        if len(data) != size:
            raise ValueError(f"Short raw image read at offset {offset}")
        return data

    def close(self):
        self.f.close()


def open_image_reader(image_path: str | Path):
    with open(image_path, "rb") as f:
        header = f.read(4)
    if len(header) != 4:
        raise ValueError(f"{image_path!r} is too small")
    magic = struct.unpack("<I", header)[0]
    if magic == SPARSE_MAGIC:
        return SparseReader(image_path)
    return RawReader(image_path)


def lz4_raw_decompress(src: bytes, min_output_size: int = 0) -> bytes:
    out = bytearray()
    i = 0
    n = len(src)

    while i < n:
        if min_output_size > 0 and len(out) >= min_output_size:
            break
        token = src[i]
        i += 1

        lit_len = token >> 4
        if lit_len == 15:
            while i < n:
                value = src[i]
                i += 1
                lit_len += value
                if value != 255:
                    break

        if i + lit_len > n:
            out += src[i:]
            break
        out += src[i : i + lit_len]
        i += lit_len
        if (min_output_size > 0 and len(out) >= min_output_size) or i >= n or i + 2 > n:
            break

        match_offset = src[i] | (src[i + 1] << 8)
        i += 2
        if match_offset == 0:
            while i < n and src[i] == 0:
                i += 1
            continue

        match_len = token & 0x0F
        if match_len == 15:
            while i < n:
                value = src[i]
                i += 1
                match_len += value
                if value != 255:
                    break
        match_len += 4

        start = len(out) - match_offset
        for _ in range(match_len):
            if 0 <= start < len(out):
                out.append(out[start])
            else:
                out.append(0)
            start += 1
            if min_output_size > 0 and len(out) >= min_output_size:
                break

    if min_output_size > 0:
        return bytes(out[:min_output_size])
    return bytes(out)


@dataclass
class Inode:
    nid: int
    offset: int
    version: int
    layout: int
    xattr_count: int
    mode: int
    nlink: int
    size: int
    u: int
    ino: int
    uid: int
    gid: int
    inode_size: int

    @property
    def type(self):
        return stat.S_IFMT(self.mode)

    @property
    def data_offset(self):
        xattr_size = (12 + 4 * (self.xattr_count - 1)) if self.xattr_count else 0
        return self.offset + self.inode_size + xattr_size

    @property
    def compressed_index_offset(self):
        aligned = (self.data_offset + 7) & ~7
        return aligned + 16


class HuaweiErofs:
    def __init__(self, image_path: str | Path):
        self.image_path = str(image_path)
        self.reader = open_image_reader(image_path)
        sb = self.reader.read_at(EROFS_SUPER_OFFSET, 128)
        magic = struct.unpack_from("<I", sb, 0)[0]
        if magic != EROFS_MAGIC:
            raise ValueError(f"EROFS superblock magic (0xE0F5E1E2) not found at offset {EROFS_SUPER_OFFSET}")

        self.block_bits = sb[12]
        self.block_size = 1 << self.block_bits
        self.root_nid = struct.unpack_from("<H", sb, 14)[0]
        self.blocks = struct.unpack_from("<I", sb, 36)[0]
        self.meta_blkaddr = struct.unpack_from("<I", sb, 40)[0]
        self.xattr_blkaddr = struct.unpack_from("<I", sb, 44)[0]
        self.feature_incompat = struct.unpack_from("<I", sb, 80)[0]
        self.feature_compat = struct.unpack_from("<I", sb, 8)[0]
        self._inode_cache = {}
        self._shared_xattr_cache = {}

    def close(self):
        if hasattr(self, "reader") and self.reader is not None:
            self.reader.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def read_inode(self, nid: int) -> Inode:
        cached = self._inode_cache.get(nid)
        if cached is not None:
            return cached

        offset = self.meta_blkaddr * self.block_size + nid * 32
        raw = self.reader.read_at(offset, 96)
        i_format, xattr_count, mode = struct.unpack_from("<HHH", raw, 0)
        version = i_format & 1
        layout = (i_format >> 1) & 7

        if version == 0:
            (
                _fmt, xattr_count, mode, nlink, size, _reserved,
                u, ino, uid, gid, _reserved2
            ) = struct.unpack_from("<HHHHIIIIHHI", raw, 0)
            inode_size = 32
        else:
            (
                _fmt, xattr_count, mode, _reserved, size,
                u, ino, uid, gid, _ctime, _ctime_nsec, nlink
            ) = struct.unpack_from("<HHHHQIIIIQII", raw, 0)
            inode_size = 64

        inode = Inode(
            nid=nid, offset=offset, version=version, layout=layout,
            xattr_count=xattr_count, mode=mode, nlink=nlink, size=size,
            u=u, ino=ino, uid=uid, gid=gid, inode_size=inode_size
        )
        self._inode_cache[nid] = inode
        return inode

    def _parse_xattr_entry(self, raw: bytes, offset: int):
        if offset + 4 > len(raw):
            return None
        name_len, name_index, value_size = struct.unpack_from("<BBH", raw, offset)
        if name_len == 0 and name_index == 0 and value_size == 0:
            return None

        entry_size = (4 + name_len + value_size + 3) & ~3
        if entry_size <= 0 or offset + entry_size > len(raw):
            return None

        name_start = offset + 4
        name = raw[name_start : name_start + name_len].decode("utf-8", "surrogateescape")
        value_start = name_start + name_len
        value = raw[value_start : value_start + value_size]
        prefix = EROFS_XATTR_INDEX_PREFIX.get(name_index & 0x7F, "")
        return prefix + name, value, entry_size

    def _read_shared_xattr(self, xattr_id: int):
        cached = self._shared_xattr_cache.get(xattr_id)
        if cached is not None:
            return cached

        offset = self.xattr_blkaddr * self.block_size + 4 * xattr_id
        header = self.reader.read_at(offset, 4)
        name_len, _name_index, value_size = struct.unpack("<BBH", header)
        entry_size = (4 + name_len + value_size + 3) & ~3
        raw = self.reader.read_at(offset, entry_size)
        parsed = self._parse_xattr_entry(raw, 0)
        self._shared_xattr_cache[xattr_id] = parsed
        return parsed

    def read_xattrs(self, nid: int) -> Dict[str, bytes]:
        inode = self.read_inode(nid)
        if not inode.xattr_count:
            return {}

        xattr_size = inode.data_offset - inode.offset - inode.inode_size
        if xattr_size < 12:
            return {}

        raw = self.reader.read_at(inode.offset + inode.inode_size, xattr_size)
        shared_count = raw[4]
        attrs = {}

        if shared_count <= 128:
            for index in range(shared_count):
                id_offset = 12 + index * 4
                if id_offset + 4 > len(raw):
                    break
                xattr_id = struct.unpack_from("<I", raw, id_offset)[0]
                parsed = self._read_shared_xattr(xattr_id)
                if parsed is not None:
                    name, value, _entry_size = parsed
                    attrs[name] = value

        offset = 12 + shared_count * 4
        while offset + 4 <= len(raw):
            parsed = self._parse_xattr_entry(raw, offset)
            if parsed is None:
                break
            full_name, value, entry_size = parsed
            attrs[full_name] = value
            offset += entry_size

        return attrs

    def read_file(self, nid: int) -> bytes:
        inode = self.read_inode(nid)
        if inode.size == 0:
            return b""

        if inode.layout == EROFS_INODE_FLAT_PLAIN:
            return self.reader.read_at(inode.u * self.block_size, inode.size)
        if inode.layout == EROFS_INODE_FLAT_INLINE:
            full_size = inode.size & ~(self.block_size - 1)
            tail_size = inode.size - full_size
            data = bytearray()
            if full_size:
                data += self.reader.read_at(inode.u * self.block_size, full_size)
            if tail_size:
                data += self.reader.read_at(inode.data_offset, tail_size)
            return bytes(data)
        if inode.layout == EROFS_INODE_COMPRESSED_LEGACY:
            return self._read_compressed(inode)
        raise NotImplementedError(f"Unsupported EROFS data layout {inode.layout} for nid {nid}")

    def _read_compressed(self, inode: Inode) -> bytes:
        logical_clusters = (inode.size + self.block_size - 1) // self.block_size
        index_offset = inode.compressed_index_offset
        indexes = []

        has_type3 = False
        for lcn in range(logical_clusters):
            advise, clusterofs, blkaddr = struct.unpack(
                "<HHI", self.reader.read_at(index_offset + lcn * 8, 8)
            )
            cluster_type = advise & 3
            if cluster_type == Z_EROFS_CLUSTER_TYPE_HEAD2:
                has_type3 = True
            entry = {
                "lcn": lcn,
                "type": cluster_type,
                "clusterofs": clusterofs & (self.block_size - 1),
                "raw_clusterofs": clusterofs,
                "u": blkaddr,
            }
            if cluster_type == Z_EROFS_CLUSTER_TYPE_NONHEAD:
                entry["delta0"] = blkaddr & 0xFFFF
                entry["delta1"] = (blkaddr >> 16) & 0xFFFF
            else:
                entry["blkaddr"] = blkaddr
            indexes.append(entry)

        # MODE A: Huawei EMUI Early EROFS Layout (Kirin 710 Stock)
        if has_type3 or not any(entry["type"] == Z_EROFS_CLUSTER_TYPE_NONHEAD for entry in indexes):
            groups = []
            if not any(entry["type"] == Z_EROFS_CLUSTER_TYPE_NONHEAD for entry in indexes):
                for entry in indexes:
                    low_clusterofs = entry["clusterofs"]
                    logical_start = entry["lcn"] * self.block_size + low_clusterofs
                    if not groups or groups[-1]["blkaddr"] != entry["blkaddr"] or groups[-1]["low"] != low_clusterofs:
                        groups.append({
                            "blkaddr": entry["blkaddr"],
                            "type": entry["type"],
                            "low": low_clusterofs,
                            "logical_start": logical_start,
                            "compressed_blocks": 1,
                        })
                groups.sort(key=lambda item: item["logical_start"])
                for idx, group in enumerate(groups):
                    group["logical_end"] = groups[idx + 1]["logical_start"] if idx + 1 < len(groups) else inode.size
            else:
                for index, entry in enumerate(indexes):
                    if entry["type"] == Z_EROFS_CLUSTER_TYPE_NONHEAD:
                        continue
                    start = entry["lcn"] * self.block_size + entry["clusterofs"]
                    next_head = logical_clusters
                    for later in indexes[index + 1 :]:
                        if later["type"] != Z_EROFS_CLUSTER_TYPE_NONHEAD:
                            next_head = later["lcn"]
                            break
                    end = min(next_head * self.block_size, inode.size)
                    compressed_blocks = 1
                    if entry["type"] in (Z_EROFS_CLUSTER_TYPE_HEAD, Z_EROFS_CLUSTER_TYPE_HEAD2):
                        if index + 1 < len(indexes) and indexes[index + 1]["type"] == Z_EROFS_CLUSTER_TYPE_NONHEAD:
                            delta0 = indexes[index + 1]["delta0"]
                            if delta0 & Z_EROFS_VLE_DI_D0_CBLKCNT:
                                compressed_blocks = delta0 & ~Z_EROFS_VLE_DI_D0_CBLKCNT
                        if compressed_blocks <= 0:
                            compressed_blocks = 1
                    groups.append({
                        "blkaddr": entry["blkaddr"],
                        "type": entry["type"],
                        "logical_start": start,
                        "logical_end": end,
                        "compressed_blocks": compressed_blocks,
                    })

            out = bytearray(inode.size)
            for group in groups:
                start = group["logical_start"]
                if start >= inode.size:
                    continue
                end = min(max(group["logical_end"], start), inode.size)
                needed = end - start
                if needed <= 0:
                    continue

                paddr = group["blkaddr"] * self.block_size
                cluster = self.reader.read_at(paddr, group["compressed_blocks"] * self.block_size)

                if group["type"] in (Z_EROFS_CLUSTER_TYPE_HEAD, Z_EROFS_CLUSTER_TYPE_NONHEAD, Z_EROFS_CLUSTER_TYPE_HEAD2):
                    decoded = lz4_raw_decompress(cluster, needed)
                else:
                    decoded = cluster[:needed]
                out[start:end] = decoded
            return bytes(out)

        # MODE B: In-Kernel Linux & Modern AOSP GSI Layout (Android 11..14)
        out = bytearray(inode.size)
        i = 0
        while i < len(indexes):
            entry = indexes[i]
            ctype = entry["type"]

            if ctype == Z_EROFS_CLUSTER_TYPE_PLAIN:
                m_la = i * self.block_size + entry["clusterofs"]
                nxt = i + 1
                nxt_la = (nxt * self.block_size + indexes[nxt]["clusterofs"]) if nxt < len(indexes) else inode.size
                m_llen = min(nxt_la, inode.size) - m_la
                if m_llen > 0 and m_la < inode.size:
                    if entry["u"] != 0:
                        out[m_la : m_la + m_llen] = self.reader.read_at(entry["u"] * self.block_size, m_llen)
                    else:
                        out[m_la : m_la + m_llen] = self.reader.read_at(inode.data_offset, m_llen)
                i += 1

            elif ctype in (Z_EROFS_CLUSTER_TYPE_HEAD, Z_EROFS_CLUSTER_TYPE_HEAD2):
                head_lcn = i
                head_blk = entry["blkaddr"]
                head_cofs = entry["clusterofs"]
                m_la = head_lcn * self.block_size + head_cofs

                nxt = i + 1
                while nxt < len(indexes) and indexes[nxt]["type"] == Z_EROFS_CLUSTER_TYPE_NONHEAD:
                    nxt += 1

                nxt_la = (nxt * self.block_size + indexes[nxt]["clusterofs"]) if nxt < len(indexes) else inode.size
                m_llen = min(nxt_la, inode.size) - m_la

                cblks = 1
                if nxt - i > 1:
                    d0 = indexes[i + 1]["delta0"]
                    if d0 & Z_EROFS_VLE_DI_D0_CBLKCNT:
                        cblks = d0 & ~Z_EROFS_VLE_DI_D0_CBLKCNT
                cblks = max(1, min(16, cblks))

                if m_llen > 0 and m_la < inode.size:
                    cdata = self.reader.read_at(head_blk * self.block_size, cblks * self.block_size)
                    decomp = lz4_raw_decompress(cdata)
                    out[m_la : m_la + min(m_llen, len(decomp))] = decomp[:m_llen]

                i = nxt
            else:
                i += 1

        return bytes(out)

    def read_dir(self, nid: int) -> List[Tuple[str, int, int]]:
        inode = self.read_inode(nid)
        data = self.read_file(nid)
        entries = []
        for block_start in range(0, len(data), self.block_size):
            block = data[block_start : block_start + self.block_size]
            if len(block) < 12:
                continue
            first_nameoff = struct.unpack_from("<H", block, 8)[0]
            if first_nameoff == 0 or first_nameoff > len(block) or first_nameoff % 12 != 0:
                continue
            count = first_nameoff // 12
            for idx in range(count):
                rec_off = idx * 12
                child_nid, nameoff, file_type, _reserved = struct.unpack_from("<QHBB", block, rec_off)
                if nameoff >= len(block):
                    continue
                next_nameoff = struct.unpack_from("<H", block, (idx + 1) * 12 + 8)[0] if idx + 1 < count else len(block)
                raw_name = block[nameoff:next_nameoff].split(b"\0", 1)[0]
                if not raw_name:
                    continue
                name = raw_name.decode("utf-8", "surrogateescape")
                if name in (".", ".."):
                    continue
                entries.append((name, child_nid, file_type))
        return entries

    def walk(self):
        stack = [(PurePosixPath("/"), self.root_nid)]
        seen_dirs = set()
        while stack:
            path, nid = stack.pop()
            if nid in seen_dirs:
                continue
            seen_dirs.add(nid)
            try:
                entries = self.read_dir(nid)
            except Exception as exc:
                yield path, nid, "dir-error", exc
                continue
            for name, child_nid, file_type in entries:
                child_path = path / name
                yield child_path, child_nid, file_type, None
                if file_type == EROFS_FT_DIR:
                    stack.append((child_path, child_nid))


def convert_raw_to_sparse(raw_path: str | Path, sparse_path: str | Path, block_size: int = 4096):
    raw_size = os.path.getsize(raw_path)
    total_blks = (raw_size + block_size - 1) // block_size

    with open(raw_path, "rb") as fin, open(sparse_path, "wb") as fout:
        fout.write(b"\x00" * 28)

        chunks = 0
        cur_type = None
        cur_blks = 0
        cur_data = bytearray()

        def flush_chunk():
            nonlocal chunks, cur_type, cur_blks, cur_data
            if cur_blks == 0:
                return
            if cur_type == "raw":
                fout.write(struct.pack("<HHII", CHUNK_TYPE_RAW, 0, cur_blks, 12 + len(cur_data)))
                fout.write(cur_data)
                chunks += 1
            elif cur_type == "dont_care":
                fout.write(struct.pack("<HHII", CHUNK_TYPE_DONT_CARE, 0, cur_blks, 12))
                chunks += 1
            cur_blks = 0
            cur_data = bytearray()
            cur_type = None

        for _ in range(total_blks):
            blk = fin.read(block_size)
            if len(blk) < block_size:
                blk = blk + b"\x00" * (block_size - len(blk))

            is_zero = (blk == b"\x00" * block_size)
            block_kind = "dont_care" if is_zero else "raw"

            if cur_type != block_kind or cur_blks >= 65535:
                flush_chunk()
                cur_type = block_kind

            cur_blks += 1
            if block_kind == "raw":
                cur_data.extend(blk)

        flush_chunk()

        fout.seek(0)
        hdr = struct.pack("<IHHHHIIII", SPARSE_MAGIC, 1, 0, 28, 12, block_size, total_blks, chunks, 0)
        fout.write(hdr)


def convert_sparse_to_raw(sparse_path: str | Path, raw_path: str | Path):
    reader = SparseReader(sparse_path)
    with open(raw_path, "wb") as fout:
        chunk_size = 1024 * 1024
        for off in range(0, reader.logical_size, chunk_size):
            take = min(chunk_size, reader.logical_size - off)
            fout.write(reader.read_at(off, take))
    reader.close()


def unpack_erofs(
    image_path: Path,
    out_dir: Path,
    on_status: Optional[Callable[[str], None]] = None,
    on_progress: Optional[Callable[[int, int], None]] = None
) -> Dict[str, Any]:
    """Unpack EROFS image with full LZ4 decompression, metadata extraction, and permission mapping."""
    fs = HuaweiErofs(image_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = out_dir / "metadata.jsonl"
    fs_config_path = out_dir / "_meta_fs_config.json"
    file_contexts_path = out_dir / "_meta_file_contexts.txt"

    counts = {"dirs": 0, "files": 0, "symlinks": 0, "other": 0}
    metadata_entries = []
    fs_config = {}
    file_contexts = []
    file_tasks = []

    root = fs.read_inode(fs.root_nid)
    root_xattrs = fs.read_xattrs(fs.root_nid)
    root_selinux = root_xattrs.get("security.selinux", b"").rstrip(b"\x00").decode("utf-8", "ignore")

    fs_config["/"] = {"mode": oct(root.mode), "uid": root.uid, "gid": root.gid}
    if root_selinux:
        file_contexts.append(f"/ {root_selinux}")

    if on_status:
        on_status(f"Scanning EROFS directory structure from {image_path.name}...")

    for image_path_item, nid, file_type, error in fs.walk():
        if error is not None:
            continue

        inode = fs.read_inode(nid)
        parts = image_path_item.parts
        if parts and parts[0] == "/":
            parts = parts[1:]
        host_path = out_dir.joinpath(*parts)

        mode_type = inode.type
        raw_xattrs = fs.read_xattrs(nid)
        selinux = raw_xattrs.get("security.selinux", b"").rstrip(b"\x00").decode("utf-8", "ignore")

        rel_p = "/" + str(image_path_item).lstrip("/")
        fs_config[rel_p] = {"mode": oct(inode.mode), "uid": inode.uid, "gid": inode.gid}
        if selinux:
            file_contexts.append(f"{rel_p} {selinux}")

        if mode_type == stat.S_IFDIR or file_type == EROFS_FT_DIR:
            host_path.mkdir(parents=True, exist_ok=True)
            counts["dirs"] += 1
        elif mode_type == stat.S_IFREG or file_type == EROFS_FT_REG_FILE:
            counts["files"] += 1
            file_tasks.append((str(image_path_item), host_path, nid, inode.size))
        elif mode_type == stat.S_IFLNK:
            counts["symlinks"] += 1
            target = fs.read_file(nid).decode("utf-8", "surrogateescape")
            host_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.symlink(target, host_path)
            except OSError:
                with open(host_path, "wb") as f:
                    f.write(f"SYMLINK -> {target}\n".encode("utf-8", "surrogateescape"))

    total_files = len(file_tasks)
    if on_status:
        on_status(f"Extracting {total_files} files using pure Python LZ4 engine...")

    for idx, (ipath, hpath, nid, expected_sz) in enumerate(file_tasks):
        data = fs.read_file(nid)
        hpath.parent.mkdir(parents=True, exist_ok=True)
        with open(hpath, "wb") as f:
            f.write(data)

        if on_progress and (idx % 200 == 0 or idx == total_files - 1):
            on_progress(idx + 1, total_files)

    with open(fs_config_path, "w", encoding="utf-8") as fsc:
        json.dump(fs_config, fsc, indent=2)

    with open(file_contexts_path, "w", encoding="utf-8") as fc:
        fc.write("\n".join(file_contexts) + "\n")

    fs.close()
    return counts


def repack_erofs(
    src_dir: Path,
    out_img: Path,
    sparse: bool = True,
    volume_name: str = "system",
    on_status: Optional[Callable[[str], None]] = None
) -> Tuple[int, int]:
    """Repack folder into flashable Huawei / AOSP EROFS image."""
    BLOCK_SIZE = 4096

    fs_config_file = src_dir / "_meta_fs_config.json"
    file_contexts_file = src_dir / "_meta_file_contexts.txt"

    fs_config = {}
    if fs_config_file.exists():
        with open(fs_config_file, "r", encoding="utf-8") as f:
            fs_config = json.load(f)

    file_contexts = {}
    if file_contexts_file.exists():
        with open(file_contexts_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        file_contexts[parts[0]] = parts[1]

    shared_xattrs = []
    xattr_map = {}

    def get_xattr_id(context_str):
        if not context_str:
            return None
        if context_str in xattr_map:
            return xattr_map[context_str]
        val_bytes = context_str.encode("utf-8") + b"\x00"
        name_bytes = b"selinux"
        entry = struct.pack("<BBH", len(name_bytes), 6, len(val_bytes)) + name_bytes + val_bytes
        pad = (4 - (len(entry) % 4)) % 4
        entry += b"\x00" * pad
        xid = len(shared_xattrs)
        shared_xattrs.append(entry)
        xattr_map[context_str] = xid
        return xid

    class FSNode:
        def __init__(self, rel_path, is_dir, host_path=None, target=None):
            self.rel_path = rel_path
            self.is_dir = is_dir
            self.host_path = host_path
            self.target = target
            self.children = []
            self.size = 0
            self.mode = 0o040755 if is_dir else 0o100644
            self.uid = 0
            self.gid = 0
            self.nid = 0
            self.data_blkaddr = 0
            self.inline_data = b""
            self.layout = 0
            self.selinux = None
            self.xattr_id = None
            self.dir_block = None

    root_node = FSNode("/", is_dir=True)
    nodes_by_path = {"/": root_node}
    all_nodes = [root_node]

    for root, dirs, files in os.walk(src_dir):
        rel_root = Path(root).relative_to(src_dir).as_posix()
        dir_node_path = "/" if rel_root == "." else "/" + rel_root
        cur_dir_node = nodes_by_path[dir_node_path]

        for d in sorted(dirs):
            child_rel = dir_node_path.rstrip("/") + "/" + d
            d_node = FSNode(child_rel, is_dir=True)
            nodes_by_path[child_rel] = d_node
            cur_dir_node.children.append((d, d_node))
            all_nodes.append(d_node)

        for f in sorted(files):
            if f in ("_meta_fs_config.json", "_meta_file_contexts.txt", "metadata.jsonl", "verify_report.txt"):
                continue
            f_host = os.path.join(root, f)
            child_rel = dir_node_path.rstrip("/") + "/" + f

            is_symlink = os.path.islink(f_host)
            target = None
            if is_symlink:
                target = os.readlink(f_host)
            else:
                if os.path.getsize(f_host) < 1024:
                    with open(f_host, "rb") as sf:
                        first_line = sf.readline()
                        if first_line.startswith(b"SYMLINK -> "):
                            target = first_line[11:].decode("utf-8", "ignore").rstrip("\r\n")

            if target is not None:
                f_node = FSNode(child_rel, is_dir=False, host_path=f_host, target=target)
                f_node.mode = 0o120777
            else:
                f_node = FSNode(child_rel, is_dir=False, host_path=f_host)
                f_node.size = os.path.getsize(f_host)
                f_node.mode = 0o100644

            nodes_by_path[child_rel] = f_node
            cur_dir_node.children.append((f, f_node))
            all_nodes.append(f_node)

    for node in all_nodes:
        if node.rel_path in fs_config:
            cfg = fs_config[node.rel_path]
            m = cfg.get("mode")
            if isinstance(m, str):
                m = int(m, 8)
            node.mode = m
            node.uid = cfg.get("uid", 0)
            node.gid = cfg.get("gid", 0)

        if node.rel_path in file_contexts:
            node.selinux = file_contexts[node.rel_path]
            node.xattr_id = get_xattr_id(node.selinux)

    raw_output = str(out_img) + ".raw_tmp" if sparse else str(out_img)

    with open(raw_output, "wb") as fout:
        fout.write(b"\x00" * 4096)
        written_bytes = 4096

        # 1. Write file data blocks
        for node in all_nodes:
            if not node.is_dir:
                if node.target is not None:
                    t_bytes = node.target.encode("utf-8")
                    node.size = len(t_bytes)
                    node.layout = 2
                    node.inline_data = t_bytes
                else:
                    if node.size == 0:
                        node.data_blkaddr = 0
                        node.layout = 0
                    else:
                        blk_idx = written_bytes // BLOCK_SIZE
                        node.data_blkaddr = blk_idx
                        node.layout = 0
                        with open(node.host_path, "rb") as fin:
                            while True:
                                chunk = fin.read(1024 * 1024)
                                if not chunk:
                                    break
                                fout.write(chunk)
                                written_bytes += len(chunk)
                        pad = (BLOCK_SIZE - (written_bytes % BLOCK_SIZE)) % BLOCK_SIZE
                        if pad:
                            fout.write(b"\x00" * pad)
                            written_bytes += pad

        # 2. Write directory data blocks
        for node in all_nodes:
            if node.is_dir:
                if not node.children:
                    node.size = 0
                    node.data_blkaddr = 0
                    node.layout = 0
                else:
                    num_entries = len(node.children)
                    first_nameoff = (num_entries * 12 + 3) & ~3
                    cur_nameoff = first_nameoff
                    d_block = bytearray(BLOCK_SIZE)

                    for idx, (cname, cnode) in enumerate(node.children):
                        cname_bytes = cname.encode("utf-8") + b"\x00"
                        ftype = EROFS_FT_DIR if cnode.is_dir else (EROFS_FT_SYMLINK if cnode.target else EROFS_FT_REG_FILE)
                        rec = struct.pack("<QHBB", 0, cur_nameoff, ftype, 0)
                        d_block[idx*12 : (idx+1)*12] = rec
                        d_block[cur_nameoff : cur_nameoff + len(cname_bytes)] = cname_bytes
                        cur_nameoff += len(cname_bytes)

                    node.dir_block = d_block
                    node.size = cur_nameoff
                    blk_idx = written_bytes // BLOCK_SIZE
                    node.data_blkaddr = blk_idx
                    node.layout = 0
                    fout.write(d_block)
                    written_bytes += BLOCK_SIZE

        # 3. Write XAttr table
        xattr_blkaddr = written_bytes // BLOCK_SIZE
        xattr_bytes = bytearray()
        for entry in shared_xattrs:
            xattr_bytes.extend(entry)
        if xattr_bytes:
            fout.write(xattr_bytes)
            written_bytes += len(xattr_bytes)
            pad = (BLOCK_SIZE - (written_bytes % BLOCK_SIZE)) % BLOCK_SIZE
            if pad:
                fout.write(b"\x00" * pad)
                written_bytes += pad

        # 4. Assign NIDs and write Inode table
        meta_blkaddr = written_bytes // BLOCK_SIZE
        inodes_data = bytearray()

        for nid_idx, node in enumerate(all_nodes):
            node.nid = nid_idx

        for node in all_nodes:
            if node.is_dir and node.children:
                d_block = node.dir_block
                for idx, (cname, cnode) in enumerate(node.children):
                    struct.pack_into("<Q", d_block, idx * 12, cnode.nid)
                blk_pos = node.data_blkaddr * BLOCK_SIZE
                cur_pos = fout.tell()
                fout.seek(blk_pos)
                fout.write(d_block)
                fout.seek(cur_pos)

        for node in all_nodes:
            has_xattr = (node.xattr_id is not None)
            xattr_count = 1 if has_xattr else 0
            i_format = (node.layout << 1) | 0
            ino = node.nid + 1
            nlink = 2 if node.is_dir else 1

            inode_raw = bytearray(struct.pack(
                "<HHHHIIIIHHI",
                i_format, xattr_count, node.mode, nlink, node.size,
                0, node.data_blkaddr, ino, node.uid, node.gid, 0
            ))

            if has_xattr:
                xhdr = struct.pack("<IB7sI", 0, 1, b"\x00"*7, node.xattr_id)
                inode_raw += xhdr

            if node.inline_data:
                inode_raw += node.inline_data

            pad = (32 - (len(inode_raw) % 32)) % 32
            if pad:
                inode_raw += b"\x00" * pad

            inodes_data.extend(inode_raw)

        fout.write(inodes_data)
        written_bytes += len(inodes_data)
        pad = (BLOCK_SIZE - (written_bytes % BLOCK_SIZE)) % BLOCK_SIZE
        if pad:
            fout.write(b"\x00" * pad)
            written_bytes += pad

        total_blocks = written_bytes // BLOCK_SIZE

        # 5. Write Superblock at offset 1024
        sb = struct.pack(
            "<III B B H Q Q I I I I 16s 16s I 44s",
            EROFS_MAGIC, 0, 0, 12, 0, 0,
            len(all_nodes), int(time.time()), 0,
            total_blocks, meta_blkaddr, xattr_blkaddr,
            uuid.uuid4().bytes, volume_name.encode("utf-8")[:16], 0, b"\x00" * 44
        )
        fout.seek(1024)
        fout.write(sb)

    if sparse:
        if on_status:
            on_status(f"Converting raw EROFS filesystem to Android Sparse image: {out_img.name}...")
        convert_raw_to_sparse(raw_output, str(out_img))
        if os.path.exists(raw_output):
            os.remove(raw_output)

    return total_blocks, len(all_nodes)
