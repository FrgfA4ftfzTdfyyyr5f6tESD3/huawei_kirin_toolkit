"""
Companion Manager - Standalone GUI Companion Tools Launcher.
Strict zero-hosting policy for external third-party software:
- Directs users to official developer websites and download releases.
- Tracks local executable paths without storing or redistributing binaries in the repository.
- Launches official companion tools safely in isolated subprocesses.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
import webbrowser
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


@dataclass
class CompanionItem:
    id: str
    name: str
    author: str
    version_label: str
    description: str
    website_url: str
    download_url: str
    default_exe_names: List[str]
    tasks: List[str]
    archive_password: Optional[str] = None
    category: str = "GUI Companion"
    exe_path: Optional[str] = None
    require_admin: bool = False


DEFAULT_COMPANIONS: List[CompanionItem] = [
    CompanionItem(
        id="kirin_tool",
        name="Kirin-Tool",
        author="Da-Niel",
        version_label="Official Edition",
        description="Premier HiSilicon Kirin hardware servicing suite specialized in testpoint operations, bootloader unlocking, and partition dumps.",
        website_url="https://kirintool.cfd/",
        download_url="https://kirintool.cfd/download.php?action=download",
        default_exe_names=["Kirin-Tool.exe", "KirinTool.exe", "kirin_tool.exe"],
        tasks=[
            "Software & Hardware Testpoint Mode",
            "Bootloader Unlocking",
            "Enable Downgrade Mode",
            "Partition Read & Write / Dump",
            "Multi-Stage FRP Erase & Removal",
        ],
    ),
    CompanionItem(
        id="fastboot_flasher",
        name="FastbootFlasher",
        author="Natsume324",
        version_label="Latest GitHub Release",
        description="Comprehensive high-speed firmware unpacker and universal Fastboot flasher supporting all Huawei device models.",
        website_url="https://github.com/Natsume324/FastbootFlasher",
        download_url="https://github.com/Natsume324/FastbootFlasher/releases",
        default_exe_names=["FastbootFlasher.exe", "fastboot_flasher.exe", "Fastboot_Flasher.exe"],
        tasks=[
            "Extract all kinds of APP updates (UPDATE.APP and full firmware packages)",
            "Fastboot flash all kinds of Huawei updates & flash files",
            "Full Fastboot flash support for any Huawei device model",
        ],
    ),
    CompanionItem(
        id="android_utility",
        name="Android Utility (A-Utility)",
        author="mfl team",
        version_label="Official Edition",
        description="Multi-mode service tool specialized in Huawei Upgrade Mode flashing and USB eRecovery cable transfers.",
        website_url="https://www.mfdl.io/",
        download_url="https://www.mediafire.com/file/dp73po1rf9x4rgz",
        archive_password="mfdl",
        default_exe_names=["AndroidUtility.exe", "Android_Utility.exe", "mTool.exe", "A-Utility.exe"],
        tasks=[
            "Write files in Upgrade Mode (DLOAD / USB Upgrade)",
            "Flash & Update via USB cable in Recovery mode (eRecovery / USB Update)",
        ],
        require_admin=True,
    ),
    CompanionItem(
        id="huawei_idt",
        name="Huawei IDT (Image Download Tool)",
        author="Huawei Technologies Co., Ltd.",
        version_label="Factory Service Edition",
        description="Official factory service board flasher for flashing XML board software and initial xloader stages via testpoint COM.",
        website_url="https://consumer.huawei.com",
        download_url="https://forum.xda-developers.com",
        default_exe_names=["IDT.exe", "ImageDownloadTool.exe"],
        tasks=[
            "Factory Board Software flashing via Download.xml",
            "Direct xLoader initial boot injection via testpoint COM",
        ],
    ),
    CompanionItem(
        id="hisuite_proxy",
        name="HiSuite & HiSuite Proxy",
        author="ProfessorJTJ / Huawei",
        version_label="v11.x - v14.x / Proxy v2.x",
        description="Official Huawei management suite paired with HiSuite Proxy to allow custom firmware downgrades and regional rollbacks.",
        website_url="https://github.com/ProfessorJTJ/HISuite-Proxy",
        download_url="https://github.com/ProfessorJTJ/HISuite-Proxy/releases",
        default_exe_names=["HiSuite.exe", "HiSuiteProxy.exe"],
        tasks=[
            "Custom firmware downgrade proxy injection",
            "Official EMUI rollback package delivery",
        ],
    ),
]


def _find_7z_binary() -> Optional[str]:
    """Locate 7-Zip executable on the system."""
    for candidate in [
        shutil.which("7z"),
        shutil.which("7za"),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "7-Zip", "7z.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "7-Zip", "7z.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "7-Zip", "7z.exe"),
    ]:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


class CompanionManager:
    """Manages external GUI companion tools registration, configuration, and launching."""

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path(__file__).resolve().parent.parent / "config"
        self.config_file = config_dir / "companions.json"
        self.items: Dict[str, CompanionItem] = {item.id: item for item in DEFAULT_COMPANIONS}
        self.load_config()
        self.auto_discover_all()

    def auto_discover_all(self) -> None:
        """Automatically detect executables in tools/<item_id>/ on disk."""
        base_tools_dir = Path(__file__).resolve().parent.parent.parent / "tools"
        changed = False
        for item in self.items.values():
            if not self.is_installed(item.id):
                item_dir = base_tools_dir / item.id
                if item_dir.exists():
                    found_exe = None
                    for def_name in item.default_exe_names:
                        matches = list(item_dir.rglob(def_name))
                        if matches:
                            found_exe = matches[0]
                            break
                    if not found_exe:
                        all_exes = [p for p in item_dir.rglob("*.exe") if not p.name.lower().startswith("uninstall")]
                        if all_exes:
                            found_exe = all_exes[0]
                    if found_exe:
                        item.exe_path = str(found_exe)
                        changed = True
        if changed:
            self.save_config()

    def load_config(self) -> None:
        """Load user-configured local executable paths from JSON file."""
        if not self.config_file.exists():
            return
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
                for item_id, path_val in saved.items():
                    if item_id in self.items and path_val:
                        self.items[item_id].exe_path = str(path_val)
        except Exception:
            pass

    def save_config(self) -> None:
        """Persist configured executable paths."""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            data = {k: v.exe_path for k, v in self.items.items() if v.exe_path}
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def get_all(self) -> List[CompanionItem]:
        return list(self.items.values())

    def get_item(self, item_id: str) -> Optional[CompanionItem]:
        return self.items.get(item_id)

    def set_exe_path(self, item_id: str, exe_path: str) -> bool:
        if item_id in self.items:
            self.items[item_id].exe_path = exe_path
            self.save_config()
            return True
        return False

    def is_installed(self, item_id: str) -> bool:
        item = self.items.get(item_id)
        if not item or not item.exe_path:
            return False
        p = Path(item.exe_path)
        return p.exists() and p.is_file()

    def open_official_site(self, item_id: str) -> bool:
        item = self.items.get(item_id)
        if item and item.website_url:
            webbrowser.open(item.website_url)
            return True
        return False

    def open_about_page(self, item_id: str) -> bool:
        """Open official project website / about page."""
        return self.open_official_site(item_id)

    def open_download_page(self, item_id: str) -> bool:
        item = self.items.get(item_id)
        if item and item.download_url:
            webbrowser.open(item.download_url)
            return True
        return False

    def extract_archive(
        self,
        archive_path: Path,
        destination_dir: Path,
        password: Optional[str] = None,
        log_cb: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        Extract an archive (.zip, .7z, .rar, etc.) into destination_dir using available extractors:
        1. 7-Zip binary (handles all formats including 7z and rar, with password)
        2. Built-in zipfile (for .zip archives)
        3. Built-in tarfile (for .tar, .tar.gz, etc.)
        4. System tar utility fallback
        """
        destination_dir.mkdir(parents=True, exist_ok=True)

        # 1. Try 7-Zip if available
        seven_zip = _find_7z_binary()
        if seven_zip:
            if log_cb:
                log_cb(f"Extracting with 7-Zip engine ({Path(seven_zip).name})...")
            cmd = [seven_zip, "x", str(archive_path), f"-o{str(destination_dir)}", "-y", "-aoa"]
            if password:
                cmd.append(f"-p{password}")
            else:
                cmd.append("-p-")

            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, creationflags=creation_flags)
                if res.returncode == 0:
                    return True
                if log_cb and res.stderr:
                    log_cb(f"7-Zip note: {res.stderr.strip()}")
            except Exception as e:
                if log_cb:
                    log_cb(f"7-Zip execution error: {e}")

        # 2. Try Python zipfile if archive is a ZIP
        try:
            if zipfile.is_zipfile(archive_path):
                if log_cb:
                    log_cb("Extracting with built-in zipfile engine...")
                with zipfile.ZipFile(archive_path, "r") as zf:
                    pwd_bytes = password.encode("utf-8") if password else None
                    zf.extractall(path=destination_dir, pwd=pwd_bytes)
                return True
        except Exception as e:
            if log_cb:
                log_cb(f"zipfile extraction note: {e}")

        # 3. Try Python tarfile if archive is a TAR
        try:
            if tarfile.is_tarfile(archive_path):
                if log_cb:
                    log_cb("Extracting with built-in tarfile engine...")
                with tarfile.open(archive_path, "r:*") as tf:
                    tf.extractall(path=destination_dir)
                return True
        except Exception as e:
            if log_cb:
                log_cb(f"tarfile extraction note: {e}")

        # 4. Try system tar utility
        system_tar = shutil.which("tar")
        if system_tar:
            try:
                if log_cb:
                    log_cb("Extracting with system tar utility...")
                creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                res = subprocess.run(
                    [system_tar, "-xf", str(archive_path), "-C", str(destination_dir)],
                    capture_output=True,
                    text=True,
                    creationflags=creation_flags,
                )
                if res.returncode == 0:
                    return True
            except Exception as e:
                if log_cb:
                    log_cb(f"System tar error: {e}")

        return False

    def import_archive(
        self,
        item_id: str,
        archive_path: str | Path,
        log_cb: Optional[Callable[[str], None]] = None,
    ) -> Tuple[bool, str]:
        """
        Extracts user-provided archive (.zip, .7z, .rar, etc.) into tools/<item_id>/,
        applying archive password if configured (e.g. 'mfdl' for Android Utility),
        automatically detects the executable (.exe), registers it, and updates configuration.
        """
        item = self.items.get(item_id)
        if not item:
            return False, f"Companion tool '{item_id}' not found."

        archive_file = Path(archive_path)
        if not archive_file.is_file():
            return False, f"Archive file '{archive_file}' does not exist or is not a file."

        base_tools_dir = Path(__file__).resolve().parent.parent.parent / "tools"
        tools_dir = base_tools_dir / item.id
        tools_dir.mkdir(parents=True, exist_ok=True)

        if log_cb:
            log_cb(f"📦 Extracting {archive_file.name} to {tools_dir}...")
            if item.archive_password:
                log_cb(f"🔑 Applying archive password: {item.archive_password}")

        success = self.extract_archive(
            archive_path=archive_file,
            destination_dir=tools_dir,
            password=item.archive_password,
            log_cb=log_cb,
        )

        if not success:
            return False, (
                f"Failed to extract archive '{archive_file.name}'. "
                f"Please ensure 7-Zip is installed if this is a .7z or .rar file, or verify the archive integrity."
            )

        if log_cb:
            log_cb("🔍 Scanning extracted directory for companion executable (.exe)...")

        # Locate executable
        found_exe = None
        for def_name in item.default_exe_names:
            matches = list(tools_dir.rglob(def_name))
            if matches:
                found_exe = matches[0]
                break

        if not found_exe:
            all_exes = [p for p in tools_dir.rglob("*.exe") if not p.name.lower().startswith("uninstall")]
            if all_exes:
                found_exe = all_exes[0]

        if found_exe:
            self.set_exe_path(item.id, str(found_exe))
            if log_cb:
                log_cb(f"✅ Executable registered: {found_exe}")
            return True, f"Successfully imported and extracted {item.name}! Executable detected: {found_exe.name}"
        else:
            return False, (
                f"Archive successfully extracted to '{tools_dir}', but could not automatically detect an executable (.exe). "
                f"Please verify the folder contents."
            )

    def download_and_setup(
        self,
        item_id: str,
        on_status: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_finished: Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        """Deprecated: Direct URL background downloading has been decommissioned to prevent expired host link errors."""
        self.open_official_site(item_id)
        msg = "Automatic background downloading has been decommissioned. Please download from the opened official website and use 'Import Downloaded Archive'."
        if on_status:
            on_status(msg)
        if on_finished:
            on_finished(False, msg)

    def launch(self, item_id: str) -> Tuple[bool, str]:
        """
        Execute the standalone companion application in its own independent process.
        Automatically elevates with administrator privileges ('runas') if required by the application.
        """
        item = self.items.get(item_id)
        if not item:
            return False, f"Companion '{item_id}' is not registered."

        if not self.is_installed(item_id):
            return False, f"Executable for '{item.name}' is not configured or not found. Please click 'Browse' to select the .exe."

        exe_file = Path(item.exe_path)
        working_dir = str(exe_file.parent)

        def _launch_elevated() -> Tuple[bool, str]:
            if os.name == "nt":
                try:
                    import ctypes
                    ret = ctypes.windll.shell32.ShellExecuteW(
                        None,
                        "runas",
                        str(exe_file),
                        None,
                        working_dir,
                        1,  # SW_SHOWNORMAL
                    )
                    if ret > 32:
                        return True, f"Successfully launched {item.name} with administrator privileges."
                    elif ret == 1223:  # ERROR_CANCELLED (user canceled UAC prompt)
                        return False, f"Administrator elevation was cancelled by the user for {item.name}."
                    else:
                        return False, f"Failed to launch {item.name} as administrator (Error code: {ret})."
                except Exception as ex_elev:
                    return False, f"Administrator elevation failed for {item.name}: {ex_elev}"
            return False, f"Elevation is not supported on this platform for {item.name}."

        # If explicitly designated as requiring admin on Windows, elevate directly
        if getattr(item, "require_admin", False) and os.name == "nt":
            return _launch_elevated()

        try:
            # Launch detached process in its own working directory
            subprocess.Popen(
                [str(exe_file)],
                cwd=working_dir,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            return True, f"Successfully launched {item.name}."
        except OSError as oe:
            # WinError 740: The requested operation requires elevation
            if getattr(oe, "winerror", None) == 740 or "requires elevation" in str(oe).lower():
                return _launch_elevated()
            return False, f"Failed to launch {item.name}: {oe}"
        except Exception as e:
            return False, f"Failed to launch {item.name}: {e}"
