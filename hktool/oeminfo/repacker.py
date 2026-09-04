"""
Repacks unpacked OEMINFO directories (manifest.json + block files) back into binary images.
"""
from __future__ import annotations

import json
import os
import struct
from pathlib import Path
from typing import Optional
from ..core.exceptions import OemInfoError

REGION_SIZE = 0x2000000       # 32 MiB
TOTAL_REGION_SIZE = REGION_SIZE * 2
BLOCK_HEADER_STRUCT = struct.Struct("<8sIIIIII")
OEM_MAGIC_1 = bytes([0x55, 0xAA, 0x5A, 0xA5, 0x00, 0x00, 0x00, 0x00])


class OemInfoRepacker:
    @staticmethod
    def repack(unpacked_dir: Path, output_image: Path, pad_byte: int = 0x00) -> Path:
        manifest_p = unpacked_dir / "manifest.json"
        if not manifest_p.exists():
            raise OemInfoError(f"manifest.json not found in {unpacked_dir}")

        manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
        blocks_dir = unpacked_dir / "blocks"

        region_buffer = bytearray(bytes([pad_byte]) * REGION_SIZE)
        offset = 0

        for blk_info in manifest.get("blocks", []):
            blk_id = int(blk_info["block_id"], 16) if isinstance(blk_info["block_id"], str) else blk_info["block_id"]
            sub_id = blk_info.get("sub_id", 0)
            age = blk_info.get("age", 1)
            pad = blk_info.get("padding", 0)
            filename = blk_info["filename"]
            file_p = blocks_dir / filename

            if not file_p.exists():
                raise OemInfoError(f"Missing block file: {filename}")

            data = file_p.read_bytes()
            length = len(data)

            magic = OEM_MAGIC_1
            ver = 1
            hdr = BLOCK_HEADER_STRUCT.pack(magic, ver, blk_id, sub_id, length, age, pad)

            if offset + len(hdr) + length > REGION_SIZE:
                raise OemInfoError("OEMINFO data exceeds 32MB region limit!")

            region_buffer[offset:offset + len(hdr)] = hdr
            offset += len(hdr)
            region_buffer[offset:offset + length] = data
            offset += length

            if offset % 4 != 0:
                align_pad = 4 - (offset % 4)
                offset += align_pad

        output_image.parent.mkdir(parents=True, exist_ok=True)
        with open(output_image, "wb") as dst:
            dst.write(region_buffer)
            dst.write(region_buffer)

        return output_image
