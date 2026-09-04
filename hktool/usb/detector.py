"""
Universal device state detector (Fastboot, Factory Fastboot, VCOM, DBAdapter).
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Optional
from .serial_comm import SerialPortManager
from ..config import FASTBOOT_BIN


@dataclass
class DeviceState:
    mode: str  # "FASTBOOT", "FACTORY_FASTBOOT", "VCOM_TESTPOINT", "USB_UPGRADE", "NONE"
    identifier: str
    details: str
    is_connected: bool


class DeviceDetector:
    """Scans and detects connected Huawei/Honor devices across all modes."""

    @classmethod
    def detect(cls) -> DeviceState:
        """Perform comprehensive device discovery."""
        # 1. Check for HUAWEI USB COM 1.0 (Testpoint mode)
        vcom_port = SerialPortManager.find_vcom_port()
        if vcom_port:
            return DeviceState(
                mode="VCOM_TESTPOINT",
                identifier=vcom_port,
                details="HUAWEI USB COM 1.0 (Kirin Testpoint Mode)",
                is_connected=True
            )

        # 2. Check for DBAdapter Reserved Interface (USB Upgrade / eRecovery)
        db_port = SerialPortManager.find_dbadapter_port()
        if db_port:
            return DeviceState(
                mode="USB_UPGRADE",
                identifier=db_port,
                details="Huawei USB Upgrade / eRecovery Serial Interface",
                is_connected=True
            )

        # 3. Check for Fastboot Mode via official Huawei fastboot CLI
        try:
            fb_exe = str(FASTBOOT_BIN) if FASTBOOT_BIN.is_file() else "fastboot"
            res = subprocess.run([fb_exe, "devices"], capture_output=True, text=True, timeout=2)
            if res.stdout and "fastboot" in res.stdout:
                lines = res.stdout.strip().splitlines()
                serial_no = lines[0].split()[0] if lines else "Unknown"
                
                is_factory = False
                try:
                    info_res = subprocess.run([fb_exe, "oem", "get-bootinfo"], capture_output=True, text=True, timeout=2)
                    if "factory" in info_res.stdout.lower() or "factory" in info_res.stderr.lower():
                        is_factory = True
                except Exception:
                    pass

                mode = "FACTORY_FASTBOOT" if is_factory else "FASTBOOT"
                return DeviceState(
                    mode=mode,
                    identifier=serial_no,
                    details=f"Huawei Fastboot ({mode}) Serial: {serial_no}",
                    is_connected=True
                )
        except Exception:
            pass

        return DeviceState(
            mode="NONE",
            identifier="",
            details="No Huawei device detected.",
            is_connected=False
        )
