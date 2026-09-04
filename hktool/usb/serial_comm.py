"""
Serial COM port manager for Huawei VCOM (Testpoint) and eRecovery / DBAdapter interfaces.
Supports HDLC framing, byte escaping, and high-throughput transfers.
"""
from __future__ import annotations

import re
import struct
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import serial
import serial.tools.list_ports


from ..config import (
    DBADAPTER_DESC,
    HDLC_ESC,
    HDLC_ESC_ESC,
    HDLC_ESC_FLAG,
    HDLC_FLAG,
    HUAWEI_VID,
    IDT_VCOM_PID,
)
from ..core.crypto import Crc16
from ..core.exceptions import UsbProtocolError


@dataclass
class SerialPortInfo:
    port: str
    description: str
    hwid: str
    vid: Optional[int]
    pid: Optional[int]
    is_vcom: bool = False
    is_dbadapter: bool = False


class SerialPortManager:
    """Manages discovery and connection to Huawei serial devices."""

    @staticmethod
    def list_ports() -> List[SerialPortInfo]:
        """Enumerate all available COM ports and identify Huawei devices."""
        ports: List[SerialPortInfo] = []
        for p in serial.tools.list_ports.comports():
            vid = p.vid
            pid = p.pid
            desc = p.description or ""
            hwid = p.hwid or ""

            is_vcom = (vid == HUAWEI_VID and pid == IDT_VCOM_PID) or "USB COM 1.0" in desc or "3609" in hwid
            is_dbadapter = (vid == HUAWEI_VID and (DBADAPTER_DESC in desc or "DBAdapter" in desc))

            ports.append(SerialPortInfo(
                port=p.device,
                description=desc,
                hwid=hwid,
                vid=vid,
                pid=pid,
                is_vcom=is_vcom,
                is_dbadapter=is_dbadapter
            ))
        return ports

    @classmethod
    def find_vcom_port(cls) -> Optional[str]:
        """Find active HUAWEI USB COM 1.0 (Testpoint) port name."""
        for p in cls.list_ports():
            if p.is_vcom:
                return p.port
        return None

    @classmethod
    def find_dbadapter_port(cls) -> Optional[str]:
        """Find active DBAdapter Reserved Interface (USB Upgrade / eRecovery) port name."""
        for p in cls.list_ports():
            if p.is_dbadapter:
                return p.port
        return None


class HdlcSerialTransport:
    """HDLC framing and serial communication transport for Huawei USB Upgrade."""

    def __init__(self, port_name: str, baud_rate: int = 115200, timeout: float = 5.0):
        self.port_name = port_name
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.serial: Optional[serial.Serial] = None

    def open(self) -> None:
        self.serial = serial.Serial(
            port=self.port_name,
            baudrate=self.baud_rate,
            timeout=self.timeout,
            write_timeout=self.timeout
        )
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()

    def close(self) -> None:
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.serial = None

    @staticmethod
    def encode_hdlc(payload: bytes) -> bytes:
        """Escape payload and wrap with HDLC 0x7E framing and X.25 CRC."""
        crc_bytes = Crc16.x25_bytes(payload)
        full_data = payload + crc_bytes
        escaped = bytearray([HDLC_FLAG])
        for b in full_data:
            if b == HDLC_FLAG:
                escaped.extend([HDLC_ESC, HDLC_ESC_FLAG])
            elif b == HDLC_ESC:
                escaped.extend([HDLC_ESC, HDLC_ESC_ESC])
            else:
                escaped.append(b)
        escaped.append(HDLC_FLAG)
        return bytes(escaped)

    @staticmethod
    def decode_hdlc(frame: bytes) -> bytes:
        """Unescape an HDLC frame and verify X.25 CRC."""
        data = frame.strip(bytes([HDLC_FLAG]))
        unescaped = bytearray()
        i = 0
        while i < len(data):
            if data[i] == HDLC_ESC and i + 1 < len(data):
                if data[i+1] == HDLC_ESC_FLAG:
                    unescaped.append(HDLC_FLAG)
                elif data[i+1] == HDLC_ESC_ESC:
                    unescaped.append(HDLC_ESC)
                i += 2
            else:
                unescaped.append(data[i])
                i += 1

        if len(unescaped) < 2:
            raise UsbProtocolError("HDLC frame too short")
        payload = bytes(unescaped[:-2])
        rec_crc = struct.unpack("<H", unescaped[-2:])[0]
        calc_crc = Crc16.x25(payload)
        if rec_crc != calc_crc:
            raise UsbProtocolError(f"HDLC CRC mismatch (expected {hex(calc_crc)}, got {hex(rec_crc)})")
        return payload
