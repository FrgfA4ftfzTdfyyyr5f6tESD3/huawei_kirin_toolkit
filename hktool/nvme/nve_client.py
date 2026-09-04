"""
Huawei NVE / NVME Direct Communication & Variable Engine.
Reads and writes calibration and identity properties (SN, IMEI, MAC, BSN, FBLOCK, WVLOCK, VENDOR_COUNTRY)
in Fastboot mode and ADB / Root / Recovery mode via native hisi-nve binary.
"""
from __future__ import annotations

import re
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable


@dataclass
class NveDeviceInfo:
    sn: str = "Unknown"
    imei: str = "Unknown"
    imei2: str = "Unknown"
    wifi_mac: str = "Unknown"
    bt_mac: str = "Unknown"
    bsn: str = "Unknown"
    boardid: str = "Unknown"
    vendor_country: str = "Unknown"
    fblock_state: str = "Unknown"
    wvlock: str = "Unknown"
    model: str = "Unknown"


class NveClient:
    """Interface to Huawei NVME / NVE properties via Fastboot & ADB."""

    @staticmethod
    def run_fastboot(args: List[str], timeout: int = 15) -> Tuple[bool, str]:
        try:
            cmd = ["fastboot"] + args
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            out = (res.stdout + "\n" + res.stderr).strip()
            success = res.returncode == 0 or "OKAY" in out.upper() or "set nv ok" in out.lower()
            return success, out
        except Exception as e:
            return False, str(e)

    @staticmethod
    def run_adb(args: List[str], timeout: int = 20) -> Tuple[bool, str]:
        try:
            cmd = ["adb"] + args
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            out = (res.stdout + "\n" + res.stderr).strip()
            success = res.returncode == 0
            return success, out
        except Exception as e:
            return False, str(e)

    @classmethod
    def _sanitize_val(cls, val: Optional[str]) -> Optional[str]:
        if not val:
            return None
        v = val.strip()
        v_upper = v.upper()
        if not v or "FAIL" in v_upper or "NV ERROR" in v_upper or "NOT FOUND" in v_upper or v_upper in ("UNKNOWN", "NONE", "NULL", "ERROR"):
            return None
        return v

    @classmethod
    def read_fastboot_getvar(cls, var_name: str) -> Optional[str]:
        """Read a single variable using fastboot getvar."""
        ok, out = cls.run_fastboot(["getvar", var_name])
        pattern = rf"{re.escape(var_name)}:\s*([^\r\n]+)"
        m = re.search(pattern, out, re.IGNORECASE)
        if m:
            val = cls._sanitize_val(m.group(1))
            if val:
                return val

        for line in out.splitlines():
            if var_name.lower() in line.lower() and ":" in line:
                parts = line.split(":", 1)
                if len(parts) >= 2:
                    val = cls._sanitize_val(parts[1])
                    if val:
                        return val
        return None

    @classmethod
    def read_variable(cls, var_name: str) -> Optional[str]:
        """Read an NVE property using getvar nve:<var_name>."""
        return cls.read_fastboot_getvar(f"nve:{var_name}")

    @classmethod
    def write_variable(cls, var_name: str, value: str) -> Tuple[bool, str]:
        """Write an NVE property using getvar nve:<var_name>@<value>."""
        ok, out = cls.run_fastboot(["getvar", f"nve:{var_name}@{value}"])
        success = "set nv ok" in out.lower() or "OKAY" in out.upper() or ok
        return success, out

    @classmethod
    def read_all_properties(cls) -> NveDeviceInfo:
        """Query all standard Huawei device NVME variables with intelligent fallbacks."""
        info = NveDeviceInfo()

        # 1. Serial Number (SN)
        sn = cls.read_variable("SN") or cls.read_fastboot_getvar("serialno")
        if not sn:
            _, psid_out = cls.run_fastboot(["oem", "get-psid"])
            m_psid = re.search(r"SN:([A-Za-z0-9]+)", psid_out)
            if m_psid:
                sn = m_psid.group(1).strip()
        info.sn = sn or "Unknown"

        # 2. Model & Product
        model = cls.read_fastboot_getvar("product") or cls.read_variable("MODEL") or cls.read_variable("PROD_MODEL")
        if not model:
            _, bld_out = cls.run_fastboot(["oem", "get-build-number"])
            m_bld = re.search(r"([A-Z0-9]{3,8}-[A-Z0-9]{3,8})", bld_out)
            if m_bld:
                model = m_bld.group(1).strip()
        info.model = model or "Unknown"

        # 3. IMEI & Identifiers
        imei_val = cls.read_variable("IMEI")
        if imei_val and imei_val != "IMEI" and re.match(r"^\d{14,16}$", imei_val):
            info.imei = imei_val
        else:
            info.imei = "Protected / Unset"

        imei2_val = cls.read_variable("IMEI1") or cls.read_variable("IMEI2")
        if imei2_val and re.match(r"^\d{14,16}$", imei2_val):
            info.imei2 = imei2_val
        else:
            info.imei2 = "Protected / Unset"

        info.wifi_mac = cls.read_variable("WIFI_MAC") or cls.read_variable("MAC") or "Protected / Unset"
        info.bt_mac = cls.read_variable("BT_MAC") or "Protected / Unset"
        info.bsn = cls.read_variable("BSN") or "Protected / Unset"
        info.boardid = cls.read_variable("BOARDID") or "Protected / Unset"
        info.vendor_country = cls.read_fastboot_getvar("vendorcountry") or cls.read_variable("VENDOR_COUNTRY") or "Protected / Unset"
        info.wvlock = cls.read_variable("WVLOCK") or "Protected / Unset"

        # 4. Lock State & FBLOCK
        ok, fb_out = cls.run_fastboot(["oem", "backdoor", "info"])
        if "UNLOCKED" in fb_out.upper():
            info.fblock_state = "UNLOCKED (0)"
        elif "LOCKED" in fb_out.upper():
            info.fblock_state = "LOCKED (1)"
        else:
            ok_boot, boot_out = cls.run_fastboot(["oem", "get-bootinfo"])
            if "FB LockState: UNLOCKED" in boot_out:
                info.fblock_state = "UNLOCKED (0)"
            elif "FB LockState: LOCKED" in boot_out:
                info.fblock_state = "LOCKED (1)"
            else:
                nve_fb = cls.read_variable("FBLOCK")
                if nve_fb in ("1", "01"):
                    info.fblock_state = "LOCKED (1)"
                elif nve_fb in ("0", "00"):
                    info.fblock_state = "UNLOCKED (0)"
                else:
                    info.fblock_state = "Unknown / Protected"

        return info

    @classmethod
    def dump_nvme_via_adb(cls, local_dest_path: str, on_status: Optional[Callable[[str], None]] = None) -> bool:
        """
        Extracts the live nvme partition directly from device via ADB / Root / Recovery
        using the native hisi-nve binary payload.
        """
        payload_bin = Path(__file__).resolve().parent.parent / "payloads" / "hisi_nve_binaries" / "arm64-v8a" / "hisi-nve"
        if not payload_bin.exists():
            if on_status:
                on_status(f"Native hisi-nve binary payload not found at: {payload_bin}")
            return False

        if on_status:
            on_status("Pushing native hisi-nve binary to /data/local/tmp/hisi-nve...")

        cls.run_adb(["push", str(payload_bin), "/data/local/tmp/hisi-nve"])
        cls.run_adb(["shell", "chmod", "755", "/data/local/tmp/hisi-nve"])

        if on_status:
            on_status("Dumping /dev/block/bootdevice/by-name/nvme...")

        cls.run_adb(["shell", "su -c 'dd if=/dev/block/bootdevice/by-name/nvme of=/sdcard/nvme_dump.img' 2>/dev/null || dd if=/dev/block/bootdevice/by-name/nvme of=/sdcard/nvme_dump.img 2>/dev/null || dd if=/dev/block/by-name/nvme of=/sdcard/nvme_dump.img 2>/dev/null"])

        if on_status:
            on_status("Pulling nvme dump to PC...")

        cls.run_adb(["pull", "/sdcard/nvme_dump.img", str(local_dest_path)])
        cls.run_adb(["shell", "rm", "-f", "/sdcard/nvme_dump.img"])

        if Path(local_dest_path).exists() and Path(local_dest_path).stat().st_size > 0:
            if on_status:
                on_status(f"✔ Successfully dumped nvme.img ({Path(local_dest_path).stat().st_size} bytes) via ADB!")
            return True

        if on_status:
            on_status("❌ Could not dump nvme partition via ADB. Ensure device has root or is in TWRP/Recovery mode.")
        return False
