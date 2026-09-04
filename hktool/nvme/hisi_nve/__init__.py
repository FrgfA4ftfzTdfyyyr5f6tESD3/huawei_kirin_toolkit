"""
HisiNve-Py: Comprehensive offline reader, writer, and manager for Huawei Kirin NVE partitions.
"""
from .crc import crc32c, compute_nv_item_crc
from .structures import (
    NVEPartitionHeader,
    NVItem,
    NVE_BLOCK_SIZE,
    PARTITION_HEADER_SIZE,
    NV_ITEM_SIZE,
    NV_ITEMS_PER_BLOCK,
    NV_DATA_MAX_SIZE,
)
from .soc_profiles import SocProfile, SOC_PROFILES, detect_soc_from_entries
from .parser import HisiNveImage, NVEBlock

__version__ = "3.0.0"
__all__ = [
    "HisiNveImage",
    "NVEBlock",
    "NVItem",
    "NVEPartitionHeader",
    "SocProfile",
    "SOC_PROFILES",
    "detect_soc_from_entries",
    "crc32c",
    "compute_nv_item_crc",
    "NVE_BLOCK_SIZE",
    "PARTITION_HEADER_SIZE",
    "NV_ITEM_SIZE",
    "NV_ITEMS_PER_BLOCK",
    "NV_DATA_MAX_SIZE",
]
