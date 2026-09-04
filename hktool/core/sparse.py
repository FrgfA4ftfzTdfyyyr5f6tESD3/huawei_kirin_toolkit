"""
Android Sparse Image parser, unpacker, splitter, and SuperMerger.
Compliant with Android sparse image v1.0 specifications.
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, Generator, List, Optional, Tuple, Union
from .exceptions import SparseImageError

SPARSE_HEADER_MAGIC = 0xED26FF3A
SPARSE_HEADER_FORMAT = "<I4H4I"
SPARSE_HEADER_SIZE = struct.calcsize(SPARSE_HEADER_FORMAT)

CHUNK_HEADER_FORMAT = "<2H2I"
CHUNK_HEADER_SIZE = struct.calcsize(CHUNK_HEADER_FORMAT)

CHUNK_RAW = 0xCAC1
CHUNK_FILL = 0xCAC2
CHUNK_DONT_CARE = 0xCAC3
CHUNK_CRC32 = 0xCAC4


@dataclass
class SparseHeader:
    magic: int
    major_version: int
    minor_version: int
    file_header_size: int
    chunk_header_size: int
    block_size: int
    total_blocks: int
    total_chunks: int
    image_checksum: int

    @classmethod
    def from_bytes(cls, data: bytes) -> SparseHeader:
        if len(data) < SPARSE_HEADER_SIZE:
            raise SparseImageError("Header data too short")
        values = struct.unpack(SPARSE_HEADER_FORMAT, data[:SPARSE_HEADER_SIZE])
        if values[0] != SPARSE_HEADER_MAGIC:
            raise SparseImageError(f"Invalid sparse magic: {hex(values[0])}")
        return cls(*values)

    def to_bytes(self) -> bytes:
        return struct.pack(
            SPARSE_HEADER_FORMAT,
            self.magic,
            self.major_version,
            self.minor_version,
            self.file_header_size,
            self.chunk_header_size,
            self.block_size,
            self.total_blocks,
            self.total_chunks,
            self.image_checksum
        )


@dataclass
class ChunkHeader:
    chunk_type: int
    reserved: int
    chunk_blocks: int
    total_size: int

    @classmethod
    def from_bytes(cls, data: bytes) -> ChunkHeader:
        if len(data) < CHUNK_HEADER_SIZE:
            raise SparseImageError("Chunk header data too short")
        return cls(*struct.unpack(CHUNK_HEADER_FORMAT, data[:CHUNK_HEADER_SIZE]))

    def to_bytes(self) -> bytes:
        return struct.pack(
            CHUNK_HEADER_FORMAT,
            self.chunk_type,
            self.reserved,
            self.chunk_blocks,
            self.total_size
        )


def is_sparse_image(path_or_data: Union[str, Path, bytes, BinaryIO]) -> bool:
    try:
        if isinstance(path_or_data, (str, Path)):
            with open(path_or_data, "rb") as f:
                header_bytes = f.read(SPARSE_HEADER_SIZE)
        elif isinstance(path_or_data, (bytes, bytearray)):
            header_bytes = path_or_data[:SPARSE_HEADER_SIZE]
        else:
            pos = path_or_data.tell()
            header_bytes = path_or_data.read(SPARSE_HEADER_SIZE)
            path_or_data.seek(pos)
        
        if len(header_bytes) < SPARSE_HEADER_SIZE:
            return False
        magic = struct.unpack_from("<I", header_bytes)[0]
        return magic == SPARSE_HEADER_MAGIC
    except Exception:
        return False


class SparseSplitter:
    @staticmethod
    def split(
        src_path: Path,
        out_dir: Path,
        max_chunk_size_bytes: int = 256 * 1024 * 1024,
        progress_cb: Optional[Callable[[int, int], None]] = None
    ) -> List[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = src_path.stem
        chunk_files: List[Path] = []

        with open(src_path, "rb") as src:
            orig_header = SparseHeader.from_bytes(src.read(SPARSE_HEADER_SIZE))
            block_size = orig_header.block_size
            max_blocks_per_file = max_chunk_size_bytes // block_size

            part_idx = 1
            current_out_path = out_dir / f"{stem}.sparse.{part_idx:02d}.img"
            current_out = open(current_out_path, "wb")
            chunk_files.append(current_out_path)

            current_out.write(b"\x00" * SPARSE_HEADER_SIZE)
            curr_blocks = 0
            curr_chunks = 0

            for _ in range(orig_header.total_chunks):
                chunk_header_bytes = src.read(CHUNK_HEADER_SIZE)
                if not chunk_header_bytes:
                    break
                chunk_hdr = ChunkHeader.from_bytes(chunk_header_bytes)
                data_size = chunk_hdr.total_size - CHUNK_HEADER_SIZE

                if curr_blocks + chunk_hdr.chunk_blocks > max_blocks_per_file and curr_chunks > 0:
                    hdr = SparseHeader(
                        magic=SPARSE_HEADER_MAGIC,
                        major_version=1,
                        minor_version=0,
                        file_header_size=SPARSE_HEADER_SIZE,
                        chunk_header_size=CHUNK_HEADER_SIZE,
                        block_size=block_size,
                        total_blocks=curr_blocks,
                        total_chunks=curr_chunks,
                        image_checksum=0
                    )
                    current_out.seek(0)
                    current_out.write(hdr.to_bytes())
                    current_out.close()

                    part_idx += 1
                    current_out_path = out_dir / f"{stem}.sparse.{part_idx:02d}.img"
                    current_out = open(current_out_path, "wb")
                    chunk_files.append(current_out_path)
                    current_out.write(b"\x00" * SPARSE_HEADER_SIZE)
                    curr_blocks = 0
                    curr_chunks = 0

                current_out.write(chunk_header_bytes)
                if data_size > 0:
                    copied = 0
                    buf_sz = 1024 * 1024
                    while copied < data_size:
                        to_read = min(buf_sz, data_size - copied)
                        buf = src.read(to_read)
                        if not buf:
                            break
                        current_out.write(buf)
                        copied += len(buf)

                curr_blocks += chunk_hdr.chunk_blocks
                curr_chunks += 1

            if curr_chunks > 0:
                hdr = SparseHeader(
                    magic=SPARSE_HEADER_MAGIC,
                    major_version=1,
                    minor_version=0,
                    file_header_size=SPARSE_HEADER_SIZE,
                    chunk_header_size=CHUNK_HEADER_SIZE,
                    block_size=block_size,
                    total_blocks=curr_blocks,
                    total_chunks=curr_chunks,
                    image_checksum=0
                )
                current_out.seek(0)
                current_out.write(hdr.to_bytes())
            current_out.close()

        return chunk_files


class SuperMerger:
    @staticmethod
    def merge(
        part1_path: Path,
        part2_path: Path,
        output_path: Path,
        progress_cb: Optional[Callable[[float], None]] = None
    ) -> None:
        len1 = part1_path.stat().st_size
        len2 = part2_path.stat().st_size

        large_path, small_path = (part1_path, part2_path) if len1 >= len2 else (part2_path, part1_path)
        
        with open(large_path, "rb") as f_large, open(small_path, "rb") as f_small:
            h_large = SparseHeader.from_bytes(f_large.read(SPARSE_HEADER_SIZE))
            h_small = SparseHeader.from_bytes(f_small.read(SPARSE_HEADER_SIZE))

            if h_large.block_size != h_small.block_size:
                raise SparseImageError(f"Block size mismatch: {h_large.block_size} vs {h_small.block_size}")

            last_chunk_offset = SPARSE_HEADER_SIZE
            for _ in range(h_large.total_chunks):
                last_chunk_offset = f_large.tell()
                chunk_hdr = ChunkHeader.from_bytes(f_large.read(CHUNK_HEADER_SIZE))
                f_large.seek(chunk_hdr.total_size - CHUNK_HEADER_SIZE, os.SEEK_CUR)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        buf_size = 4 * 1024 * 1024
        total_size = len1 + len2
        written_total = 0

        with open(output_path, "wb") as dst:
            dst.write(b"\x00" * SPARSE_HEADER_SIZE)

            with open(large_path, "rb") as src_large:
                src_large.seek(SPARSE_HEADER_SIZE)
                remaining = last_chunk_offset - SPARSE_HEADER_SIZE
                while remaining > 0:
                    to_read = min(buf_size, remaining)
                    buf = src_large.read(to_read)
                    if not buf:
                        break
                    dst.write(buf)
                    remaining -= len(buf)
                    written_total += len(buf)
                    if progress_cb:
                        progress_cb(min(1.0, written_total / total_size))

            with open(small_path, "rb") as src_small:
                src_small.seek(SPARSE_HEADER_SIZE)
                while buf := src_small.read(buf_size):
                    dst.write(buf)
                    written_total += len(buf)
                    if progress_cb:
                        progress_cb(min(1.0, written_total / total_size))

            combined_hdr = SparseHeader(
                magic=SPARSE_HEADER_MAGIC,
                major_version=1,
                minor_version=0,
                file_header_size=SPARSE_HEADER_SIZE,
                chunk_header_size=CHUNK_HEADER_SIZE,
                block_size=h_large.block_size,
                total_blocks=h_large.total_blocks + h_small.total_blocks,
                total_chunks=h_large.total_chunks + h_small.total_chunks,
                image_checksum=0
            )
            dst.seek(0)
            dst.write(combined_hdr.to_bytes())

        if progress_cb:
            progress_cb(1.0)
