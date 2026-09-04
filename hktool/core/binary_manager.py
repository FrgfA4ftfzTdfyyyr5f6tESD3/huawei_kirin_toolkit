"""
Huawei Official Fastboot Binary Manager.
Auto-locates and injects official Huawei Fastboot (from HiSuite hwtools or hktool/bin)
into the system environment.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Optional

from ..config import FASTBOOT_BIN, BIN_DIR, HISUITE_HWTOOLS_DIR


class BinaryManager:
    """Manages official Huawei Fastboot executable and environment PATH injection."""

    _initialized: bool = False

    @classmethod
    def init_environment(cls) -> None:
        """Inject Huawei Fastboot directory into PATH."""
        if cls._initialized:
            return

        target_dir = FASTBOOT_BIN.parent
        if target_dir.exists():
            bin_str = str(target_dir.resolve())
            current_path = os.environ.get("PATH", "")
            if bin_str not in current_path:
                os.environ["PATH"] = bin_str + os.pathsep + current_path

        cls._initialized = True

    @classmethod
    def get_fastboot_path(cls) -> str:
        """Return absolute path to official Huawei fastboot executable."""
        cls.init_environment()
        if FASTBOOT_BIN.exists():
            return str(FASTBOOT_BIN.resolve())
        return shutil.which("fastboot") or "fastboot"
