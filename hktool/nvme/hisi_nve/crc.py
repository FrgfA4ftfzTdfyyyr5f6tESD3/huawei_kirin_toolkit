"""
CRC32C (Castagnoli) Checksum Implementation for HiSilicon NVE Partitions.
Polynomial: 0x1EDC6F41 (Reversed: 0x82F63B78)
Initial Value: 0xFFFFFFFF
XOR Output: 0xFFFFFFFF
Reflected In/Out: True
"""

def _make_crc32c_table() -> list[int]:
    poly = 0x82F63B78
    table = []
    for i in range(256):
        c = i
        for _ in range(8):
            if c & 1:
                c = (c >> 1) ^ poly
            else:
                c >>= 1
        table.append(c)
    return table

_CRC32C_TABLE = _make_crc32c_table()

def crc32c(data: bytes) -> int:
    """
    Calculate the CRC32C (Castagnoli) checksum of the input bytes.
    Used by Huawei Kirin NVE driver to verify integrity of NV items.
    """
    crc = 0xFFFFFFFF
    table = _CRC32C_TABLE
    for b in data:
        crc = (crc >> 8) ^ table[(crc ^ b) & 0xFF]
    return (crc ^ 0xFFFFFFFF) & 0xFFFFFFFF


def compute_nv_item_crc(item_raw_128: bytes) -> int:
    """
    Computes CRC32C over the 20-byte item header and 104-byte data payload,
    skipping the 4-byte CRC field at offset 20..24.
    """
    if len(item_raw_128) != 128:
        raise ValueError(f"Item must be exactly 128 bytes, got {len(item_raw_128)}")
    buf = item_raw_128[0:20] + item_raw_128[24:128]
    return crc32c(buf)
