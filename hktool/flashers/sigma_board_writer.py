"""
Sigma & Board Software Partition Writer.
Unified multi-format partition flashing engine supporting:
1. SigmaKey Dump Backups (*.skd, partition binary dumps, manifest)
2. Factory Fastboot packages (*.img raw partition images)
3. Board Software / IDT XML packages (Download.xml, fastboot.xml)
"""
from __future__ import annotations

import os
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from ..config import FASTBOOT_BIN
from ..core.utils import human_size


@dataclass
class WritePartitionItem:
    index: int
    name: str
    file_path: Path
    size_bytes: int
    format_source: str  # "SigmaKey Dump", "Factory Fastboot", "Board Software"
    is_selected: bool = True
    status: str = "Ready"  # "Ready", "Flashing", "Success", "Failed", "Skipped"

    @property
    def size_human(self) -> str:
        return human_size(self.size_bytes)


class SigmaBoardWriter:
    """Unified partition flasher for SigmaKey Dumps, Factory Fastboot & Board Software."""

    def __init__(self):
        self.partitions: List[WritePartitionItem] = []
        self.source_path: Optional[Path] = None
        self.source_type: str = "Unknown"

    def load_source(self, path: Path) -> List[WritePartitionItem]:
        """
        Auto-detect format and load partitions from file or directory:
        1. SigmaKey Dump Backups
        2. Factory Fastboot Images
        3. Board Software / IDT XML
        """
        self.partitions.clear()
        self.source_path = path

        if not path.exists():
            raise FileNotFoundError(f"Source path does not exist: {path}")

        # Case A: Board Software XML
        if path.is_file() and path.suffix.lower() == ".xml":
            self.source_type = "Board Software (IDT XML)"
            self.partitions = self._parse_board_xml(path)
            return self.partitions

        # If it's a directory, inspect contents
        if path.is_dir():
            # Check for Board XML inside directory
            xml_files = list(path.glob("*[Dd]ownload*.xml")) + list(path.glob("*fastboot*.xml")) + list(path.glob("*.xml"))
            if xml_files:
                self.source_type = "Board Software (IDT Package)"
                self.partitions = self._parse_board_xml(xml_files[0])
                if self.partitions:
                    return self.partitions

            # Check for SigmaKey dumps (*.skd or partitions.txt)
            skd_files = list(path.glob("*.skd"))
            sig_txt = list(path.glob("*partition*.txt")) + list(path.glob("*sigma*.txt"))
            if skd_files or sig_txt:
                self.source_type = "SigmaKey Dump Backup"
                self.partitions = self._parse_sigma_dump(path)
                if self.partitions:
                    return self.partitions

            # Fallback to Factory Fastboot (.img files)
            img_files = list(path.glob("*.img")) + list(path.glob("*.bin"))
            if img_files:
                self.source_type = "Factory Fastboot Package"
                self.partitions = self._parse_fastboot_images(path)
                return self.partitions

        # If single file is .img or .bin
        if path.is_file() and path.suffix.lower() in [".img", ".bin", ".skd"]:
            self.source_type = "Single Partition Image"
            p_name = path.stem.lower().replace(".skd", "")
            self.partitions.append(
                WritePartitionItem(
                    index=1,
                    name=p_name,
                    file_path=path,
                    size_bytes=path.stat().st_size,
                    format_source="Direct Image",
                    is_selected=True,
                )
            )
            return self.partitions

        raise ValueError("Unsupported format. Please select a SigmaKey dump folder, Factory Fastboot folder, or Board Software XML.")

    def _parse_board_xml(self, xml_path: Path) -> List[WritePartitionItem]:
        items: List[WritePartitionItem] = []
        base_dir = xml_path.parent
        raw_bytes = xml_path.read_bytes()
        try:
            raw_text = raw_bytes.decode("gb2312", errors="replace")
        except Exception:
            raw_text = raw_bytes.decode("utf-8", errors="replace")

        clean_xml = re.sub(r'<\?xml.*?\?>', '', raw_text, flags=re.DOTALL).strip()
        root = ET.fromstring(clean_xml)

        idx = 1
        # Search for both <IMAGE> and <image> elements
        found_elements = root.findall(".//IMAGE") + root.findall(".//image")
        for img in found_elements:
            name = img.get("name", "").strip() or img.get("id", "").strip() or img.get("identifier", "").strip()
            path_str = (
                img.get("path", "").strip()
                or img.get("file", "").strip()
                or img.get("filename", "").strip()
                or (img.text or "").strip()
            )
            if not path_str or path_str.startswith("<"):
                continue

            target_file = (base_dir / path_str).resolve()
            if not target_file.exists():
                fn = Path(path_str).name
                matches = list(base_dir.rglob(fn))
                if matches:
                    target_file = matches[0]

            sz = target_file.stat().st_size if target_file.exists() else 0
            items.append(
                WritePartitionItem(
                    index=idx,
                    name=name if name else target_file.stem,
                    file_path=target_file,
                    size_bytes=sz,
                    format_source="Board Software",
                    is_selected=True,
                    status="Ready" if target_file.exists() else "File Missing"
                )
            )
            idx += 1

        # Fallback to BoardSoftwareParser if standard IDT configuration format
        if not items:
            try:
                from .board_flasher import BoardSoftwareParser
                cfg = BoardSoftwareParser.parse_xml(xml_path)
                all_board_imgs = cfg.bootloader_images + cfg.erase_images + cfg.fastboot_images
                for b_img in all_board_imgs:
                    p_file = b_img.resolved_path or (base_dir / b_img.rel_path)
                    sz = p_file.stat().st_size if p_file.exists() else 0
                    items.append(
                        WritePartitionItem(
                            index=idx,
                            name=b_img.name or b_img.identifier,
                            file_path=p_file,
                            size_bytes=sz,
                            format_source="IDT XML Config",
                            is_selected=True,
                            status="Ready" if p_file.exists() else "File Missing"
                        )
                    )
                    idx += 1
            except Exception:
                pass

        return items

    def _parse_sigma_dump(self, dump_dir: Path) -> List[WritePartitionItem]:
        items: List[WritePartitionItem] = []
        idx = 1
        for f in sorted(list(dump_dir.glob("*.skd")) + list(dump_dir.glob("*.bin")) + list(dump_dir.glob("*.img"))):
            if f.name.lower() in ["partitions.txt", "manifest.json", "log.txt"]:
                continue
            name = f.stem.lower()
            name = re.sub(r'_dump$', '', name)
            name = re.sub(r'\.skd$', '', name)

            items.append(
                WritePartitionItem(
                    index=idx,
                    name=name,
                    file_path=f,
                    size_bytes=f.stat().st_size,
                    format_source="SigmaKey Dump",
                    is_selected=True,
                    status="Ready"
                )
            )
            idx += 1
        return items

    def _parse_fastboot_images(self, img_dir: Path) -> List[WritePartitionItem]:
        items: List[WritePartitionItem] = []
        idx = 1
        for f in sorted(list(img_dir.glob("*.img")) + list(img_dir.glob("*.bin"))):
            name = f.stem.lower()
            items.append(
                WritePartitionItem(
                    index=idx,
                    name=name,
                    file_path=f,
                    size_bytes=f.stat().st_size,
                    format_source="Factory Fastboot",
                    is_selected=True,
                    status="Ready"
                )
            )
            idx += 1
        return items

    def validate_integrity(self, items: List[WritePartitionItem]) -> Tuple[bool, List[str]]:
        """Validate partition files existence and non-zero size before flashing."""
        errors: List[str] = []
        for it in items:
            if not it.file_path.exists():
                errors.append(f"Missing file for {it.name}: {it.file_path.name}")
            elif it.size_bytes == 0:
                errors.append(f"Empty partition image (0 bytes) for {it.name}")
        return len(errors) == 0, errors

    def flash_partitions(
        self,
        items: List[WritePartitionItem],
        on_log: Callable[[str], None],
        on_progress: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> Tuple[int, int]:
        """
        Sequentially flashes the specified partitions via Fastboot with real-time log streaming.
        Returns: (success_count, fail_count)
        """
        fb_exe = str(FASTBOOT_BIN) if FASTBOOT_BIN.exists() else "fastboot"
        success_count = 0
        fail_count = 0
        total = len(items)

        on_log(f"⚡ Starting Fastboot Partition Writer: {total} partitions queued for flashing.\n")

        for idx, item in enumerate(items, 1):
            if cancel_check and cancel_check():
                on_log("⚠️ Flashing process cancelled by user.\n")
                break

            item.status = "Flashing..."
            if on_progress:
                on_progress(idx, total)

            on_log(f"[{idx}/{total}] Flashing {item.name} ({item.size_human}) from {item.file_path.name}...")

            if not item.file_path.exists():
                item.status = "Failed"
                fail_count += 1
                on_log(f"  ❌ Error: File not found: {item.file_path}\n")
                continue

            try:
                cmd = [fb_exe, "flash", item.name, str(item.file_path)]
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                for line in iter(proc.stdout.readline, ''):
                    if line:
                        on_log(f"    {line.strip()}")

                proc.stdout.close()
                proc.wait()

                if proc.returncode == 0:
                    item.status = "Success"
                    success_count += 1
                    on_log(f"  ✔ {item.name} flashed successfully.\n")
                else:
                    item.status = "Failed"
                    fail_count += 1
                    on_log(f"  ❌ Fastboot flash failed for {item.name} (exit code: {proc.returncode})\n")

            except Exception as e:
                item.status = "Failed"
                fail_count += 1
                on_log(f"  ❌ Execution Error flashing {item.name}: {e}\n")

        on_log("═══════════════════════════════════════════════════════════════════")
        on_log(f"🏁 Flashing Summary: {success_count} Succeeded, {fail_count} Failed.")
        on_log("═══════════════════════════════════════════════════════════════════\n")
        return success_count, fail_count
