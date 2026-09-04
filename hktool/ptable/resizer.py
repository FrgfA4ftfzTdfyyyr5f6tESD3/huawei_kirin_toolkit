"""
Huawei ptable.img Partition Resizer Engine
Universal resizing and CRC32 recalculation across all GPT tables.
"""
from __future__ import annotations

import struct
import zlib
from typing import Any, Dict, List, Optional, Tuple

from .gpt_parser import GPTTable, PartitionEntry, PTableAnalysis


class TableResizeInfo:
    def __init__(
        self,
        table_lba: int,
        table_role: str,
        sector_size: int,
        system_name: str,
        product_name: str,
        old_sys_lba: Tuple[int, int],
        new_sys_lba: Tuple[int, int],
        old_prod_lba: Tuple[int, int],
        new_prod_lba: Tuple[int, int],
        old_sys_mb: float,
        new_sys_mb: float,
        old_prod_mb: float,
        new_prod_mb: float,
        old_hdr_crc: int,
        new_hdr_crc: int,
        old_part_crc: int,
        new_part_crc: int
    ):
        self.table_lba = table_lba
        self.table_role = table_role
        self.sector_size = sector_size
        self.system_name = system_name
        self.product_name = product_name
        self.old_sys_lba = old_sys_lba
        self.new_sys_lba = new_sys_lba
        self.old_prod_lba = old_prod_lba
        self.new_prod_lba = new_prod_lba
        self.old_sys_mb = old_sys_mb
        self.new_sys_mb = new_sys_mb
        self.old_prod_mb = old_prod_mb
        self.new_prod_mb = new_prod_mb
        self.old_hdr_crc = old_hdr_crc
        self.new_hdr_crc = new_hdr_crc
        self.old_part_crc = old_part_crc
        self.new_part_crc = new_part_crc


class ResizeResult:
    def __init__(self, success: bool, message: str, modified_data: bytearray = None, table_reports: List[TableResizeInfo] = None):
        self.success = success
        self.message = message
        self.modified_data = modified_data or bytearray()
        self.table_reports = table_reports or []


class PTableResizer:
    def __init__(self, analysis: PTableAnalysis):
        self.analysis = analysis
        if not self.analysis.is_supported:
            raise ValueError(f"Unsupported file: {self.analysis.unsupported_reason}")

    def resize(self, add_mb: float) -> ResizeResult:
        """
        Transfers `add_mb` from the product partition to the system partition.
        Modifies all matching GPT tables in the ptable.img binary and recalculates CRCs.
        """
        if add_mb <= 0:
            return ResizeResult(False, "Added space must be greater than 0 MB.")

        if add_mb > self.analysis.max_add_mb:
            return ResizeResult(
                False,
                f"Requested size (+{add_mb:.1f} MB) exceeds maximum transferable capacity ({self.analysis.max_add_mb:.1f} MB). "
                f"At least 100 MB must be preserved for the {self.analysis.product_name} partition."
            )

        data = bytearray(self.analysis.raw_data)
        reports: List[TableResizeInfo] = []

        system_candidates = ["system_a", "system", "system_b"]
        product_candidates = ["product_a", "product", "product_b"]

        for table in self.analysis.tables:
            if table.entries_offset is None:
                continue

            sys_part = table.find_partition(system_candidates)
            prod_part = table.find_partition(product_candidates)

            if not sys_part or not prod_part:
                continue

            # Calculate sector shift for this table
            sector_size = table.sector_size
            sectors_per_mb = (1024 * 1024) // sector_size
            add_sectors = int(round(add_mb * sectors_per_mb))

            old_sys_lba = (sys_part.first_lba, sys_part.last_lba)
            old_prod_lba = (prod_part.first_lba, prod_part.last_lba)

            new_sys_first = sys_part.first_lba
            new_sys_last = sys_part.last_lba + add_sectors

            new_prod_first = new_sys_last + 1
            new_prod_last = prod_part.last_lba

            if new_prod_first > new_prod_last:
                return ResizeResult(
                    False,
                    f"Error in Table @ LBA {table.header_lba}: {prod_part.name} partition does not have sufficient space."
                )

            # Sizes in MB
            old_sys_mb = (old_sys_lba[1] - old_sys_lba[0] + 1) * sector_size / (1024 * 1024)
            new_sys_mb = (new_sys_last - new_sys_first + 1) * sector_size / (1024 * 1024)
            old_prod_mb = (old_prod_lba[1] - old_prod_lba[0] + 1) * sector_size / (1024 * 1024)
            new_prod_mb = (new_prod_last - new_prod_first + 1) * sector_size / (1024 * 1024)

            # Update partition entry bytes in data
            struct.pack_into("<QQ", data, sys_part.table_offset + 32, new_sys_first, new_sys_last)
            struct.pack_into("<QQ", data, prod_part.table_offset + 32, new_prod_first, new_prod_last)

            # Recalculate Partition Array CRC32
            num_bytes = table.num_part_entries * table.part_entry_size
            entries_bytes = data[table.entries_offset : table.entries_offset + num_bytes]
            new_part_crc = zlib.crc32(entries_bytes) & 0xffffffff
            struct.pack_into("<I", data, table.header_offset + 88, new_part_crc)

            # Recalculate GPT Header CRC32 (zero out CRC field at offset 16 first)
            struct.pack_into("<I", data, table.header_offset + 16, 0)
            hdr_bytes = data[table.header_offset : table.header_offset + table.header_size]
            new_hdr_crc = zlib.crc32(hdr_bytes) & 0xffffffff
            struct.pack_into("<I", data, table.header_offset + 16, new_hdr_crc)

            reports.append(TableResizeInfo(
                table_lba=table.header_lba,
                table_role=table.table_role,
                sector_size=sector_size,
                system_name=sys_part.name,
                product_name=prod_part.name,
                old_sys_lba=old_sys_lba,
                new_sys_lba=(new_sys_first, new_sys_last),
                old_prod_lba=old_prod_lba,
                new_prod_lba=(new_prod_first, new_prod_last),
                old_sys_mb=old_sys_mb,
                new_sys_mb=new_sys_mb,
                old_prod_mb=old_prod_mb,
                new_prod_mb=new_prod_mb,
                old_hdr_crc=table.header_crc,
                new_hdr_crc=new_hdr_crc,
                old_part_crc=table.part_array_crc,
                new_part_crc=new_part_crc
            ))

        if not reports:
            return ResizeResult(False, "No matching partition tables were updated.")

        return ResizeResult(
            success=True,
            message=f"Successfully resized {len(reports)} GPT partition table(s) and recalculated CRCs.",
            modified_data=data,
            table_reports=reports
        )
