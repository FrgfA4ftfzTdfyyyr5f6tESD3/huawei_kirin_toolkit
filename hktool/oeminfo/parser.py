"""
Parses and unpacks Huawei/Honor OEMINFO image files (32MB / 64MB A/B regions).
"""
from __future__ import annotations

import json
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.exceptions import OemInfoError

REGION_SIZE = 0x2000000       # 32 MiB
TOTAL_REGION_SIZE = REGION_SIZE * 2
BLOCK_HEADER_STRUCT = struct.Struct("<8sIIIIII")
OEM_MAGIC_1 = bytes([0x55, 0xAA, 0x5A, 0xA5])


@dataclass
class OemBlock:
    magic: bytes
    version: int
    block_id: int
    sub_id: int
    length: int
    age: int
    padding: int
    offset: int
    data: bytes = b""


class OemInfoParser:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.file_size = file_path.stat().st_size
        self.raw_data = file_path.read_bytes()
        self.blocks: List[OemBlock] = []
        self.manifest: Dict[str, Any] = {}
        self._parse()

    def _parse(self) -> None:
        if len(self.raw_data) < REGION_SIZE:
            raise OemInfoError(f"OEMINFO file size too small ({len(self.raw_data)} bytes, min {REGION_SIZE})")

        region_a_data = self.raw_data[:REGION_SIZE]
        region_b_data = self.raw_data[REGION_SIZE:TOTAL_REGION_SIZE] if len(self.raw_data) >= TOTAL_REGION_SIZE else b""

        blocks_a = self._scan_region(region_a_data, 0)
        blocks_b = self._scan_region(region_b_data, REGION_SIZE) if region_b_data else []

        if len(blocks_b) > len(blocks_a):
            self.blocks = blocks_b
            self.active_region = "B"
        else:
            self.blocks = blocks_a
            self.active_region = "A"

        self.manifest = {
            "source_file": self.file_path.name,
            "total_size": len(self.raw_data),
            "active_region": self.active_region,
            "blocks_count": len(self.blocks),
            "blocks": []
        }

    def _scan_region(self, region_data: bytes, base_offset: int) -> List[OemBlock]:
        blocks: List[OemBlock] = []
        offset = 0
        while offset + BLOCK_HEADER_STRUCT.size <= len(region_data):
            hdr_bytes = region_data[offset:offset + BLOCK_HEADER_STRUCT.size]
            magic, ver, blk_id, sub_id, length, age, pad = BLOCK_HEADER_STRUCT.unpack(hdr_bytes)

            if magic.startswith(OEM_MAGIC_1) or magic.startswith(b"HW") or blk_id > 0:
                if 0 < length <= 4 * 1024 * 1024 and offset + BLOCK_HEADER_STRUCT.size + length <= len(region_data):
                    data_offset = offset + BLOCK_HEADER_STRUCT.size
                    data = region_data[data_offset:data_offset + length]
                    block = OemBlock(
                        magic=magic,
                        version=ver,
                        block_id=blk_id,
                        sub_id=sub_id,
                        length=length,
                        age=age,
                        padding=pad,
                        offset=base_offset + offset,
                        data=data
                    )
                    blocks.append(block)
                    offset = data_offset + length
                    if offset % 4 != 0:
                        offset += 4 - (offset % 4)
                    continue

            offset += 4
        return blocks

    def unpack(self, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        blocks_dir = out_dir / "blocks"
        blocks_dir.mkdir(exist_ok=True)

        manifest_blocks = []
        for idx, blk in enumerate(self.blocks):
            filename = f"block_{blk.block_id:08X}_{blk.sub_id:04X}.bin"
            file_p = blocks_dir / filename
            file_p.write_bytes(blk.data)

            text_val = ""
            try:
                decoded = blk.data.decode("ascii").strip("\x00 \t\r\n")
                if len(decoded) >= 2 and all(32 <= ord(c) <= 126 for c in decoded):
                    text_val = decoded
            except Exception:
                pass

            manifest_blocks.append({
                "index": idx,
                "block_id": f"0x{blk.block_id:08X}",
                "sub_id": blk.sub_id,
                "length": blk.length,
                "age": blk.age,
                "padding": blk.padding,
                "filename": filename,
                "text_content": text_val if text_val else None
            })

        self.manifest["blocks"] = manifest_blocks
        manifest_path = out_dir / "manifest.json"
        manifest_path.write_text(json.dumps(self.manifest, indent=2), encoding="utf-8")
        return manifest_path
