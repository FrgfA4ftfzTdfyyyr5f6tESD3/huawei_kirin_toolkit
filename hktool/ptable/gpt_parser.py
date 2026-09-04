"""
Huawei GPT Partition Table Parser
Universal dynamic parser for Huawei ptable.img files.
Handles 512B, 4096B (4K) sector sizes, Primary GPT, and Secondary/Backup GPT tables.
"""
from __future__ import annotations

import struct
import zlib
from typing import Any, Dict, List, Optional, Tuple

GPT_SIGNATURE = b"EFI PART"
GPT_HEADER_FORMAT = "<8sIIIIQQQQ16sQIII"
GPT_HEADER_SIZE = struct.calcsize(GPT_HEADER_FORMAT)  # 92 bytes
GPT_ENTRY_SIZE = 128


class PartitionEntry:
    def __init__(self, index: int, raw_bytes: bytes, table_offset: int):
        self.index = index
        self.raw_bytes = bytearray(raw_bytes)
        self.table_offset = table_offset

        self.type_guid = bytes(self.raw_bytes[0:16])
        self.unique_guid = bytes(self.raw_bytes[16:32])
        self.first_lba, self.last_lba, self.flags = struct.unpack("<QQQ", self.raw_bytes[32:56])

        raw_name = self.raw_bytes[56:128]
        self.name = raw_name.decode("utf-16le", errors="ignore").rstrip("\x00")
        self.is_used = self.type_guid != b"\x00" * 16

    @property
    def sector_count(self) -> int:
        if not self.is_used or self.last_lba < self.first_lba:
            return 0
        return self.last_lba - self.first_lba + 1

    def get_size_bytes(self, sector_size: int) -> int:
        return self.sector_count * sector_size

    def get_size_mb(self, sector_size: int) -> float:
        return self.get_size_bytes(sector_size) / (1024 * 1024)

    def get_size_gb(self, sector_size: int) -> float:
        return self.get_size_bytes(sector_size) / (1024 * 1024 * 1024)


class GPTTable:
    def __init__(self, header_lba: int, header_offset: int, header_data: bytes, data: bytearray):
        self.header_lba = header_lba
        self.header_offset = header_offset
        self.header_data = bytearray(header_data[:GPT_HEADER_SIZE])

        (
            self.signature,
            self.revision,
            self.header_size,
            self.header_crc,
            self.reserved,
            self.my_lba,
            self.alt_lba,
            self.first_usable_lba,
            self.last_usable_lba,
            self.disk_guid,
            self.part_entry_lba,
            self.num_part_entries,
            self.part_entry_size,
            self.part_array_crc
        ) = struct.unpack(GPT_HEADER_FORMAT, self.header_data)

        self.entries_offset: Optional[int] = None
        self.entries: List[PartitionEntry] = []
        self.sector_size: int = 512  # Dynamic detection
        self.table_role: str = "Primary/Standard"

        self._locate_entries(data)

    def _locate_entries(self, data: bytearray):
        num_bytes = self.num_part_entries * self.part_entry_size

        # Candidate 1: Immediately after header sector
        cand1 = self.header_offset + 512
        if cand1 + num_bytes <= len(data):
            cand_bytes = data[cand1 : cand1 + num_bytes]
            if (zlib.crc32(cand_bytes) & 0xffffffff) == self.part_array_crc:
                self.entries_offset = cand1
                self.table_role = "Primary GPT Table"

        # Candidate 2: Before header (Backup GPT table)
        if self.entries_offset is None and self.header_offset >= num_bytes:
            cand2 = self.header_offset - num_bytes
            cand_bytes = data[cand2 : self.header_offset]
            if (zlib.crc32(cand_bytes) & 0xffffffff) == self.part_array_crc:
                self.entries_offset = cand2
                self.table_role = "Backup GPT Table"

        # Candidate 3: At part_entry_lba * 512
        if self.entries_offset is None:
            cand3 = self.part_entry_lba * 512
            if cand3 + num_bytes <= len(data):
                cand_bytes = data[cand3 : cand3 + num_bytes]
                if (zlib.crc32(cand_bytes) & 0xffffffff) == self.part_array_crc:
                    self.entries_offset = cand3
                    self.table_role = f"GPT Table @ LBA {self.part_entry_lba}"

        # Candidate 4: Heuristic match
        if self.entries_offset is None and cand1 + num_bytes <= len(data):
            cand_bytes = data[cand1 : cand1 + num_bytes]
            if any(cand_bytes[i*128 : (i+1)*128][:16] != b"\x00"*16 for i in range(min(5, self.num_part_entries))):
                self.entries_offset = cand1
                self.table_role = "GPT Table (Heuristic match)"

        if self.entries_offset is not None:
            for i in range(self.num_part_entries):
                e_off = self.entries_offset + i * self.part_entry_size
                entry_raw = data[e_off : e_off + self.part_entry_size]
                self.entries.append(PartitionEntry(i + 1, entry_raw, e_off))

    def get_used_partitions(self) -> List[PartitionEntry]:
        return [e for e in self.entries if e.is_used]

    def find_partition(self, name_candidates: List[str]) -> Optional[PartitionEntry]:
        cand_lower = [c.lower() for c in name_candidates]
        for e in self.entries:
            if e.is_used and e.name.lower() in cand_lower:
                return e
        return None


class PTableAnalysis:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.raw_data = bytearray()
        self.tables: List[GPTTable] = []
        self.is_supported = False
        self.unsupported_reason: Optional[str] = None
        self.has_super = False
        self.system_name: Optional[str] = None
        self.product_name: Optional[str] = None
        self.system_size_mb: float = 0.0
        self.product_size_mb: float = 0.0
        self.max_add_mb: float = 0.0
        self.editable_tables_count: int = 0

        self._load_and_analyze()

    def _load_and_analyze(self):
        with open(self.file_path, "rb") as f:
            self.raw_data = bytearray(f.read())

        total_sectors = len(self.raw_data) // 512

        # Scan binary for all GPT headers
        for lba in range(total_sectors):
            offset = lba * 512
            if self.raw_data[offset : offset + 8] == GPT_SIGNATURE:
                table = GPTTable(lba, offset, self.raw_data[offset : offset + GPT_HEADER_SIZE], self.raw_data)
                if table.entries_offset is not None:
                    self.tables.append(table)

        if not self.tables:
            self.is_supported = False
            self.unsupported_reason = "No valid GPT headers found in this file."
            return

        # Check for dynamic partition 'super'
        for t in self.tables:
            for p in t.get_used_partitions():
                if "super" in p.name.lower():
                    self.has_super = True
                    self.is_supported = False
                    self.unsupported_reason = (
                        "Dynamic Partition ('super') detected. "
                        "This device uses dynamic super partition rather than traditional partitions."
                    )
                    return

        # Dynamically determine sector sizes
        self._detect_sector_sizes()

        # Find system and product
        system_candidates = ["system_a", "system", "system_b"]
        product_candidates = ["product_a", "product", "product_b"]

        primary_table = max(self.tables, key=lambda t: len(t.get_used_partitions()), default=self.tables[0])
        sys_part = primary_table.find_partition(system_candidates)
        prod_part = primary_table.find_partition(product_candidates)

        if not sys_part or not prod_part:
            self.is_supported = False
            self.unsupported_reason = (
                f"Required partitions not found. "
                f"(system: {'Found' if sys_part else 'Missing'}, product: {'Found' if prod_part else 'Missing'})"
            )
            return

        self.system_name = sys_part.name
        self.product_name = prod_part.name
        self.system_size_mb = sys_part.get_size_mb(primary_table.sector_size)
        self.product_size_mb = prod_part.get_size_mb(primary_table.sector_size)

        # Minimum product reserve: 100 MB
        min_product_reserve_mb = 100.0
        self.max_add_mb = max(0.0, self.product_size_mb - min_product_reserve_mb)

        # Count tables that contain both system and product to be resized
        self.editable_tables_count = sum(
            1 for t in self.tables
            if t.find_partition(system_candidates) and t.find_partition(product_candidates)
        )

        self.is_supported = True

    def _detect_sector_sizes(self):
        max_sectors_table = max(
            self.tables,
            key=lambda t: max((p.sector_count for p in t.get_used_partitions()), default=0)
        )
        max_sectors_table.sector_size = 512

        ref_parts = {p.name.lower(): p.sector_count for p in max_sectors_table.get_used_partitions()}

        for t in self.tables:
            if t == max_sectors_table:
                continue

            ratios = []
            for p in t.get_used_partitions():
                ref_count = ref_parts.get(p.name.lower())
                if ref_count and p.sector_count > 0:
                    ratios.append(ref_count / p.sector_count)

            if ratios:
                avg_ratio = sum(ratios) / len(ratios)
                if abs(avg_ratio - 8.0) < 0.5:
                    t.sector_size = 4096  # 4KB UFS table
                elif abs(avg_ratio - 1.0) < 0.5:
                    t.sector_size = 512
                else:
                    t.sector_size = int(512 * avg_ratio)
            else:
                max_sec = max((p.sector_count for p in t.get_used_partitions()), default=0)
                t.sector_size = 512 if max_sec > 1000000 else 4096
