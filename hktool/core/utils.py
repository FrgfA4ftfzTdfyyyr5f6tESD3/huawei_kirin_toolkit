"""
General utility functions, formatters, and progress monitors.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Callable, Optional


def human_size(size_bytes: int) -> str:
    """Format bytes into human-readable string (KB, MB, GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


class ProgressTracker:
    """Thread-safe progress monitor with speed calculation and ETA."""

    def __init__(self, total_bytes: int, unit_name: str = "bytes", callback: Optional[Callable[[int, int, float, float], None]] = None):
        self.total_bytes = total_bytes
        self.unit_name = unit_name
        self.callback = callback
        self.transferred = 0
        self.start_time = time.time()
        self.last_update = self.start_time

    def update(self, added_bytes: int) -> None:
        self.transferred += added_bytes
        now = time.time()
        elapsed = now - self.start_time
        speed = self.transferred / elapsed if elapsed > 0 else 0
        eta = (self.total_bytes - self.transferred) / speed if speed > 0 and self.total_bytes > self.transferred else 0
        
        if self.callback and (now - self.last_update >= 0.1 or self.transferred >= self.total_bytes):
            self.last_update = now
            self.callback(self.transferred, self.total_bytes, speed, eta)

    def print_progress(self, task_name: str = "Processing") -> None:
        now = time.time()
        elapsed = now - self.start_time
        speed = self.transferred / elapsed if elapsed > 0 else 0
        percent = (self.transferred * 100 / self.total_bytes) if self.total_bytes > 0 else 0
        
        sys.stdout.write(
            f"\r[{task_name}] {percent:5.1f}% | {human_size(self.transferred)} / {human_size(self.total_bytes)} | {human_size(int(speed))}/s"
        )
        sys.stdout.flush()
        if self.transferred >= self.total_bytes:
            sys.stdout.write("\n")
            sys.stdout.flush()


def copy_stream_chunked(
    src,
    dst,
    length: int,
    chunk_size: int = 4 * 1024 * 1024,
    progress_cb: Optional[Callable[[int], None]] = None
) -> int:
    """Stream data between file handles with progress callback."""
    remaining = length
    copied = 0
    while remaining > 0:
        to_read = min(chunk_size, remaining)
        buf = src.read(to_read)
        if not buf:
            break
        dst.write(buf)
        read_len = len(buf)
        copied += read_len
        remaining -= read_len
        if progress_cb:
            progress_cb(read_len)
    return copied
