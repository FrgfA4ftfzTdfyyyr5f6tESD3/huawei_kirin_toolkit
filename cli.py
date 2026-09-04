"""
Universal CLI interface for Huawei & Kirin Universal Toolkit.
Supports subcommands as well as a rich interactive terminal menu.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

from colorama import Fore, Style, init
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from hktool.config import HUAWEI_REGIONS, TOOL_NAME, TOOL_VERSION
from hktool.flashers.board_flasher import BoardSoftwareFlasher, BoardSoftwareParser
from hktool.flashers.sigma_board_writer import SigmaBoardWriter, WritePartitionItem
from hktool.kirin.chipsets import KIRIN_PROFILES
from hktool.nvme.nve_client import NveClient
from hktool.oeminfo.editor import OemInfoEditor
from hktool.kirin.kirin_710_protection import KIRIN_710_FASTBOOT_PATCHES, execute_kirin_710_fastboot_patches
from hktool.companions.companion_manager import CompanionManager
from hktool.cli_tools.headless_manager import HeadlessToolManager

init(autoreset=True)
console = Console()


def print_banner():
    banner = f"""[bold cyan]
=======================================================================
   H U A W E I   &   K I R I N   U N I V E R S A L   T O O L K I T
=======================================================================
    [/bold cyan]
    [bold yellow]{TOOL_NAME} v{TOOL_VERSION} (Clean Edition)[/bold yellow]
    [green]Tier 1: Native In-House Core | Tier 2: GUI Companions Launcher | Tier 3: Headless CLI & Writer[/green]
    """
    console.print(banner)


def cmd_detect():
    """Detect and display connected device status (Read Info)."""
    console.print("[bold yellow]Scanning for connected devices...[/bold yellow]")
    state = DeviceDetector.detect()
    table = Table(title="Device Status (Read Info)")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Connected", "YES" if state.is_connected else "NO")
    table.add_row("Mode", state.mode)
    table.add_row("Identifier / Port", state.identifier or "N/A")
    table.add_row("Details", state.details)
    console.print(table)


def cmd_kirin_710_protection():
    """Display Kirin 710 Fastboot memory write patch primitives."""
    console.print("[bold green]=== Kirin 710 Direct Fastboot Memory Patches ===[/bold green]")
    table = Table(title="Kirin 710 Fastboot Hardware Register Patches")
    table.add_column("Security Target", style="cyan")
    table.add_column("Fastboot Command", style="green")
    table.add_column("Function", style="yellow")
    for label, cmd, desc in KIRIN_710_FASTBOOT_PATCHES:
        table.add_row(label, f"fastboot oem {cmd}", desc)
    console.print(table)


def cmd_gui_companions():
    """List and manage standalone GUI companion tools without bundled binaries."""
    console.print("[bold magenta]=== Standalone GUI Companion Tools Launcher ===[/bold magenta]")
    console.print("[italic]Zero-Hosting Policy: Direct official developer releases & isolated execution.[/italic]")
    manager = CompanionManager()
    table = Table(title="Registered GUI Companions & Specialized Roles")
    table.add_column("#", style="cyan", width=3)
    table.add_column("Companion Tool", style="bold", width=22)
    table.add_column("Author", style="blue", width=14)
    table.add_column("Specialized Tasks (Primary Roles)", style="green")
    table.add_column("Status", style="yellow", width=16)

    items = manager.get_all()
    for idx, item in enumerate(items, 1):
        is_inst = manager.is_installed(item.id)
        status_str = "[green]Ready[/green]" if is_inst else "[red]Not Configured[/red]"
        tasks_bullets = "\n".join(f"* {t}" for t in item.tasks)
        if item.archive_password:
            tasks_bullets += f"\n[bold yellow](Password: {item.archive_password})[/bold yellow]"
        table.add_row(str(idx), item.name, item.author, tasks_bullets, status_str)
    console.print(table)


def cmd_sigma_writer(source_path_str: Optional[str] = None):
    """Execute Sigma & Board Software Partition Writer."""
    console.print("[bold blue]=== Sigma & Board Software Partition Writer ===[/bold blue]")
    if not source_path_str:
        source_path_str = input("Enter path to SigmaKey dump, Fastboot images folder, or Board Software XML: ").strip("\"' ")

    path = Path(source_path_str)
    if not path.exists():
        console.print(f"[red]Error: Path does not exist: {path}[/red]")
        return

    writer = SigmaBoardWriter()
    try:
        parts = writer.load_source(path)
        console.print(f"[bold green]Detected Format: {writer.source_type}[/bold green]")
        console.print(f"Loaded {len(parts)} partitions from source.\n")

        table = Table(title=f"Partitions in {path.name}")
        table.add_column("#", style="cyan", width=4)
        table.add_column("Partition Name", style="bold")
        table.add_column("Image File Name", style="green")
        table.add_column("Size", style="magenta")
        table.add_column("Format", style="yellow")
        for it in parts:
            table.add_row(str(it.index), it.name, it.file_path.name, it.size_human, it.format_source)
        console.print(table)

        confirm = input("\nDo you want to flash all loaded partitions via Fastboot? [y/N]: ").strip().lower()
        if confirm == "y":
            succ, fail = writer.flash_partitions(parts, on_log=lambda s: console.print(f"[cyan]{s}[/cyan]"))
            console.print(f"[bold green]Flashing Complete: {succ} succeeded, {fail} failed.[/bold green]")
    except Exception as ex:
        console.print(f"[bold red]Error: {ex}[/bold red]")


def interactive_menu():
    """Interactive text menu for user-friendly operation."""
    while True:
        print_banner()
        console.print("[bold cyan]Select an Operation:[/bold cyan]")
        console.print("  [bold green]--- 1. NATIVE IN-HOUSE CORE ---[/bold green]")
        console.print("  [1] 🛡️ Kirin 710 Write-Protection Hex Map & Exploit Vector")
        console.print("  [2] 🏷️ NVE / NVME Direct Calibration (Read/Write IMEI, MAC, SN, BSN)")
        console.print("  [3] 🌍 Dual SIM & OEMINFO Downgrade Patcher")
        console.print("  [bold magenta]--- 2. STANDALONE GUI COMPANIONS (LAUNCHER) ---[/bold magenta]")
        console.print("  [4] 🚀 GUI Companions Hub (Kirin-Tool, FastbootFlasher, Android Utility)")
        console.print("  [bold cyan]--- 3. PARTITION WRITER & DIAGNOSTICS ---[/bold cyan]")
        console.print("  [5] ⚡ Sigma & Board Software Partition Writer (Flash Sigma dumps, Fastboot & XML)")
        console.print("  [6] 🔍 Device Status & Read Info (Fastboot & USB Detection)")
        console.print("  [0] Exit")

        choice = input("\nEnter option [0-6]: ").strip()
        if choice == "0":
            console.print("[green]Goodbye![/green]")
            break
        elif choice == "1":
            cmd_kirin_710_protection()
            input("\nPress Enter to continue...")
        elif choice == "2":
            console.print("[cyan]Querying all NVE properties from device...[/cyan]")
            info = NveClient.read_all_properties()
            table = Table(title="NVE / Hardware Properties")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Serial Number (SN)", info.sn)
            table.add_row("IMEI", info.imei)
            table.add_row("IMEI2 / MEID", info.imei2)
            table.add_row("Wi-Fi MAC", info.wifi_mac)
            table.add_row("Bluetooth MAC", info.bt_mac)
            table.add_row("Board Serial (BSN)", info.bsn)
            table.add_row("Board ID", info.boardid)
            table.add_row("Vendor / Country", info.vendor_country)
            table.add_row("FBLOCK State", info.fblock_state)
            table.add_row("Factory Key (WVLOCK)", info.wvlock)
            console.print(table)

            write_q = input("\nDo you want to write an NVE property? [y/N]: ").strip().lower()
            if write_q == "y":
                prop = input("Enter property name (e.g. SN, IMEI, WIFI_MAC, BT_MAC, VENDOR_COUNTRY): ").strip()
                val = input(f"Enter new value for {prop}: ").strip()
                if prop and val:
                    ok, out = NveClient.write_variable(prop, val)
                    console.print(f"[bold green]Result: {out}[/bold green]")
            input("\nPress Enter to continue...")
        elif choice == "3":
            oem = input("Enter path to oeminfo.img / oeminfo.mbn: ").strip("\"' ")
            if not Path(oem).exists():
                console.print("[red]File not found![/red]")
            else:
                editor = OemInfoEditor(Path(oem))
                info = editor.get_device_info()
                table = Table(title="OEMINFO Details")
                for k, v in info.items():
                    table.add_row(k, v)
                console.print(table)
                rebrand_choice = input("\nDo you want to convert to Dual-SIM? [y/N]: ").strip().lower()
                if rebrand_choice == "y":
                    out_oem = input("Output image path [./oeminfo_dualsim.img]: ").strip("\"' ") or "./oeminfo_dualsim.img"
                    editor.rebrand(Path(out_oem), enable_dual_sim=True)
                    console.print(f"[bold green]Dual-SIM OEMINFO saved to {out_oem}[/bold green]")
            input("\nPress Enter to continue...")
        elif choice == "4":
            cmd_gui_companions()
            input("\nPress Enter to continue...")
        elif choice == "5":
            cmd_sigma_writer()
            input("\nPress Enter to continue...")
        elif choice == "6":
            cmd_detect()
            input("\nPress Enter to continue...")


def main():
    parser = argparse.ArgumentParser(description="Huawei & Kirin Universal Flash, Write & Diagnostics Toolkit")
    subparsers = parser.add_subparsers(dest="command")

    # Detect
    subparsers.add_parser("detect", help="Detect connected device mode and serial/port (Read Info)")

    # NVE Read/Write
    p_nve_r = subparsers.add_parser("nve-read", help="Read all NVE / calibration variables")
    p_nve_w = subparsers.add_parser("nve-write", help="Write an NVE variable")
    p_nve_w.add_argument("name", help="Variable name (e.g. SN, IMEI, WIFI_MAC, VENDOR_COUNTRY)")
    p_nve_w.add_argument("value", help="New value")

    # Kirin 710 Protection
    subparsers.add_parser("kirin710-protect", help="Inspect Kirin 710 memory map and BootROM exploit frame")

    # Companions
    subparsers.add_parser("companions", help="List registered standalone GUI companion tools")

    # Sigma & Board Writer
    p_sw = subparsers.add_parser("write-partitions", help="Flash partitions from SigmaKey dump, Fastboot folder, or Board XML")
    p_sw.add_argument("path", help="Path to SigmaKey dump, Fastboot folder, or Board Software XML")

    args = parser.parse_args()
    if not args.command:
        interactive_menu()
    elif args.command == "detect":
        cmd_detect()
    elif args.command == "kirin710-protect":
        cmd_kirin_710_protection()
    elif args.command == "companions":
        cmd_gui_companions()
    elif args.command == "write-partitions":
        cmd_sigma_writer(args.path)
    elif args.command == "nve-read":
        info = NveClient.read_all_properties()
        print(f"SN: {info.sn}\nIMEI: {info.imei}\nWIFI_MAC: {info.wifi_mac}\nBT_MAC: {info.bt_mac}\nBSN: {info.bsn}\nVENDOR_COUNTRY: {info.vendor_country}\nFBLOCK: {info.fblock_state}\nWVLOCK: {info.wvlock}")
    elif args.command == "nve-write":
        ok, out = NveClient.write_variable(args.name, args.value)
        print(f"Response: {out}")


if __name__ == "__main__":
    main()
