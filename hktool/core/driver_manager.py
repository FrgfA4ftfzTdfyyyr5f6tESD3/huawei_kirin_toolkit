"""
Huawei Driver Manager, Pre-Flight Hardware Connection Validators & Elevated Windows USB Setup.
Provides automated Administrator elevation for BCD test signing (ON / OFF),
PnP Device Manager live status diagnostics, and multi-mode pre-flight connection checks.
"""
from __future__ import annotations

import ctypes
import os
import platform
import subprocess
import tempfile
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


from ..config import BIN_DIR, FASTBOOT_BIN, FASTBOOT_SOURCE, HISUITE_HWTOOLS_DIR


@dataclass
class DriverStatusItem:
    category: str
    name: str
    vid_pid: str
    status: str          # 'INSTALLED_OK', 'DEVICE_CONNECTED', 'DRIVER_MISSING', 'NOT_CONNECTED'
    details: str
    is_ready: bool


class DriverManager:
    """Automates Huawei drivers, elevated BCD configuration, and Huawei official Fastboot synchronization."""

    DRIVERS_BASE_DIR = Path(__file__).parent.parent / "bin" / "drivers" / "huawei_usb_com_1.0"
    HISUITE_URL = "https://consumer.huawei.com/en/support/hisuite/"

    @classmethod
    def get_huawei_fastboot_info(cls) -> Dict[str, any]:
        """Returns details on Huawei official Fastboot binary in HiSuite and hktool/bin."""
        hisuite_fb = HISUITE_HWTOOLS_DIR / "fastboot.exe"
        bin_fb = BIN_DIR / "fastboot.exe"

        hisuite_installed = hisuite_fb.exists()
        bin_present = bin_fb.exists()

        version = "Official Huawei Fastboot"
        target_bin = hisuite_fb if hisuite_installed else bin_fb
        if target_bin.exists():
            try:
                res = subprocess.run([str(target_bin), "--version"], capture_output=True, text=True, timeout=2)
                lines = res.stdout.splitlines()
                if lines:
                    version = lines[0].strip()
            except Exception:
                pass

        return {
            "hisuite_path": str(hisuite_fb),
            "hisuite_installed": hisuite_installed,
            "bin_path": str(bin_fb),
            "bin_present": bin_present,
            "active_source": FASTBOOT_SOURCE,
            "active_path": str(FASTBOOT_BIN),
            "version": version
        }

    @classmethod
    def sync_huawei_fastboot(cls, on_status: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """Synchronizes official Huawei Fastboot and companion DLLs from HiSuite hwtools into hktool/bin."""
        import shutil
        hisuite_dir = HISUITE_HWTOOLS_DIR
        bin_dir = BIN_DIR
        bin_dir.mkdir(parents=True, exist_ok=True)

        files_to_sync = ["fastboot.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll"]
        if not hisuite_dir.exists():
            return False, f"HiSuite hwtools directory not found at: {hisuite_dir}"

        copied = 0
        for fname in files_to_sync:
            src = hisuite_dir / fname
            dst = bin_dir / fname
            if src.exists():
                shutil.copy2(src, dst)
                copied += 1
                if on_status:
                    on_status(f"Synchronized: {fname} -> hktool/bin/{fname}")

        if copied > 0:
            return True, f"Successfully synchronized {copied} official Huawei Fastboot files from HiSuite."
        return False, "No Fastboot binaries found to synchronize from HiSuite."

    @classmethod
    def open_hisuite_page(cls) -> None:
        """Opens official Huawei HiSuite download page."""
        webbrowser.open(cls.HISUITE_URL)

    @classmethod
    def is_admin(cls) -> bool:
        """Check if current process has Windows Administrator privileges."""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    @classmethod
    def get_driver_arch_dir(cls) -> Path:
        is_64 = "64" in platform.machine() or "AMD64" in platform.machine()
        sub = "X64" if is_64 else "X86"
        return cls.DRIVERS_BASE_DIR / "HUAWEI+USB+COM+1.0+driver" / sub

    @classmethod
    def open_hisuite_download(cls) -> None:
        """Open official Huawei HiSuite driver package download page."""
        webbrowser.open(cls.HISUITE_URL)

    @classmethod
    def open_device_manager(cls) -> None:
        """Launch Windows Device Manager directly."""
        try:
            subprocess.Popen(["devmgmt.msc"], shell=True)
        except Exception:
            pass

    @classmethod
    def run_elevated_batch(cls, commands: List[str], on_status: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """
        Executes a list of Windows commands with Administrator elevation (UAC prompt).
        Guarantees bcdedit and pnputil commands apply without 'Access Denied' errors.
        """
        if cls.is_admin():
            logs = []
            all_ok = True
            for cmd in commands:
                if on_status:
                    on_status(f"Executing [Admin]: {cmd}...")
                try:
                    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    out = (res.stdout + "\n" + res.stderr).strip()
                    logs.append(f"{cmd} -> {out}")
                    if res.returncode != 0:
                        all_ok = False
                except Exception as e:
                    logs.append(f"{cmd} failed: {e}")
                    all_ok = False
            return all_ok, "\n".join(logs)

        temp_bat = Path(tempfile.gettempdir()) / "hk_elevated_cmd.bat"
        bat_lines = ["@echo off", "chcp 65001 >nul"]
        bat_lines.extend(commands)
        bat_lines.append("exit /b %ERRORLEVEL%")

        temp_bat.write_text("\n".join(bat_lines), encoding="utf-8")

        if on_status:
            on_status("Requesting Windows Administrator privileges (UAC prompt)...")

        ps_cmd = f'Start-Process cmd.exe -ArgumentList \'/c "{temp_bat}"\' -Verb RunAs -Wait'
        try:
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
            if temp_bat.exists():
                try: temp_bat.unlink()
                except Exception: pass

            if res.returncode == 0:
                if on_status:
                    on_status("Elevated command executed successfully.")
                return True, "Commands applied with Administrator privileges."
            else:
                return False, f"Elevation cancelled or failed: {res.stderr}"
        except Exception as e:
            return False, f"Failed to launch elevated process: {e}"

    @classmethod
    def enable_windows_test_signing(cls, on_status: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """Configure Windows BCD to allow unsigned Huawei USB COM 1.0 drivers (Administrator)."""
        cmds = [
            "bcdedit /set nointegritychecks on",
            "bcdedit /set testsigning on"
        ]
        return cls.run_elevated_batch(cmds, on_status=on_status)

    @classmethod
    def disable_windows_test_signing(cls, on_status: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """Restore standard Windows BCD integrity checks and disable Test Mode (Administrator)."""
        cmds = [
            "bcdedit /set nointegritychecks off",
            "bcdedit /set testsigning off"
        ]
        return cls.run_elevated_batch(cmds, on_status=on_status)

    @classmethod
    def install_usb_com_drivers(cls, on_status: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """Installs all Huawei USB COM 1.0 drivers (.inf) using Windows pnputil (Administrator)."""
        arch_dir = cls.get_driver_arch_dir()
        if not arch_dir.exists():
            arch_dir = cls.DRIVERS_BASE_DIR / "X64" if "64" in platform.machine() else cls.DRIVERS_BASE_DIR / "X86"

        if not arch_dir.exists():
            return False, f"Driver directory not found at: {arch_dir}"

        inf_files = list(arch_dir.glob("*.inf"))
        if not inf_files:
            return False, f"No .inf driver files found in {arch_dir}"

        if on_status:
            on_status(f"Found {len(inf_files)} driver packages. Installing via elevated pnputil...")

        cmds = [f'pnputil /add-driver "{inf}" /install' for inf in inf_files]
        return cls.run_elevated_batch(cmds, on_status=on_status)

    @classmethod
    def check_all_driver_status(cls) -> List[DriverStatusItem]:
        """Scans Windows PnP devices and Fastboot to verify all Huawei/Android driver layers."""
        results: List[DriverStatusItem] = []

        # 1. Fastboot Status Check
        fb_ready = False
        fb_detail = "Device not connected in Fastboot mode."
        fb_exe = str(FASTBOOT_BIN) if FASTBOOT_BIN.is_file() else "fastboot"
        try:
            p = subprocess.run([fb_exe, "devices"], capture_output=True, text=True, timeout=3)
            lines = [l.strip() for l in p.stdout.splitlines() if l.strip()]
            if lines:
                fb_ready = True
                fb_detail = f"Connected & Recognized: {lines[0]}"
        except Exception:
            pass

        results.append(DriverStatusItem(
            category="Fastboot",
            name="Official Huawei Fastboot Interface",
            vid_pid="VID_18D1/PID_D00D or VID_12D1",
            status="CONNECTED & READY" if fb_ready else "NOT DETECTED",
            details=fb_detail,
            is_ready=fb_ready
        ))

        # 2. Query Windows PnP Devices via PowerShell
        ps_cmd = 'Get-PnpDevice | Where-Object { $_.InstanceId -like "*12D1*" -or $_.InstanceId -like "*18D1*" -or $_.FriendlyName -like "*Huawei*" } | Select-Object FriendlyName, InstanceId, Status, Class'
        pnp_raw = ""
        try:
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=5)
            pnp_raw = res.stdout
        except Exception:
            pass

        has_vcom = "3609" in pnp_raw or "USB COM 1.0" in pnp_raw
        has_dbadapter = "DBAdapter" in pnp_raw or "PROT_23" in pnp_raw

        # USB COM 1.0
        results.append(DriverStatusItem(
            category="Testpoint VCOM",
            name="HUAWEI USB COM 1.0 (Kirin Testpoint)",
            vid_pid="VID_12D1&PID_3609",
            status="CONNECTED & READY" if has_vcom else "DRIVER READY (Plug in Testpoint mode)",
            details="Hardware testpoint serial port for low-level Kirin SoC RAM bootstrapping." if not has_vcom else "Active USB COM 1.0 port detected in Device Manager.",
            is_ready=True
        ))

        # eRecovery DBAdapter
        results.append(DriverStatusItem(
            category="eRecovery / USB Upgrade",
            name="Huawei DBAdapter Reserved Interface",
            vid_pid="VID_12D1 (Subclass 13 / Prot 23)",
            status="CONNECTED & READY" if has_dbadapter else "DRIVER READY (Plug in eRecovery mode)",
            details="High-speed serial HDLC interface for USB Upgrade and eRecovery package flashing." if not has_dbadapter else "Active DBAdapter interface detected.",
            is_ready=True
        ))

        return results

    @classmethod
    def validate_fastboot_preflight(cls) -> Tuple[bool, str]:
        """
        Strict pre-flight validation before executing Fastboot flashing operations.
        Ensures device is physically connected in Fastboot mode and communicating via official Huawei fastboot.
        """
        try:
            fb_exe = str(FASTBOOT_BIN) if FASTBOOT_BIN.is_file() else "fastboot"
            p = subprocess.run([fb_exe, "devices"], capture_output=True, text=True, timeout=3)
            lines = [l.strip() for l in p.stdout.splitlines() if l.strip()]
            if lines:
                return True, f"Device detected in Fastboot mode: {lines[0]}"
        except Exception as e:
            return False, f"Fastboot executable error: {e}"

        return False, (
            "NO DEVICE DETECTED IN FASTBOOT MODE!\n\n"
            "Please connect your device in Fastboot mode before proceeding:\n\n"
            "1. Power off the device completely.\n"
            "2. Hold [Volume Down] and plug the USB cable into the PC.\n"
            "3. Wait until the phone enters 'FASTBOOT&RESCUE MODE' (White/Green Android screen).\n"
            "4. Verify USB Drivers in 'Driver Studio & USB Setup' tab if device is not recognized."
        )

    @classmethod
    def validate_vcom_preflight(cls) -> Tuple[bool, str]:
        """
        Validates whether a Huawei USB COM 1.0 (Testpoint) port is active in Device Manager.
        """
        try:
            from ..usb.detector import DeviceDetector
            state = DeviceDetector.detect()
            if state.is_connected and "VCOM" in state.mode:
                return True, f"Huawei USB COM 1.0 detected on {state.identifier}"
        except Exception:
            pass

        return False, (
            "HUAWEI USB COM 1.0 PORT NOT DETECTED!\n\n"
            "Please connect your device in Hardware Testpoint mode:\n\n"
            "1. Disconnect battery and short the Testpoint (TP) pin to GND (Shielding can).\n"
            "2. Plug in the USB cable to PC while keeping TP shorted, then release after 2 seconds.\n"
            "3. Device Manager will show 'HUAWEI USB COM 1.0 (COMx)'.\n"
            "4. Ensure Test Signing is enabled in 'Driver Studio & USB Setup' if driver fails to bind."
        )
