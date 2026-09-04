"""
Structured exception classes for the toolkit.
"""

class HuaweiToolkitError(Exception):
    """Base exception for all toolkit errors."""
    pass

# Alias for backward compatibility
ToolkitError = HuaweiToolkitError

class FirmwareFormatError(HuaweiToolkitError):
    """Raised when firmware or UPDATE.APP format is invalid or corrupted."""
    pass

class SparseImageError(HuaweiToolkitError):
    """Raised when an Android sparse image is malformed or invalid."""
    pass

class FastbootError(HuaweiToolkitError):
    """Raised on Fastboot communication or flashing failure."""
    pass

class VcomError(HuaweiToolkitError):
    """Raised during USB COM 1.0 (Testpoint) injection operations."""
    pass

class ERecoveryError(HuaweiToolkitError):
    """Raised during Huawei eRecovery / DLOAD USB Upgrade communication."""
    pass

class OemInfoError(HuaweiToolkitError):
    """Raised on OEMINFO parsing, editing or repacking failure."""
    pass

class DeviceNotFoundError(HuaweiToolkitError):
    """Raised when the expected device mode or port is not detected."""
    pass

class PartitionError(HuaweiToolkitError):
    """Raised when a partition table is invalid or missing requested partition."""
    pass

class UsbProtocolError(HuaweiToolkitError):
    """Raised during USB serial or bulk protocol transfer errors."""
    pass
