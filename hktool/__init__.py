"""
Huawei and Kirin Universal Flash, Extract, Backup and Testpoint Toolkit
A comprehensive, unified, high-performance toolkit for Huawei and HiSilicon Kirin devices.
"""

__version__ = "2.3.0"
__author__ = "Antigravity DeepMind Team and Open-Source Contributors"

# Automatically inject official Huawei Fastboot into environment
from .core.binary_manager import BinaryManager
BinaryManager.init_environment()

