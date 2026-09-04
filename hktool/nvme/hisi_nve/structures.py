"""
Binary data structures and models for HiSilicon NVE partitions.
"""
from dataclasses import dataclass, field
import struct
from typing import Optional
from .crc import compute_nv_item_crc

NVE_BLOCK_SIZE = 131072       # 128 KB (0x20000)
PARTITION_HEADER_SIZE = 128   # 128 bytes at the end of each block (0x1FF80)
NV_ITEM_SIZE = 128            # 128 bytes per item slot
NV_ITEMS_PER_BLOCK = 1023     # 1023 items * 128 = 130944 (0x1FF80)
NV_DATA_MAX_SIZE = 104        # Max data length per item
NV_NAME_MAX_LEN = 8           # Max name length

HEADER_MAGIC = b"Hisi-NV-Partition"

@dataclass
class NVEPartitionHeader:
    """Represents the 128-byte header located at the end of each reliable NVE block."""
    raw_offset: int
    partition_name: str       # 32 bytes (typically "Hisi-NV-Partition")
    nve_version: int          # uint32 (typically 1)
    nve_block_id: int         # uint32
    nve_block_count: int      # uint32
    valid_items: int          # uint32
    nv_checksum: int          # uint32
    nve_crc_support: int      # uint32 (2 = CRC32C enabled)
    reserved: bytes           # 68 bytes
    nve_age: int              # uint32 (incrementing counter)

    @classmethod
    def unpack(cls, data: bytes, offset: int = 0) -> "NVEPartitionHeader":
        if len(data) < PARTITION_HEADER_SIZE:
            raise ValueError(f"Header data must be at least {PARTITION_HEADER_SIZE} bytes")
        name_raw = data[:32]
        p_name = name_raw.split(b"\x00")[0].decode("ascii", errors="replace")
        nve_ver, blk_id, blk_cnt, valid_items, checksum, crc_sup = struct.unpack("<IIIIII", data[32:56])
        reserved = data[56:124]
        age = struct.unpack("<I", data[124:128])[0]
        return cls(
            raw_offset=offset,
            partition_name=p_name,
            nve_version=nve_ver,
            nve_block_id=blk_id,
            nve_block_count=blk_cnt,
            valid_items=valid_items,
            nv_checksum=checksum,
            nve_crc_support=crc_sup,
            reserved=reserved,
            nve_age=age,
        )

    def pack(self) -> bytes:
        name_bytes = self.partition_name.encode("ascii", errors="replace")[:32].ljust(32, b"\x00")
        hdr_core = struct.pack(
            "<IIIIII",
            self.nve_version,
            self.nve_block_id,
            self.nve_block_count,
            self.valid_items,
            self.nv_checksum,
            self.nve_crc_support
        )
        res_bytes = self.reserved[:68].ljust(68, b"\x00")
        age_bytes = struct.pack("<I", self.nve_age)
        return name_bytes + hdr_core + res_bytes + age_bytes


# Huawei Kirin Kernel Defined Protected NV Numbers (from hisi_nve_whitelist.h)
KERNEL_PROTECTED_NV_NUMBERS = {2, 193, 194, 364}

KERNEL_NV_METADATA = {
    1: {"name": "USRKEY", "desc": "Bootloader Unlock Key (16-char ASCII or SHA-256 binary hash)", "protected": False},
    2: {"name": "SN", "desc": "Device Serial Number (Kernel Whitelist Protected)", "protected": True},
    3: {"name": "BOARDID", "desc": "Hardware PCB Board Identifier", "protected": False},
    193: {"name": "IMEI", "desc": "Primary SIM IMEI (Kernel Whitelist Protected)", "protected": True},
    194: {"name": "IMEI1", "desc": "Secondary SIM IMEI (Kernel Whitelist Protected)", "protected": True},
    259: {"name": "CALC1C2", "desc": "Radio Frequency / Modem Calibration C1/C2", "protected": False},
    276: {"name": "VERIFY_MODE", "desc": "Kernel dm-verity & Recovery verification mode", "protected": False},
    292: {"name": "FULLHD", "desc": "Display panel resolution mode", "protected": False},
    293: {"name": "MANUAL_DUMP", "desc": "Kernel panic / SoC crash ramdump mode", "protected": False},
    294: {"name": "AT_SERVER", "desc": "Modem AT command USB port server flag", "protected": False},
    295: {"name": "PWC_SWITCH", "desc": "HiSilicon Power Control switch", "protected": False},
    296: {"name": "ETB", "desc": "Embedded Trace Buffer debug log mode", "protected": False},
    297: {"name": "HIMNTN", "desc": "HiSilicon Maintenance & Factory Test mode", "protected": False},
    298: {"name": "SS_COUL", "desc": "Battery Coulomb counter & fuel gauge calibration", "protected": False},
    299: {"name": "HIPSE", "desc": "HiSilicon Security Engine mode flag", "protected": False},
    364: {"name": "BSN", "desc": "Mainboard Serial / MEID (Kernel Whitelist Protected)", "protected": True},
    371: {"name": "HW_HASH_ERR", "desc": "Hardware security hash error log", "protected": False},
    400: {"name": "WVLOCK", "desc": "Widevine DRM & Factory Security Key", "protected": False},
    402: {"name": "FBLOCK", "desc": "Factory Lock / FRP Lock state (0=Unlocked, 1=Locked)", "protected": False},
}


@dataclass
class NVItem:
    """Represents a single 128-byte NV item in an NVE block."""
    index: int                # Slot index (0..1022)
    nv_number: int            # NV entry number
    nv_name: str              # 8-char identifier (e.g. SN, USRKEY, FBLOCK)
    nv_property: int          # Property flags (uint32)
    valid_size: int           # Valid payload length in bytes (uint32)
    crc: int                  # CRC32C checksum (uint32)
    nv_data: bytes            # 104-byte payload

    @property
    def is_valid(self) -> bool:
        return self.nv_number != 0xFFFFFFFF and bool(self.nv_name.strip())

    @property
    def is_crc_valid(self) -> bool:
        return self.verify_crc()

    @property
    def is_kernel_protected(self) -> bool:
        return self.nv_number in KERNEL_PROTECTED_NV_NUMBERS

    @property
    def description(self) -> str:
        meta = KERNEL_NV_METADATA.get(self.nv_number)
        if meta:
            return meta["desc"]
        if "MAC" in self.nv_name:
            return "Network MAC Address"
        if "BAT" in self.nv_name:
            return "Battery / Power Calibration"
        if "CAM" in self.nv_name:
            return "Camera Sensor Calibration"
        if "AUDIO" in self.nv_name or "CODEC" in self.nv_name:
            return "Audio Hardware Calibration"
        return "Generic Hardware / Radio NV Item"

    @property
    def value_bytes(self) -> bytes:
        """Returns only the valid slice of data."""
        sz = min(self.valid_size, NV_DATA_MAX_SIZE)
        return self.nv_data[:sz]

    @property
    def value_hex(self) -> str:
        return self.value_bytes.hex()

    @property
    def value_text(self) -> str:
        """Decodes bytes as readable string, handling flags and binary payloads cleanly."""
        raw = self.value_bytes.rstrip(b"\x00")
        if not raw:
            return ""

        # Specific binary flags
        if self.nv_name == "FBLOCK":
            return "1" if (raw[0] == 1 or raw == b"1") else "0"
        if self.nv_name in ("FULLHD", "MANUDMP", "ATSERV", "USBPORT", "ATSTATE", "BFMR_ON", "LOGCTL", "BOOTCTL", "FWEN", "WANPING", "IPFLTEN", "TLTEN", "CURPROF"):
            if len(raw) == 1:
                return str(raw[0])
            if len(raw) == 4:
                try:
                    return str(struct.unpack("<I", raw)[0])
                except Exception:
                    pass

        # Check if printable ASCII/UTF-8
        if all(32 <= b <= 126 or b in (9, 10, 13) for b in raw):
            try:
                return raw.decode("utf-8", errors="replace").strip()
            except Exception:
                pass

        return raw.hex()

    @classmethod
    def unpack(cls, data: bytes, index: int) -> "NVItem":
        if len(data) != NV_ITEM_SIZE:
            raise ValueError(f"NVItem data must be exactly {NV_ITEM_SIZE} bytes")
        nv_num = struct.unpack("<I", data[0:4])[0]
        name_raw = data[4:12].rstrip(b"\x00")
        name = name_raw.decode("ascii", errors="replace").strip()
        prop, val_sz, crc = struct.unpack("<III", data[12:24])
        nv_data = data[24:128]
        return cls(
            index=index,
            nv_number=nv_num,
            nv_name=name,
            nv_property=prop,
            valid_size=val_sz,
            crc=crc,
            nv_data=nv_data
        )

    def pack(self, update_crc: bool = True) -> bytes:
        """Packs the item into 128 bytes, optionally recomputing CRC32C."""
        name_bytes = self.nv_name.encode("ascii", errors="replace")[:NV_NAME_MAX_LEN].ljust(NV_NAME_MAX_LEN, b"\x00")
        data_padded = self.nv_data[:NV_DATA_MAX_SIZE].ljust(NV_DATA_MAX_SIZE, b"\x00")
        
        # Build 20-byte header without crc
        hdr20 = struct.pack("<I", self.nv_number) + name_bytes + struct.pack("<II", self.nv_property, self.valid_size)
        
        if update_crc:
            crc_calc = compute_nv_item_crc(hdr20 + b"\x00\x00\x00\x00" + data_padded)
            self.crc = crc_calc
        
        crc_bytes = struct.pack("<I", self.crc)
        return hdr20 + crc_bytes + data_padded

    def verify_crc(self) -> bool:
        """Checks if current CRC field matches computed CRC32C."""
        expected = compute_nv_item_crc(self.pack(update_crc=False))
        return self.crc == expected
