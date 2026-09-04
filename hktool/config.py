"""
Configuration constants, device identifiers, and transfer limits.
"""
import os
from pathlib import Path

TOOL_NAME = "Huawei & Kirin Universal Toolkit"
TOOL_VERSION = "6.2.0 Free Edition"

# Base Paths
PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
BIN_DIR = PACKAGE_ROOT / "bin"
HISUITE_HWTOOLS_DIR = Path(r"C:\Program Files (x86)\HiSuite\hwtools")

# Huawei Official Fastboot Engine Resolution
if (HISUITE_HWTOOLS_DIR / "fastboot.exe").exists():
    FASTBOOT_BIN = HISUITE_HWTOOLS_DIR / "fastboot.exe"
    FASTBOOT_SOURCE = "HiSuite Official (C:\\Program Files (x86)\\HiSuite\\hwtools)"
elif (BIN_DIR / "fastboot.exe").exists():
    FASTBOOT_BIN = BIN_DIR / "fastboot.exe"
    FASTBOOT_SOURCE = "Huawei Official Standalone (hktool/bin)"
else:
    FASTBOOT_BIN = Path("fastboot.exe" if os.name == "nt" else "fastboot")
    FASTBOOT_SOURCE = "System PATH"

# Ensure fastboot binary directory is in system PATH for dependent DLLs
if FASTBOOT_BIN.is_file():
    fb_parent = str(FASTBOOT_BIN.parent)
    cur_path = os.environ.get("PATH", "")
    if fb_parent not in cur_path:
        os.environ["PATH"] = fb_parent + os.pathsep + cur_path

# Huawei USB Identifiers
HUAWEI_VID = 0x12D1
IDT_VCOM_PID = 0x3609           # HUAWEI USB COM 1.0 (Testpoint mode)
FASTBOOT_PID = 0x103A           # Fastboot interface PID
DBADAPTER_DESC = "DBAdapter Reserved Interface"  # Huawei USB Upgrade / eRecovery Serial

# Safe Transfer & Buffer Sizes
DEFAULT_CHUNK_SIZE = 4 * 1024 * 1024       # 4 MiB stream buffer
HUAWEI_SPARSE_MAX = 0x1E000000             # 480 MiB (Huawei Dload & Fastboot limit)
FASTBOOT_DEFAULT_MAX_CHUNK = 256 * 1024 * 1024  # 256 MiB safe fastboot flash chunk
VCOM_MAX_DATA_LEN = 0x400                  # 1024 bytes per VCOM frame
ERECOVERY_BLOCK_SIZE = 0x20000             # 128 KiB uncompressed USB Update block
HDLC_FRAME_MAX = 0x10000                   # 64 KiB serial packet chunk

# VCOM Frame Constants
VCOM_HEAD_MAGIC = bytes([0xFE, 0x00, 0xFF, 0x01])
VCOM_DATA_MAGIC = bytes([0xDA])
VCOM_TAIL_MAGIC = bytes([0xED])
VCOM_INQUIRY_MAGIC = bytes([0xCD])

# HDLC Framing Constants (Huawei eRecovery / DLOAD)
HDLC_FLAG = 0x7E
HDLC_ESC = 0x7D
HDLC_ESC_FLAG = 0x5E
HDLC_ESC_ESC = 0x5D

# Known Huawei Vendor / Country Code Mappings
HUAWEI_REGIONS = {
    "C432": {"vendor": "hw", "country": "eu", "desc": "Europe / Global"},
    "C185": {"vendor": "hw", "country": "meaf", "desc": "Middle East & Africa"},
    "C636": {"vendor": "hw", "country": "spcseas", "desc": "Asia Pacific"},
    "C00":  {"vendor": "all", "country": "cn", "desc": "China (Full Netcom)"},
    "C10":  {"vendor": "hw", "country": "ru", "desc": "Russia"},
    "C605": {"vendor": "hw", "country": "la", "desc": "Latin America"},
    "C431": {"vendor": "hw", "country": "eea", "desc": "European Economic Area"},
    "C461": {"vendor": "hw", "country": "za", "desc": "South Africa"},
    "C706": {"vendor": "hw", "country": "nz", "desc": "New Zealand"},
    "C34":  {"vendor": "optus", "country": "au", "desc": "Australia (Optus)"},
    "C55":  {"vendor": "tim", "country": "it", "desc": "Italy (TIM)"},
}
