"""
Core HisiNveImage engine to parse, validate, edit, synchronize, and save nvme.img partitions.
"""
import os
import shutil
import hashlib
import datetime
from typing import Optional, List, Dict, Tuple

from .structures import (
    NVE_BLOCK_SIZE,
    PARTITION_HEADER_SIZE,
    NV_ITEM_SIZE,
    NV_ITEMS_PER_BLOCK,
    NV_DATA_MAX_SIZE,
    NVEPartitionHeader,
    NVItem
)
from .soc_profiles import detect_soc_from_entries, SocProfile, SOC_PROFILES
from .crc import compute_nv_item_crc

class NVEBlock:
    """Represents one 128 KB partition block (containing up to 1023 items + 1 header)."""
    def __init__(self, block_index: int, offset: int, items: List[NVItem], header: Optional[NVEPartitionHeader]):
        self.block_index = block_index
        self.offset = offset
        self.items = items
        self.header = header
        
        # Build mapping: key -> list of items (supports duplicate names like CAMDCTE)
        self.items_by_name: Dict[str, List[NVItem]] = {}
        self.items_by_number: Dict[int, NVItem] = {}
        for it in items:
            if it.is_valid:
                if it.nv_name not in self.items_by_name:
                    self.items_by_name[it.nv_name] = []
                self.items_by_name[it.nv_name].append(it)
                self.items_by_number[it.nv_number] = it

    @property
    def valid_items_count(self) -> int:
        return sum(len(v) for v in self.items_by_name.values())

    def get_item(self, name_or_number, occurrence: int = 0) -> Optional[NVItem]:
        """Returns item matching name or NV number. Includes kernel ID fallbacks."""
        if isinstance(name_or_number, int):
            return self.items_by_number.get(name_or_number)

        name = str(name_or_number).strip()
        if name.isdigit():
            num = int(name)
            if num in self.items_by_number:
                return self.items_by_number[num]

        items = self.items_by_name.get(name, [])
        if 0 <= occurrence < len(items):
            return items[occurrence]

        # Kernel ID Fallbacks
        alias_map = {
            "SN": 2,
            "WIFI_MAC": 193,
            "MACWLAN": 193,
            "BT_MAC": 194,
            "MACBT": 194,
            "BSN": 364,
            "CSTMSN": 364,
            "BOARDID": 1,
            "USRKEY": 315,
            "FBLOCK": 312,
            "FRPKEY": 338,
            "BATCALI": 317,
        }
        fallback_num = alias_map.get(name.upper())
        if fallback_num and fallback_num in self.items_by_number:
            return self.items_by_number[fallback_num]

        return None

    def get_all_items_with_name(self, name: str) -> List[NVItem]:
        return self.items_by_name.get(name.strip(), [])


class HisiNveImage:
    """
    Complete offline manager for Huawei Kirin NVME partition images.
    Supports reading, writing, batch editing, multi-block synchronization,
    CRC32C verification/recalculation, and automatic backups.
    """
    def __init__(self, filepath: str):
        self.filepath = os.path.abspath(filepath)
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Image file not found: {self.filepath}")
        
        self.raw_data = bytearray()
        self.blocks: List[NVEBlock] = []
        self.active_blocks: List[NVEBlock] = []
        self.detected_soc: Optional[SocProfile] = None
        self._load()

    def _load(self):
        with open(self.filepath, "rb") as f:
            self.raw_data = bytearray(f.read())
        
        file_size = len(self.raw_data)
        if file_size < NVE_BLOCK_SIZE:
            raise ValueError(f"Image too small ({file_size} bytes). Minimum is {NVE_BLOCK_SIZE} bytes.")
        
        num_blocks = file_size // NVE_BLOCK_SIZE
        self.blocks = []
        self.active_blocks = []

        for b_idx in range(num_blocks):
            blk_offset = b_idx * NVE_BLOCK_SIZE
            blk_data = self.raw_data[blk_offset:blk_offset + NVE_BLOCK_SIZE]
            
            # Parse header at offset 0x1FF80
            hdr_raw = blk_data[NVE_BLOCK_SIZE - PARTITION_HEADER_SIZE : NVE_BLOCK_SIZE]
            header = None
            if hdr_raw[:17] == b"Hisi-NV-Partition":
                try:
                    header = NVEPartitionHeader.unpack(hdr_raw, offset=blk_offset + NVE_BLOCK_SIZE - PARTITION_HEADER_SIZE)
                except Exception:
                    pass

            # Parse 1023 item slots
            items = []
            for i in range(NV_ITEMS_PER_BLOCK):
                item_offset = i * NV_ITEM_SIZE
                item_bytes = blk_data[item_offset:item_offset + NV_ITEM_SIZE]
                item = NVItem.unpack(item_bytes, index=i)
                items.append(item)

            block = NVEBlock(block_index=b_idx, offset=blk_offset, items=items, header=header)
            self.blocks.append(block)
            if block.header is not None or block.valid_items_count > 0:
                self.active_blocks.append(block)

        # Detect SoC profile using the first active block
        if self.active_blocks:
            ref_blk = self.active_blocks[0]
            text_dict = {it.nv_name: it.value_text for it in ref_blk.items if it.is_valid}
            self.detected_soc = detect_soc_from_entries(text_dict, ref_blk.valid_items_count)

    @property
    def is_hashed_soc(self) -> bool:
        """Determines if the SoC uses hashed USRKEY."""
        # Check WVLOCK in active blocks
        for blk in self.active_blocks:
            wvlock = blk.get_item("WVLOCK")
            if wvlock and b"UUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUU" in wvlock.nv_data:
                return True
        if self.detected_soc:
            return self.detected_soc.nve_hashed_key
        return True

    def get_entry(self, key: str, block_index: Optional[int] = None) -> Optional[NVItem]:
        """
        Reads an NV entry by name. If block_index is None, returns from the first active block.
        """
        key = key.strip().upper()
        if block_index is not None:
            if 0 <= block_index < len(self.blocks):
                return self.blocks[block_index].get_item(key)
            return None
        
        for blk in self.active_blocks:
            item = blk.get_item(key)
            if item:
                return item
        return None

    def read_all_blocks_for_key(self, key: str) -> List[Tuple[int, Optional[NVItem]]]:
        """Returns values of a key across all blocks."""
        key = key.strip().upper()
        results = []
        for blk in self.active_blocks:
            results.append((blk.block_index, blk.get_item(key)))
        return results

    def create_backup(self, custom_path: Optional[str] = None) -> str:
        """
        Creates a safe backup of the original image before modification.
        """
        if custom_path:
            bak_path = custom_path
        else:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            bak_path = f"{self.filepath}.bak_{ts}"
        shutil.copy2(self.filepath, bak_path)
        return bak_path

    def write_entry(
        self,
        key: str,
        value: bytes | str,
        valid_size: Optional[int] = None,
        sync_all_blocks: bool = True,
        auto_backup: bool = True
    ) -> bool:
        """
        Writes a value to an NV item, recomputes CRC32C, and synchronizes across all active blocks.
        """
        key = key.strip().upper()
        if not key:
            raise ValueError("Key cannot be empty")

        if isinstance(value, str):
            val_bytes = value.encode("utf-8")
        else:
            val_bytes = bytes(value)

        if len(val_bytes) > NV_DATA_MAX_SIZE:
            raise ValueError(f"Value too long ({len(val_bytes)} bytes). Max allowed is {NV_DATA_MAX_SIZE} bytes.")

        if valid_size is None:
            valid_size = len(val_bytes)

        if auto_backup:
            self.create_backup()

        updated_count = 0
        target_blocks = self.active_blocks if sync_all_blocks else self.active_blocks[:1]

        for blk in target_blocks:
            items_to_update = blk.get_all_items_with_name(key)
            for item in items_to_update:
                item.valid_size = valid_size
                item.nv_data = val_bytes.ljust(NV_DATA_MAX_SIZE, b"\x00")
                # Pack with recomputed CRC
                item_raw = item.pack(update_crc=True)
                
                # Write back to raw image buffer
                offset = blk.offset + item.index * NV_ITEM_SIZE
                self.raw_data[offset:offset + NV_ITEM_SIZE] = item_raw
                updated_count += 1

        return updated_count > 0

    def set_bootloader_unlock_key(self, code_or_hash: str, auto_hash: bool = True, auto_backup: bool = True) -> dict:
        """
        Specialized helper to set USRKEY bootloader unlock key.
        Supports automatic SHA256 hashing if required by the SoC.
        """
        code_or_hash = code_or_hash.strip()
        is_hashed_mode = self.is_hashed_soc

        if auto_hash and is_hashed_mode and len(code_or_hash) == 16:
            # 16-char unlock key on modern Kirin -> SHA-256 binary digest (32 bytes)
            raw_hash = hashlib.sha256(code_or_hash.encode("ascii")).digest()
            val_bytes = raw_hash
            val_size = 32
            mode_desc = "SHA-256 Hashed (32-byte binary)"
        elif len(code_or_hash) == 64 and all(c in "0123456789abcdefABCDEF" for c in code_or_hash):
            # User passed 64-character hex string -> convert to 32 bytes
            val_bytes = bytes.fromhex(code_or_hash)
            val_size = 32
            mode_desc = "Direct SHA-256 Hex Digested"
        else:
            # Plain string
            val_bytes = code_or_hash.encode("ascii")
            val_size = len(val_bytes)
            mode_desc = f"Plain Text ({val_size} bytes)"

        success = self.write_entry("USRKEY", val_bytes, valid_size=val_size, sync_all_blocks=True, auto_backup=auto_backup)
        return {
            "success": success,
            "key": "USRKEY",
            "mode": mode_desc,
            "size": val_size,
            "raw_hex": val_bytes.hex(),
            "code": code_or_hash
        }

    def set_frp_fblock(self, unlock: bool = True, auto_backup: bool = True) -> bool:
        """
        Specialized helper to unlock FRP / Factory block (FBLOCK).
        0 = Unlocked, 1 = Locked.
        """
        val = b"\x00" if unlock else b"\x01"
        return self.write_entry("FBLOCK", val, valid_size=1, sync_all_blocks=True, auto_backup=auto_backup)

    def verify_integrity(self) -> dict:
        """
        Scans all blocks and checks the validity of CRC32C for every single item.
        """
        results = {
            "total_blocks": len(self.blocks),
            "active_blocks": len(self.active_blocks),
            "total_items_checked": 0,
            "valid_crc_count": 0,
            "invalid_crc_count": 0,
            "errors": [],
            "block_summaries": []
        }

        for blk in self.active_blocks:
            blk_errors = []
            blk_checked = 0
            blk_valid = 0
            for item in blk.items:
                if not item.is_valid:
                    continue
                blk_checked += 1
                if item.verify_crc():
                    blk_valid += 1
                else:
                    expected_crc = compute_nv_item_crc(item.pack(update_crc=False))
                    blk_errors.append({
                        "block": blk.block_index,
                        "slot": item.index,
                        "name": item.nv_name,
                        "current_crc": f"0x{item.crc:08x}",
                        "expected_crc": f"0x{expected_crc:08x}"
                    })

            results["total_items_checked"] += blk_checked
            results["valid_crc_count"] += blk_valid
            results["invalid_crc_count"] += len(blk_errors)
            results["errors"].extend(blk_errors)
            results["block_summaries"].append({
                "block": blk.block_index,
                "header_name": blk.header.partition_name if blk.header else "None",
                "age": blk.header.nve_age if blk.header else 0,
                "valid_items": blk.valid_items_count,
                "crc_errors": len(blk_errors)
            })

        return results

    def fix_all_crcs(self, auto_backup: bool = True) -> int:
        """
        Iterates over all items in all blocks and repairs any broken CRC32C checksums.
        """
        if auto_backup:
            self.create_backup()

        fixed_count = 0
        for blk in self.active_blocks:
            for item in blk.items:
                if not item.is_valid:
                    continue
                if not item.verify_crc():
                    item_raw = item.pack(update_crc=True)
                    offset = blk.offset + item.index * NV_ITEM_SIZE
                    self.raw_data[offset:offset + NV_ITEM_SIZE] = item_raw
                    fixed_count += 1
        return fixed_count

    def save(self, output_path: Optional[str] = None):
        """
        Writes the current in-memory buffer back to disk.
        """
        target = os.path.abspath(output_path) if output_path else self.filepath
        with open(target, "wb") as f:
            f.write(self.raw_data)
        # Reload to update cached state
        if target == self.filepath:
            self._load()

    def write_item(self, key: str, value, auto_backup: bool = False) -> bool:
        """Convenience method to write string or bytes item value."""
        if isinstance(value, str):
            val_bytes = value.encode("utf-8")
        else:
            val_bytes = bytes(value)
        return self.write_entry(key, val_bytes, auto_backup=auto_backup)

    def unlock_bootloader(self, code: str, auto_hash: bool = True, auto_backup: bool = False) -> dict:
        """Configures 16-character bootloader unlock key with auto-hashing."""
        return self.set_bootloader_unlock_key(code, auto_hash=auto_hash, auto_backup=auto_backup)

    def unlock_frp(self, auto_backup: bool = False) -> bool:
        """Sets FBLOCK to 0 (Unlocked)."""
        return self.set_frp_fblock(unlock=True, auto_backup=auto_backup)

    def lock_frp(self, auto_backup: bool = False) -> bool:
        """Sets FBLOCK to 1 (Locked)."""
        return self.set_frp_fblock(unlock=False, auto_backup=auto_backup)

    def export_dump_json(self, output_path: str):
        """Exports full NV partition dump as JSON."""
        import json
        summary = self.export_summary()
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

    def export_dump_csv(self, output_path: str):
        """Exports full NV partition dump as CSV."""
        import csv
        summary = self.export_summary()
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Slot", "Name", "Property", "ValidSize", "CRC32C", "CRCValid", "HexData", "TextValue"])
            for item in summary.get("items_list", []):
                writer.writerow([item["index"], item["name"], item["property"], item["valid_size"], item["crc"], item["crc_valid"], item["hex"], item["text"]])

    def export_summary(self) -> dict:
        """
        Exports a full JSON-serializable dictionary summary of all entries.
        """
        ref_blk = self.active_blocks[0] if self.active_blocks else None
        items_list = []
        items_dict = {}
        if ref_blk:
            for item in ref_blk.items:
                if not item.is_valid:
                    continue
                item_info = {
                    "index": item.index,
                    "nv_number": item.nv_number,
                    "name": item.nv_name,
                    "property": item.nv_property,
                    "valid_size": item.valid_size,
                    "crc": f"0x{item.crc:08x}",
                    "crc_valid": item.verify_crc(),
                    "hex": item.value_bytes.hex(),
                    "text": item.value_text
                }
                items_list.append(item_info)
                key_name = item.nv_name if item.nv_name not in items_dict else f"{item.nv_name}_{item.index}"
                items_dict[key_name] = item_info

        return {
            "image_path": self.filepath,
            "image_size": len(self.raw_data),
            "detected_soc": self.detected_soc.display_name if self.detected_soc else "Unknown",
            "active_blocks_count": len(self.active_blocks),
            "total_entries": len(items_list),
            "items": items_dict,
            "items_list": items_list
        }
