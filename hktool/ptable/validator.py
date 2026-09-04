"""
Huawei ptable.img Partition Table Validator
Ensures partition bounds, ordering, and CRC integrity across all tables.
"""
from __future__ import annotations

import struct
import zlib
from typing import Any, Dict, List, Tuple

from .gpt_parser import GPT_ENTRY_SIZE, GPT_HEADER_FORMAT, GPT_HEADER_SIZE, GPT_SIGNATURE


class ValidationIssue:
    def __init__(self, table_lba: int, level: str, message: str):
        self.table_lba = table_lba
        self.level = level  # "ERROR" or "WARNING"
        self.message = message

    def __str__(self):
        return f"[{self.level}] [Table @ LBA {self.table_lba}] {self.message}"


class PTableValidator:
    @staticmethod
    def validate_binary(data: bytearray) -> Tuple[bool, List[ValidationIssue]]:
        issues: List[ValidationIssue] = []
        total_sectors = len(data) // 512

        tables_found = 0
        for lba in range(total_sectors):
            offset = lba * 512
            if data[offset : offset + 8] != GPT_SIGNATURE:
                continue

            tables_found += 1
            hdr_raw = data[offset : offset + GPT_HEADER_SIZE]
            (
                sig, rev, hdr_size, hdr_crc, rsvd,
                my_lba, alt_lba, first_lba, last_lba,
                disk_guid, part_lba, num_parts, part_size, part_crc
            ) = struct.unpack(GPT_HEADER_FORMAT, hdr_raw)

            # Check Header CRC
            zeroed_hdr = bytearray(hdr_raw)
            struct.pack_into("<I", zeroed_hdr, 16, 0)
            calc_hdr_crc = zlib.crc32(zeroed_hdr) & 0xffffffff
            if calc_hdr_crc != hdr_crc:
                issues.append(ValidationIssue(
                    lba, "ERROR",
                    f"GPT Header CRC32 mismatch: calculated 0x{calc_hdr_crc:08X} vs stored 0x{hdr_crc:08X}"
                ))

            # Check Partition Entries
            cand1 = offset + 512
            cand2 = offset - (num_parts * part_size) if offset >= (num_parts * part_size) else None

            entries_offset = None
            if cand1 + num_parts * part_size <= len(data):
                cand_bytes = data[cand1 : cand1 + num_parts * part_size]
                if (zlib.crc32(cand_bytes) & 0xffffffff) == part_crc:
                    entries_offset = cand1
            if entries_offset is None and cand2 is not None:
                cand_bytes = data[cand2 : offset]
                if (zlib.crc32(cand_bytes) & 0xffffffff) == part_crc:
                    entries_offset = cand2

            if entries_offset is None:
                issues.append(ValidationIssue(
                    lba, "ERROR",
                    "Partition array CRC32 mismatch or entries could not be resolved"
                ))
                continue

            # Validate individual partition bounds and overlaps
            parsed_parts = []
            for i in range(num_parts):
                e_off = entries_offset + i * part_size
                entry_raw = data[e_off : e_off + part_size]
                type_guid = entry_raw[:16]
                if type_guid == b"\x00" * 16:
                    continue

                flba, llba, flags = struct.unpack("<QQQ", entry_raw[32:56])
                name = entry_raw[56:128].decode("utf-16le", errors="ignore").rstrip("\x00")

                if flba > llba:
                    issues.append(ValidationIssue(
                        lba, "ERROR",
                        f"Partition '{name}' has start LBA greater than end LBA ({flba} > {llba})"
                    ))

                parsed_parts.append((name, flba, llba))

            # Sort by start LBA and check for overlapping
            parsed_parts.sort(key=lambda p: p[1])
            for i in range(len(parsed_parts) - 1):
                cur_name, cur_start, cur_end = parsed_parts[i]
                next_name, next_start, next_end = parsed_parts[i + 1]

                if cur_end >= next_start:
                    issues.append(ValidationIssue(
                        lba, "ERROR",
                        f"Partition overlap detected between '{cur_name}' (ends at LBA {cur_end}) and '{next_name}' (starts at LBA {next_start})"
                    ))

        if tables_found == 0:
            issues.append(ValidationIssue(0, "ERROR", "No valid GPT tables found in binary data."))

        has_errors = any(issue.level == "ERROR" for issue in issues)
        return (not has_errors), issues
