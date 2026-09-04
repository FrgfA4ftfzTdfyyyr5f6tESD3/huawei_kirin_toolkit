"""
Headless CLI Utilities Engine.
Orchestrates open-source command-line tools (MIT, GPL, Apache):
- Official GitHub repository and releases navigation.
- Real-time process execution with streaming pipe redirection to the toolkit's embedded console.
- Clean process lifecycle management (start, stream, terminate).
"""
from __future__ import annotations

import os
import subprocess
import threading
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


@dataclass
class HeadlessToolItem:
    id: str
    name: str
    license_type: str
    github_url: str
    releases_url: str
    description: str
    is_python_native: bool = False
    binary_path: Optional[str] = None


DEFAULT_HEADLESS_TOOLS: List[HeadlessToolItem] = [
    HeadlessToolItem(
        id="huawei_oeminfo_tool",
        name="huawei-oeminfo-tool",
        license_type="MIT License",
        github_url="https://github.com/ud3v0id/huawei-oeminfo-tool",
        releases_url="https://github.com/ud3v0id/huawei-oeminfo-tool/archive/refs/heads/main.zip",
        description="Official open-source OEMINFO parsing, unpacking, and packing engine for Huawei EMUI & MagicOS devices by ud3v0id.",
        is_python_native=True,
    ),
]


class HeadlessToolManager:
    """Manages open-source CLI utilities and streams their execution to the embedded console."""

    def __init__(self):
        self.items: Dict[str, HeadlessToolItem] = {item.id: item for item in DEFAULT_HEADLESS_TOOLS}
        self.active_processes: Dict[str, subprocess.Popen] = {}

    def get_all(self) -> List[HeadlessToolItem]:
        return list(self.items.values())

    def get_item(self, tool_id: str) -> Optional[HeadlessToolItem]:
        return self.items.get(tool_id)

    def open_github(self, tool_id: str) -> bool:
        item = self.items.get(tool_id)
        if item and item.github_url:
            webbrowser.open(item.github_url)
            return True
        return False

    def open_releases(self, tool_id: str) -> bool:
        item = self.items.get(tool_id)
        if item and item.releases_url:
            webbrowser.open(item.releases_url)
            return True
        return False

    def run_streaming_command(
        self,
        cmd_args: List[str],
        cwd: Optional[str] = None,
        job_id: str = "cli_job",
        on_output_line: Optional[Callable[[str], None]] = None,
        on_completed: Optional[Callable[[int], None]] = None,
    ) -> threading.Thread:
        """
        Execute command asynchronously while streaming stdout and stderr line-by-line
        into the supplied callback.
        """
        def _worker():
            try:
                proc = subprocess.Popen(
                    cmd_args,
                    cwd=cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                self.active_processes[job_id] = proc

                if on_output_line:
                    on_output_line(f"[*] Started: {' '.join(cmd_args)}\n")

                for line in iter(proc.stdout.readline, ""):
                    if on_output_line:
                        on_output_line(line)

                proc.stdout.close()
                return_code = proc.wait()
                if on_output_line:
                    on_output_line(f"[*] Process exited with return code: {return_code}\n")
                if on_completed:
                    on_completed(return_code)
            except Exception as ex:
                if on_output_line:
                    on_output_line(f"[!] Execution failed: {ex}\n")
                if on_completed:
                    on_completed(-1)
            finally:
                self.active_processes.pop(job_id, None)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        return thread

    def cancel_job(self, job_id: str) -> bool:
        """Terminate a running CLI job."""
        proc = self.active_processes.get(job_id)
        if proc:
            try:
                proc.terminate()
                return True
            except Exception:
                pass
        return False
