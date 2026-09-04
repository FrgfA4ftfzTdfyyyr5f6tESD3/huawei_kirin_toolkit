"""
NVE / NVME property management, offline editor, and repair tools.
"""
from .hisi_nve import (
    HisiNveImage,
    NVEBlock,
    NVItem,
    NVEPartitionHeader,
    SocProfile,
    SOC_PROFILES,
    detect_soc_from_entries,
    crc32c,
    compute_nv_item_crc,
    NVE_BLOCK_SIZE,
    PARTITION_HEADER_SIZE,
    NV_ITEM_SIZE,
    NV_ITEMS_PER_BLOCK,
    NV_DATA_MAX_SIZE,
)
from .nve_client import NveClient, NveDeviceInfo
