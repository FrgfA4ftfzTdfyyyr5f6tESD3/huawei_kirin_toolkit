"""
Huawei IDT (Image Download Tool) Board Software XML Parser and Flasher.
Parses Board Software download XML, executes partition erase commands, and flashes images via Fastboot with Smart Chunking.
"""
from __future__ import annotations

import os
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from ..core.exceptions import FastbootError, FirmwareFormatError
from ..core.utils import human_size


@dataclass
class BoardImageItem:
    name: str
    identifier: str
    address: str
    rel_path: str
    resolved_path: Optional[Path] = None


@dataclass
class BoardCmdItem:
    cmd_type: str
    command: str
    identifier: str
    rel_path: str
    resolved_path: Optional[Path] = None
    req: str = ""
    resp: str = ""


@dataclass
class BoardConfig:
    ap_platform: str
    product_id: str
    version: str
    bootloader_images: List[BoardImageItem]
    erase_images: List[BoardImageItem]
    fastboot_images: List[BoardImageItem]
    partially_erase_commands: List[BoardCmdItem]
    customize_erase_commands: List[BoardCmdItem]
    totally_erase_commands: List[BoardCmdItem]


class BoardSoftwareParser:
    """Parses official Huawei IDT Board Software XML configuration files."""

    @staticmethod
    def parse_xml(xml_path: Path) -> BoardConfig:
        if not xml_path.exists():
            raise FirmwareFormatError(f"Board Software XML not found: {xml_path}")

        raw_bytes = xml_path.read_bytes()
        try:
            raw_text = raw_bytes.decode("gb2312", errors="replace")
        except Exception:
            raw_text = raw_bytes.decode("utf-8", errors="replace")

        clean_xml = re.sub(r'<\?xml.*?\?>', '', raw_text, flags=re.DOTALL).strip()
        root = ET.fromstring(clean_xml)

        cfg_elem = root.find("configuration")
        if cfg_elem is None:
            raise FirmwareFormatError("Invalid Board Software XML: missing <configuration> element")

        ap_platform = cfg_elem.attrib.get("ap_platform", "unknown")
        product_id = cfg_elem.attrib.get("product_id", "unknown")
        version = cfg_elem.attrib.get("version", "unknown")

        xml_dir = xml_path.parent

        def resolve_file(rel_p: str) -> Optional[Path]:
            if not rel_p:
                return None
            candidate1 = xml_dir / rel_p
            candidate2 = xml_dir / Path(rel_p).name
            candidate3 = xml_dir / "fastbootimage" / Path(rel_p).name
            candidate4 = xml_dir / "bootloaderimage" / Path(rel_p).name
            if candidate1.exists():
                return candidate1
            if candidate2.exists():
                return candidate2
            if candidate3.exists():
                return candidate3
            if candidate4.exists():
                return candidate4
            return None

        def extract_items(section_tag: str) -> List[BoardImageItem]:
            items = []
            sec = cfg_elem.find(section_tag)
            if sec is not None:
                for img in sec.findall("image"):
                    name = img.attrib.get("name", "")
                    ident = img.attrib.get("identifier", name.lower())
                    addr = img.attrib.get("address", "0xFFFFFFFF")
                    rel_p = (img.text or "").strip().replace("\\", "/")
                    resolved = resolve_file(rel_p)

                    items.append(BoardImageItem(
                        name=name,
                        identifier=ident,
                        address=addr,
                        rel_path=rel_p,
                        resolved_path=resolved
                    ))
            return items

        def extract_commands(section_tag: str) -> List[BoardCmdItem]:
            cmds = []
            sec = cfg_elem.find(section_tag)
            if sec is not None:
                for cmd in sec.findall("cmd"):
                    c_type = cmd.attrib.get("type", "fastboot")
                    command = cmd.attrib.get("command", "")
                    ident = cmd.attrib.get("identifier", "")
                    rel_p = (cmd.text or "").strip().replace("\\", "/")
                    req = cmd.attrib.get("req", "")
                    resp = cmd.attrib.get("resp", "")
                    resolved = resolve_file(rel_p) if rel_p else None

                    cmds.append(BoardCmdItem(
                        cmd_type=c_type,
                        command=command,
                        identifier=ident,
                        rel_path=rel_p,
                        resolved_path=resolved,
                        req=req,
                        resp=resp
                    ))
            return cmds

        return BoardConfig(
            ap_platform=ap_platform,
            product_id=product_id,
            version=version,
            bootloader_images=extract_items("bootloaderimage"),
            erase_images=extract_items("eraseimage"),
            fastboot_images=extract_items("fastbootimage"),
            partially_erase_commands=extract_commands("partially_erase_configuration"),
            customize_erase_commands=extract_commands("customize_erase_configuration"),
            totally_erase_commands=extract_commands("totally_erase_configuration")
        )


class BoardSoftwareFlasher:
    """Executes Board Software flash operations in Factory Fastboot mode."""

    def __init__(self, fastboot_flasher: Optional[FastbootFlasher] = None):
        self.flasher = fastboot_flasher or FastbootFlasher()

    def flash_board_software(
        self,
        xml_path: Path,
        selected_identifiers: Optional[List[str]] = None,
        selected_erase_identifiers: Optional[List[str]] = None,
        enable_erase: bool = True,
        erase_partitions: bool = True,
        on_status: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[float], None]] = None
    ) -> bool:
        """Parse XML and execute all board software commands and images sequentially via Fastboot."""
        config = BoardSoftwareParser.parse_xml(xml_path)

        if on_status:
            on_status(f"Parsed Board Software: Platform={config.ap_platform}, Product={config.product_id}, Version={config.version}")

        # If XML contains official partially_erase_configuration, execute in exact factory sequence!
        if config.partially_erase_commands:
            commands_to_run: List[BoardCmdItem] = []
            pending_crc: Optional[BoardCmdItem] = None
            for cmd in config.partially_erase_commands:
                c_name = cmd.command.lower()
                if c_name == "flash":
                    if cmd.identifier == "huawei_crc_check":
                        pending_crc = cmd
                        continue

                    is_selected = selected_identifiers is None or cmd.identifier in selected_identifiers
                    if is_selected:
                        if pending_crc is not None:
                            commands_to_run.append(pending_crc)
                        commands_to_run.append(cmd)
                    pending_crc = None

                elif c_name in ("erase", "oem", "reboot-bootloader", "reboot"):
                    if enable_erase:
                        is_match = (
                            selected_erase_identifiers is None or
                            cmd.identifier in selected_erase_identifiers or
                            c_name in selected_erase_identifiers or
                            f"{c_name}:{cmd.identifier}" in selected_erase_identifiers
                        )
                        if is_match:
                            commands_to_run.append(cmd)

            total_cmds = len(commands_to_run)
            if on_status:
                on_status(f"Executing official Factory IDT Sequence ({total_cmds} sequential operations)...")

            for idx, cmd in enumerate(commands_to_run, start=1):
                if on_progress:
                    on_progress(idx / total_cmds)

                if cmd.cmd_type.lower() == "fastboot":
                    c_name = cmd.command.lower()
                    ident = cmd.identifier

                    if c_name == "flash":
                        if ident == "huawei_crc_check":
                            # CRC checks are official factory hardware validations; flash with huawei_crc_check
                            if cmd.resolved_path and cmd.resolved_path.exists():
                                if on_status:
                                    on_status(f"[{idx}/{total_cmds}] 🛡️ Flashing CRC check [{ident}] from {cmd.resolved_path.name}...")
                                self.flasher.flash_partition("huawei_crc_check", cmd.resolved_path, on_status=on_status)
                            else:
                                if on_status:
                                    on_status(f"[{idx}/{total_cmds}] ⚠️ Skipping CRC check [{ident}]: '{cmd.rel_path}' not found.")
                            continue

                        if cmd.resolved_path and cmd.resolved_path.exists():
                            if on_status:
                                on_status(f"[{idx}/{total_cmds}] ⚡ Flashing [{ident}] from {cmd.resolved_path.name} ({human_size(cmd.resolved_path.stat().st_size)})...")
                            self.flasher.flash_partition(ident, cmd.resolved_path, on_status=on_status)
                        else:
                            if on_status:
                                on_status(f"[{idx}/{total_cmds}] ⚠️ Skipping flash [{ident}]: Image file '{cmd.rel_path}' not found on disk.")

                    elif c_name == "erase":
                        if on_status:
                            on_status(f"[{idx}/{total_cmds}] 🗑️ Erasing partition [{ident}]...")
                        subprocess.run(["fastboot", "erase", ident], capture_output=True, text=True)

                    elif c_name == "oem":
                        if on_status:
                            on_status(f"[{idx}/{total_cmds}] ⚙️ Executing OEM command [fastboot oem {ident}]...")
                        subprocess.run(["fastboot", "oem", ident], capture_output=True, text=True)

                    elif c_name == "reboot-bootloader":
                        if on_status:
                            on_status(f"[{idx}/{total_cmds}] 🔄 Rebooting Bootloader [fastboot reboot-bootloader]...")
                        subprocess.run(["fastboot", "reboot-bootloader"], capture_output=True, text=True)
                        import time
                        time.sleep(3)

                    elif c_name == "reboot":
                        if on_status:
                            on_status(f"[{idx}/{total_cmds}] 🔄 Rebooting Device [fastboot reboot]...")
                        subprocess.run(["fastboot", "reboot"], capture_output=True, text=True)

            if on_status:
                on_status("✔ Official Factory Board Software IDT Sequence completed successfully!")
            return True

        # Fallback: standard separate erase + sequential flash
        # 1. Erase partitions if requested
        if enable_erase and erase_partitions and config.erase_images:
            erases_to_run = [item for item in config.erase_images if selected_erase_identifiers is None or item.identifier in selected_erase_identifiers]
            if on_status:
                on_status(f"Erasing {len(erases_to_run)} factory partitions...")
            for item in erases_to_run:
                ident = item.identifier
                if on_status:
                    on_status(f"Erasing partition: {ident}...")
                subprocess.run(["fastboot", "erase", ident], capture_output=True, text=True)

        # 2. Flash fastboot images in sequential order
        flash_queue = []
        for item in config.fastboot_images:
            if item.identifier == "huawei_crc_check" or item.name.endswith("_CRC"):
                continue
            if selected_identifiers is not None and item.identifier not in selected_identifiers:
                continue
            if item.resolved_path and item.resolved_path.exists():
                flash_queue.append((item.identifier, item.resolved_path))

        if on_status:
            on_status(f"Starting flash for {len(flash_queue)} valid partition images...")

        total = len(flash_queue)
        for idx, (part_ident, img_p) in enumerate(flash_queue, start=1):
            if on_status:
                on_status(f"[{idx}/{total}] Flashing {part_ident} from {img_p.name} ({human_size(img_p.stat().st_size)})...")

            self.flasher.flash_partition(part_ident, img_p, on_status=on_status)
            if on_progress:
                on_progress(idx / total)

        if on_status:
            on_status("✔ Board Software flashing completed successfully!")

        return True
