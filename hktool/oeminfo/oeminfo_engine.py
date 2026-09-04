"""
oeminfo_tool.py - Tool for parsing, packing, and managing HUAWEI/HONOR OEMINFO image files.

This tool provides a set of functionalities including:
- `list`: Lists all data blocks within an OEMINFO image without actual extraction.
- `unpack`: Unpacks an OEMINFO image into a specified directory, extracting data blocks and metadata.
- `repack`: Repacks content from an unpacked directory (including manifest.json and data files) back into an OEMINFO image file.

Author: ud3v0id
"""

import struct
import os
import json
import argparse
import mmap
import collections
import math
from typing import List, Dict, Optional, Tuple, Union, BinaryIO, Any

# --- Configuration Constants ---
# Default input OEMINFO image file path.
DEFAULT_FILE_PATH = "oeminfo.img"
# Default output directory path for unpacked files.
DEFAULT_OUTPUT_DIR = "oeminfo_extracted"
# Size of each OEMINFO region (e.g., A/B regions), 32MB in this case.
REGION_SIZE = 0x2000000  # 32MB
# Total size of combined A and B regions.
TOTAL_REGION_SIZE = REGION_SIZE * 2
# Version number of the tool.
VERSION = "1.0.1"
# Default padding byte used whenever actual padding contents are unknown or mixed.
DEFAULT_PADDING_BYTE = 0x00

# Mapping between padding bytes and compact profile symbols.
# Profile strings store counts in decimal followed by an uppercase symbol.
# Example: "12Z3F" = 12 chunks of 0x00 + 3 chunks of 0xFF (chunk = 0x80 bytes).
PROFILE_BYTE_SYMBOLS = {
    0x00: 'Z',
    0xFF: 'F'
}
PROFILE_SYMBOL_TO_BYTE = {sym.lower(): val for val, sym in PROFILE_BYTE_SYMBOLS.items()}
HIGH_ENTROPY_THRESHOLD = 7.5

# Pre-compiled struct formats for performance
# Standard Block Header: Magic(8s), Ver(I), ID(I), SubID(I), Len(I), Age(I), Padding(I)
BLOCK_HEADER_STRUCT = struct.Struct('<8sIIIIII')
# Image Header Start: StartOffset(I), EndOffset(I), RandAdjust(I)
IMAGE_HEADER_PREFIX_STRUCT = struct.Struct('<III')
# Image Header Full (for packing): Start(I), End(I), Rand(I), Ver(12s)
IMAGE_HEADER_PACK_STRUCT = struct.Struct('<III12s')


def is_safe_path(base_dir: str, target_path: str) -> bool:
    """
    Ensures that the target path (relative to base_dir) resolves to a location
    inside the base directory, preventing path traversal attacks.
    """
    # Resolve the base directory to an absolute path.
    abs_base = os.path.abspath(base_dir)
    # Join and resolve the target path.
    abs_target = os.path.abspath(os.path.join(base_dir, target_path))
    # Check if the target path starts with the base path.
    return os.path.commonpath([abs_base, abs_target]) == abs_base


def _decode_profile_symbol(symbol: str) -> int:
    """
    Converts a profile symbol (e.g., 'Z'/'F') into the corresponding padding byte.
    """
    val = PROFILE_SYMBOL_TO_BYTE.get(symbol.lower())
    if val is None:
        raise ValueError(f"Unknown padding profile symbol '{symbol}'.")
    return val


def _profile_string_length(profile: str, chunk_size: int = 0x80) -> int:
    """
    Calculates total byte length represented by a compact padding profile string.
    """
    profile = (profile or "").strip()
    if not profile:
        return 0
    count_buffer = ""
    total = 0
    for ch in profile:
        if ch.isdigit():
            count_buffer += ch
            continue
        if not count_buffer:
            raise ValueError("Padding profile missing count before symbol.")
        total += int(count_buffer, 10) * chunk_size
        count_buffer = ""
    if count_buffer:
        raise ValueError("Padding profile missing symbol for trailing count.")
    return total


def _expand_profile_segments(profile: str, start_offset: int, chunk_size: int = 0x80) -> List[Dict[str, int]]:
    """
    Expands a compact profile string into concrete segments beginning at start_offset.
    """
    profile = (profile or "").strip()
    if not profile:
        return []
    cursor = start_offset
    count_buffer = ""
    segments: List[Dict[str, int]] = []
    for ch in profile:
        if ch.isdigit():
            count_buffer += ch
            continue
        if not count_buffer:
            raise ValueError("Padding profile missing count before symbol.")
        seg_len = int(count_buffer, 10) * chunk_size
        count_buffer = ""
        segments.append({
            "start": cursor,
            "length": seg_len,
            "byte": _decode_profile_symbol(ch)
        })
        cursor += seg_len
    if count_buffer:
        raise ValueError("Padding profile missing symbol for trailing count.")
    return segments


def _write_profile_segments(
    outfile: BinaryIO,
    segments: List[Dict[str, int]],
    skip: int,
    length: int
) -> int:
    """
    Writes padding bytes described by expanded profile segments.
    """
    if length <= 0:
        return 0
    remaining = length
    skipped = skip
    for seg in segments:
        seg_len = seg.get("length", 0)
        if skipped >= seg_len:
            skipped -= seg_len
            continue
        local_start = skipped
        seg_available = seg_len - local_start
        write_len = min(seg_available, remaining)
        if write_len > 0:
            byte_val = seg.get("byte", DEFAULT_PADDING_BYTE) & 0xFF
            chunk = bytes([byte_val]) * min(write_len, 1024 * 1024)
            written = 0
            while written < write_len:
                to_write = min(write_len - written, len(chunk))
                outfile.write(chunk[:to_write])
                written += to_write
        remaining -= write_len
        skipped = 0
        if remaining <= 0:
            break
    if remaining > 0:
        raise ValueError("Padding profile shorter than required write length.")
    return length


class CliLogger:
    """
    Simple logger that keeps logging style consistent across commands and classes.
    """
    def __init__(self, debug: bool = False, silent: bool = False):
        self._debug_enabled = debug
        self._silent = silent

    def info(self, message: str) -> None:
        if self._silent:
            return
        add_prefix = self._debug_enabled and not message.startswith("[INFO]")
        prefix = "[INFO] " if add_prefix else ""
        print(f"{prefix}{message}")

    def warn(self, message: str) -> None:
        if self._silent:
            return
        prefix = "[WARN]" if self._debug_enabled else "Warning:"
        print(f"{prefix} {message}")

    def debug(self, message: str) -> None:
        if self._silent or not self._debug_enabled:
            return
        print(f"[DEBUG] {message}")

    def error(self, message: str) -> None:
        if self._silent:
            return
        print(f"Error: {message}")

class OemUnpacker:
    """
    Handles parsing OEMINFO image files, extracting their contents, and generating a manifest.json
    file for repacking. It processes various types of data blocks, including standard blocks,
    reused blocks, images (GZIP/BMP), TLV (Type-Length-Value) structures, and raw binary data.
    """
    def __init__(self, file_path: str, output_dir: str, dry_run: bool = False, debug: bool = False, logger: Optional[CliLogger] = None):
        """
        Initializes an OemUnpacker instance.

        Args:
            file_path (str): Path to the OEMINFO image file to process.
            output_dir (str): Path to the directory where unpacked files will be stored.
            dry_run (bool): If True, no file system write operations will be performed,
                            only information will be printed.
        """
        self.file_path: str = file_path
        self.output_dir: str = output_dir
        self.dry_run: bool = dry_run
        self.debug: bool = debug
        self.logger: CliLogger = logger or CliLogger(debug)
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File '{file_path}' not found.")
        
        self.file_size: int = os.path.getsize(file_path)
        self.headers: List[Dict] = []  # Stores information about all detected block headers.
        # Stores metadata for the unpacking process, including region sizing details
        # and detailed information for all data blocks.
        self.manifest: Dict = {
            "region_size": REGION_SIZE,
            "file_size": self.file_size,
            "blocks": []
        }
        self._layout_finalized: bool = False
        self._layout_entries: List[Dict] = []
        # Stores the list of data blocks awaiting processing (classification and extraction).
        self.processing_queue: List[Dict] = []
        
        # Pre-compile ASCII character sets for performance.
        # Strict ASCII: 0x20-0x7E (printable characters), 0x09 (TAB), 0x0A (LF), 0x0D (CR).
        strict_allowed = bytearray(range(0x20, 0x7F))
        strict_allowed.extend([0x09, 0x0A, 0x0D])
        self._strict_ascii_bytes = bytes(strict_allowed)
        self._strict_ascii_set = set(self._strict_ascii_bytes)

        # Loose ASCII: Strict ASCII character set + 0x00 (NUL) + 0xFF (padding byte).
        loose_allowed = bytearray(strict_allowed)
        loose_allowed.extend([0x00, 0xFF])
        self._loose_ascii_bytes = bytes(loose_allowed)
        
        # Performance optimization: Pre-allocate common padding chunks for fast comparison.
        # We handle 0x80 (small) and 0x1000 (large) chunks for 0x00 and 0xFF.
        self._padding_cache = {}
        for size in [0x80, 0x1000]:
            self._padding_cache[(size, 0x00)] = b'\x00' * size
            self._padding_cache[(size, 0xFF)] = b'\xFF' * size

        self.mm: Optional[mmap.mmap] = None  # Memory-mapped file object.
        self._mm_len = 0
        self._f = None  # File handle.
    
    def _warn(self, message: str) -> None:
        self.logger.warn(message)

    def _debug(self, message: str) -> None:
        self.logger.debug(message)

    def _info(self, message: str) -> None:
        self.logger.info(message)
    
    def _error(self, message: str) -> None:
        self.logger.error(message)

    def _region_matches_padding(self, start: int, length: int, pad_byte: int) -> bool:
        """
        Checks whether the region [start, start+length) consists entirely of the specified padding byte.
        Optimized to use memcmp (via bytes equality) instead of Python loops.
        """
        if length <= 0 or not self.mm:
            return False
        end = start + length
        if end > self._mm_len:
            return False
        
        # Read the chunk directly as bytes.
        chunk = self.mm[start:end]
        if not chunk: 
            return False
        
        # Fast path: check against pre-cached chunks if size matches
        cached = self._padding_cache.get((length, pad_byte))
        if cached:
            return chunk == cached
            
        # Generic path: construct comparison target on the fly
        # (Still faster than iterating 448+ times in Python)
        return chunk == bytes([pad_byte]) * length

    def _infer_block_layout(self, header_info: Dict) -> None:
        """
        Determines whether a block uses the standard 0x1000-aligned layout or is a reused block.
        """
        # 1. header_padding_byte default value: Check last 4 bytes of first 32 bytes.
        #    If uniform, use it. Else fallback to STANDARD(0xFF)/REUSED(0x00).
        # This is handled partially in parse_block_header (setting initial value or None)
        # and finalized here.
        current_pad: Optional[int] = header_info.get('header_padding_byte')
        
        # Set default state (REUSED)
        header_info['header_size'] = 64
        header_info['classification'] = "REUSED"
        # If pad is unknown, default reused pad is 0x00
        header_info['header_padding_byte'] = current_pad if current_pad is not None else 0x00

        offset = header_info['offset']
        # Note: We no longer return early if offset % 0x1000 != 0.
        # We check for valid standard padding structure first.

        # Try to validate STANDARD layout (512-byte header with clean padding).
        # If we have a specific pad byte, we must match it.
        # If we don't (None), we try 0xFF (standard default).
        test_pad = current_pad if current_pad is not None else 0xFF

        if not self._region_matches_padding(offset + 32, 32, test_pad):
            return
        if not self._region_matches_padding(offset + 64, 4, test_pad):
            return
        if not self._region_matches_padding(offset + 64, 448, test_pad):
            return
        
        # If we reach here, the 512-byte header structure is valid.
        # Now determine classification based on alignment.
        if offset % 0x1000 == 0:
            header_info['classification'] = "STANDARD"
        else:
            header_info['classification'] = "STANDARD_COMPACT"

        header_info['header_size'] = 512
        header_info['header_padding_byte'] = test_pad
    
    def _collect_uniform_chunks(self, start: int, length: int, chunk_size: int, context: str) -> Optional[List[int]]:
        """
        Returns a list of padding bytes (one per chunk) if each chunk is uniform
        and uses a known padding byte. Otherwise returns None.
        """
        if not self.mm:
            return None
        if length <= 0 or chunk_size <= 0 or (length % chunk_size) != 0:
            return None
        end = start + length
        if end > self._mm_len:
            return None
        
        chunks = []
        total = length // chunk_size

        # Emit progress info for large scans to surface long pauses in debug mode.
        progress_step = None
        if total >= 512:  # ~512 chunks ~= 0x200000 with 0x1000 chunk size.
            progress_step = max(1, total // 10)
            self._debug(
                f"{context}: scanning padding profile from 0x{start:X} len 0x{length:X} "
                f"chunk 0x{chunk_size:X} ({total} chunks)"
            )

        # Pre-fetch cached comparison blocks for this chunk size
        cache_00 = self._padding_cache.get((chunk_size, 0x00))
        cache_FF = self._padding_cache.get((chunk_size, 0xFF))
        
        # If not cached, creating them once here is still better than inside the loop
        if not cache_00:
            cache_00 = b'\x00' * chunk_size
        if not cache_FF:
            cache_FF = b'\xFF' * chunk_size

        for idx in range(total):
            chunk_start = start + idx * chunk_size
            chunk_end = chunk_start + chunk_size
            
            # Read as bytes (copy) for fast comparison
            seg = self.mm[chunk_start:chunk_end]
            if not seg:
                return None
            
            first = seg[0]
            
            # Optimization: Check against the expected full block
            is_uniform = False
            if first == 0x00:
                if seg == cache_00:
                    is_uniform = True
            elif first == 0xFF:
                if seg == cache_FF:
                    is_uniform = True
            else:
                # Fallback for exotic padding bytes (rare, but possible)
                if seg == bytes([first]) * chunk_size:
                     is_uniform = True

            if not is_uniform:
                self._warn(
                    f"{context} chunk#{idx} (0x{chunk_size:X}) has mixed bytes. "
                    "Falling back to raw padding byte recording."
                )
                return None
                
            if first not in PROFILE_BYTE_SYMBOLS:
                self._warn(
                    f"{context} chunk#{idx} uses unsupported padding byte 0x{first:02X}. "
                    "Falling back to raw padding byte recording."
                )
                return None
            chunks.append(first)
            if progress_step and (idx + 1) % progress_step == 0:
                self._debug(
                    f"{context}: scanned {idx + 1}/{total} chunks "
                    f"(offset 0x{chunk_start + chunk_size:X})"
                )
        return chunks

    def _compress_profile_from_chunks(self, chunk_bytes: List[int], multiplier: int = 1) -> str:
        """
        Compresses consecutive chunk bytes into a profile string. Multiplier allows mapping
        coarser chunks (e.g., 0x1000) into 0x80-sized chunks by scaling run lengths.
        """
        if not chunk_bytes:
            return ""
        parts: List[str] = []
        i = 0
        while i < len(chunk_bytes):
            current: int = chunk_bytes[i]
            run: int = 1
            i += 1
            while i < len(chunk_bytes) and chunk_bytes[i] == current:
                run += 1
                i += 1
            total_chunks: int = run * multiplier
            symbol: str = PROFILE_BYTE_SYMBOLS[current]
            parts.append(f"{total_chunks}{symbol}")
        return "".join(parts)

    def _block_alignment(self, block_info: Dict) -> int:
        return 0x1000 if block_info.get('classification') == "STANDARD" else 0x80

    def _compute_tail_region(self, block_info: Dict) -> Tuple[int, int, int]:
        align: int = self._block_alignment(block_info)
        header_end: int = block_info['offset'] + block_info.get('header_size', 64)
        payload_end: int = header_end + block_info['len']
        aligned_end: int = (payload_end + (align - 1)) & ~(align - 1)
        tail_len: int = max(0, aligned_end - payload_end)
        return payload_end, tail_len, align

    def _record_block_tail_padding(self, block_info: Dict) -> None:
        tail_start, tail_len, _ = self._compute_tail_region(block_info)
        # block_padding_byte default uses header_padding_byte.
        default_pad: int = block_info.get('header_padding_byte', 0x00)
        
        pad_byte: int = default_pad
        if tail_len > 0 and self.mm:
            read_end: int = min(tail_start + tail_len, self._mm_len)
            if read_end > tail_start:
                segment: memoryview = memoryview(self.mm)[tail_start:read_end]
                if segment:
                    first: int = segment[0]
                    if all(b == first for b in segment):
                        pad_byte = first
                    else:
                        self._warn(
                            f"Tail padding for ID {block_info['id']} Sub {block_info['sub_id']} mixed bytes. "
                            f"Defaulting to 0x{default_pad:02X}."
                        )
        block_info['block_padding_byte'] = pad_byte

    def _build_padding_profile(self, start: int, length: int, context: str) -> Optional[str]:
        """
        Builds a compact profile string for a padding region aligned to 0x80-byte chunks.
        Returns None if a profile cannot be constructed.
        """
        base_chunk: int = 0x80
        if length <= 0 or (length % base_chunk) != 0:
            return None

        # Prefer analyzing at 0x1000 granularity for speed, but store as 0x80 chunks.
        if (length % 0x1000) == 0:
            coarse_chunks: Optional[List[int]] = self._collect_uniform_chunks(start, length, 0x1000, context)
            if coarse_chunks:
                return self._compress_profile_from_chunks(coarse_chunks, 0x1000 // base_chunk)

        fine_chunks: Optional[List[int]] = self._collect_uniform_chunks(start, length, base_chunk, context)
        if fine_chunks:
            return self._compress_profile_from_chunks(fine_chunks)
        return None

    def _build_padding_entry(self, start: int, length: int, context: str) -> Optional[Dict]:
        """
        Builds a manifest-friendly padding entry. Attempts to encode padding contents
        as a compact profile; otherwise relies on the default padding byte.
        """
        if length <= 0:
            return None

        entry: Dict[str, Union[int, str]] = {"type": "PADDING", "offset": start, "_length": length}
        profile: Optional[str] = self._build_padding_profile(start, length, context)
        if profile:
            entry["profile"] = profile
        return entry

    def _finalize_layout_metadata(self) -> None:
        """
        Computes padding metadata and prepares a combined list of data/padding entries.
        This version correctly handles blocks outside the nominal AB regions.
        """
        if self._layout_finalized:
            return
        self._info("Step 4: Scanning padding and finalizing layout...")

        # Ensure all discovered blocks are sorted by their offset.
        blocks: List[Dict] = sorted(self.manifest['blocks'], key=lambda x: x['offset'])
        layout_entries: List[Dict] = []
        padding_count: int = 0

        cursor: int = 0
        for idx, block in enumerate(blocks):
            # If there's a gap between the current cursor and the start of the next block,
            # insert a padding entry.
            if block['offset'] > cursor:
                context: str = f"Padding before Block ID {block['id']} Sub {block['sub_id']} " \
                               f"(0x{cursor:X} to 0x{block['offset']:X})"
                gap_entry: Optional[Dict] = self._build_padding_entry(cursor, block['offset'] - cursor, context)
                if gap_entry:
                    layout_entries.append(gap_entry)
                    padding_count += 1
                cursor = block['offset'] # Move cursor to the start of the current block
            elif block['offset'] < cursor:
                # This should ideally not happen if blocks are sorted and validated,
                # but adding a warning for robustness.
                self._warn(
                    f"Block ID {block['id']} Sub {block['sub_id']} overlaps previous region "
                    f"(cursor 0x{cursor:X} > offset 0x{block['offset']:X}). This may indicate a malformed image."
                )
                # Adjust cursor to current block's start to proceed, avoiding infinite loop.
                cursor = block['offset']
            
            # Add the current data block to the layout entries.
            layout_entries.append(block)
            
            # Calculate the logical end of the current block, including its payload and any tail padding.
            payload_end, tail_len, _ = self._compute_tail_region(block)
            cursor = payload_end + tail_len # Update cursor to after this block's logical end.

        # After processing all blocks, if there's any remaining space from the last block's end
        # to the file's actual size, fill it with padding.
        if cursor < self.file_size:
            context: str = f"File tail padding (0x{cursor:X} to 0x{self.file_size:X})"
            tail_entry: Optional[Dict] = self._build_padding_entry(cursor, self.file_size - cursor, context)
            if tail_entry:
                layout_entries.append(tail_entry)
                padding_count += 1
        
        self._layout_entries = layout_entries
        self._layout_finalized = True
        self._debug(f"Recorded {padding_count} padding entries and {len(layout_entries) - padding_count} data blocks.")


    def __enter__(self) -> "OemUnpacker":
        """
        Opens the file and creates a memory map when entering the context manager.
        """
        try:
            self._f = open(self.file_path, "rb")
            if self.file_size > 0:
                self.mm = mmap.mmap(self._f.fileno(), 0, access=mmap.ACCESS_READ)
                self._mm_len = len(self.mm)
            else:
                self.mm = b""
                self._mm_len = 0
        except Exception as e:
            self._error(f"Failed to open or memory-map '{self.file_path}': {e}")
            self.mm = None # Ensure mm is None if there was an error
            self._mm_len = 0
            # Re-raise to prevent further operations on an invalid state
            raise
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Closes the memory map and file when exiting the context manager.
        """
        if self.mm and isinstance(self.mm, mmap.mmap):
            self.mm.close()
        if self._f:
            self._f.close()
        self.mm = None
        self._mm_len = 0

    def is_ascii_content(self, data: bytes, strict: bool = True) -> bool:
        """
        Checks if the byte data primarily consists of allowed ASCII characters.

        Args:
            data (bytes): The byte data to check.
            strict (bool): If True, uses a strict ASCII character set; otherwise, uses a loose set.

        Returns:
            bool: True if the data is primarily ASCII characters; False otherwise.
        """
        if not data: return False
        
        allowed_set = self._strict_ascii_bytes if strict else self._loose_ascii_bytes
        
        # Fast check using translate.
        # If the result is empty, it means ALL characters were in allowed_set.
        non_allowed_count = len(data.translate(None, delete=allowed_set))
        
        # If more than 5% of characters are not allowed, it's not considered ASCII-like.
        return (non_allowed_count / len(data)) <= 0.05

    def _sanitize_preview(self, data: bytes) -> str:
        """
        Formats byte data for preview, limited to the first 100 characters.
        Non-printable characters will be escaped as '\\xHH'.

        Args:
            data (bytes): Raw byte data.

        Returns:
            str: The formatted preview string.
        """
        # Optimization: Process only the required slice.
        chunk: bytes = data[:100] 
        result: List[str] = []
        for b in chunk:
            if 0x20 <= b <= 0x7E or b == 0x09:  # Printable ASCII characters or TAB.
                result.append(chr(b))
            else:
                result.append(f"\\x{b:02x}")  # Escape non-printable characters.
        
        full_str: str = "".join(result)
        if len(full_str) > 97:
            return f"'{full_str[:97]}...'"
        return f"'{full_str}'"

    def _format_block_summary(self, block_info: Dict, prefix: Optional[str] = None) -> str:
        """
        Generates a consistent textual summary for a block, used by both list/unpack outputs.
        """
        classification: str = block_info.get('classification', 'N/A').upper()
        type_desc: str = block_info.get('type', 'UNKNOWN')
        label_text: str = prefix.strip() if prefix else ""
        header_prefix: str = f"{label_text:<12}" if label_text else ""
        include_type: bool = not (type_desc == "TLV" and 'tlv_subtype_description' in block_info)
        type_fragment: str = f" ({type_desc})" if include_type else ""
        base_header: str = (
            f"ID {block_info['id']:>4} Sub {block_info['sub_id']:>3} "
            f"({classification}){type_fragment}"
        )
        descriptor_text: str = ""
        if 'tlv_subtype_description' in block_info:
            descriptor_text = f" ([TLV]{block_info['tlv_subtype_description']})"

        header_body: str = f"{header_prefix} {base_header}" if header_prefix else base_header
        header_body += descriptor_text
        label_prefix: str = "[INFO] " if self.debug else ""
        header: str = f"{label_prefix}{header_body}"
        if block_info.get('is_active') is True:
            header += " (Active)"
        elif block_info.get('is_active') is False:
            header += " (Inactive/Backup)"
        header += ":"
        details: str = (
            f"{label_prefix}  Offset: 0x{block_info.get('offset', 0):08X}  "
            f"Region: {block_info.get('region', 'N/A')}  "
            f"Age: {block_info['age']:>6}  "
            f"Size: {block_info['len']:>6}"
        )
        return f"{header}\n{details}"

    def _get_ascii_preview(self, data: bytes) -> Tuple[Optional[str], bool]:
        """
        Returns a sanitized preview string for ASCII-like payloads.

        Args:
            data (bytes): Raw payload bytes to inspect.

        Returns:
            Tuple[Optional[str], bool]: (preview string if ASCII-like else None, True if strict ASCII).
        """
        # If it's not even loose ASCII (e.g., random binary), we can fail early
        # and skip the strict check entirely.
        if not self.is_ascii_content(data, strict=False):
            return None, False

        # If it passes loose check, it might be strict or loose.
        # Now check strict to differentiate.
        if self.is_ascii_content(data, strict=True):
            return self._sanitize_preview(data), True
        
        return self._sanitize_preview(data), False

    def _is_ascii_with_padding_only(self, data: bytes) -> bool:
        """
        Allows ASCII content that includes padding bytes (0x00 or 0xFF) exclusively.
        """
        if not data:
            return False
        allowed: set[int] = self._strict_ascii_set
        for b in data:
            if b not in allowed and b not in (0x00, 0xFF):
                return False
        return True

    def _calculate_entropy(self, data: bytes) -> float:
        """
        Calculates Shannon entropy for the given byte sequence.
        """
        if not data:
            return 0.0
        counts: collections.Counter = collections.Counter(data)
        total: int = len(data)
        entropy: float = 0.0
        for count in counts.values():
            probability: float = count / total
            entropy -= probability * math.log2(probability)
        return entropy

    def _is_high_entropy(self, data: bytes, threshold: float = HIGH_ENTROPY_THRESHOLD) -> bool:
        """
        Determines whether the data exhibits high entropy (appears random).
        """
        return self._calculate_entropy(data) >= threshold

    def parse_block_header(self, offset: int) -> Optional[Dict]:
        """
        Parses a standard 512-byte block header or a 64-byte mini header from the memory map.

        Args:
            offset (int): The starting offset of the block header in the file.

        Returns:
            Optional[Dict]: A dictionary containing header information if successfully parsed;
                            otherwise, None.
        """
        try:
            # Ensure enough bytes are available to read the start of the header (at least 32 bytes).
            if offset + 32 > self._mm_len: return None
            
            # Read the first 32 bytes, containing the magic number and other key fields.
            data: bytes = self.mm[offset : offset + 32]
            # Unpack format '<8sIIIIII':
            magic: bytes
            version: int
            mid: int
            sub: int
            dlen: int
            age: int
            # padding_field is unused here as we inspect the raw bytes directly later.
            magic, version, mid, sub, dlen, age, _ = BLOCK_HEADER_STRUCT.unpack(data)
            
            # Quick check if the magic number matches 'OEM_INFO'.
            if magic != b'OEM_INFO':
                # Attempt to decode as ASCII and remove trailing null bytes.
                magic_str: str = magic.decode('ascii', errors='ignore').rstrip('\x00')
                if magic_str != "OEM_INFO":
                    return None  # Magic number does not match, not a valid OEMINFO block.
            else:
                magic_str = "OEM_INFO"

            # header_padding_byte default: Compare last 4 bytes of the 32-byte header.
            # If uniform, use it. Else fallback (handled in _infer_block_layout).
            padding_field_bytes = data[28:32]
            header_padding_byte: Optional[int] = None
            if all(b == padding_field_bytes[0] for b in padding_field_bytes):
                header_padding_byte = padding_field_bytes[0]

            header_size: int = 64

            # Determine the padding byte used between the OEM header structure and payload.
            tail_len: int = header_size - 32
            if tail_len > 0 and self.mm and offset + header_size <= self._mm_len:
                header_tail: memoryview = memoryview(self.mm)[offset + 32 : offset + header_size]
                if header_tail:
                    first_byte: int = header_tail[0]
                    if all(b == first_byte for b in header_tail):
                        header_padding_byte = first_byte
                    else:
                        self._warn(
                            f"Header padding for ID {mid} Sub {sub} at offset 0x{offset:X} "
                            f"is not uniform. Falling back to derived default."
                        )
                        # If tail is mixed, we keep header_padding_byte as determined by the 4-byte check (or None).

            header_info: Dict = {
                "offset": offset,
                "version": version,
                "id": mid,
                "sub_id": sub,
                "len": dlen,
                "age": age,
                "type": "UNKNOWN",  # Initial type, will be overwritten by content type.
                "header_size": header_size,
                "header_padding_byte": header_padding_byte
            }
            self._infer_block_layout(header_info)
            return header_info
        except struct.error:
            # If unpacking fails, e.g., due to insufficient data or incorrect format.
            pass
        return None

    def parse_custom_header(self, data: bytes) -> Optional[Dict]:
        """
        Parses the custom header used by image blocks.

        Layout (little-endian):
            - uint32: data start offset (currently observed as 0x1A)
            - uint32: data end offset
            - uint32: random adjustment value
            - 12 bytes: version string
            - 4 bytes: data magic (00 00 1F 8B for GZIP or 00 00 42 4D for BMP)

        Conditions for acceptance:
            * start offset must be 0x1A (26)
            * (end_offset - rand_adjust) equals the payload length
            * magic must match the supported signatures
        Returns a dictionary that keeps only the fields required by downstream logic:
            * data_offset: byte offset of the actual payload within the block payload.
            * rand_adjust: random adjustment value stored in the header.
            * ver: ASCII version string (trimmed).
            * magic: raw 4-byte signature identifying the payload type.
        """
        minimum_size: int = 28
        if len(data) < minimum_size:
            return None
        start_offset: int
        end_offset: int
        rand_adjust: int
        start_offset, end_offset, rand_adjust = IMAGE_HEADER_PREFIX_STRUCT.unpack_from(data, 0)
        if start_offset != 0x1A:
            return None
        ver_bytes: bytes = data[12:24]
        if len(ver_bytes) != 12:
            return None
        magic: bytes = data[24:28]
        if magic not in (b'\x00\x00\x1f\x8b', b'\x00\x00BM'):
            return None
        total_payload_len: int = len(data)
        data_end: int = end_offset - rand_adjust
        if data_end <= start_offset or data_end > total_payload_len:
            return None
        if data_end != total_payload_len: # This check seems redundant if data_end <= total_payload_len is already checked and it must equal total_payload_len in practice.
            return None
        return {
            "data_offset": start_offset,
            "rand_adjust": rand_adjust,
            "ver": ver_bytes, # Store as bytes
            "magic": magic
        }

    def parse_tlv(self, data: bytes) -> Optional[List[bytes]]:
        """
        Attempts to parse 'LenStr\\0Data' chains (Type-Length-Value structure).
        Allows for trailing padding bytes (0x00 or 0xFF).

        Args:
            data (bytes): Byte data containing TLV structures.

        Returns:
            Optional[List[bytes]]: A list of all TLV parts if successfully parsed;
                                   otherwise, None.
        """
        parts: List[bytes] = []
        ptr: int = 0
        data_len: int = len(data)
        
        while ptr < data_len:
            # Check if only padding bytes (0x00 or 0xFF) remain at the end.
            if data[ptr] in (0x00, 0xFF):
                remaining: bytes = data[ptr:]
                if all(b == data[ptr] for b in remaining):
                    break  # Remaining part is all padding, end parsing.
            
            # Find the null terminator for the length string.
            # The format uses 1-3 ASCII digits terminated by '\x00' (2-4 bytes total).
            search_limit: int = min(ptr + 4, data_len)
            null_idx: int = data.find(b'\x00', ptr, search_limit)
            
            if null_idx == -1:
                break  # Null terminator not found, parsing interrupted.
            
            len_str_bytes: bytes = data[ptr:null_idx]
            if not len_str_bytes.isdigit() or not (1 <= len(len_str_bytes) <= 3):
                break  # Length string is not a digit, parsing interrupted.
                
            try:
                item_len: int = int(len_str_bytes)
            except ValueError:
                break  # Conversion to integer failed, parsing interrupted.

            start_data: int = null_idx + 1
            if start_data + item_len > data_len:
                break  # Data overflow, beyond available data range, parsing interrupted.
                
            item_data: bytes = data[start_data : start_data + item_len]
            parts.append(item_data)
            ptr = start_data + item_len
            
        # Check if the remaining data after parsing is valid padding.
        remaining_after_parse: bytes = data[ptr:]
        is_padding: bool = True
        if remaining_after_parse:
            # Efficiently check if all bytes are 0x00 or all are 0xFF.
            for b in remaining_after_parse:
                if b != 0x00 and b != 0xFF:
                    is_padding = False
                    break
        
        if len(parts) > 0 and (ptr == data_len or is_padding):
            return parts  # Successfully parsed at least one part, and the rest is valid padding or empty.
        return None

    def find_tail_tlv(self, data: bytes) -> Tuple[Optional[bytes], int]:
        """
        Scans byte data backwards to find a valid TLV (LenStr\\0Data) structure at the end.
        This is primarily used to identify signature or random data blocks that might be
        appended to raw data.

        Args:
            data (bytes): The byte data to scan.

        Returns:
            Tuple[Optional[bytes], int]: If found, returns (tlv_data, length_of_tlv_structure);
                                         otherwise, returns (None, 0).
        """
        if len(data) < 3: return None, 0
        
        offset: int = len(data) - 1
        while True:
            # Search backwards for a null byte.
            null_idx: int = data.rfind(b'\x00', 0, offset)
            if null_idx == -1: break  # No more null bytes found, stop searching.
            
            # Check if bytes before the null byte are digits (1-3 bytes total).
            max_digit_span: int = 3
            digits_found: int = 0
            scan_idx: int = null_idx - 1
            while scan_idx >= 0 and 0x30 <= data[scan_idx] <= 0x39 and digits_found < max_digit_span:
                digits_found += 1
                scan_idx -= 1
            digit_start: int = scan_idx + 1
            
            if digits_found == 0:
                offset = null_idx
                continue
            if scan_idx >= 0 and 0x30 <= data[scan_idx] <= 0x39:
                # More than 3 digit bytes before the null terminator, invalid TLV tail.
                offset = null_idx
                continue
            
            digit_seq: bytes = data[digit_start:null_idx]
            
            try:
                val_len: int = int(digit_seq)
                remaining_len: int = len(data) - (null_idx + 1)
                
                if val_len == remaining_len:
                    # Return only the value data part, but keep the total length for slicing.
                    return data[null_idx + 1:], len(data) - digit_start
            except ValueError:
                pass  # Length string is not a valid number.
            
            offset = null_idx  # Continue searching backwards from the previous null byte.
            
        return None, 0

    def _check_ab_region_bounds(self, block_info: Dict) -> Optional[str]:
        """
        Checks whether a block resides completely inside the valid AB region.

        Args:
            block_info (Dict): Metadata for the block to evaluate.

        Returns:
            Optional[str]: Warning message if the block falls outside the AB region,
                           otherwise None.
        """
        header_len: int = block_info.get('header_size', 0)
        block_start: int = block_info['offset']
        block_end: int = block_start + header_len + block_info['len']

        outside: bool = block_start < 0 or block_end > TOTAL_REGION_SIZE
        if outside:
            return (f"Block ID {block_info['id']} Sub {block_info['sub_id']} spans "
                    f"0x{block_start:X}-0x{block_end:X}, outside valid AB region "
                    f"(relative 0x0-0x{TOTAL_REGION_SIZE:X}).")
        return None

    def scan_headers(self) -> None:
        """
        Scans the entire file for all possible OEM_INFO headers and stores them in `self.headers`.
        """
        self._info("Step 1: Scanning file for headers...")
        self._debug("Beginning linear scan for OEM_INFO headers")
        start: int = 0
        
        # Optimized memory-mapped search, directly using mmap's find method.
        while True:
            idx: int = self.mm.find(b'OEM_INFO', start)  # Search for the magic number using mmap's find.
            if idx == -1: break  # No more magic numbers found, stop scanning.
            
            # A potential header is found, attempt to parse it.
            hdr: Optional[Dict] = self.parse_block_header(idx)
            if hdr:  # Only add if parse_block_header successfully determined type and size.
                self.headers.append(hdr)
                self._debug(f"Header parsed at 0x{idx:X} (ID {hdr['id']}, Sub {hdr['sub_id']}, {hdr['classification']})")
            
            # Continue searching from the current index + 8 (length of magic number)
            # to avoid re-detecting the same magic.
            start = idx + 8 
            
        self._info(f"Found {len(self.headers)} potential headers.")

    def classify_topology(self) -> None:
        """
        Classifies the discovered headers, distinguishing between standard and reused blocks,
        and assigns them to regions A/B. Additionally, it determines the active block within
        each (ID, SubID) pair based on the 'age' field.
        """
        self._info("Step 2: Mapping topology (Standard vs Reused, and Region Assignment)...")
        self._debug("Classifying blocks by region and determining active copies")
        
        # Ensure self.headers is sorted by offset for consistent processing.
        all_headers_sorted: List[Dict] = sorted(self.headers, key=lambda x: x['offset'])

        initial_filtered_headers: List[Dict] = []
        last_block_physical_end: int = -1 # Tracks the physical end offset of the last successfully processed block.

        # --- GHOST BLOCK FILTERING LOGIC ---
        for current_block in all_headers_sorted:
            # Calculate the end of the current block based on its header size and payload length.
            # This represents the actual physical space occupied by the block's header and payload.
            current_block_physical_end = current_block['offset'] + current_block['header_size'] + current_block['len']
            
            if current_block['offset'] < last_block_physical_end:
                # This block starts before the previous one ended, meaning it's inside its payload/tail.
                self._warn(
                    f"Identified potential ghost block ID {current_block['id']} Sub {current_block['sub_id']} "
                    f"at 0x{current_block['offset']:X} which is inside the physical bounds of a preceding block. "
                    "This block will be ignored to prevent structural conflicts and data ambiguity."
                )
            else:
                initial_filtered_headers.append(current_block)
                # Update the end of the last block for the next iteration's comparison.
                last_block_physical_end = current_block_physical_end
        # --- END GHOST BLOCK FILTERING LOGIC ---
        
        # Conflict Resolution: Check for Standard blocks overlapping with subsequent blocks.
        # If a Standard block's required tail alignment (0x1000) encroaches on the next block,
        # downgrade it to STANDARD_COMPACT.
        for i in range(len(initial_filtered_headers) - 1):
            curr_blk = initial_filtered_headers[i]
            next_blk = initial_filtered_headers[i+1]

            if curr_blk.get('classification') == 'STANDARD':
                # Calculate the theoretical end of this block if it remains STANDARD.
                # Standard blocks consume 512 bytes of header + payload + padding to next 0x1000.
                # Note: We must use the specific Standard header size (512) for this calc.
                payload_end = curr_blk['offset'] + 512 + curr_blk['len']
                align = 0x1000
                expected_end = (payload_end + (align - 1)) & ~(align - 1)

                # If the next block starts BEFORE the current block's aligned end, we have a conflict.
                if next_blk['offset'] < expected_end:
                    self._warn(
                        f"Conflict detected: Standard Block ID {curr_blk['id']} Sub {curr_blk['sub_id']} "
                        f"(Expected End 0x{expected_end:X}) overlaps Next Block at 0x{next_blk['offset']:X}. "
                        "Converting current block to STANDARD_COMPACT (preserving 512-byte header but relaxing tail alignment)."
                    )
                    # Resolve conflict by relaxing alignment requirement
                    curr_blk['classification'] = "STANDARD_COMPACT"
        
        # Group headers by (ID, SubID) to determine active blocks based on Age.
        block_groups: Dict[Tuple[int, int], List[Dict]] = collections.defaultdict(list)
        for h in initial_filtered_headers: # Iterate over initial_filtered_headers
            # Determine the region (A or B) the block belongs to based on its offset.
            if 0 <= h['offset'] < REGION_SIZE:
                h['region'] = 'A'
            elif REGION_SIZE <= h['offset'] < (2 * REGION_SIZE):
                h['region'] = 'B'
            else:
                h['region'] = 'Unknown'

            # Only consider valid regions (A/B) for active/inactive determination.
            if h['region'] in ['A', 'B']:
                block_groups[(h['id'], h['sub_id'])].append(h)

        final_processing_queue: List[Dict] = []
        processed_ids_sub_ids: set[Tuple[int, int]] = set()

        for (block_id, sub_id), group in block_groups.items():
            processed_ids_sub_ids.add((block_id, sub_id))
            if not group:
                continue

            if len(group) == 1:
                # If only one instance of this ID/SubID is found, it's active by default.
                group[0]['is_active'] = True
                final_processing_queue.append(group[0])
            else:
                # If multiple instances exist (potentially in A and B regions), compare 'age' fields.
                active_block: Optional[Dict] = None
                max_age: int = -1
                
                # Find the block with the highest 'age'.
                # In case of a tie, the one appearing first in `group` (which is sorted by offset) will be picked.
                for block in group:
                    if block['age'] > max_age:
                        max_age = block['age']
                        active_block = block
                
                # Mark blocks as active or inactive.
                for block in group:
                    if block is active_block:
                        block['is_active'] = True
                    else:
                        block['is_active'] = False  # For backup or older versions.
                    final_processing_queue.append(block)

        # Add any headers not part of a recognized A/B pair (e.g., 'Unknown' region).
        # These will be treated as independent blocks.
        for h in initial_filtered_headers: # Iterate over initial_filtered_headers
            if (h['id'], h['sub_id']) not in processed_ids_sub_ids:
                # If a block was not processed as part of an A/B pair, it's considered active.
                h['is_active'] = True
                final_processing_queue.append(h)

        # Sort the final queue by ID, then by SubID for consistent and readable output order.
        self.processing_queue = sorted(final_processing_queue, key=lambda x: (x['id'], x['sub_id']))
        self._debug(f"Topology classification complete: {len(self.processing_queue)} blocks queued")

    def _build_filename_base(self, block_info: Dict) -> str:
        """
        Builds a deterministic filename prefix based on block identity and classification.

        Args:
            block_info (Dict): Current block metadata.

        Returns:
            str: A filename-safe prefix.
        """
        base: str = f"{block_info['id']}_{block_info['sub_id']}_{block_info.get('classification', 'UNKNOWN').lower()}"
        if block_info.get('is_active') is True:
            base += "_active"
        elif block_info.get('is_active') is False:
            base += "_inactive"
        return base

    def _try_extract_image(self, block: Dict, payload: bytes, filename_base: str) -> Tuple[bool, Optional[Dict]]:
        """
        Attempts to extract image data (GZIP or BMP format) from the given payload.

        Args:
            block (Dict): Metadata of the current data block.
            payload (bytes): The payload (content) of the data block.
            filename_base (str): Base string for generating output filenames.

        Returns:
            Tuple[bool, Optional[Dict]]: If an image is successfully extracted, returns
                                         (True, a dictionary containing image metadata);
                                         otherwise, returns (False, None).
        """
        custom_hdr: Optional[Dict] = self.parse_custom_header(payload)
        if not custom_hdr:
            return False, None  # No valid custom header, not an image.

        data_offset: int = custom_hdr.get("data_offset", 0)
        data_end: int = len(payload)
        if data_offset >= data_end:
            return False, None
        magic_bytes: bytes = custom_hdr.get("magic")
        block_update: Dict = {}
        data_slice: bytes = payload[data_offset:data_end]

        if magic_bytes == b'\x00\x00\x1f\x8b':  # GZIP image branch
            gz_data: bytes = data_slice
            if self.dry_run:
                block_update.update({'type': "IMAGE_GZIP", 'custom_meta': custom_hdr})
                return True, block_update

            # Write raw GZIP data; do not decompress to BMP.
            self.write_file(f"{filename_base}.gz", gz_data)
            block_update.update({'type': "IMAGE_GZIP", 'custom_meta': custom_hdr})
            return True, block_update

        elif magic_bytes == b'\x00\x00BM':  # BMP image branch
            bmp_data: bytes = data_slice
            if self.dry_run:
                block_update.update({'type': "IMAGE_RAW", 'custom_meta': custom_hdr})
                return True, block_update
            
            out_file: str = f"{filename_base}.bmp"
            self.write_file(out_file, bmp_data)
            block_update.update({'type': "IMAGE_RAW", 'custom_meta': custom_hdr})
            return True, block_update
        
        return False, None  # If neither GZIP nor BMP magic is found, return False.

    def _try_extract_tlv(self, block: Dict, payload: bytes, filename_base: str) -> Tuple[bool, Optional[Dict], Optional[Tuple[str, str]]]:
        """
        Attempts to extract TLV (Type-Length-Value) formatted data from the given payload.

        Args:
            block (Dict): Metadata of the current data block.
            payload (bytes): The payload (content) of the data block.
            filename_base (str): Base string for generating output filenames.

        Returns:
            Tuple[bool, Optional[Dict], Optional[str]]: If TLV is successfully extracted, returns
                                                        (True, a dictionary with TLV metadata, ASCII preview string);
                                                        otherwise, returns (False, None, None).
        """
        tlv_parts: Optional[List[bytes]] = self.parse_tlv(payload)
        if not tlv_parts: return False, None, None  # Failed to parse as TLV structure.

        preview_meta: Optional[Dict] = None
        # Preset TLV part suffixes for generating meaningful filenames.
        suffixes: List[str] = ["tlv_data", "tlv_sign", "tlv_rand"]
        ascii_preview: Optional[Tuple[str, str]] = None
        
        for i, part in enumerate(tlv_parts):
            suffix: str = suffixes[i] if i < len(suffixes) else f"tlv_unknown_{i}"
            ext: str = ".bin"
            if i == 0:  # Typically, the first part is the main data.
                preview: Optional[str]
                strict_ascii: bool
                preview, strict_ascii = self._get_ascii_preview(part)
                if preview:
                    label: str = "ASCII" if strict_ascii else "ASCII Preview"
                    ascii_preview = (label, preview)
                    preview_meta = {
                        'text_preview': preview,
                        'text_preview_label': label
                    }
                    if strict_ascii:
                        ext = ".txt"  # If strictly ASCII, save as a .txt file.
            
            f_name: str = f"{filename_base}_{suffix}{ext}"
            self.write_file(f_name, part)  # Write each TLV part to a separate file.
        
        block_update: Dict = {'type': "TLV"}
        if preview_meta:
            block_update.update(preview_meta)
        
        # Attempt to describe the TLV subtype for better understanding of its structure.
        subtype_parts_list: List[str] = []
        for i, part in enumerate(tlv_parts):
            label: str = f"PART{i}"
            if i == 0:
                label = "ASCII" if self.is_ascii_content(part, strict=True) else "RAW"
            elif len(part) == 256 and not (all(b==0 for b in part) or all(b==255 for b in part)):
                label = "SIGN"  # 256 bytes and not all 0x00 or 0xFF, possibly a signature.
            elif i == len(tlv_parts) - 1:
                label = "RANDOM"  # The last part, possibly random data.
            subtype_parts_list.append(label)
        
        block_update['tlv_subtype_description'] = "+".join(subtype_parts_list)
        return True, block_update, ascii_preview

    def _extract_raw(self, block: Dict, payload: bytes, filename_base: str) -> Tuple[Dict, Optional[Tuple[str, str]]]:
        """
        Extracts raw binary data and attempts to identify ASCII content, signatures, and
        trailing TLV random data.

        Args:
            block (Dict): Metadata of the current data block.
            payload (bytes): The payload (content) of the data block.
            filename_base (str): Base string for generating output filenames.

        Returns:
            Tuple[Dict, Optional[Tuple[str, str]]]: Raw metadata dictionary and optional preview tuple.
        """
        ascii_preview: Optional[Tuple[str, str]] = None
        preview, strict_ascii = self._get_ascii_preview(payload)
        if preview is None and self._is_ascii_with_padding_only(payload):
            preview = self._sanitize_preview(payload)
        if strict_ascii:
            f_name = f"{filename_base}_data.txt"
            self.write_file(f_name, payload)
            ascii_preview = ("ASCII", preview) if preview else None
            return {
                'type': "ASCII",
                'text_preview': preview,
                'text_preview_label': "ASCII"
            }, ascii_preview

        # Attempt to find a trailing TLV structure (random/checksum). Only used when a signature is present.
        rand_data, rand_len = self.find_tail_tlv(payload)
        remaining_payload = payload[:-rand_len] if rand_data else payload
        rand_present = bool(rand_data)
        if rand_present and len(remaining_payload) <= 256:
            self._warn(
                f"Block ID {block['id']} Sub {block['sub_id']} random padding detected without room for signature; treating as RAW."
            )
            rand_data = b""
            rand_len = 0
            remaining_payload = payload
            rand_present = False

        has_sign = False
        sign_data = b""
        data_data = remaining_payload

        if len(remaining_payload) > 256:
            candidate_sign = remaining_payload[-256:]
            candidate_data = remaining_payload[:-256]
            data_preview_candidate, data_strict_ascii_candidate = self._get_ascii_preview(candidate_data)
            data_is_ascii = data_preview_candidate is not None
            data_is_loose_ascii = data_is_ascii and not data_strict_ascii_candidate
            data_is_high_entropy = not data_is_ascii and self._is_high_entropy(candidate_data)
            sign_is_high_entropy = self._is_high_entropy(candidate_sign)

            if rand_present:
                has_sign = True
            else:
                if not data_is_ascii and data_is_high_entropy:
                    has_sign = False
                elif data_is_loose_ascii and sign_is_high_entropy:
                    has_sign = True
                elif data_is_ascii and data_strict_ascii_candidate:
                    has_sign = sign_is_high_entropy
                elif not data_is_ascii:
                    has_sign = sign_is_high_entropy
                else:
                    has_sign = False

            if has_sign:
                data_data = candidate_data
                sign_data = candidate_sign

        if has_sign:
            data_ext = ".bin"
            data_preview, data_strict_ascii = self._get_ascii_preview(data_data)
            if data_preview is None and self._is_ascii_with_padding_only(data_data):
                data_preview = self._sanitize_preview(data_data)
            if data_preview:
                label = "ASCII" if data_strict_ascii else "ASCII Preview"
                ascii_preview = (label, data_preview)
                raw_meta = {
                    'text_preview': data_preview,
                    'text_preview_label': label
                }
                if data_strict_ascii:
                    data_ext = ".txt"
            else:
                raw_meta = {}

            sign_file = f"{filename_base}_sign.bin"
            data_file = f"{filename_base}_data{data_ext}"
            self.write_file(sign_file, sign_data)
            self.write_file(data_file, data_data)

            if rand_present:
                rand_file = f"{filename_base}_tlv_rand.bin"
                self.write_file(rand_file, rand_data)
            final_type_base = "ASCII_SIGNED" if data_strict_ascii else "RAW_SIGNED"
            meta = {
                'type': f"{final_type_base}_RANDOM" if rand_present else final_type_base
            }
            if data_preview:
                meta.update(raw_meta)
            return meta, ascii_preview
            
        # No signature: ignore trailing rand_data for classification; keep full payload as raw.
        f_name = f"{filename_base}_data.bin"
        self.write_file(f_name, payload)
        if preview:
            label = "ASCII" if strict_ascii else "ASCII Preview"
            ascii_preview = (label, preview)
        raw_entry = {'type': "RAW"}
        if preview:
            raw_entry['text_preview'] = preview
            raw_entry['text_preview_label'] = label
        return raw_entry, ascii_preview

    def _classify_payload(self, block_info: Dict, payload: bytes, filename_base: str) -> Tuple[Dict, Optional[Tuple[str, str]]]:
        """
        Classifies a block payload as image, TLV, or raw and updates metadata accordingly.

        Args:
            block_info (Dict): Mutable block metadata.
            payload (bytes): Block payload to classify.
            filename_base (str): Base filename for any generated files.

        Returns:
            Tuple[Dict, Optional[Tuple[str, str]]]: Updated block info and an optional preview tuple.
        """
        ascii_preview: Optional[Tuple[str, str]] = None

        is_image: bool
        img_update: Optional[Dict]
        is_image, img_update = self._try_extract_image(block_info, payload, filename_base)
        if is_image:
            block_info.update(img_update) # type: ignore
            if block_info.get('classification') == "REUSED":
                block_info['header_size'] = 512
                if 'header_padding_byte' not in block_info:
                    block_info['header_padding_byte'] = 0x00
            return block_info, ascii_preview

        is_tlv: bool
        tlv_update: Optional[Dict]
        tlv_preview: Optional[Tuple[str, str]]
        is_tlv, tlv_update, tlv_preview = self._try_extract_tlv(block_info, payload, filename_base)
        if is_tlv:
            block_info.update(tlv_update) # type: ignore
            ascii_preview = tlv_preview
        else:
            raw_update: Dict
            raw_preview: Optional[Tuple[str, str]]
            raw_update, raw_preview = self._extract_raw(block_info, payload, filename_base)
            block_info.update(raw_update)
            ascii_preview = raw_preview

        if 'header_padding_byte' not in block_info:
            block_info['header_padding_byte'] = 0x00

        return block_info, ascii_preview

    def extract_data(self) -> None:
        """
        Extracts and classifies data based on the block information in `self.processing_queue`.
        For each block, it attempts to identify images, TLV, or raw data, and writes them
        to the output directory.
        """
        # Suppress verbose "Step 3" message if in dry-run mode.
        if not self.dry_run:
            self._info("Step 3: Extracting and classifying data...")
        self._debug(f"Beginning payload extraction for {len(self.processing_queue)} blocks")

        if not self.dry_run:
            try:
                os.makedirs(self.output_dir, exist_ok=True) # Create directory, don't fail if it exists
                self._info(f"Ensuring output directory '{self.output_dir}' exists.")
            except OSError as e:
                self._error(f"Failed to create or ensure output directory '{self.output_dir}': {e}. Please check permissions.")
                return


        for block in self.processing_queue:
            payload_start: int = block['offset'] + block['header_size']
            payload_end: int = payload_start + block['len']

            # Calculate the maximum readable length to prevent reading beyond file boundaries.
            if not self.mm: # Should have been caught by __enter__ but defensive check.
                self._error("Error: Memory map is not initialized. Cannot extract data.")
                return
            if payload_end > self._mm_len:
                if not self.dry_run:  # Only print warning if not in dry_run mode.
                    self._warn(
                        f"Block ID {block['id']} Sub {block['sub_id']} extends beyond file size, skipped."
                    )
                continue

            # Read the payload once based on the determined header size.
            payload: bytes = self.mm[payload_start:payload_end]

            block_info: Dict = block.copy()
            self._debug(f"Classifying block ID {block_info['id']} Sub {block_info['sub_id']} at 0x{block_info['offset']:X}")

            filename_base: str = self._build_filename_base(block_info)
            block_info, ascii_preview = self._classify_payload(block_info, payload, filename_base)
            self._debug(
                f"Block ID {block_info['id']} Sub {block_info['sub_id']} "
                f"classified as {block_info['type']} len={block_info['len']}"
            )
            self._record_block_tail_padding(block_info)
            ab_warning: Optional[str] = self._check_ab_region_bounds(block_info)
            if ab_warning:
                if not self.dry_run:
                    self._warn(ab_warning)

            self.manifest['blocks'].append(block_info)
            
            if not self.dry_run:  # Only print verbose extraction info if not in dry_run mode.
                self._info(self._format_block_summary(block_info, prefix="EXTRACTED"))
                if ascii_preview:
                    label, preview_text = ascii_preview
                    self._info(f"  {label}:")
                    self._info(f"    {preview_text}")

    def write_file(self, rel_path: str, data: Union[bytes, memoryview]) -> None:
        """
        Writes data to a file at the specified relative path. No writing is performed in dry_run mode.

        Args:
            rel_path (str): The file path relative to the output directory.
            data (Union[bytes, memoryview]): The byte data to write.
        """
        if self.dry_run:
            return
            
        if not is_safe_path(self.output_dir, rel_path):
            self._error(f"Security: Attempted path traversal detected for '{rel_path}'. Skipping write.")
            return

        full_path: str = os.path.join(self.output_dir, rel_path)
        # Ensure the directory containing the file exists.
        dir_name: str = os.path.dirname(full_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        try:
            with open(full_path, "wb") as f:
                f.write(data)
        except OSError as e:
            self._error(f"Failed to write file '{full_path}': {e}. Please check permissions and disk space.")

    def _serialize_block_for_manifest(self, block: Dict) -> Dict:
        """
        Reduces block metadata to only the fields required for repacking.
        """
        layout: str = block.get("classification", "REUSED").upper()
        serialized: Dict = {
            "type": block["type"],
            "offset": f"0x{block['offset']:X}", # Convert to Hex string
            "version": block["version"],
            "id": block["id"],
            "sub_id": block["sub_id"],
            "age": block["age"],
            "layout": layout,
            "header_padding_byte": block.get("header_padding_byte", 0),
            "block_padding_byte": block.get("block_padding_byte", 0)
        }

        if block["type"].startswith("IMAGE"):
            custom_meta: Dict = block.get("custom_meta", {})
            # 'ver' is stored as bytes internally. Convert to HEX string for JSON serialization
            # to ensure unambiguous storage and editability.
            ver_val = custom_meta.get("ver", b"")
            ver_str = f"0x{ver_val.hex().upper()}" if isinstance(ver_val, bytes) else str(ver_val)
            
            serialized["custom_meta"] = {
                "ver": ver_str,
                "rand_adjust": custom_meta.get("rand_adjust", 0)
            }

        return serialized

    def _serialize_padding_for_manifest(self, entry: Dict) -> Dict:
        """
        Serializes a padding entry for manifest storage.
        """
        serialized: Dict = {
            "type": "PADDING",
            "offset": f"0x{entry['offset']:X}" # Convert to Hex string
        }
        if "profile" in entry:
            serialized["profile"] = entry["profile"]
        return serialized

    def save_manifest(self) -> None:
        """
        Saves `self.manifest` as `manifest.json` to the output directory.
        No manifest is saved in dry_run mode.
        """
        if self.dry_run:  # Do not save manifest in dry_run mode.
            return
        self._finalize_layout_metadata()
        layout_entries: List[Dict] = getattr(self, "_layout_entries", []) or []
        self._info("Step 5: Saving manifest.json...")
        man_path: str = os.path.join(self.output_dir, "manifest.json")
        manifest_to_save: Dict = {
            "file_size": self.manifest["file_size"],
            "blocks": []
        }
        for entry in layout_entries:
            if entry.get("type") == "PADDING":
                manifest_to_save["blocks"].append(self._serialize_padding_for_manifest(entry))
            else:
                manifest_to_save["blocks"].append(self._serialize_block_for_manifest(entry))
        try:
            with open(man_path, "w", encoding='utf-8') as f:  # Specify encoding for compatibility.
                json.dump(manifest_to_save, f, indent=4)
            self._info(f"Manifest saved to {man_path}")
            self._debug(f"Manifest contains {len(manifest_to_save['blocks'])} blocks")
        except OSError as e:
            self._error(f"Failed to save manifest to '{man_path}': {e}. Please check permissions and disk space.")

    def run(self) -> None:
        """
        Executes the unpacking process for the OEMINFO image.
        """
        try:
            with self:  # Use a context manager to ensure file and mmap are properly closed.
                if not self.mm:  # Check if mmap is empty (empty file or initialization failed).
                    self._error("Error: Input file is empty or could not be memory-mapped. Aborting unpack.")
                    return # Already handled by __enter__ re-raising, but good for defensive coding.
                self.scan_headers()
                self.classify_topology()
                self.extract_data()
                self._finalize_layout_metadata()
                self.save_manifest()
            self._info("Unpacking Complete!")
        except FileNotFoundError as e:
            self._error(f"File not found: {e}. Please check the input path.")
            # sys.exit(1) implicitly handled by top-level argparse calls
        except PermissionError as e:
            self._error(f"Permission denied: {e}. Please check file/directory permissions.")
        except ValueError as e:
            self._error(f"Data parsing error: {e}. The OEMINFO file might be corrupted or malformed.")
        except Exception as e:
            self._error(f"An unexpected error occurred during unpacking: {e}")


class OemPacker:
    """
    Handles repacking unpacked data (including manifest.json and content files)
    back into an OEMINFO image file. It reconstructs each data block based on
    the metadata in the manifest and the extracted files.
    """
    def __init__(self, input_dir: str, output_file: str, debug: bool = False, logger: Optional[CliLogger] = None):
        """
        Initializes an OemPacker instance.

        Args:
            input_dir (str): Path to the directory containing manifest.json and extracted file contents.
            output_file (str): Path to the output OEMINFO image file to be created.
        """
        self.input_dir: str = input_dir
        self.output_file: str = output_file
        self.manifest: Optional[Dict] = None
        self.debug: bool = debug
        self.logger: CliLogger = logger or CliLogger(debug)
        self.entries: List[Dict] = []

    def _debug(self, message: str) -> None:
        self.logger.debug(message)

    def _info(self, message: str) -> None:
        self.logger.info(message)

    def _error(self, message: str) -> None:
        self.logger.error(message)

    def _convert_manifest_hex_to_int(self, data: Union[Dict, List, Any]) -> Union[Dict, List, Any]:
        """
        Recursively converts hexadecimal string values (e.g., "0xABCD") back to integers
        within the loaded manifest structure.
        """
        if isinstance(data, Dict):
            return {k: self._convert_manifest_hex_to_int(v) for k, v in data.items()}
        if isinstance(data, List):
            return [self._convert_manifest_hex_to_int(elem) for elem in data]
        if isinstance(data, str) and data.startswith("0x"):
            try:
                return int(data, 16)
            except ValueError:
                # If it's not a valid hex, keep as string.
                return data
        return data

    def _build_filename_base(self, block_info: Dict) -> str:
        """
        Mirrors the unpacker naming scheme to infer content file names.
        """
        classification: str = block_info.get("classification", "UNKNOWN").lower()
        base: str = f"{block_info['id']}_{block_info['sub_id']}_{classification}"
        if block_info.get('is_active') is True:
            base += "_active"
        elif block_info.get('is_active') is False:
            base += "_inactive"
        return base

    def _find_first_existing(self, candidates: List[str]) -> Optional[str]:
        """
        Returns the first relative path that exists inside the input directory.
        """
        for rel_path in candidates:
            full_path: str = os.path.join(self.input_dir, rel_path)
            if os.path.exists(full_path):
                return rel_path
        return None

    def _resolve_tlv_files(self, base: str) -> List[str]:
        """
        Determines TLV part file paths in the expected order.
        """
        parts: List[str] = []
        suffixes: List[str] = ["tlv_data", "tlv_sign", "tlv_rand"]
        for idx, suffix in enumerate(suffixes):
            if idx == 0:
                candidates: List[str] = [f"{base}_{suffix}.txt", f"{base}_{suffix}.bin"]
            else:
                candidates = [f"{base}_{suffix}.bin"]
            rel: Optional[str] = self._find_first_existing(candidates)
            if not rel:
                if idx == 0:
                    raise FileNotFoundError(f"TLV data file missing for base '{base}'. Expected {candidates[0]} or {candidates[1]}.")
                continue
            parts.append(rel)
        unknown_prefix: str = f"{base}_tlv_unknown_"
        extra_files: List[str] = [
            name for name in os.listdir(self.input_dir)
            if name.startswith(unknown_prefix)
        ]
        parts.extend(sorted(extra_files))
        return parts

    def _resolve_signed_files(self, block_type: str, base: str) -> List[str]:
        """
        Determines file paths for signed/raw/random data blocks.
        """
        is_ascii: bool = block_type.startswith("ASCII")
        data_ext: str = ".txt" if is_ascii else ".bin"
        files: List[str] = [f"{base}_data{data_ext}"]
        if "SIGNED" in block_type:
            files.append(f"{base}_sign.bin")
        if block_type.endswith("_RANDOM"):
            files.append(f"{base}_tlv_rand.bin")
        return files

    def load_manifest(self) -> None:
        """
        Loads the manifest.json file from the input directory.
        """
        manifest_path: str = os.path.join(self.input_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            raise FileNotFoundError(f"Manifest file not found: {manifest_path}")
        try:
            with open(manifest_path, "r", encoding='utf-8') as f:
                raw_manifest = json.load(f)
            self.manifest = self._convert_manifest_hex_to_int(raw_manifest) # Convert hex strings to int
            self._debug(f"Manifest loaded from {manifest_path}")
            self._prepare_layout_entries()
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse manifest.json: {e}. File might be corrupted.")

    def _prepare_layout_entries(self) -> None:
        """
        Materializes the mixed data/padding entries from the loaded manifest.
        """
        if not self.manifest:
            return
        file_size: int = self.manifest.get("file_size", 0)
        raw_entries: List[Dict] = self.manifest.get("blocks", [])
        loaded_entries: List[Dict] = []
        for raw in sorted(raw_entries, key=lambda e: e.get("offset", 0)):
            entry: Dict = dict(raw)
            entry_type: Optional[str] = entry.get("type")
            if entry_type == "PADDING":
                loaded_entries.append(entry)
                continue
            layout: str = entry.get("layout", "REUSED")
            layout_upper: str = layout.upper()
            entry["layout"] = layout_upper
            entry["classification"] = layout_upper
            
            is_std_variant = (layout_upper == "STANDARD" or layout_upper == "STANDARD_COMPACT")
            entry["header_size"] = 512 if is_std_variant else 64
            
            if "header_padding_byte" not in entry:
                entry["header_padding_byte"] = 0xFF if is_std_variant else 0x00
            if "block_padding_byte" not in entry:
                entry["block_padding_byte"] = 0xFF if is_std_variant else 0x00
            loaded_entries.append(entry)
        self._assign_padding_lengths(loaded_entries, file_size)
        self._assign_active_status(loaded_entries)
        self.entries = loaded_entries
        self._compute_layout_constraints()

    def _assign_padding_lengths(self, entries: List[Dict], file_size: int) -> None:
        """
        Infers padding lengths for all padding entries using adjacency or profile data.
        Assumes entries are ordered by offset, allowing a single reverse pass.
        """
        if not entries:
            return

        next_offset: int = file_size
        for entry in reversed(entries):
            if entry.get("type") == "PADDING":
                start: int = entry.get("offset", 0)
                length: int = max(0, next_offset - start)
                if length == 0:
                    profile: Optional[str] = entry.get("profile")
                    if profile:
                        try:
                            length = _profile_string_length(profile)
                        except ValueError:
                            length = 0
                entry["_length"] = length
            next_offset = entry.get("offset", next_offset)

    def _assign_active_status(self, entries: List[Dict]) -> None:
        """
        Determines active/inactive status per (id, sub_id) based on maximum age.
        """
        groups: Dict[Tuple[int, int], List[Dict]] = collections.defaultdict(list)
        for entry in entries:
            if entry.get("type") == "PADDING":
                continue
            key: Tuple[int, int] = (entry.get("id"), entry.get("sub_id")) # type: ignore
            groups.setdefault(key, []).append(entry)
        for block_list in groups.values():
            if len(block_list) == 1:
                block_list[0]["is_active"] = True
                continue
            max_age: int = max(block.get("age", 0) for block in block_list)
            for block in block_list:
                block["is_active"] = (block.get("age", 0) == max_age)

    def _compute_layout_constraints(self) -> None:
        """
        Computes helper offsets for each data block to enforce non-overlap on repack.
        """
        if not self.entries:
            return
        file_size: int = self.manifest.get("file_size", 0) if self.manifest else 0

        next_data_offset: int = file_size
        for idx in range(len(self.entries) - 1, -1, -1):
            entry: Dict = self.entries[idx]
            if entry.get("type") == "PADDING":
                continue
            entry["_next_data_offset"] = next_data_offset
            next_data_offset = entry.get("offset", 0)

    def _read_content_file(self, rel_path: str) -> bytes:
        """
        Reads a content file at the specified relative path.

        Args:
            rel_path (str): The file path relative to the input directory.

        Returns:
            bytes: The byte data of the file content.

        Raises:
            FileNotFoundError: If the content file is not found.
            ValueError: If path traversal is detected.
        """
        if not is_safe_path(self.input_dir, rel_path):
            raise ValueError(f"Security: Attempted path traversal detected for '{rel_path}'. Blocked.")

        full_path: str = os.path.join(self.input_dir, rel_path)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"Content file not found: {full_path}")
        try:
            with open(full_path, "rb") as f:
                return f.read()
        except OSError as e:
            raise IOError(f"Failed to read content file '{full_path}': {e}. Please check permissions.") from e

    def _resolve_padding_byte(self, block_info: Dict) -> int:
        """
        Returns the effective padding byte for the OEM header region. If the manifest did not
        record a byte, fall back to the canonical defaults (standard=0xFF, reused=0x00).
        """
        val: Optional[int] = block_info.get('header_padding_byte')
        if val is None:
            return 0xFF if block_info.get('header_size', 64) == 512 else 0x00
        return val & 0xFF

    def _write_repeated_byte(self, outfile: BinaryIO, byte_val: int, length: int) -> int:
        """
        Writes `length` bytes filled with `byte_val` to the output file.
        """
        if length <= 0:
            return 0
        byte_val &= 0xFF
        chunk: bytes = bytes([byte_val]) * min(length, 1024 * 1024)
        remaining: int = length
        while remaining > 0:
            to_write: int = min(remaining, len(chunk))
            outfile.write(chunk[:to_write])
            remaining -= to_write
        return length

    def _write_padding_entry(self, outfile: BinaryIO, entry: Dict, cursor: int) -> int:
        """
        Writes padding entry bytes, accounting for previously consumed portions.
        """
        pad_len: Optional[int] = entry.get("_length")
        if pad_len is None:
            profile: Optional[str] = entry.get("profile")
            if profile:
                try:
                    pad_len = _profile_string_length(profile)
                except ValueError:
                    pad_len = 0
            else:
                pad_len = 0
            entry["_length"] = pad_len
        if pad_len <= 0:
            return 0
        start: int = entry.get("offset", 0)
        if cursor < start:
            raise ValueError(
                f"Current offset 0x{cursor:X} precedes padding start 0x{start:X}."
            )
        skip: int = cursor - start
        if skip >= pad_len:
            return 0
        remaining: int = pad_len - skip
        profile: Optional[str] = entry.get("profile")
        if profile:
            segments: Optional[List[Dict[str, int]]] = entry.get("_profile_segments")
            if segments is None:
                segments = _expand_profile_segments(profile, entry.get("offset", 0))
                entry["_profile_segments"] = segments
            return _write_profile_segments(outfile, segments, skip, remaining) # type: ignore
        return self._write_repeated_byte(outfile, DEFAULT_PADDING_BYTE, remaining)

    def reconstruct_block(self, block_info: Dict) -> bytes:
        """
        Reconstructs a single OEMINFO data block based on manifest metadata and extracted files.
        """
        block_type: str = str(block_info['type'])
        base_name: str = self._build_filename_base(block_info)
        content_data: bytes = b""

        if block_type in ["ASCII", "RAW"]:
            data_ext: str = ".txt" if block_type == "ASCII" else ".bin"
            rel_path: str = f"{base_name}_data{data_ext}"
            content_data = self._read_content_file(rel_path)
        elif block_type == "TLV":
            part_files: List[str] = self._resolve_tlv_files(base_name)
            reconstructed: bytes = b""
            for rel_path in part_files:
                part_data: bytes = self._read_content_file(rel_path)
                reconstructed += f"{len(part_data)}".encode('ascii') + b'\x00' + part_data
            content_data = reconstructed
        elif block_type.startswith("IMAGE"):
            custom_meta: Optional[Dict] = block_info.get("custom_meta")
            if not custom_meta:
                raise ValueError(f"Image block ID {block_info['id']} Sub {block_info['sub_id']} missing custom_meta.")
            
            # Handle 'ver' field: it could be an integer (from hex string in JSON) or a raw ASCII string.
            ver_val: Union[int, str] = custom_meta.get("ver", "")
            ver_bytes: bytes

            if isinstance(ver_val, int):
                try:
                    # Convert integer back to bytes (Big Endian to match hex representation)
                    ver_bytes = ver_val.to_bytes(12, byteorder='big')
                except OverflowError:
                    raise ValueError(f"Image Version value {ver_val} exceeds 12 bytes.")
            else:
                ver_str = str(ver_val)
                encoded_ver: bytes = ver_str.encode('ascii', errors='ignore')
                if len(encoded_ver) > 12:
                    self._warn(f"Image Version string '{ver_str}' exceeds 12 bytes and will be truncated.")
                ver_bytes = encoded_ver[:12].ljust(12, b'\x00')

            if block_type == "IMAGE_GZIP":
                gz_rel: str = f"{base_name}.gz"
                image_payload: bytes = self._read_content_file(gz_rel)
            else:
                rel_path: str = f"{base_name}.bmp"
                image_payload = self._read_content_file(rel_path)

            start_offset: int = 0x1A
            rand_adjust: Optional[int] = custom_meta.get('rand_adjust')
            if rand_adjust is None:
                raise ValueError(
                    f"Image block ID {block_info['id']} Sub {block_info['sub_id']} missing rand_adjust metadata."
                )
            magic: bytes = b'\x00\x00\x1f\x8b' if block_type == "IMAGE_GZIP" else b'\x00\x00BM'
            pre_data_pad: int = min(len(magic), max(0, start_offset - 24))
            end_offset: int = rand_adjust + start_offset + len(image_payload)
            header_bytes: bytes = IMAGE_HEADER_PACK_STRUCT.pack(
                start_offset,
                end_offset,
                rand_adjust,
                ver_bytes
            )
            header_bytes += magic[:pre_data_pad]
            data_prefix: bytes = magic[pre_data_pad:]
            if data_prefix and not image_payload.startswith(data_prefix):
                raise ValueError(
                    f"Image payload for block ID {block_info['id']} Sub {block_info['sub_id']} "
                    "does not match required magic prefix."
                )
            content_data = header_bytes + image_payload
        elif block_type in [
            "ASCII_SIGNED",
            "RAW_SIGNED",
            "ASCII_RANDOM",
            "RAW_RANDOM",
            "ASCII_SIGNED_RANDOM",
            "RAW_SIGNED_RANDOM"
        ]:
            files: List[str] = self._resolve_signed_files(block_type, base_name)
            rand_payload: Optional[bytes] = None
            if block_type.endswith("_RANDOM") and files:
                rand_file: str = files[-1]
                rand_payload = self._read_content_file(rand_file)
                files = files[:-1]
            for rel_path in files:
                content_data += self._read_content_file(rel_path)
            if rand_payload is not None:
                tlv_len_bytes: bytes = f"{len(rand_payload)}".encode('ascii') + b'\x00'
                content_data += tlv_len_bytes + rand_payload
        else:
            raise ValueError(f"Unsupported block type for packing: {block_type}")

        actual_payload_len: int = len(content_data)
        recorded_payload_len: int = block_info.get('len', 0)
        block_info['len'] = actual_payload_len

        header_size: int = block_info.get('header_size', 64)
        next_data_offset: int = block_info.get('_next_data_offset', block_info['offset'])
        max_total: int = max(0, next_data_offset - block_info['offset'])
        available_payload_space: int = max(0, max_total - header_size)

        if available_payload_space and actual_payload_len > available_payload_space:
            raise ValueError(
                f"Block ID {block_info['id']} Sub {block_info['sub_id']} payload (0x{actual_payload_len:X}) "
                f"exceeds available space 0x{available_payload_space:X}."
            )
        if recorded_payload_len and actual_payload_len > recorded_payload_len:
            self._warn(
                f"Block ID {block_info['id']} Sub {block_info['sub_id']} payload grew from "
                f"0x{recorded_payload_len:X} to 0x{actual_payload_len:X}. Padding will shrink accordingly."
            )

        header_pad_byte: int = self._resolve_padding_byte(block_info)
        pad_word: int = header_pad_byte | (header_pad_byte << 8) | (header_pad_byte << 16) | (header_pad_byte << 24)
        oem_header: bytes = BLOCK_HEADER_STRUCT.pack(
            b'OEM_INFO',
            block_info['version'],
            block_info['id'],
            block_info['sub_id'],
            actual_payload_len,
            block_info['age'],
            pad_word
        )
        if len(oem_header) < header_size:
            padding_byte: bytes = bytes([header_pad_byte & 0xFF])
            oem_header += padding_byte * (header_size - len(oem_header))

        return oem_header + content_data

    def pack(self) -> None:
        """
        Executes the repacking process for OEMINFO data.
        It loads the manifest, reconstructs each data block, and writes them sequentially.
        Uses atomic writing (write to temp -> rename) to prevent output corruption on failure.
        """
        self._info("Step 1: Loading manifest...")
        try:
            self.load_manifest()
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
            self._error(f"Failed to load manifest: {e}. Aborting packing.")
            return
        except Exception as e:
            self._error(f"An unexpected error occurred while loading manifest: {e}. Aborting packing.")
            return

        output_dir: str = os.path.dirname(self.output_file)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except OSError as e:
                self._error(f"Failed to create output directory '{output_dir}': {e}. Please check permissions.")
                return

        if not self.manifest:
            self._error("Manifest not loaded after successful loading attempt. This should not happen. Aborting.")
            return

        recorded_file_size: Optional[int] = self.manifest.get('file_size')
        if recorded_file_size is None:
            self._error("Manifest missing 'file_size'. Cannot determine target image size. Aborting packing.")
            return

        entries: List[Dict] = self.entries
        if not entries:
            self._error("Manifest contains no layout entries for packing. Aborting.")
            return

        # Atomic Write: Write to a temp file first
        temp_output_file = self.output_file + ".tmp"
        self._info(f"Step 2: Reconstructing and writing blocks to temporary file {temp_output_file}...")
        self._debug("Starting block reconstruction and streaming write for repack")

        layout_needs_ab_fill: bool = recorded_file_size < TOTAL_REGION_SIZE

        current_offset: int = 0
        try:
            with open(temp_output_file, "wb") as outfile:
                for entry in entries:
                    entry_type: Optional[str] = entry.get("type")
                    entry_offset: int = entry.get("offset", 0)
                    
                    if entry_type == "PADDING":
                        if current_offset < entry_offset:
                            raise ValueError(
                                f"Padding entry at 0x{entry_offset:X} is unreachable. Current write offset is 0x{current_offset:X}."
                            )
                        
                        self._debug(
                            f"Writing padding at 0x{entry_offset:X} (cursor 0x{current_offset:X})"
                        )
                        written: int = self._write_padding_entry(outfile, entry, current_offset)
                        current_offset += written
                        continue

                    if current_offset != entry_offset:
                        raise ValueError(
                            f"Block ID {entry['id']} Sub {entry['sub_id']} expected at "
                            f"0x{entry_offset:X} but current write offset is 0x{current_offset:X}."
                        )

                    self._debug(
                        f"Reconstructing and writing block ID {entry['id']} Sub {entry['sub_id']} at 0x{entry_offset:X}"
                    )
                    
                    # Reconstruct block immediately before writing (Streaming)
                    # Errors here will be caught by the outer try-except and trigger cleanup
                    block_bytes: bytes = self.reconstruct_block(entry)
                    
                    # Temporarily attach bytes to entry for the writing helper
                    entry["_block_bytes"] = block_bytes 
                    current_offset = self._write_block_with_alignment(outfile, entry, current_offset)
                    del entry["_block_bytes"]

                if recorded_file_size is not None and current_offset != recorded_file_size:
                    raise ValueError(
                        f"Final written size 0x{current_offset:X} does not match recorded manifest size 0x{recorded_file_size:X}."
                    )

                if layout_needs_ab_fill and recorded_file_size is not None:
                    fill_len: int = TOTAL_REGION_SIZE - recorded_file_size
                    if fill_len > 0:
                        self._write_repeated_byte(outfile, DEFAULT_PADDING_BYTE, fill_len)
                        current_offset += fill_len
                        self._info(
                            f"Output padded to cover AB region (data length 0x{TOTAL_REGION_SIZE:X})."
                        )
            
            # If we reached here, writing was successful. Now swap files.
            self._info(f"Step 3: Packing complete! Finalizing output to {self.output_file}")
            if os.path.exists(self.output_file):
                os.remove(self.output_file)
            os.rename(temp_output_file, self.output_file)
            self._debug(f"Total bytes written: 0x{current_offset:X}")

        except (ValueError, FileNotFoundError, IOError, OSError) as e:
            self._error(f"Packing failed: {e}. Aborting.")
            # Cleanup temp file
            if os.path.exists(temp_output_file):
                try:
                    os.remove(temp_output_file)
                    self._debug(f"Cleaned up temporary file {temp_output_file}")
                except OSError as cleanup_err:
                    self._warn(f"Failed to clean up partial file {temp_output_file}: {cleanup_err}")
            return
        except Exception as e:
            self._error(f"An unexpected error occurred during packing process: {e}")
            if os.path.exists(temp_output_file):
                try:
                    os.remove(temp_output_file)
                except OSError:
                    pass
            return

    def _write_block_with_alignment(self, outfile: BinaryIO, block_entry: Dict, current_offset: int) -> int:
        """
        Writes a reconstructed block and pads it to its required alignment boundary.
        """
        block_bytes: bytes = block_entry.get("_block_bytes", b"")
        outfile.write(block_bytes)
        current_offset += len(block_bytes)

        align: int = 0x1000 if block_entry.get("header_size", 64) == 512 else 0x80
        aligned_offset: int = (current_offset + (align - 1)) & ~(align - 1)
        tail_len: int = aligned_offset - current_offset
        if tail_len > 0:
            pad_byte: Optional[int] = block_entry.get("block_padding_byte")
            if pad_byte is None:
                pad_byte = block_entry.get("header_padding_byte", DEFAULT_PADDING_BYTE)
            self._write_repeated_byte(outfile, pad_byte, tail_len)
        return aligned_offset



# --- Helper functions for dispatching modes ---
def run_list_mode(args: argparse.Namespace) -> None:
    """
    Executes the 'list' mode, scanning the OEMINFO image and printing a summary
    of all data blocks without performing actual file extraction.
    Supports previewing ASCII text content.
    """
    logger: CliLogger = CliLogger(args.debug)
    logger.info(f"Listing blocks from {args.input}...")
    try:
        # Initialize OemUnpacker in dry_run mode to avoid actual file writing.
        unpacker: OemUnpacker = OemUnpacker(args.input, "", dry_run=True, debug=args.debug, logger=logger)
        with unpacker:
            unpacker.scan_headers()
            unpacker.classify_topology()
            # Run extract_data to populate block types and other metadata, even in dry_run mode.
            unpacker.extract_data()
            # Skip padding layout computation in list mode to speed up output; not needed for summaries.

            logger.info("Block Summary:")
            sorted_blocks: List[Dict] = sorted(
                unpacker.manifest['blocks'],
                key=lambda b: (b['id'], b['sub_id'], b.get('region', '')) # type: ignore
            )
            for block_info in sorted_blocks:
                logger.info(unpacker._format_block_summary(block_info))

                if block_info.get('ab_region_warning'):
                    logger.warn(block_info['ab_region_warning'])

                # If preview is requested and the block is text-like, display the preview.
                if args.preview and 'text_preview' in block_info:
                    label: str = block_info.get('text_preview_label', "ASCII")
                    logger.info(f"  {label}:")
                    logger.info(f"    {block_info['text_preview']}")
                    # Note: In dry_run mode, actual content files are not extracted,
                    # so we can only rely on the 'text_preview' field.
            logger.info("Listing Complete.")
    except FileNotFoundError as e:
        logger.error(f"Input file not found: {e}. Please check the path.")
        exit(1)
    except PermissionError as e:
        logger.error(f"Permission denied: {e}. Please check file permissions.")
        exit(1)
    except ValueError as e:
        logger.error(f"Data parsing error during listing: {e}. The OEMINFO file might be corrupted or malformed.")
        exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred during listing: {e}")
        exit(1)

def run_unpack_mode(args: argparse.Namespace) -> None:
    """
    Executes the 'unpack' mode, unpacking the OEMINFO image into the specified output directory.
    """
    file_to_process: str = args.input
    output_target: str = args.output
    
    logger: CliLogger = CliLogger(args.debug)
    if not os.path.exists(file_to_process):
        logger.error(f"Input file '{file_to_process}' for unpacking not found.")
        exit(1)

    # Validation for unpack mode: check output_target existence and type
    if os.path.exists(output_target):
        if os.path.isfile(output_target):
            logger.error(f"Output path '{output_target}' is an existing file. Please remove it manually or specify a directory.")
            exit(1)
        elif os.path.isdir(output_target):
            if not args.force:
                logger.error(f"Output directory '{output_target}' already exists. Use --force to unpack into it.")
                exit(1)
            else:
                logger.info(f"Output directory '{output_target}' already exists. --force provided, unpacking into it.")
        else:
            # Handle other types like symlinks to files, block devices etc. as an error.
            logger.error(f"Output path '{output_target}' exists but is not a directory. Please ensure it's a writable directory or does not exist.")
            exit(1)

    unpacker: OemUnpacker = OemUnpacker(file_to_process, output_target, debug=args.debug, logger=logger)
    try:
        unpacker.run()
    except Exception as e:
        logger.error(f"Unpacking failed: {e}")
        exit(1)

def run_repack_mode(args: argparse.Namespace) -> None:
    """
    Executes the 'repack' mode, repacking extracted OEMINFO data from a directory
    back into an OEMINFO image file.
    Requires a manifest.json file to be present in the input directory.
    """
    input_directory: str = args.input
    output_image_file: str = args.output
    
    logger: CliLogger = CliLogger(args.debug)
    if not os.path.isdir(input_directory):
        logger.error(f"Input directory '{input_directory}' for repacking not found or is not a directory.")
        exit(1)
    # Check if manifest.json exists inside the input directory.
    if not os.path.exists(os.path.join(input_directory, "manifest.json")):
        logger.error(f"'manifest.json' not found in input directory '{input_directory}'.")
        exit(1)

    # Handle existing output file for repack mode.
    if os.path.exists(output_image_file):
        if os.path.isdir(output_image_file):
            logger.error(f"Output path '{output_image_file}' is a directory. Please specify a file path.")
            exit(1)
        if not args.force:
            logger.error(f"Output file '{output_image_file}' already exists. Use --force to overwrite it.")
            exit(1)
        else:
            try:
                os.remove(output_image_file) # Remove existing file if --force is used
            except OSError as e:
                logger.error(f"Failed to remove existing output file '{output_image_file}': {e}. Please check permissions.")
                exit(1)

    packer: OemPacker = OemPacker(input_directory, output_image_file, debug=args.debug, logger=logger)
    try:
        packer.pack()
    except Exception as e:
        logger.error(f"Repacking failed: {e}")
        exit(1)


if __name__ == "__main__":
    main_parser = argparse.ArgumentParser(
        description="HUAWEI/HONOR OEM Info Unpacker/Packer Tool",
        formatter_class=argparse.RawTextHelpFormatter  # Allows multiline text and formatting in description.
    )
    
    # Global arguments
    main_parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {VERSION}",
                             help="Show program's version number and exit.")
    subparsers = main_parser.add_subparsers(dest="mode", help="Operation mode. Use '<mode> -h' for mode-specific help.")

    # List mode parser
    list_parser = subparsers.add_parser("list", help="List all data blocks from FILE without extracting.")
    list_parser.add_argument("-i", "--input", default=DEFAULT_FILE_PATH, 
                             help=f"Input oeminfo.img file path (default: {DEFAULT_FILE_PATH})")
    list_parser.add_argument("-p", "--preview", action="store_true", 
                             help="Preview ASCII data content for text-based blocks.")
    list_parser.add_argument("-d", "--debug", action="store_true",
                             help="Enable debug logging.")
    list_parser.set_defaults(func=run_list_mode)  # Assign a function to be called.

    # Unpack mode parser
    unpack_parser = subparsers.add_parser("unpack", help="Unpack oeminfo.img into an output directory.")
    unpack_parser.add_argument("-i", "--input", default=DEFAULT_FILE_PATH, 
                               help=f"Input oeminfo.img file path (default: {DEFAULT_FILE_PATH})")
    unpack_parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT_DIR, 
                               help=f"Output directory path (default: {DEFAULT_OUTPUT_DIR})")
    unpack_parser.add_argument("-f", "--force", action="store_true",
                               help="Force removal of the output directory if it exists before unpacking.")
    unpack_parser.add_argument("-d", "--debug", action="store_true",
                               help="Enable debug logging.")
    unpack_parser.set_defaults(func=run_unpack_mode)

    # Repack mode parser
    repack_parser = subparsers.add_parser("repack", help="Repack extracted oeminfo data from a directory into an oeminfo.img.")
    repack_parser.add_argument("-i", "--input", default=DEFAULT_OUTPUT_DIR,
                               help=f"Input directory containing manifest.json (default: {DEFAULT_OUTPUT_DIR})")
    repack_parser.add_argument("-o", "--output", default="oeminfo_repacked.img",
                               help="Output oeminfo.img file path (default: oeminfo_repacked.img)")
    repack_parser.add_argument("-f", "--force", action="store_true",
                               help="Force removal of the output file if it exists before repacking.")
    repack_parser.add_argument("-d", "--debug", action="store_true",
                               help="Enable debug logging.")
    repack_parser.set_defaults(func=run_repack_mode)

    args = main_parser.parse_args()

    # Dispatch logic
    if hasattr(args, 'func'):
        args.func(args)
    else:
        main_parser.print_help()  # If no subcommand is specified, print the main help message.

