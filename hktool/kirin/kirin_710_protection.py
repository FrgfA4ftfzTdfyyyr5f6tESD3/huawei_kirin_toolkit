"""
Native In-House Core: Kirin 710 Write-Protection & Memory Patch Engine.
Direct volatile hardware security register bypass in Fastboot Mode for HiSilicon Kirin 710 / 710F.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Tuple

# Direct Kirin 710 Fastboot hardware memory patch commands
KIRIN_710_FASTBOOT_PATCHES: List[Tuple[str, str, str]] = [
    ("NVME Protection Bypass", "write@0x3C3E4ED8@0x3C001364", "Disables NVME hardware write lock in memory"),
    ("Certification Validation Bypass", "write@0x3C3EC1F0@0x3C001364", "Bypasses certificate security validation token"),
    ("HDCP Protection Register", "write@0x3C412344@0x00000001", "Initializes HDCP DRM hardware register"),
]


def execute_kirin_710_fastboot_patches(
    fastboot_bin: Path,
    on_log: Callable[[str], None]
) -> Tuple[int, int]:
    """
    Executes the 3 official Fastboot memory patches for Kirin 710 sequentially:
    1. fastboot oem write@0x3C3E4ED8@0x3C001364
    2. fastboot oem write@0x3C3EC1F0@0x3C001364
    3. fastboot oem write@0x3C412344@0x00000001
    Returns: (success_count, fail_count)
    """
    import subprocess
    fb_exe = str(fastboot_bin) if fastboot_bin.is_file() else "fastboot"
    success_count = 0
    fail_count = 0

    on_log("⚡ Executing Kirin 710 Direct Fastboot Memory Patches...\n")
    for idx, (label, cmd_arg, desc) in enumerate(KIRIN_710_FASTBOOT_PATCHES, 1):
        full_cmd = [fb_exe, "oem", cmd_arg]
        cmd_str = f"fastboot oem {cmd_arg}"
        on_log(f"[{idx}/3] {label}: {cmd_str}")
        on_log(f"      Description: {desc}")
        try:
            res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=10)
            out = (res.stdout + "\n" + res.stderr).strip()
            if out:
                for line in out.splitlines():
                    on_log(f"      > {line}")

            if res.returncode == 0 or "OKAY" in out:
                on_log(f"      ✔ {label} applied successfully.\n")
                success_count += 1
            else:
                on_log(f"      ❌ {label} returned non-zero code ({res.returncode})\n")
                fail_count += 1
        except Exception as e:
            on_log(f"      ❌ Execution failed: {e}\n")
            fail_count += 1

    on_log(f"🏁 Patch Results: {success_count} Succeeded, {fail_count} Failed.\n")
    return success_count, fail_count
