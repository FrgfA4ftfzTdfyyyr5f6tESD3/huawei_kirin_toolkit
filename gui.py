"""
Huawei & Kirin Universal Toolkit - Ultra-Modern PySide6 Edition (v6.2.0 Free Edition)
Clean Enterprise White Architecture (Crisp High-DPI, Full-Height Word-Wrapped Sidebar, Engineering DataTables).
100% English Interface. Zero UI Freezing.
"""
from __future__ import annotations

import os
import re
import sys
import shutil
import subprocess
import threading
import webbrowser
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import (
    QCoreApplication,
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QDesktopServices,
    QFont,
    QIcon,
    QKeySequence,
    QPalette,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# Core toolkit imports
from hktool.config import (
    FASTBOOT_BIN,
    FASTBOOT_SOURCE,
    HUAWEI_REGIONS,
    TOOL_NAME,
    TOOL_VERSION,
)
from hktool.core.driver_manager import DriverManager, DriverStatusItem
from hktool.core.utils import human_size
from hktool.erofs import (
    HuaweiErofs,
    convert_raw_to_sparse,
    convert_sparse_to_raw,
    repack_erofs,
    unpack_erofs,
)
from hktool.flashers.board_flasher import BoardSoftwareFlasher, BoardSoftwareParser
from hktool.flashers.sigma_board_writer import SigmaBoardWriter, WritePartitionItem
from hktool.kirin.chipsets import KIRIN_PROFILES
from hktool.nvme import HisiNveImage, NveClient, NveDeviceInfo
from hktool.oeminfo.editor import OemInfoEditor
from hktool.oeminfo.oeminfo_engine import CliLogger, OemPacker, OemUnpacker
from hktool.ptable import (
    GPTTable,
    PartitionEntry,
    PTableAnalysis,
    PTableResizer,
    PTableValidator,
    ResizeResult,
)
from hktool.usb.detector import DeviceDetector, DeviceState
from hktool.kirin.kirin_710_protection import (
    KIRIN_710_FASTBOOT_PATCHES,
    execute_kirin_710_fastboot_patches,
)
from hktool.companions.companion_manager import CompanionItem, CompanionManager
from hktool.cli_tools.headless_manager import HeadlessToolItem, HeadlessToolManager


# Global Version String
EDITION_LABEL = "6.2.0 Free Edition"


# =============================================================================
# CLEAN MODERN ENTERPRISE LIGHT / WHITE STYLESHEET (High-DPI Crystal Clear)
# =============================================================================
ENTERPRISE_LIGHT_QSS = """
/* Base Window & Global Fonts */
QMainWindow, QWidget#centralWidget {
    background-color: #F8FAFC;
    color: #0F172A;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px;
}

/* Sidebar Frame */
QFrame#sidebarFrame {
    background-color: #F8FAFC;
    border-right: 1px solid #E2E8F0;
}

/* Top Header Bar */
QFrame#topHeaderFrame {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E2E8F0;
}

/* Sub-Navbar Container Frame */
QFrame#subNavBarContainer {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
}

/* Standard Buttons */
QPushButton {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #F1F5F9;
    border-color: #94A3B8;
    color: #0F172A;
}

QPushButton:pressed {
    background-color: #E2E8F0;
}

/* Sidebar Master Tier Navigation Buttons (Distinct Borders, Generous Padding) */
QPushButton.TierBtn {
    text-align: left;
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 6px 8px;
}

QPushButton.TierBtn:hover {
    background-color: #F1F5F9;
    border: 1px solid #CBD5E1;
}

QPushButton.TierBtn[active="true"] {
    background-color: #EFF6FF;
    border: 1.5px solid #BFDBFE;
    border-left: 5px solid #2563EB;
}

/* High-Tech Operational Action Buttons */
/* Primary Blue */
QPushButton.BtnPrimary {
    background-color: #2563EB;
    color: #FFFFFF;
    border: 1px solid #1D4ED8;
}
QPushButton.BtnPrimary:hover {
    background-color: #1D4ED8;
    border-color: #1E40AF;
}
QPushButton.BtnPrimary:pressed {
    background-color: #1E3A8A;
}

/* Success Emerald Green */
QPushButton.BtnSuccess {
    background-color: #059669;
    color: #FFFFFF;
    border: 1px solid #047857;
}
QPushButton.BtnSuccess:hover {
    background-color: #047857;
    border-color: #065F46;
}
QPushButton.BtnSuccess:pressed {
    background-color: #064E3B;
}

/* Danger Rose Red */
QPushButton.BtnDanger {
    background-color: #DC2626;
    color: #FFFFFF;
    border: 1px solid #B91C1C;
}
QPushButton.BtnDanger:hover {
    background-color: #B91C1C;
}
QPushButton.BtnDanger:pressed {
    background-color: #991B1B;
}

/* Warning Amber */
QPushButton.BtnWarning {
    background-color: #D97706;
    color: #FFFFFF;
    border: 1px solid #B45309;
}
QPushButton.BtnWarning:hover {
    background-color: #B45309;
}
QPushButton.BtnWarning:pressed {
    background-color: #92400E;
}

/* Input Fields & Combos */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 6px 9px;
    font-size: 12.5px;
    selection-background-color: #2563EB;
    selection-color: #FFFFFF;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1.5px solid #2563EB;
    background-color: #FFFFFF;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    selection-background-color: #EFF6FF;
    selection-color: #1D4ED8;
    padding: 4px;
}

/* Checkboxes */
QCheckBox {
    color: #0F172A;
    font-weight: 600;
    spacing: 7px;
}
QCheckBox::indicator {
    width: 17px;
    height: 17px;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    background-color: #FFFFFF;
}
QCheckBox::indicator:checked {
    background-color: #2563EB;
    border-color: #1D4ED8;
}

/* Professional Engineering Data Table */
QTableWidget {
    background-color: #FFFFFF;
    alternate-background-color: #F8FAFC;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    gridline-color: #E2E8F0;
    font-family: -apple-system, "Segoe UI", sans-serif;
    font-size: 12px;
    selection-background-color: #EFF6FF;
    selection-color: #1D4ED8;
}

QTableWidget::item {
    padding: 5px 8px;
    border-bottom: 1px solid #E2E8F0;
}

QTableWidget::item:selected {
    background-color: #EFF6FF;
    color: #1D4ED8;
    font-weight: 600;
}

QTableWidget::item:hover {
    background-color: #F1F5F9;
}

QHeaderView::section {
    background-color: #F1F5F9;
    color: #334155;
    font-weight: 700;
    font-size: 11.5px;
    padding: 7px 8px;
    border: none;
    border-right: 1px solid #E2E8F0;
    border-bottom: 2px solid #CBD5E1;
}

/* Tree Widgets */
QTreeWidget {
    background-color: #FFFFFF;
    alternate-background-color: #F8FAFC;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    font-size: 12px;
}
QTreeWidget::item {
    padding: 5px 4px;
    border-bottom: 1px solid #F1F5F9;
}
QTreeWidget::item:selected {
    background-color: #EFF6FF;
    color: #1D4ED8;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: #F8FAFC;
    width: 9px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #CBD5E1;
    min-height: 22px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #94A3B8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: #F8FAFC;
    height: 9px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #CBD5E1;
    min-width: 22px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #94A3B8;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Progress Bar */
QProgressBar {
    background-color: #F1F5F9;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    text-align: center;
    color: #0F172A;
    font-weight: 700;
    height: 20px;
}
QProgressBar::chunk {
    background-color: #10B981;
    border-radius: 5px;
}

/* Terminal Console (Developer Dark Slate for Real-Time Logs) */
QPlainTextEdit.TerminalConsole {
    background-color: #0F172A;
    color: #4ADE80;
    font-family: "JetBrains Mono", "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
    border: 1px solid #1E293B;
    border-radius: 6px;
    padding: 8px;
}

/* Sub-Navbar Horizontal Tab Buttons (Responsive & Full Width) */
QPushButton.SubNavBtn {
    background-color: #FFFFFF;
    color: #64748B;
    border: none;
    border-top: 3px solid transparent;
    border-bottom: 2px solid transparent;
    padding: 8px 6px;
    font-weight: 600;
    font-size: 11.5px;
    border-radius: 0px;
}
QPushButton.SubNavBtn:hover {
    background-color: #F8FAFC;
    color: #0F172A;
}
QPushButton.SubNavBtn[active="true"] {
    background-color: #EFF6FF;
    color: #2563EB;
    border-top: 3px solid #2563EB;
    border-bottom: 2px solid #2563EB;
    font-weight: 700;
}

/* Badges */
QLabel.BadgeGreen {
    background-color: #ECFDF5;
    color: #047857;
    border: 1px solid #A7F3D0;
    border-radius: 4px;
    padding: 2px 7px;
    font-weight: 700;
    font-size: 11px;
}
QLabel.BadgeGray {
    background-color: #F1F5F9;
    color: #475569;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    padding: 2px 7px;
    font-weight: 700;
    font-size: 11px;
}
QLabel.BadgeBlue {
    background-color: #EFF6FF;
    color: #1D4ED8;
    border: 1px solid #BFDBFE;
    border-radius: 4px;
    padding: 2px 7px;
    font-weight: 700;
    font-size: 11px;
}
QLabel.BadgeAmber {
    background-color: #FFFBEB;
    color: #B45309;
    border: 1px solid #FDE68A;
    border-radius: 4px;
    padding: 2px 7px;
    font-weight: 700;
    font-size: 11px;
}
"""


# =============================================================================
# HIGH-VISIBILITY WORD-WRAPPING SIDEBAR TIER BUTTON COMPONENT
# =============================================================================
class SidebarTierButton(QPushButton):
    """
    Sidebar workstation tier button featuring generous breathing room, distinct borders,
    large bold 11pt headings, readable 9.5pt multi-line subtitles, and active indicators.
    """
    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setProperty("class", "TierBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(78)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)

        self.lbl_title = QLabel(title)
        self.lbl_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.lbl_title.setStyleSheet("color: #0F172A; background: transparent; border: none;")
        self.lbl_title.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setFont(QFont("Segoe UI", 9.5))
        self.lbl_sub.setStyleSheet("color: #475569; background: transparent; border: none; line-height: 1.3;")
        self.lbl_sub.setWordWrap(True)
        self.lbl_sub.setAttribute(Qt.WA_TransparentForMouseEvents)

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_sub)

    def set_active(self, active: bool):
        self.setProperty("active", "true" if active else "false")
        if active:
            self.lbl_title.setStyleSheet("color: #1D4ED8; font-weight: bold; background: transparent; border: none;")
            self.lbl_sub.setStyleSheet("color: #2563EB; font-weight: 600; background: transparent; border: none;")
        else:
            self.lbl_title.setStyleSheet("color: #0F172A; font-weight: bold; background: transparent; border: none;")
            self.lbl_sub.setStyleSheet("color: #475569; background: transparent; border: none;")
        self.style().unpolish(self)
        self.style().polish(self)


# =============================================================================
# COMPACT ENTERPRISE CARD CONTAINER COMPONENT
# =============================================================================
class EnterpriseCard(QFrame):
    """
    Standardized, clean-bordered card container with a distinct header bar,
    title, subtitle, badge, and compact internal padding to eliminate vertical scrolling.
    """
    def __init__(
        self,
        title: str,
        subtitle: Optional[str] = None,
        badge_text: Optional[str] = None,
        badge_class: str = "BadgeBlue",
        parent=None
    ):
        super().__init__(parent)
        self.setObjectName("enterpriseCard")
        self.setStyleSheet("""
            QFrame#enterpriseCard {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
        """)

        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # 1. Card Header Bar
        header_bar = QFrame()
        header_bar.setStyleSheet("""
            background-color: #F8FAFC;
            border-top-left-radius: 7px;
            border-top-right-radius: 7px;
            border-bottom: 1px solid #E2E8F0;
        """)
        h_layout = QHBoxLayout(header_bar)
        h_layout.setContentsMargins(12, 6, 12, 6)
        h_layout.setSpacing(8)

        lbl_title = QLabel(title)
        lbl_title.setFont(QFont("Segoe UI", 9.5, QFont.Bold))
        lbl_title.setStyleSheet("color: #1E3A8A; background: transparent; border: none;")
        h_layout.addWidget(lbl_title)

        if subtitle:
            lbl_sub = QLabel(f"• {subtitle}")
            lbl_sub.setFont(QFont("Segoe UI", 8.5))
            lbl_sub.setStyleSheet("color: #64748B; background: transparent; border: none;")
            h_layout.addWidget(lbl_sub)

        h_layout.addStretch()

        if badge_text:
            badge = QLabel(badge_text)
            badge.setProperty("class", badge_class)
            h_layout.addWidget(badge)

        card_layout.addWidget(header_bar)

        # 2. Card Content Body
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(12, 8, 12, 10)
        self.body_layout.setSpacing(8)
        card_layout.addWidget(self.body)

    def add_widget(self, widget: QWidget):
        self.body_layout.addWidget(widget)

    def add_layout(self, layout):
        self.body_layout.addLayout(layout)


# =============================================================================
# PROFESSIONAL ENGINEERING DATA TABLE WIDGET
# =============================================================================
class EngineeringDataTable(QTableWidget):
    """
    Standardized, clean-bordered data table with alternating rows,
    distinct cell separators, hover highlighting, and comfortable row heights.
    """
    def __init__(self, rows: int = 0, columns: int = 0, parent=None):
        super().__init__(rows, columns, parent)
        self.setShowGrid(True)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(30)


# =============================================================================
# ASYNCHRONOUS WORKER THREADS (NO UI FREEZING & CLEAN SHUTDOWN)
# =============================================================================
class GenericWorker(QThread):
    """Executes long-running background tasks without freezing the Qt main loop."""
    log_signal = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, func: Callable, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            self.func(self.log_signal.emit, *self.args, **self.kwargs)
            self.finished_signal.emit(True, "Execution completed successfully.")
        except Exception as ex:
            self.finished_signal.emit(False, str(ex))


class DeviceMonitorWorker(QThread):
    """
    Continuously monitors USB hardware connection states in a non-blocking loop.
    Responsive stop() ensures clean shutdown with zero QThread destruction warnings.
    """
    device_state_changed = Signal(object)

    def __init__(self, interval_ms: int = 2500):
        super().__init__()
        self.interval_ms = interval_ms
        self._is_running = True

    def run(self):
        while self._is_running and not self.isInterruptionRequested():
            try:
                state = DeviceDetector.detect()
                self.device_state_changed.emit(state)
            except Exception:
                pass
            # Sleep in short 50ms intervals so it exits immediately when stopped!
            for _ in range(self.interval_ms // 50):
                if not self._is_running or self.isInterruptionRequested():
                    return
                self.msleep(50)

    def stop(self):
        self._is_running = False
        self.requestInterruption()
        self.quit()
        self.wait(1000)


# =============================================================================
# RESPONSIVE FULL-WIDTH SUB-NAVBAR (setExpanding = True)
# =============================================================================
class SubNavBar(QFrame):
    """
    Horizontal top sub-navbar with expanding buttons filling 100% width.
    Active tab displays high-tech #2563EB accent indicators.
    """
    tab_changed = Signal(int)

    def __init__(self, items: List[Tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setObjectName("subNavBarContainer")
        self.buttons: List[QPushButton] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        for idx, (key, title) in enumerate(items):
            btn = QPushButton(title)
            btn.setProperty("class", "SubNavBtn")
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(title)
            btn.clicked.connect(lambda checked=False, i=idx: self.select_tab(i))
            layout.addWidget(btn)
            self.buttons.append(btn)

        if self.buttons:
            self.select_tab(0)

    def select_tab(self, index: int):
        for i, btn in enumerate(self.buttons):
            is_active = (i == index)
            btn.setProperty("active", "true" if is_active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.tab_changed.emit(index)


# =============================================================================
# MAIN WINDOW: CLEAN ENTERPRISE WHITE UI (6.2.0 Free Edition)
# =============================================================================
class UnifiedToolkitWindow(QMainWindow):
    """
    Unified Tri-Tier Huawei & Kirin Firmware Engineering Studio.
    Written from the ground up in PySide6 / Qt6 with Clean Enterprise Light Styling.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{TOOL_NAME} - {EDITION_LABEL}")
        self.resize(1360, 900)
        self.setMinimumSize(1120, 720)

        # Managers
        self.companion_manager = CompanionManager()
        self.headless_manager = HeadlessToolManager()

        # UI references
        self.sidebar_buttons: Dict[str, SidebarTierButton] = {}
        self.companion_status_badges: Dict[str, QLabel] = {}
        self.companion_launch_btns: Dict[str, QPushButton] = {}

        # Build UI Hierarchy
        self._build_main_layout()

        # Start Background Device Monitor
        self.device_monitor = DeviceMonitorWorker(interval_ms=2500)
        self.device_monitor.device_state_changed.connect(self._on_device_state_updated)
        self.device_monitor.start()

        # Initial log
        self.log(f"⚡ {TOOL_NAME} initialized successfully.")
        self.log(f"   Fastboot Binary: {FASTBOOT_SOURCE} ({FASTBOOT_BIN})")
        self.log(f"   Version: {EDITION_LABEL} (High-DPI Crystal Clear).")

    def closeEvent(self, event):
        """Cleanly terminate background monitoring thread on exit without warnings."""
        if hasattr(self, "device_monitor") and self.device_monitor.isRunning():
            self.device_monitor.stop()
        event.accept()

    # -------------------------------------------------------------------------
    # MAIN LAYOUT (Header, Sidebar, Content Stack)
    # -------------------------------------------------------------------------
    def _build_main_layout(self):
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Top Header Bar
        root_layout.addWidget(self._create_top_header())

        # 2. Body Splitter (Sidebar + Content Stack)
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Left Sidebar (280px fixed width for full-size word-wrapped buttons)
        body_layout.addWidget(self._create_sidebar())

        # Right Content Stack
        self.master_stack = QStackedWidget()
        self.master_stack.addWidget(self._create_tier1_page())
        self.master_stack.addWidget(self._create_tier2_page())
        self.master_stack.addWidget(self._create_tier3_page())
        self.master_stack.addWidget(self._create_about_page())

        body_layout.addWidget(self.master_stack, stretch=1)
        root_layout.addWidget(body_widget, stretch=1)

        # Activate Tier 1 by default
        self._select_master_tier("tier1")

    # -------------------------------------------------------------------------
    # TOP HEADER BAR
    # -------------------------------------------------------------------------
    def _create_top_header(self) -> QWidget:
        header_frame = QFrame()
        header_frame.setObjectName("topHeaderFrame")
        layout = QHBoxLayout(header_frame)
        layout.setContentsMargins(18, 8, 18, 8)
        layout.setSpacing(12)

        # Left: Branding
        lbl_brand = QLabel("⚡ HUAWEI & KIRIN UNIVERSAL TOOLKIT")
        lbl_brand.setFont(QFont("Segoe UI", 12, QFont.Bold))
        lbl_brand.setStyleSheet("color: #1E40AF;")
        layout.addWidget(lbl_brand)

        # Exact 6.2.0 Free Edition Badge
        lbl_ver = QLabel(EDITION_LABEL)
        lbl_ver.setProperty("class", "BadgeBlue")
        layout.addWidget(lbl_ver)

        layout.addStretch()

        # Right: Hardware Connection Guard Pill
        self.lbl_device_status = QLabel("○ Scanning Hardware...")
        self.lbl_device_status.setProperty("class", "BadgeGray")
        layout.addWidget(self.lbl_device_status)

        btn_scan = QPushButton("🔍 Scan Device")
        btn_scan.setProperty("class", "BtnPrimary")
        btn_scan.setCursor(Qt.PointingHandCursor)
        btn_scan.clicked.connect(self._manual_scan_device)
        layout.addWidget(btn_scan)

        return header_frame

    # -------------------------------------------------------------------------
    # LEFT SIDEBAR (Width 280px with Large, Framed, Word-Wrapped Tier Buttons)
    # -------------------------------------------------------------------------
    def _create_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebarFrame")
        sidebar.setFixedWidth(280)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(10)

        lbl_nav = QLabel("WORKSTATION TIERS")
        lbl_nav.setFont(QFont("Segoe UI", 8.5, QFont.Bold))
        lbl_nav.setStyleSheet("color: #64748B; letter-spacing: 1px; padding-left: 4px;")
        layout.addWidget(lbl_nav)

        tier_data = [
            ("tier1", "🛡️ 1. Native In-House Core", "Firmware, GPT, NVE, OEMINFO & Flash Engines"),
            ("tier2", "🚀 2. Standalone Companions", "Kirin-Tool, FastbootFlasher, Android Utility Hub"),
            ("tier3", "⚡ 3. Common CLI & Utilities", "CLI Tools, Drivers, Firmware Downloader & Console"),
        ]

        for key, title, sub in tier_data:
            btn = SidebarTierButton(title, sub)
            btn.clicked.connect(lambda checked=False, k=key: self._select_master_tier(k))
            layout.addWidget(btn)
            self.sidebar_buttons[key] = btn

        layout.addStretch()

        # Bottom Architecture & Credits Button (Framed and matched)
        btn_about = SidebarTierButton("ℹ️ Architecture & Credits", "Attribution, References & Community Hub")
        btn_about.clicked.connect(lambda: self._select_master_tier("about"))
        layout.addWidget(btn_about)
        self.sidebar_buttons["about"] = btn_about

        return sidebar

    def _select_master_tier(self, tier_key: str):
        """Switches active master workstation tier in sidebar and stack."""
        tier_map = {"tier1": 0, "tier2": 1, "tier3": 2, "about": 3}
        idx = tier_map.get(tier_key, 0)
        self.master_stack.setCurrentIndex(idx)

        for k, btn in self.sidebar_buttons.items():
            btn.set_active(k == tier_key)

    # -------------------------------------------------------------------------
    # TIER 1: NATIVE IN-HOUSE CORE (6 Sub-Tabs with Compact Layout)
    # -------------------------------------------------------------------------
    def _create_tier1_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        sub_items = [
            ("wp", "🛡️ Write Protection"),
            ("gpt", "📐 PTABLE Resizer"),
            ("oem", "🌐 Dual SIM & Downgrade"),
            ("nve", "🏷️ NVE Calibration"),
            ("erofs", "📦 EROFS Studio"),
            ("sigma", "⚡ Board Writer"),
        ]
        sub_nav = SubNavBar(sub_items)
        layout.addWidget(sub_nav)

        sub_stack = QStackedWidget()
        sub_stack.addWidget(self._create_subtab_write_protection())
        sub_stack.addWidget(self._create_subtab_ptable_resizer())
        sub_stack.addWidget(self._create_subtab_oeminfo_studio())
        sub_stack.addWidget(self._create_subtab_nve_studio())
        sub_stack.addWidget(self._create_subtab_erofs_studio())
        sub_stack.addWidget(self._create_subtab_sigma_writer())

        sub_nav.tab_changed.connect(sub_stack.setCurrentIndex)
        layout.addWidget(sub_stack, stretch=1)
        return page

    # --- Tier 1.1: Write Protection & Direct Fastboot Patches (Compact) ---
    def _create_subtab_write_protection(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Card 1: Combined Architecture & SoC Selection
        card_soc = EnterpriseCard("Target Architecture & Memory Security Vector", subtitle="HiSilicon Fastboot Vector", badge_text="● Fastboot Mode", badge_class="BadgeGreen")

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(QLabel("Select Kirin SoC:"))
        self.combo_soc = QComboBox()
        self.combo_soc.addItem("Kirin 710 / 710F (Hi6260) [ACTIVE & SUPPORTED]")
        self.combo_soc.addItem("Kirin 659 (Hi6250) [Coming Soon]")
        self.combo_soc.addItem("Kirin 970 (Hi3670) [Coming Soon]")
        self.combo_soc.addItem("Kirin 980 (Hi3680) [Coming Soon]")
        self.combo_soc.addItem("Kirin 990 (Hi3690) [Coming Soon]")
        row1.addWidget(self.combo_soc, stretch=1)
        card_soc.add_layout(row1)

        txt_arch = (
            "Kirin 710 registers guard NVME & factory partitions in RAM. Fastboot OEM write primitives bypass them directly:\n"
            "• 0x3C3E4ED8 -> 0x3C001364 (NVME Write-Lock)  |  • 0x3C3EC1F0 -> 0x3C001364 (Certificate Token)  |  • 0x3C412344 -> 0x00000001 (HDCP DRM)"
        )
        lbl_arch = QLabel(txt_arch)
        lbl_arch.setStyleSheet("color: #1E293B; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px 10px;")
        card_soc.add_widget(lbl_arch)
        layout.addWidget(card_soc)

        # Card 2: Direct Fastboot Patches Panel & Execution
        card_exec = EnterpriseCard("Direct Fastboot Memory Patches Panel", subtitle="3 Hardware Vectors")
        tbl = EngineeringDataTable(3, 3)
        tbl.setHorizontalHeaderLabels(["Security Vector", "Direct Fastboot Command", "Description"])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

        for i, (label, cmd_arg, desc) in enumerate(KIRIN_710_FASTBOOT_PATCHES):
            tbl.setItem(i, 0, QTableWidgetItem(label))
            tbl.setItem(i, 1, QTableWidgetItem(f"fastboot oem {cmd_arg}"))
            tbl.setItem(i, 2, QTableWidgetItem(desc))
        tbl.setFixedHeight(120)
        card_exec.add_widget(tbl)

        btn_run_patches = QPushButton("⚡ Execute Fastboot Patches (HiSuite Fastboot Binary)")
        btn_run_patches.setProperty("class", "BtnSuccess")
        btn_run_patches.setCursor(Qt.PointingHandCursor)
        btn_run_patches.clicked.connect(self._do_execute_kirin_710_fastboot_patches)
        card_exec.add_widget(btn_run_patches)

        layout.addWidget(card_exec)
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    def _do_execute_kirin_710_fastboot_patches(self):
        state = DeviceDetector.detect()
        if not state.is_fastboot:
            QMessageBox.warning(
                self,
                "Fastboot Not Detected",
                "Your device is not detected in Fastboot Mode!\n\nPlease put your Huawei/Honor phone into Fastboot Mode (hold Volume Down + connect USB cable) and try again."
            )
            return

        self._switch_to_console_tab()
        self.log("[*] Executing Kirin 710 Direct Fastboot Memory Patches...")

        def worker(log_cb):
            succ, fail = execute_kirin_710_fastboot_patches(FASTBOOT_BIN, log_cb)
            return succ, fail

        self._run_async(
            worker,
            on_done=lambda ok, msg: QMessageBox.information(
                self, "Patch Complete", "✅ Fastboot memory patches execution completed!\n\nReview the terminal log for details."
            )
        )

    # --- Tier 1.2: GPT / PTABLE Resizer Studio (Compact) ---
    def _create_subtab_ptable_resizer(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        card_file = EnterpriseCard("Huawei PTABLE / GPT Partition Image", subtitle="Binary Partition Map")
        file_layout = QHBoxLayout()
        self.txt_ptable_path = QLineEdit()
        self.txt_ptable_path.setPlaceholderText("Select ptable.img or gpt.bin partition table file...")
        btn_browse_ptable = QPushButton("📁 Browse...")
        btn_browse_ptable.clicked.connect(self._browse_ptable_file)
        btn_analyze = QPushButton("🔍 Analyze PTABLE")
        btn_analyze.setProperty("class", "BtnPrimary")
        btn_analyze.clicked.connect(self._analyze_ptable_file)

        file_layout.addWidget(self.txt_ptable_path, stretch=1)
        file_layout.addWidget(btn_browse_ptable)
        file_layout.addWidget(btn_analyze)
        card_file.add_layout(file_layout)
        layout.addWidget(card_file)

        # Partition Table View
        card_table = EnterpriseCard("Partition Layout Breakdown", subtitle="Parsed LBA Table")
        self.tbl_partitions = EngineeringDataTable(0, 5)
        self.tbl_partitions.setHorizontalHeaderLabels(["Index", "Partition Name", "Start LBA", "End LBA", "Size (MB)"])
        self.tbl_partitions.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_partitions.setFixedHeight(175)
        card_table.add_widget(self.tbl_partitions)
        layout.addWidget(card_table)

        # Resizing Parameters Card
        card_resize = EnterpriseCard("Partition Resizing & Balancing", subtitle="gdisk Engine")
        resize_layout = QGridLayout()
        resize_layout.setSpacing(6)

        lbl_tp = QLabel("Target Partition to Expand:")
        lbl_tp.setStyleSheet("font-weight: 600; color: #0F172A;")
        resize_layout.addWidget(lbl_tp, 0, 0)

        self.combo_resize_part = QComboBox()
        self.combo_resize_part.addItems(["system", "vendor", "product", "cust"])
        resize_layout.addWidget(self.combo_resize_part, 0, 1)

        lbl_ts = QLabel("New Target Size (MB):")
        lbl_ts.setStyleSheet("font-weight: 600; color: #0F172A;")
        resize_layout.addWidget(lbl_ts, 1, 0)

        self.spin_target_mb = QSpinBox()
        self.spin_target_mb.setRange(512, 32768)
        self.spin_target_mb.setValue(4096)
        self.spin_target_mb.setSingleStep(256)
        resize_layout.addWidget(self.spin_target_mb, 1, 1)

        btn_resize = QPushButton("📐 Resize & Balance Partition Table")
        btn_resize.setProperty("class", "BtnSuccess")
        btn_resize.clicked.connect(self._do_resize_ptable)
        resize_layout.addWidget(btn_resize, 2, 0, 1, 2)

        btn_flash_ptable = QPushButton("⚡ Flash Resized PTABLE to Phone (Fastboot)")
        btn_flash_ptable.setProperty("class", "BtnPrimary")
        btn_flash_ptable.clicked.connect(self._do_flash_resized_ptable)
        resize_layout.addWidget(btn_flash_ptable, 3, 0, 1, 2)

        card_resize.add_layout(resize_layout)
        layout.addWidget(card_resize)
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    def _browse_ptable_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select PTABLE Image", "", "PTABLE / Image Files (*.img *.bin);;All Files (*.*)")
        if f:
            self.txt_ptable_path.setText(f)
            self._analyze_ptable_file()

    def _analyze_ptable_file(self):
        path_str = self.txt_ptable_path.text().strip("\"' ")
        if not path_str or not Path(path_str).exists():
            QMessageBox.warning(self, "File Required", "Please select a valid PTABLE image file.")
            return

        try:
            self.tbl_partitions.setRowCount(0)
            resizer = PTableResizer(Path(path_str))
            analysis = resizer.analyze()

            row = 0
            for entry in analysis.entries:
                if not entry.name:
                    continue
                self.tbl_partitions.insertRow(row)
                self.tbl_partitions.setItem(row, 0, QTableWidgetItem(str(entry.index)))
                self.tbl_partitions.setItem(row, 1, QTableWidgetItem(entry.name))
                self.tbl_partitions.setItem(row, 2, QTableWidgetItem(str(entry.first_lba)))
                self.tbl_partitions.setItem(row, 3, QTableWidgetItem(str(entry.last_lba)))
                self.tbl_partitions.setItem(row, 4, QTableWidgetItem(f"{entry.get_size_mb(analysis.sector_size):.2f}"))
                row += 1

            self.log(f"✔ Analyzed PTABLE: {Path(path_str).name} ({row} active partitions detected).")
        except Exception as ex:
            self.log(f"❌ PTABLE analysis error: {ex}")
            QMessageBox.critical(self, "Analysis Failed", f"Failed to parse PTABLE:\n{ex}")

    def _do_resize_ptable(self):
        path_str = self.txt_ptable_path.text().strip("\"' ")
        if not path_str or not Path(path_str).exists():
            QMessageBox.warning(self, "File Required", "Please select a valid PTABLE file first.")
            return

        out_f, _ = QFileDialog.getSaveFileName(self, "Save Resized PTABLE Image", "ptable_resized.img", "Image Files (*.img);;All Files (*.*)")
        if not out_f:
            return

        target_part = self.combo_resize_part.currentText()
        target_mb = self.spin_target_mb.value()

        def worker(log_cb):
            log_cb(f"[*] Resizing {target_part} to {target_mb} MB...")
            resizer = PTableResizer(Path(path_str))
            res = resizer.resize(target_partition=target_part, new_size_mb=target_mb, output_file=Path(out_f))
            log_cb(f"✔ Resize succeeded: {res.message}")

        self._switch_to_console_tab()
        self._run_async(
            worker,
            on_done=lambda ok, msg: QMessageBox.information(self, "Success", f"Partition table resized successfully:\n{out_f}") if ok else QMessageBox.critical(self, "Error", f"Failed:\n{msg}")
        )

    def _do_flash_resized_ptable(self):
        path_str = self.txt_ptable_path.text().strip("\"' ")
        if not path_str or not Path(path_str).exists():
            QMessageBox.warning(self, "File Required", "Please select or save a valid PTABLE file first.")
            return

        state = DeviceDetector.detect()
        if not state.is_fastboot:
            QMessageBox.warning(self, "Fastboot Not Detected", "Device must be connected in Fastboot Mode.")
            return

        if QMessageBox.question(self, "Confirm Flash", f"Are you sure you want to flash '{Path(path_str).name}' to 'ptable' partition?") != QMessageBox.Yes:
            return

        self._switch_to_console_tab()
        def worker(log_cb):
            log_cb(f"⚡ Flashing ptable: {path_str}...")
            res = subprocess.run([str(FASTBOOT_BIN), "flash", "ptable", str(path_str)], capture_output=True, text=True)
            log_cb(res.stdout + res.stderr)
            if res.returncode != 0:
                raise RuntimeError(res.stderr or res.stdout)
            log_cb("✔ PTABLE flashed successfully!")

        self._run_async(worker, on_done=lambda ok, msg: QMessageBox.information(self, "Flash Complete", "✅ PTABLE flashed successfully!") if ok else QMessageBox.critical(self, "Flash Error", msg))

    # --- Tier 1.3: Dual SIM & Downgrade (OEMINFO Engine - Compact) ---
    def _create_subtab_oeminfo_studio(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Card 1: Main OEMINFO Configuration & Actions
        card_oem = EnterpriseCard("Huawei OEMINFO Configuration & Direct Unlock", subtitle="In-House Native Core")

        # File Chooser Row
        row_file = QHBoxLayout()
        self.txt_oem_path = QLineEdit()
        self.txt_oem_path.setPlaceholderText("Select oeminfo.img / oeminfo.bin image file...")
        btn_browse_oem = QPushButton("📂 Load OEMINFO")
        btn_browse_oem.clicked.connect(self._browse_oeminfo_file)
        row_file.addWidget(self.txt_oem_path, stretch=1)
        row_file.addWidget(btn_browse_oem)
        card_oem.add_layout(row_file)

        # Metadata Grid with Aligned Labels (Compact)
        grid = QGridLayout()
        grid.setSpacing(6)
        self.txt_oem_model = QLineEdit()
        self.txt_oem_vendor = QLineEdit()
        self.txt_oem_country = QLineEdit()
        self.chk_oem_dualsim = QCheckBox("Dual-SIM Enabled")
        self.txt_oem_unlock = QLineEdit()
        self.txt_oem_build = QLineEdit()

        grid.addWidget(QLabel("Device Model:"), 0, 0)
        grid.addWidget(self.txt_oem_model, 0, 1)
        grid.addWidget(QLabel("Vendor:"), 0, 2)
        grid.addWidget(self.txt_oem_vendor, 0, 3)

        grid.addWidget(QLabel("Country/Region:"), 1, 0)
        grid.addWidget(self.txt_oem_country, 1, 1)
        grid.addWidget(QLabel("SIM Mode:"), 1, 2)
        grid.addWidget(self.chk_oem_dualsim, 1, 3)

        grid.addWidget(QLabel("Unlock Code (16-ch):"), 2, 0)
        grid.addWidget(self.txt_oem_unlock, 2, 1)
        grid.addWidget(QLabel("Build Number:"), 2, 2)
        grid.addWidget(self.txt_oem_build, 2, 3)

        card_oem.add_layout(grid)

        # Action Buttons Row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_dual_sim = QPushButton("📱 Convert to Dual-SIM")
        btn_dual_sim.setProperty("class", "BtnSuccess")
        btn_dual_sim.clicked.connect(self._do_convert_oem_dual_sim)
        btn_row.addWidget(btn_dual_sim)

        btn_unlock = QPushButton("⚡ 1-Click Patch Unlock")
        btn_unlock.setProperty("class", "BtnPrimary")
        btn_unlock.clicked.connect(self._do_patch_oem_unlock)
        btn_row.addWidget(btn_unlock)

        btn_save_oem = QPushButton("💾 Save Modified")
        btn_save_oem.clicked.connect(self._do_save_oem_modified)
        btn_row.addWidget(btn_save_oem)

        btn_flash_oem = QPushButton("⚡ Flash to Phone")
        btn_flash_oem.setProperty("class", "BtnPrimary")
        btn_flash_oem.clicked.connect(self._do_flash_oeminfo_fastboot)
        btn_row.addWidget(btn_flash_oem)

        card_oem.add_layout(btn_row)
        layout.addWidget(card_oem)

        # Card 2: Firmware Downgrade Card (Compact)
        card_dg = EnterpriseCard("Huawei Firmware Downgrade Version Tag Injector", subtitle="SOFTWARE_VER_LIST.mbn Patcher")
        dg_layout = QGridLayout()
        dg_layout.setSpacing(6)

        self.txt_dg_base = QLineEdit()
        self.txt_dg_cust = QLineEdit()
        self.txt_dg_preload = QLineEdit()

        dg_layout.addWidget(QLabel("Base VER_LIST.mbn:"), 0, 0)
        dg_layout.addWidget(self.txt_dg_base, 0, 1)
        btn_b_base = QPushButton("Browse...")
        btn_b_base.clicked.connect(lambda: self.txt_dg_base.setText(QFileDialog.getOpenFileName(self, "Select Base MBN", "", "MBN Files (*.mbn);;All Files (*.*)")[0]))
        dg_layout.addWidget(btn_b_base, 0, 2)

        dg_layout.addWidget(QLabel("Cust VER_LIST.mbn:"), 1, 0)
        dg_layout.addWidget(self.txt_dg_cust, 1, 1)
        btn_b_cust = QPushButton("Browse...")
        btn_b_cust.clicked.connect(lambda: self.txt_dg_cust.setText(QFileDialog.getOpenFileName(self, "Select Cust MBN", "", "MBN Files (*.mbn);;All Files (*.*)")[0]))
        dg_layout.addWidget(btn_b_cust, 1, 2)

        dg_layout.addWidget(QLabel("Preload VER_LIST.mbn:"), 2, 0)
        dg_layout.addWidget(self.txt_dg_preload, 2, 1)
        btn_b_preload = QPushButton("Browse...")
        btn_b_preload.clicked.connect(lambda: self.txt_dg_preload.setText(QFileDialog.getOpenFileName(self, "Select Preload MBN", "", "MBN Files (*.mbn);;All Files (*.*)")[0]))
        dg_layout.addWidget(btn_b_preload, 2, 2)

        btn_dg_patch = QPushButton("⬇️ Patch OEMINFO for Downgrade")
        btn_dg_patch.setProperty("class", "BtnWarning")
        btn_dg_patch.clicked.connect(self._do_patch_firmware_downgrade)
        dg_layout.addWidget(btn_dg_patch, 3, 0, 1, 3)

        card_dg.add_layout(dg_layout)
        layout.addWidget(card_dg)
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    def _browse_oeminfo_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select OEMINFO Image", "", "OEMINFO Images (*.img *.bin *.mbn);;All Files (*.*)")
        if f:
            self.txt_oem_path.setText(f)
            try:
                editor = OemInfoEditor(Path(f))
                meta = editor.read_metadata()
                self.txt_oem_model.setText(meta.device_model)
                parts = meta.vendor_country.split("/") if "/" in meta.vendor_country else [meta.vendor_country, ""]
                self.txt_oem_vendor.setText(parts[0])
                self.txt_oem_country.setText(parts[1] if len(parts) > 1 else "")
                self.chk_oem_dualsim.setChecked(meta.is_dual_sim)
                self.txt_oem_build.setText(meta.build_number)
                code = editor.get_unlock_code()
                if code:
                    self.txt_oem_unlock.setText(code)
                self.log(f"✔ Loaded OEMINFO: {Path(f).name} | Model: {meta.device_model} | SIM: {'Dual' if meta.is_dual_sim else 'Single'}")
            except Exception as ex:
                self.log(f"❌ Failed to parse OEMINFO: {ex}")
                QMessageBox.critical(self, "Parse Error", f"Failed to parse OEMINFO:\n{ex}")

    def _do_convert_oem_dual_sim(self):
        p = self.txt_oem_path.text().strip("\"' ")
        if not p or not Path(p).exists():
            QMessageBox.warning(self, "File Required", "Please load an OEMINFO image first.")
            return

        out_f, _ = QFileDialog.getSaveFileName(self, "Save Dual-SIM OEMINFO", "oeminfo_dualsim.img", "Image Files (*.img);;All Files (*.*)")
        if not out_f:
            return

        try:
            editor = OemInfoEditor(Path(p))
            editor.rebrand(output_image=Path(out_f), enable_dual_sim=True)
            self.chk_oem_dualsim.setChecked(True)
            self.log(f"✔ OEMINFO converted to Dual-SIM: {out_f}")
            QMessageBox.information(self, "Success", f"Dual-SIM conversion completed:\n{out_f}")
        except Exception as ex:
            QMessageBox.critical(self, "Conversion Error", str(ex))

    def _do_patch_oem_unlock(self):
        p = self.txt_oem_path.text().strip("\"' ")
        if not p or not Path(p).exists():
            QMessageBox.warning(self, "File Required", "Please load an OEMINFO image first.")
            return

        out_f, _ = QFileDialog.getSaveFileName(self, "Save Unlocked OEMINFO", "oeminfo_unlocked.img", "Image Files (*.img);;All Files (*.*)")
        if not out_f:
            return

        code = self.txt_oem_unlock.text().strip()
        try:
            editor = OemInfoEditor(Path(p))
            used_code = editor.patch_bootloader_unlock(output_image=Path(out_f), custom_unlock_code=code if code else None)
            self.txt_oem_unlock.setText(used_code)
            self.log(f"✔ Bootloader unlock patched in OEMINFO! Key: {used_code}")
            QMessageBox.information(self, "Method 3 Success", f"🎉 Bootloader unlock patched in OEMINFO!\n\nUnlock Key: {used_code}\nOutput: {out_f}\n\nFlash this image to 'oeminfo' partition for instant unlock without data loss!")
        except Exception as ex:
            QMessageBox.critical(self, "Unlock Patch Error", str(ex))

    def _do_save_oem_modified(self):
        p = self.txt_oem_path.text().strip("\"' ")
        if not p or not Path(p).exists():
            QMessageBox.warning(self, "File Required", "Please load an OEMINFO image first.")
            return

        out_f, _ = QFileDialog.getSaveFileName(self, "Save Modified OEMINFO", "oeminfo_modified.img", "Image Files (*.img);;All Files (*.*)")
        if not out_f:
            return

        model = self.txt_oem_model.text().strip()
        vendor = self.txt_oem_vendor.text().strip()
        country = self.txt_oem_country.text().strip()
        dual_sim = self.chk_oem_dualsim.isChecked()
        code = self.txt_oem_unlock.text().strip()
        build = self.txt_oem_build.text().strip()
        vc = f"{vendor}/{country}" if vendor and country else (vendor or country)

        try:
            editor = OemInfoEditor(Path(p))
            editor.rebrand(
                output_image=Path(out_f),
                device_model=model if model else None,
                vendor_country=vc if vc else None,
                enable_dual_sim=dual_sim,
                unlock_code=code if code else None,
                build_number=build if build else None
            )
            self.log(f"✔ Saved modified OEMINFO: {out_f}")
            QMessageBox.information(self, "Saved", f"Modified OEMINFO saved:\n{out_f}")
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))

    def _do_flash_oeminfo_fastboot(self):
        p = self.txt_oem_path.text().strip("\"' ")
        if not p or not Path(p).exists():
            QMessageBox.warning(self, "File Required", "Please select a valid OEMINFO image first.")
            return

        state = DeviceDetector.detect()
        if not state.is_fastboot:
            QMessageBox.warning(self, "Fastboot Required", "Device is not in Fastboot Mode.")
            return

        if QMessageBox.question(self, "Confirm Flash", f"Are you sure you want to flash '{Path(p).name}' to 'oeminfo' partition?") != QMessageBox.Yes:
            return

        self._switch_to_console_tab()
        def worker(log_cb):
            log_cb(f"⚡ Flashing oeminfo: {p}...")
            res = subprocess.run([str(FASTBOOT_BIN), "flash", "oeminfo", str(p)], capture_output=True, text=True)
            log_cb(res.stdout + res.stderr)
            if res.returncode != 0:
                raise RuntimeError(res.stderr or res.stdout)
            log_cb("✔ OEMINFO partition flashed successfully!")

        self._run_async(worker, on_done=lambda ok, msg: QMessageBox.information(self, "Flash Complete", "✅ OEMINFO flashed successfully!") if ok else QMessageBox.critical(self, "Flash Error", msg))

    def _do_patch_firmware_downgrade(self):
        p = self.txt_oem_path.text().strip("\"' ")
        if not p or not Path(p).exists():
            QMessageBox.warning(self, "File Required", "Please load an OEMINFO image first.")
            return

        base_m = self.txt_dg_base.text().strip("\"' ")
        cust_m = self.txt_dg_cust.text().strip("\"' ")
        preload_m = self.txt_dg_preload.text().strip("\"' ")

        if not any([base_m, cust_m, preload_m]):
            QMessageBox.warning(self, "MBN Files Required", "Please select at least one SOFTWARE_VER_LIST.mbn file.")
            return

        out_f, _ = QFileDialog.getSaveFileName(self, "Save Downgraded OEMINFO", "oeminfo_downgraded.img", "Image Files (*.img);;All Files (*.*)")
        if not out_f:
            return

        try:
            editor = OemInfoEditor(Path(p))
            report = editor.patch_firmware_downgrade(
                output_image=Path(out_f),
                base_mbn=Path(base_m) if base_m and Path(base_m).exists() else None,
                cust_mbn=Path(cust_m) if cust_m and Path(cust_m).exists() else None,
                preload_mbn=Path(preload_m) if preload_m and Path(preload_m).exists() else None,
            )
            self.log(f"✔ Firmware downgrade patched in OEMINFO: {out_f} (Report: {report})")
            QMessageBox.information(self, "Success", f"OEMINFO patched for firmware downgrade!\n\nOutput: {out_f}")
        except Exception as ex:
            QMessageBox.critical(self, "Downgrade Patch Error", str(ex))

    # --- Tier 1.4: NVE / NVME Calibration Studio (Compact) ---
    def _create_subtab_nve_studio(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        card_nve = EnterpriseCard("Huawei NVE / NVME Hardware Calibration Engine", subtitle="Direct NVME Partition Editor")

        row_f = QHBoxLayout()
        self.txt_nve_path = QLineEdit()
        self.txt_nve_path.setPlaceholderText("Select nvme.img / nve.bin or click 'Read Live Device'...")
        btn_b_nve = QPushButton("📁 Load NVME Image")
        btn_b_nve.clicked.connect(self._browse_nve_file)
        btn_read_live = QPushButton("🔍 Read Live Device")
        btn_read_live.setProperty("class", "BtnPrimary")
        btn_read_live.clicked.connect(self._read_live_nve_device)

        row_f.addWidget(self.txt_nve_path, stretch=1)
        row_f.addWidget(btn_b_nve)
        row_f.addWidget(btn_read_live)
        card_nve.add_layout(row_f)

        # NVE Properties Table
        self.tbl_nve = EngineeringDataTable(9, 2)
        self.tbl_nve.setHorizontalHeaderLabels(["Calibration Variable", "Stored Value"])
        self.tbl_nve.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl_nve.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        self.nve_keys = ["SN", "IMEI", "IMEI1", "WIFI_MAC", "BT_MAC", "BSN", "VENDOR_COUNTRY", "FBLOCK", "WVLOCK"]
        for i, k in enumerate(self.nve_keys):
            self.tbl_nve.setItem(i, 0, QTableWidgetItem(k))
            self.tbl_nve.setItem(i, 1, QTableWidgetItem(""))
        self.tbl_nve.setFixedHeight(180)
        card_nve.add_widget(self.tbl_nve)

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_unl_m2 = QPushButton("🔓 1-Click Patch Unlock")
        btn_unl_m2.setProperty("class", "BtnPrimary")
        btn_unl_m2.clicked.connect(self._do_patch_nve_unlock)
        btn_row.addWidget(btn_unl_m2)

        btn_fblock = QPushButton("🔒 Toggle FBLOCK")
        btn_fblock.clicked.connect(self._do_toggle_fblock)
        btn_row.addWidget(btn_fblock)

        btn_crc = QPushButton("🛠️ Auto-Fix CRCs")
        btn_crc.clicked.connect(self._do_fix_nve_crc)
        btn_row.addWidget(btn_crc)

        btn_save_nve = QPushButton("💾 Save Image")
        btn_save_nve.clicked.connect(self._do_save_nve_image)
        btn_row.addWidget(btn_save_nve)

        btn_flash_nve = QPushButton("⚡ Flash to Fastboot")
        btn_flash_nve.setProperty("class", "BtnSuccess")
        btn_flash_nve.clicked.connect(self._do_flash_nve_fastboot)
        btn_row.addWidget(btn_flash_nve)

        card_nve.add_layout(btn_row)
        layout.addWidget(card_nve)
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    def _browse_nve_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select NVME Image", "", "NVME Images (*.img *.bin);;All Files (*.*)")
        if f:
            self.txt_nve_path.setText(f)
            self._load_nve_data(Path(f))

    def _load_nve_data(self, path: Path):
        try:
            nve_img = HisiNveImage(path)
            report = nve_img.parse()
            for i, k in enumerate(self.nve_keys):
                val = nve_img.get_value(k) or ""
                self.tbl_nve.setItem(i, 1, QTableWidgetItem(val))
            self.log(f"✔ Parsed NVME Image: {path.name} ({len(report.get('blocks', []))} blocks parsed).")
        except Exception as ex:
            self.log(f"❌ NVME Parse error: {ex}")
            QMessageBox.critical(self, "Parse Error", f"Failed to parse NVE image:\n{ex}")

    def _read_live_nve_device(self):
        state = DeviceDetector.detect()
        if not state.is_connected:
            QMessageBox.warning(self, "Device Disconnected", "Please connect a device in Fastboot or ADB mode.")
            return

        self._switch_to_console_tab()
        def worker(log_cb):
            log_cb("[*] Reading live device NVE variables...")
            info = NveClient.read_device_info()
            log_cb(f"✔ SN: {info.sn}, IMEI: {info.imei}, MAC: {info.wifi_mac}, FBLOCK: {info.fblock_state}")

        self._run_async(worker, on_done=lambda ok, msg: QMessageBox.information(self, "Read Complete", "Live NVE information read into console!") if ok else QMessageBox.critical(self, "Read Error", msg))

    def _do_patch_nve_unlock(self):
        p = self.txt_nve_path.text().strip("\"' ")
        if not p or not Path(p).exists():
            QMessageBox.warning(self, "File Required", "Please load an NVME image first.")
            return
        out_f, _ = QFileDialog.getSaveFileName(self, "Save Unlocked NVME", "nvme_unlocked.img", "Image Files (*.img);;All Files (*.*)")
        if not out_f:
            return

        try:
            nve_img = HisiNveImage(Path(p))
            nve_img.parse()
            nve_img.patch_bootloader_unlock()
            nve_img.write(Path(out_f))
            self.log(f"✔ Patched Bootloader Unlock in NVME: {out_f}")
            QMessageBox.information(self, "Method 2 Success", f"Bootloader unlock successfully patched into NVME image!\n\nOutput: {out_f}")
        except Exception as ex:
            QMessageBox.critical(self, "Patch Error", str(ex))

    def _do_toggle_fblock(self):
        row = self.nve_keys.index("FBLOCK")
        cur = self.tbl_nve.item(row, 1).text() if self.tbl_nve.item(row, 1) else ""
        new_v = "1" if cur != "1" else "0"
        self.tbl_nve.setItem(row, 1, QTableWidgetItem(new_v))
        self.log(f"Toggled FBLOCK state to: {new_v}")

    def _do_fix_nve_crc(self):
        p = self.txt_nve_path.text().strip("\"' ")
        if not p or not Path(p).exists():
            QMessageBox.warning(self, "File Required", "Please load an NVME image first.")
            return
        try:
            nve_img = HisiNveImage(Path(p))
            nve_img.parse()
            fixed = nve_img.fix_all_crcs()
            self.log(f"✔ Fixed {fixed} NVE block CRC checksums.")
            QMessageBox.information(self, "CRCs Fixed", f"Successfully recalculated and fixed {fixed} CRC checksums.")
        except Exception as ex:
            QMessageBox.critical(self, "CRC Error", str(ex))

    def _do_save_nve_image(self):
        p = self.txt_nve_path.text().strip("\"' ")
        if not p or not Path(p).exists():
            QMessageBox.warning(self, "File Required", "Please load an NVME image first.")
            return
        out_f, _ = QFileDialog.getSaveFileName(self, "Save NVME Image", "nvme_saved.img", "Image Files (*.img);;All Files (*.*)")
        if not out_f:
            return
        try:
            nve_img = HisiNveImage(Path(p))
            nve_img.parse()
            for i, k in enumerate(self.nve_keys):
                item = self.tbl_nve.item(i, 1)
                if item and item.text():
                    nve_img.set_value(k, item.text().strip())
            nve_img.write(Path(out_f))
            self.log(f"✔ NVME image saved: {out_f}")
            QMessageBox.information(self, "Saved", f"NVME image saved successfully:\n{out_f}")
        except Exception as ex:
            QMessageBox.critical(self, "Save Error", str(ex))

    def _do_flash_nve_fastboot(self):
        p = self.txt_nve_path.text().strip("\"' ")
        if not p or not Path(p).exists():
            QMessageBox.warning(self, "File Required", "Please select a valid NVME image first.")
            return
        state = DeviceDetector.detect()
        if not state.is_fastboot:
            QMessageBox.warning(self, "Fastboot Required", "Device must be in Fastboot Mode.")
            return
        if QMessageBox.question(self, "Confirm Flash", f"Are you sure you want to flash '{Path(p).name}' to 'nvme' partition?") != QMessageBox.Yes:
            return
        self._switch_to_console_tab()
        def worker(log_cb):
            log_cb(f"⚡ Flashing nvme: {p}...")
            res = subprocess.run([str(FASTBOOT_BIN), "flash", "nvme", str(p)], capture_output=True, text=True)
            log_cb(res.stdout + res.stderr)
            if res.returncode != 0:
                raise RuntimeError(res.stderr or res.stdout)
            log_cb("✔ NVME flashed successfully!")
        self._run_async(worker, on_done=lambda ok, msg: QMessageBox.information(self, "Complete", "✅ NVME flashed successfully!") if ok else QMessageBox.critical(self, "Error", msg))

    # --- Tier 1.5: EROFS Unpack & Repack Studio (Compact) ---
    def _create_subtab_erofs_studio(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        card = EnterpriseCard("Huawei Pure-Python EROFS Filesystem Studio", subtitle="100% In-House Python Implementation")
        c_layout = QGridLayout()
        c_layout.setSpacing(6)

        self.txt_erofs_src = QLineEdit()
        self.txt_erofs_src.setPlaceholderText("Select system.img / vendor.img / product.img EROFS image...")
        btn_b_src = QPushButton("Browse Image...")
        btn_b_src.clicked.connect(lambda: self.txt_erofs_src.setText(QFileDialog.getOpenFileName(self, "Select EROFS Image", "", "Image Files (*.img);;All Files (*.*)")[0]))

        self.txt_erofs_dst = QLineEdit()
        self.txt_erofs_dst.setPlaceholderText("Select destination directory for unpacking / repacking...")
        btn_b_dst = QPushButton("Browse Dir...")
        btn_b_dst.clicked.connect(lambda: self.txt_erofs_dst.setText(QFileDialog.getExistingDirectory(self, "Select Destination Directory")))

        c_layout.addWidget(QLabel("EROFS Image File:"), 0, 0)
        c_layout.addWidget(self.txt_erofs_src, 0, 1)
        c_layout.addWidget(btn_b_src, 0, 2)

        c_layout.addWidget(QLabel("Target Directory:"), 1, 0)
        c_layout.addWidget(self.txt_erofs_dst, 1, 1)
        c_layout.addWidget(btn_b_dst, 1, 2)

        btn_unpack = QPushButton("📦 Unpack EROFS Image")
        btn_unpack.setProperty("class", "BtnPrimary")
        btn_unpack.clicked.connect(self._do_unpack_erofs)

        btn_repack = QPushButton("🔨 Repack Directory to EROFS")
        btn_repack.setProperty("class", "BtnSuccess")
        btn_repack.clicked.connect(self._do_repack_erofs)

        btn_sparse = QPushButton("🔄 Convert Sparse <-> Raw .img")
        btn_sparse.clicked.connect(self._do_convert_sparse)

        c_layout.addWidget(btn_unpack, 2, 0, 1, 3)
        c_layout.addWidget(btn_repack, 3, 0, 1, 3)
        c_layout.addWidget(btn_sparse, 4, 0, 1, 3)

        card.add_layout(c_layout)
        layout.addWidget(card)
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    def _do_unpack_erofs(self):
        src = self.txt_erofs_src.text().strip("\"' ")
        dst = self.txt_erofs_dst.text().strip("\"' ")
        if not src or not Path(src).exists():
            QMessageBox.warning(self, "File Required", "Please select a valid EROFS image file.")
            return
        if not dst:
            dst = str(Path(src).parent / f"{Path(src).stem}_unpacked")
            self.txt_erofs_dst.setText(dst)

        self._switch_to_console_tab()
        def worker(log_cb):
            log_cb(f"[*] Unpacking EROFS: {src} -> {dst}...")
            unpack_erofs(Path(src), Path(dst), progress_cb=lambda cur, tot: log_cb(f"  Extracted {cur}/{tot} files..."))
            log_cb("✔ EROFS extraction complete!")

        self._run_async(worker, on_done=lambda ok, msg: QMessageBox.information(self, "Success", f"EROFS unpacked successfully to:\n{dst}") if ok else QMessageBox.critical(self, "Error", msg))

    def _do_repack_erofs(self):
        src_dir = self.txt_erofs_dst.text().strip("\"' ")
        if not src_dir or not Path(src_dir).exists():
            QMessageBox.warning(self, "Directory Required", "Please select a directory containing unpacked files to repack.")
            return
        out_f, _ = QFileDialog.getSaveFileName(self, "Save Repacked EROFS Image", "repacked_erofs.img", "Image Files (*.img);;All Files (*.*)")
        if not out_f:
            return

        self._switch_to_console_tab()
        def worker(log_cb):
            log_cb(f"[*] Repacking directory to EROFS: {src_dir} -> {out_f}...")
            repack_erofs(Path(src_dir), Path(out_f))
            log_cb("✔ EROFS image repacked successfully!")

        self._run_async(worker, on_done=lambda ok, msg: QMessageBox.information(self, "Success", f"EROFS repacked successfully:\n{out_f}") if ok else QMessageBox.critical(self, "Error", msg))

    def _do_convert_sparse(self):
        src = self.txt_erofs_src.text().strip("\"' ")
        if not src or not Path(src).exists():
            QMessageBox.warning(self, "File Required", "Please select an image file first.")
            return
        out_f, _ = QFileDialog.getSaveFileName(self, "Save Converted Image", f"{Path(src).stem}_converted.img", "Image Files (*.img);;All Files (*.*)")
        if not out_f:
            return

        self._switch_to_console_tab()
        def worker(log_cb):
            with open(src, "rb") as f:
                magic = f.read(4)
            if magic == b"\x3A\xFF\x26\xED":
                log_cb("[*] Converting Sparse -> Raw image...")
                convert_sparse_to_raw(Path(src), Path(out_f))
            else:
                log_cb("[*] Converting Raw -> Sparse image...")
                convert_raw_to_sparse(Path(src), Path(out_f))
            log_cb("✔ Conversion complete!")

        self._run_async(worker, on_done=lambda ok, msg: QMessageBox.information(self, "Success", f"Image converted successfully:\n{out_f}") if ok else QMessageBox.critical(self, "Error", msg))

    # --- Tier 1.6: Sigma & Board Software Writer (Multi-Format) ---
    def _create_subtab_sigma_writer(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        card_src = EnterpriseCard(
            "Board Software & SigmaKey Partition Writer",
            subtitle="Multi-Format Ingestion (IDT XML, SigmaKey Dumps, Factory Packages)"
        )
        
        # Row 1: File/Directory Path & Dual Action Buttons
        src_layout = QHBoxLayout()
        self.txt_sigma_src = QLineEdit()
        self.txt_sigma_src.setPlaceholderText("Select Board Software XML (Download.xml), SigmaKey Dump (.skd), Image (.img), or Directory...")
        
        btn_b_file = QPushButton("📄 Select XML / Dump File...")
        btn_b_file.setProperty("class", "BtnPrimary")
        btn_b_file.setCursor(Qt.PointingHandCursor)
        btn_b_file.clicked.connect(self._browse_sigma_file)
        
        btn_b_dir = QPushButton("📁 Select Package Folder...")
        btn_b_dir.setCursor(Qt.PointingHandCursor)
        btn_b_dir.clicked.connect(self._browse_sigma_dir)
        
        src_layout.addWidget(self.txt_sigma_src, stretch=1)
        src_layout.addWidget(btn_b_file)
        src_layout.addWidget(btn_b_dir)
        card_src.add_layout(src_layout)

        # Row 2: Detected Format & Readiness Badges
        row_badges = QHBoxLayout()
        self.lbl_sigma_format = QLabel("○ No Package Loaded")
        self.lbl_sigma_format.setProperty("class", "BadgeGray")
        row_badges.addWidget(self.lbl_sigma_format)

        self.lbl_sigma_count = QLabel("0 Partitions")
        self.lbl_sigma_count.setProperty("class", "BadgeBlue")
        row_badges.addWidget(self.lbl_sigma_count)
        row_badges.addStretch()
        card_src.add_layout(row_badges)

        layout.addWidget(card_src)

        # Partition Checklist Card
        card_parts = EnterpriseCard("Partitions to Write", subtitle="Sequential Flashing Pipeline")
        self.tree_sigma = QTreeWidget()
        self.tree_sigma.setHeaderLabels(["Write", "Partition", "Source Format", "Filename", "File Size", "Status"])
        self.tree_sigma.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tree_sigma.header().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tree_sigma.setFixedHeight(180)
        card_parts.add_widget(self.tree_sigma)

        row_sel = QHBoxLayout()
        row_sel.setSpacing(6)
        btn_all = QPushButton("Select All")
        btn_all.clicked.connect(lambda: self._set_all_sigma_checked(True))
        btn_none = QPushButton("Deselect All")
        btn_none.clicked.connect(lambda: self._set_all_sigma_checked(False))
        btn_crit = QPushButton("Critical Partitions Only")
        btn_crit.clicked.connect(self._select_critical_sigma_partitions)
        
        row_sel.addWidget(btn_all)
        row_sel.addWidget(btn_none)
        row_sel.addWidget(btn_crit)
        row_sel.addStretch()

        self.prog_sigma = QProgressBar()
        self.prog_sigma.setValue(0)
        row_sel.addWidget(self.prog_sigma, stretch=1)

        btn_flash_board = QPushButton("⚡ Direct Board Flash")
        btn_flash_board.setProperty("class", "BtnSuccess")
        btn_flash_board.setCursor(Qt.PointingHandCursor)
        btn_flash_board.clicked.connect(self._do_flash_sigma_board)
        row_sel.addWidget(btn_flash_board)

        card_parts.add_layout(row_sel)
        layout.addWidget(card_parts)
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    def _browse_sigma_file(self):
        f, _ = QFileDialog.getOpenFileName(
            self,
            "Select Board Software XML or SigmaKey Dump File",
            "",
            "Supported Formats (*.xml *.skd *.img *.bin);;Board Software XML (*.xml);;SigmaKey Dump (*.skd);;Partition Images (*.img *.bin);;All Files (*.*)"
        )
        if f:
            self.txt_sigma_src.setText(f)
            self._load_sigma_source(Path(f))

    def _browse_sigma_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Factory Board Software or SigmaKey Directory")
        if d:
            self.txt_sigma_src.setText(d)
            self._load_sigma_source(Path(d))

    def _load_sigma_source(self, p: Path):
        try:
            self.sigma_writer = SigmaBoardWriter()
            partitions = self.sigma_writer.load_source(p)
            self.tree_sigma.clear()

            for item in partitions:
                node = QTreeWidgetItem()
                node.setCheckState(0, Qt.Checked if item.is_selected else Qt.Unchecked)
                node.setText(1, item.name)
                node.setText(2, item.format_source)
                node.setText(3, item.file_path.name)
                node.setText(4, item.size_human)
                node.setText(5, item.status)
                node.setData(0, Qt.UserRole, str(item.file_path))
                self.tree_sigma.addTopLevelItem(node)

            st = self.sigma_writer.source_type
            self.lbl_sigma_format.setText(f"● {st}")
            self.lbl_sigma_format.setProperty("class", "BadgeGreen")
            self.lbl_sigma_format.style().unpolish(self.lbl_sigma_format)
            self.lbl_sigma_format.style().polish(self.lbl_sigma_format)

            self.lbl_sigma_count.setText(f"{len(partitions)} Partitions Ready")
            self.lbl_sigma_count.setProperty("class", "BadgeBlue")
            self.lbl_sigma_count.style().unpolish(self.lbl_sigma_count)
            self.lbl_sigma_count.style().polish(self.lbl_sigma_count)

            self.log(f"✔ Loaded {st}: {p.name} ({len(partitions)} partitions detected).")
        except Exception as ex:
            self.log(f"❌ Failed to load source: {ex}")
            QMessageBox.critical(self, "Load Error", f"Failed to load package:\n{ex}")

    def _set_all_sigma_checked(self, checked: bool):
        for i in range(self.tree_sigma.topLevelItemCount()):
            self.tree_sigma.topLevelItem(i).setCheckState(0, Qt.Checked if checked else Qt.Unchecked)

    def _select_critical_sigma_partitions(self):
        critical_names = {"xloader", "fastboot", "boot", "recovery", "nvme", "ptable", "modem_fw", "vendor"}
        for i in range(self.tree_sigma.topLevelItemCount()):
            it = self.tree_sigma.topLevelItem(i)
            is_crit = it.text(1).lower() in critical_names
            it.setCheckState(0, Qt.Checked if is_crit else Qt.Unchecked)

    def _do_flash_sigma_board(self):
        state = DeviceDetector.detect()
        if not state.is_connected:
            QMessageBox.warning(self, "Device Disconnected", "Please connect a device in Fastboot mode.")
            return

        selected_items = []
        for i in range(self.tree_sigma.topLevelItemCount()):
            it = self.tree_sigma.topLevelItem(i)
            if it.checkState(0) == Qt.Checked:
                pname = it.text(1)
                fpath_str = it.data(0, Qt.UserRole)
                if not fpath_str:
                    fpath_str = str(Path(self.txt_sigma_src.text()) / it.text(3))
                selected_items.append((pname, Path(fpath_str)))

        if not selected_items:
            QMessageBox.warning(self, "Selection Required", "Please select at least one partition to flash.")
            return

        if QMessageBox.question(self, "Confirm Flash", f"Are you sure you want to sequentially flash {len(selected_items)} selected partitions to the device?") != QMessageBox.Yes:
            return

        self._switch_to_console_tab()
        total = len(selected_items)

        def worker(log_cb):
            log_cb(f"⚡ Starting Board Software / Sigma Flashing ({total} partitions)...")
            for idx, (pname, ppath) in enumerate(selected_items, 1):
                if not ppath.exists():
                    log_cb(f"⚠️ Skipping missing partition file: {ppath.name}")
                    continue
                sz = human_size(ppath.stat().st_size)
                log_cb(f"[{idx}/{total}] Flashing {pname} <- {ppath.name} ({sz})...")
                res = subprocess.run([str(FASTBOOT_BIN), "flash", pname, str(ppath)], capture_output=True, text=True)
                log_cb(res.stdout + res.stderr)
                if res.returncode != 0:
                    raise RuntimeError(f"Flashing failed for {pname}: {res.stderr or res.stdout}")
                self.prog_sigma.setValue(int((idx / total) * 100))
            log_cb("🏁 Board Software Flashing Sequence Completed Successfully!")

        self._run_async(worker, on_done=lambda ok, msg: QMessageBox.information(self, "Flash Complete", "✅ Board software flashing finished successfully!") if ok else QMessageBox.critical(self, "Flash Error", msg))

    # -------------------------------------------------------------------------
    # TIER 2: STANDALONE COMPANIONS (3 Sub-Tabs - Zero-Config Auto-Launcher)
    # -------------------------------------------------------------------------
    def _create_tier2_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        sub_items = [
            ("kirin_tool", "🚀 Kirin-Tool (Da-Niel)"),
            ("fastboot_flasher", "⚡ FastbootFlasher (Natsume324)"),
            ("android_utility", "🛠️ Android Utility (mfl team)"),
        ]
        sub_nav = SubNavBar(sub_items)
        layout.addWidget(sub_nav)

        sub_stack = QStackedWidget()
        sub_stack.addWidget(self._create_companion_card("kirin_tool"))
        sub_stack.addWidget(self._create_companion_card("fastboot_flasher"))
        sub_stack.addWidget(self._create_companion_card("android_utility"))

        sub_nav.tab_changed.connect(sub_stack.setCurrentIndex)
        layout.addWidget(sub_stack, stretch=1)
        return page

    def _create_companion_card(self, item_id: str) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        item = self.companion_manager.get_item(item_id)
        if not item:
            layout.addWidget(QLabel(f"Tool {item_id} not found."))
            scroll.setWidget(container)
            return scroll

        is_inst = self.companion_manager.is_installed(item.id)
        card = EnterpriseCard(f"🚀 {item.name}", subtitle=f"Author: {item.author}", badge_text=item.version_label, badge_class="BadgeBlue")

        lbl_desc = QLabel(item.description)
        lbl_desc.setStyleSheet("color: #334155; line-height: 1.3;")
        lbl_desc.setWordWrap(True)
        card.add_widget(lbl_desc)

        # Specialized Capabilities & Primary Tasks (Strict 5 items for Kirin-Tool)
        if hasattr(item, "tasks") and item.tasks:
            card_tasks = QFrame()
            card_tasks.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 12px;")
            tasks_layout = QVBoxLayout(card_tasks)
            tasks_layout.setSpacing(4)

            lbl_t_title = QLabel("🎯 Specialized Capabilities & Primary Tasks (Use this tool for):")
            lbl_t_title.setFont(QFont("Segoe UI", 9, QFont.Bold))
            lbl_t_title.setStyleSheet("color: #1E3A8A;")
            tasks_layout.addWidget(lbl_t_title)

            for t in item.tasks:
                row_t = QHBoxLayout()
                lbl_chk = QLabel("✔")
                lbl_chk.setStyleSheet("color: #059669; font-weight: bold; font-size: 12px;")
                lbl_t_text = QLabel(t)
                lbl_t_text.setStyleSheet("color: #0F172A; font-size: 11.5px;")
                row_t.addWidget(lbl_chk)
                row_t.addWidget(lbl_t_text, stretch=1)
                tasks_layout.addLayout(row_t)

            card.add_widget(card_tasks)

        # Status Badge Row (Zero-Config)
        row_status = QHBoxLayout()
        lbl_s_title = QLabel("Deployment Status:")
        lbl_s_title.setStyleSheet("font-weight: bold; color: #0F172A;")
        row_status.addWidget(lbl_s_title)

        lbl_badge = QLabel("● Installed & Ready" if is_inst else "○ Not Downloaded")
        lbl_badge.setProperty("class", "BadgeGreen" if is_inst else "BadgeGray")
        row_status.addWidget(lbl_badge)
        row_status.addStretch()
        card.add_layout(row_status)

        self.companion_status_badges[item.id] = lbl_badge

        # Action Buttons Row
        row_act = QHBoxLayout()
        row_act.setSpacing(8)

        btn_about = QPushButton("⭐ About & Download Portal")
        btn_about.setCursor(Qt.PointingHandCursor)
        btn_about.clicked.connect(lambda checked=False, it=item.id: self.companion_manager.open_official_site(it))
        row_act.addWidget(btn_about)

        btn_import = QPushButton("📦 Import Downloaded Archive (.zip / .7z / .rar)")
        btn_import.setProperty("class", "BtnPrimary")
        btn_import.setCursor(Qt.PointingHandCursor)
        btn_import.clicked.connect(lambda checked=False, it=item.id: self._import_companion_archive(it))
        row_act.addWidget(btn_import)

        btn_launch = QPushButton("🚀 Launch Tool")
        btn_launch.setProperty("class", "BtnSuccess" if is_inst else "BtnPrimary")
        btn_launch.setCursor(Qt.PointingHandCursor)
        btn_launch.clicked.connect(lambda checked=False, it=item.id: self._launch_companion_tool(it))
        row_act.addWidget(btn_launch)

        self.companion_launch_btns[item.id] = btn_launch

        card.add_layout(row_act)
        layout.addWidget(card)
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    def _update_companion_ui_badge(self, item_id: str):
        is_inst = self.companion_manager.is_installed(item_id)
        if item_id in self.companion_status_badges:
            b = self.companion_status_badges[item_id]
            b.setText("● Installed & Ready" if is_inst else "○ Not Downloaded")
            b.setProperty("class", "BadgeGreen" if is_inst else "BadgeGray")
            b.style().unpolish(b)
            b.style().polish(b)

        if item_id in self.companion_launch_btns:
            btn = self.companion_launch_btns[item_id]
            btn.setProperty("class", "BtnSuccess" if is_inst else "BtnPrimary")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _import_companion_archive(self, item_id: str):
        item = self.companion_manager.get_item(item_id)
        if not item:
            return

        archive_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select Downloaded Archive for {item.name}",
            "",
            "Archive Files (*.zip *.7z *.rar *.tar *.tar.gz *.tgz);;ZIP Files (*.zip);;7-Zip Files (*.7z);;RAR Files (*.rar);;All Files (*.*)",
        )
        if not archive_path:
            return

        self._switch_to_console_tab()
        self.log(f"[*] Importing archive for {item.name}: {archive_path}")

        def worker(log_cb):
            ok, msg = self.companion_manager.import_archive(item_id, archive_path, log_cb=log_cb)
            if not ok:
                raise RuntimeError(msg)
            return msg

        def on_done(ok: bool, msg: str):
            if ok:
                self.log(f"[✔] Successfully imported {item.name}!")
                self._update_companion_ui_badge(item_id)
                QMessageBox.information(
                    self,
                    "Import Successful",
                    f"✅ {item.name} imported and verified successfully!\n\n"
                    f"Status: ● Installed & Ready\n\n"
                    f"Click '🚀 Launch Tool' to run.",
                )
            else:
                self.log(f"[❌] Import error: {msg}")
                QMessageBox.critical(self, "Import Error", f"Failed to import {item.name}:\n\n{msg}")

        self._run_async(worker, on_done=on_done)

    def _launch_companion_tool(self, item_id: str):
        item = self.companion_manager.get_item(item_id)
        if not item:
            return

        if not self.companion_manager.is_installed(item_id):
            self.companion_manager.auto_discover_all()
            if self.companion_manager.is_installed(item_id):
                self._update_companion_ui_badge(item_id)
            else:
                QMessageBox.information(
                    self,
                    "Tool Not Installed",
                    f"⚠️ {item.name} is not installed or configured yet.\n\n"
                    f"Please follow these steps:\n"
                    f"1. Click '⭐ About & Download Portal' to open the official website and download the tool archive.\n"
                    f"2. Click '📦 Import Downloaded Archive (.zip / .7z / .rar)' to select and automatically extract the file.\n"
                    f"3. Click '🚀 Launch Tool' to run it.",
                )
                return

        ok, msg = self.companion_manager.launch(item_id)
        if ok:
            self.log(f"🚀 Launched companion tool: {item.name}")
        else:
            self.log(f"❌ Launch error: {msg}")
            QMessageBox.critical(self, "Launch Error", f"Failed to launch {item.name}:\n\n{msg}")

    # -------------------------------------------------------------------------
    # TIER 3: COMMON CLI & UTILITIES (5 Sub-Tabs including Firmware Downloader)
    # -------------------------------------------------------------------------
    def _create_tier3_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        sub_items = [
            ("cli_oem", "⚡ huawei-oeminfo-tool"),
            ("read_info", "🔍 Device Read Info"),
            ("drivers", "🔌 Huawei USB Drivers"),
            ("fw_dl", "🌐 Firmware Downloader"),
            ("console", "📋 Live Embedded Console"),
        ]
        sub_nav = SubNavBar(sub_items)
        layout.addWidget(sub_nav)

        self.tier3_sub_stack = QStackedWidget()
        self.tier3_sub_stack.addWidget(self._create_subtab_headless_oeminfo())
        self.tier3_sub_stack.addWidget(self._create_subtab_device_info())
        self.tier3_sub_stack.addWidget(self._create_subtab_driver_studio())
        self.tier3_sub_stack.addWidget(self._create_subtab_firmware_downloader())
        self.tier3_sub_stack.addWidget(self._create_subtab_terminal_console())

        self.tier3_sub_nav = sub_nav
        sub_nav.tab_changed.connect(self.tier3_sub_stack.setCurrentIndex)
        layout.addWidget(self.tier3_sub_stack, stretch=1)
        return page

    def _switch_to_console_tab(self):
        """Programmatically switch view to Live Embedded Console tab."""
        self._select_master_tier("tier3")
        if hasattr(self, "tier3_sub_nav"):
            self.tier3_sub_nav.select_tab(4)

    # --- Tier 3.1: huawei-oeminfo-tool CLI manager ---
    def _create_subtab_headless_oeminfo(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        card = EnterpriseCard("huawei-oeminfo-tool by ud3v0id", subtitle="MIT License CLI Engine")
        c_layout = QGridLayout()
        c_layout.setSpacing(6)

        self.txt_cli_oem_in = QLineEdit()
        self.txt_cli_oem_in.setPlaceholderText("Select raw OEMINFO image file...")
        btn_b_in = QPushButton("Browse Image...")
        btn_b_in.clicked.connect(lambda: self.txt_cli_oem_in.setText(QFileDialog.getOpenFileName(self, "Select OEMINFO", "", "OEMINFO Files (*.img *.bin *.mbn);;All Files (*.*)")[0]))

        self.txt_cli_oem_out = QLineEdit()
        self.txt_cli_oem_out.setPlaceholderText("Select extraction / repacking directory...")
        btn_b_out = QPushButton("Browse Dir...")
        btn_b_out.clicked.connect(lambda: self.txt_cli_oem_out.setText(QFileDialog.getExistingDirectory(self, "Select Directory")))

        c_layout.addWidget(QLabel("OEMINFO File:"), 0, 0)
        c_layout.addWidget(self.txt_cli_oem_in, 0, 1)
        c_layout.addWidget(btn_b_in, 0, 2)

        c_layout.addWidget(QLabel("Extract / Repack Dir:"), 1, 0)
        c_layout.addWidget(self.txt_cli_oem_out, 1, 1)
        c_layout.addWidget(btn_b_out, 1, 2)

        btn_inspect = QPushButton("🔍 Inspect Blocks")
        btn_inspect.clicked.connect(self._do_oem_cli_inspect)

        btn_unpack = QPushButton("📦 Unpack Blocks")
        btn_unpack.setProperty("class", "BtnPrimary")
        btn_unpack.clicked.connect(self._do_oem_cli_unpack)

        btn_repack = QPushButton("🔨 Repack Blocks")
        btn_repack.setProperty("class", "BtnSuccess")
        btn_repack.clicked.connect(self._do_oem_cli_repack)

        c_layout.addWidget(btn_inspect, 2, 0, 1, 3)
        c_layout.addWidget(btn_unpack, 3, 0, 1, 3)
        c_layout.addWidget(btn_repack, 4, 0, 1, 3)

        card.add_layout(c_layout)
        layout.addWidget(card)
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    def _do_oem_cli_inspect(self):
        inp = self.txt_cli_oem_in.text().strip("\"' ")
        if not inp or not Path(inp).exists():
            QMessageBox.warning(self, "File Required", "Please select a valid OEMINFO image.")
            return

        self._switch_to_console_tab()
        def worker(log_cb):
            log_cb(f"[*] Inspecting blocks in {inp}...")
            logger = CliLogger(debug=False, silent=False)
            logger.info = lambda msg: log_cb(f"  {msg}")
            unpacker = OemUnpacker(inp, "./dummy", dry_run=True, logger=logger)
            unpacker.run()
            log_cb("✔ Inspection finished!")

        self._run_async(worker, on_done=lambda ok, msg: QMessageBox.information(self, "Success", "Inspection completed! Check console.") if ok else QMessageBox.critical(self, "Error", msg))

    def _do_oem_cli_unpack(self):
        inp = self.txt_cli_oem_in.text().strip("\"' ")
        outp = self.txt_cli_oem_out.text().strip("\"' ")
        if not inp or not Path(inp).exists():
            QMessageBox.warning(self, "File Required", "Please select a valid OEMINFO image.")
            return
        if not outp:
            outp = str(Path(inp).parent / f"{Path(inp).stem}_unpacked")
            self.txt_cli_oem_out.setText(outp)

        self._switch_to_console_tab()
        def worker(log_cb):
            log_cb(f"[*] Unpacking blocks from {inp} to {outp}...")
            logger = CliLogger(debug=False, silent=False)
            logger.info = lambda msg: log_cb(f"  {msg}")
            unpacker = OemUnpacker(inp, outp, dry_run=False, logger=logger)
            unpacker.run()
            log_cb("✔ Unpack finished successfully!")

        self._run_async(worker, on_done=lambda ok, msg: QMessageBox.information(self, "Success", f"Unpacked to:\n{outp}") if ok else QMessageBox.critical(self, "Error", msg))

    def _do_oem_cli_repack(self):
        outp = self.txt_cli_oem_out.text().strip("\"' ")
        if not outp or not Path(outp).exists():
            QMessageBox.warning(self, "Dir Required", "Please select a directory containing unpacked blocks.")
            return
        out_f, _ = QFileDialog.getSaveFileName(self, "Save Repacked OEMINFO", "oeminfo_repacked.img", "Image Files (*.img);;All Files (*.*)")
        if not out_f:
            return

        self._switch_to_console_tab()
        def worker(log_cb):
            log_cb(f"[*] Repacking blocks from {outp} into {out_f}...")
            logger = CliLogger(debug=False, silent=False)
            logger.info = lambda msg: log_cb(f"  {msg}")
            packer = OemPacker(outp, out_f, logger=logger)
            packer.run()
            log_cb("✔ Repack finished successfully!")

        self._run_async(worker, on_done=lambda ok, msg: QMessageBox.information(self, "Success", f"Repacked OEMINFO created:\n{out_f}") if ok else QMessageBox.critical(self, "Error", msg))

    # --- Tier 3.2: Device Read Info ---
    def _create_subtab_device_info(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        card = EnterpriseCard("Huawei Hardware Identifier & Fastboot Properties", subtitle="Hardware Identification")

        btn_read = QPushButton("🔍 Read Complete Device Info (Fastboot & ADB)")
        btn_read.setProperty("class", "BtnPrimary")
        btn_read.clicked.connect(self._do_read_device_info_complete)
        card.add_widget(btn_read)

        self.tbl_info = EngineeringDataTable(0, 2)
        self.tbl_info.setHorizontalHeaderLabels(["Property", "Value"])
        self.tbl_info.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl_info.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        card.add_widget(self.tbl_info)

        layout.addWidget(card, stretch=1)
        return container

    def _do_read_device_info_complete(self):
        state = DeviceDetector.detect()
        if not state.is_connected:
            QMessageBox.warning(self, "Device Disconnected", "Please connect a device in Fastboot or ADB mode.")
            return

        self.tbl_info.setRowCount(0)
        self.log("[*] Reading complete device hardware information...")

        def add_row(k, v):
            r = self.tbl_info.rowCount()
            self.tbl_info.insertRow(r)
            self.tbl_info.setItem(r, 0, QTableWidgetItem(k))
            self.tbl_info.setItem(r, 1, QTableWidgetItem(str(v)))

        add_row("Connection Mode", state.mode)
        add_row("Identifier / Port", state.identifier or "N/A")
        add_row("Driver Details", state.details)

        if state.is_fastboot:
            try:
                res = subprocess.run([str(FASTBOOT_BIN), "getvar", "all"], capture_output=True, text=True, timeout=10)
                out = res.stdout + res.stderr
                for line in out.splitlines():
                    if ":" in line:
                        parts = line.split(":", 1)
                        prop = parts[0].replace("(bootloader)", "").strip()
                        val = parts[1].strip()
                        if prop and prop != "all":
                            add_row(prop, val)
                self.log("✔ Fastboot getvar variables read successfully.")
            except Exception as ex:
                self.log(f"Error reading fastboot: {ex}")

    # --- Tier 3.3: Huawei USB Drivers Studio ---
    def _create_subtab_driver_studio(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        card_drv = EnterpriseCard("Huawei USB COM 1.0 Driver & BCD Test Signing", subtitle="Driver Ingestion Hub")

        lbl_desc = QLabel(
            "Hardware Testpoint Mode requires the certified HUAWEI USB COM 1.0 serial driver.\n"
            "On modern 64-bit Windows systems, enabling BCD Test Signing is required for unsigned INF ingestion."
        )
        lbl_desc.setStyleSheet("color: #64748B; font-size: 11.5px;")
        card_drv.add_widget(lbl_desc)

        row_bcd = QHBoxLayout()
        row_bcd.setSpacing(8)

        btn_test_on = QPushButton("🛡️ Enable BCD Test Signing (TESTSIGNING ON)")
        btn_test_on.setProperty("class", "BtnWarning")
        btn_test_on.clicked.connect(self._do_enable_test_signing)

        btn_test_off = QPushButton("🔒 Disable BCD Test Signing (TESTSIGNING OFF)")
        btn_test_off.clicked.connect(self._do_disable_test_signing)

        row_bcd.addWidget(btn_test_on)
        row_bcd.addWidget(btn_test_off)
        card_drv.add_layout(row_bcd)

        btn_inst_drv = QPushButton("🔌 Ingest & Install Huawei USB COM 1.0 Driver (pnputil)")
        btn_inst_drv.setProperty("class", "BtnSuccess")
        btn_inst_drv.clicked.connect(self._do_install_usb_com)
        card_drv.add_widget(btn_inst_drv)

        layout.addWidget(card_drv)

        # Fastboot Diagnostics Card
        card_diag = EnterpriseCard("Official Huawei Fastboot Engine Status", subtitle="Fastboot Diagnostics")
        lbl_fb_src = QLabel(f"• Active Binary: {FASTBOOT_BIN}\n• Engine Source: {FASTBOOT_SOURCE}")
        lbl_fb_src.setStyleSheet("color: #047857; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11.5px; background: #ECFDF5; border: 1px solid #A7F3D0; border-radius: 6px; padding: 8px 10px;")
        card_diag.add_widget(lbl_fb_src)
        layout.addWidget(card_diag)

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    def _do_enable_test_signing(self):
        res = DriverManager.enable_test_signing()
        self.log(f"BCD Test Signing Enable: {res}")
        QMessageBox.information(self, "BCD Configuration", f"Command output:\n\n{res}\n\nNote: A Windows reboot may be required.")

    def _do_disable_test_signing(self):
        res = DriverManager.disable_test_signing()
        self.log(f"BCD Test Signing Disable: {res}")
        QMessageBox.information(self, "BCD Configuration", f"Command output:\n\n{res}")

    def _do_install_usb_com(self):
        self._switch_to_console_tab()
        def worker(log_cb):
            log_cb("[*] Ingesting Huawei USB COM 1.0 INF driver via pnputil...")
            res = DriverManager.install_huawei_usb_com()
            log_cb(f"✔ pnputil result: {res}")

        self._run_async(worker, on_done=lambda ok, msg: QMessageBox.information(self, "Driver Installation", "Driver installation command dispatched! Review console."))

    # --- Tier 3.4: Firmware Downloader (Direct Web-Links) ---
    def _create_subtab_firmware_downloader(self) -> QWidget:
        """
        Firmware Downloader Sub-Tab featuring direct browser web-links
        to official Huawei/Honor factory firmwares, dumps, XMLs, passwords, and GSI ROMs.
        """
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Category A: Factory & Official Firmware
        card_fact = EnterpriseCard("Factory & Official Stock Firmwares", subtitle="Direct High-Speed HTTP Repository", badge_text="● Official Mirrors", badge_class="BadgeGreen")

        lbl_f_desc = QLabel("Access official Huawei & Honor stock firmware packages, unbricking board software (BD), and regular service releases:")
        lbl_f_desc.setStyleSheet("color: #334155; font-size: 12px;")
        card_fact.add_widget(lbl_f_desc)

        row_f_btns = QHBoxLayout()
        row_f_btns.setSpacing(10)

        btn_bd = QPushButton("🏭 Factory Firmware (BD)")
        btn_bd.setProperty("class", "BtnPrimary")
        btn_bd.setCursor(Qt.PointingHandCursor)
        btn_bd.setToolTip("https://iqinixfh.nopajeets.lol/Huawei,%20Honor/Firmware/BD/")
        btn_bd.clicked.connect(lambda: self._open_external_url("https://iqinixfh.nopajeets.lol/Huawei,%20Honor/Firmware/BD/"))
        row_f_btns.addWidget(btn_bd)

        btn_reg = QPushButton("📦 Official Huawei / Honor Firmware (Regular)")
        btn_reg.setProperty("class", "BtnPrimary")
        btn_reg.setCursor(Qt.PointingHandCursor)
        btn_reg.setToolTip("https://iqinixfh.nopajeets.lol/Huawei,%20Honor/Firmware/Regular/")
        btn_reg.clicked.connect(lambda: self._open_external_url("https://iqinixfh.nopajeets.lol/Huawei,%20Honor/Firmware/Regular/"))
        row_f_btns.addWidget(btn_reg)

        card_fact.add_layout(row_f_btns)
        layout.addWidget(card_fact)

        # Category B: Dumps, XML, BAT & Passwords
        card_dumps = EnterpriseCard("Dumps, XML Configurations, BAT Scripts & Passwords", subtitle="Partition Images & Archive Keys", badge_text="● Service Dumps", badge_class="BadgeBlue")

        lbl_d_desc = QLabel("Download full partition dumps (HTF, XML, BAT unbrick sequences) and extraction passwords for protected firmware archives:")
        lbl_d_desc.setStyleSheet("color: #334155; font-size: 12px;")
        card_dumps.add_widget(lbl_d_desc)

        row_d_btns = QHBoxLayout()
        row_d_btns.setSpacing(10)

        btn_dumps = QPushButton("💾 Huawei / Honor Dump (HTF, XML, BAT)")
        btn_dumps.setProperty("class", "BtnSuccess")
        btn_dumps.setCursor(Qt.PointingHandCursor)
        btn_dumps.setToolTip("https://iqinixfh.nopajeets.lol/Huawei,%20Honor/Firmware/Dump,%20XML,%20bat/")
        btn_dumps.clicked.connect(lambda: self._open_external_url("https://iqinixfh.nopajeets.lol/Huawei,%20Honor/Firmware/Dump,%20XML,%20bat/"))
        row_d_btns.addWidget(btn_dumps)

        btn_pass = QPushButton("🔑 Firmware Passwords (FIRMWARE PASSWORDS.txt)")
        btn_pass.setProperty("class", "BtnWarning")
        btn_pass.setCursor(Qt.PointingHandCursor)
        btn_pass.setToolTip("https://iqinixfh.nopajeets.lol/Huawei,%20Honor/Firmware/1.%20FIRMWARE%20PASSWORDS.txt")
        btn_pass.clicked.connect(lambda: self._open_external_url("https://iqinixfh.nopajeets.lol/Huawei,%20Honor/Firmware/1.%20FIRMWARE%20PASSWORDS.txt"))
        row_d_btns.addWidget(btn_pass)

        card_dumps.add_layout(row_d_btns)
        layout.addWidget(card_dumps)

        # Category C: Custom ROMs & GSI (SourceForge)
        card_gsi = EnterpriseCard("Custom ROMs & Project Treble GSIs", subtitle="SourceForge Community Archive", badge_text="● Open Source", badge_class="BadgeAmber")

        lbl_g_desc = QLabel("Download tested Project Treble Generic System Images (GSIs), custom recoveries, and Android custom ROMs built for Huawei & Honor devices:")
        lbl_g_desc.setStyleSheet("color: #334155; font-size: 12px;")
        card_gsi.add_widget(lbl_g_desc)

        btn_sf = QPushButton("🚀 All GSI & Custom ROMs (SourceForge Mirror)")
        btn_sf.setProperty("class", "BtnSuccess")
        btn_sf.setCursor(Qt.PointingHandCursor)
        btn_sf.setToolTip("https://sourceforge.net/projects/altairfr-huawei/files/")
        btn_sf.clicked.connect(lambda: self._open_external_url("https://sourceforge.net/projects/altairfr-huawei/files/"))
        card_gsi.add_widget(btn_sf)

        layout.addWidget(card_gsi)
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    def _open_external_url(self, url: str):
        """Opens external URL in system default browser using QDesktopServices."""
        self.log(f"🌐 Opening external portal: {url}")
        QDesktopServices.openUrl(QUrl(url))

    # --- Tier 3.5: Live Embedded Console ---
    def _create_subtab_terminal_console(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        card = EnterpriseCard("Live Embedded Diagnostic Terminal", subtitle="Real-Time Logging Stream")

        self.console_edit = QPlainTextEdit()
        self.console_edit.setProperty("class", "TerminalConsole")
        self.console_edit.setReadOnly(True)
        card.add_widget(self.console_edit)

        row_ctrl = QHBoxLayout()
        row_ctrl.setSpacing(8)

        btn_clear = QPushButton("🧹 Clear Console")
        btn_clear.clicked.connect(self.console_edit.clear)

        btn_copy = QPushButton("📋 Copy All")
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.console_edit.toPlainText()))

        btn_export = QPushButton("💾 Save Log to File")
        btn_export.clicked.connect(self._export_console_log)

        row_ctrl.addWidget(btn_clear)
        row_ctrl.addWidget(btn_copy)
        row_ctrl.addWidget(btn_export)
        row_ctrl.addStretch()

        card.add_layout(row_ctrl)
        layout.addWidget(card, stretch=1)
        return container

    def _export_console_log(self):
        f, _ = QFileDialog.getSaveFileName(self, "Save Console Log", "toolkit_console.log", "Log Files (*.log);;All Files (*.*)")
        if f:
            with open(f, "w", encoding="utf-8") as out:
                out.write(self.console_edit.toPlainText())
            QMessageBox.information(self, "Log Saved", f"Log saved to:\n{f}")

    # -------------------------------------------------------------------------
    # ABOUT & ARCHITECTURE CREDITS PAGE (Includes XDA Developers & Attribution)
    # -------------------------------------------------------------------------
    def _create_about_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Lead Developer Hub Card
        card_dev = EnterpriseCard("Lead Developer & Official GitHub Hub", subtitle="Open Source Firmware Research")
        dev_layout = QHBoxLayout()
        lbl_dev_info = QLabel(
            "Project Lead & Core Firmware Research:\n"
            "Official Open-Source Hub: https://github.com/FrgfA4ftfzTdfyyyr5f6tESD3\n\n"
            "Dedicated to transparent, 100% intellectual property compliant Kirin servicing."
        )
        lbl_dev_info.setStyleSheet("color: #0F172A; font-size: 12.5px;")
        dev_layout.addWidget(lbl_dev_info, stretch=1)

        btn_gh = QPushButton("🔗 Open GitHub Profile")
        btn_gh.setProperty("class", "BtnSuccess")
        btn_gh.setCursor(Qt.PointingHandCursor)
        btn_gh.clicked.connect(lambda: webbrowser.open("https://github.com/FrgfA4ftfzTdfyyyr5f6tESD3"))
        dev_layout.addWidget(btn_gh)
        card_dev.add_layout(dev_layout)
        layout.addWidget(card_dev)

        # XDA Developers & Key Contributors Card (AltairFR & IQINIX)
        card_xda = EnterpriseCard(
            "Official Community Contributors & XDA Developers",
            subtitle="Key Firmware Researchers & GSI Creators",
            badge_text="● XDA Senior Members",
            badge_class="BadgeAmber"
        )

        lbl_xda_intro = QLabel(
            "Special recognition and direct access to esteemed XDA developers who provide vital firmware dumps, "
            "Treble GSIs, decryption passwords, and community research for Huawei & Honor devices:"
        )
        lbl_xda_intro.setStyleSheet("color: #334155; font-size: 12px; margin-bottom: 4px;")
        card_xda.add_widget(lbl_xda_intro)

        # Contributor 1: AltairFR
        c1_frame = QFrame()
        c1_frame.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 12px;")
        c1_layout = QHBoxLayout(c1_frame)
        c1_info = QVBoxLayout()
        lbl_c1_title = QLabel("AltairFR")
        lbl_c1_title.setFont(QFont("Segoe UI", 10, QFont.Bold))
        lbl_c1_title.setStyleSheet("color: #1E40AF;")
        lbl_c1_desc = QLabel("Custom ROMs, Project Treble GSI Builds, Custom Recoveries & Partition Servicing Tools Contributor")
        lbl_c1_desc.setStyleSheet("color: #475569; font-size: 11.5px;")
        c1_info.addWidget(lbl_c1_title)
        c1_info.addWidget(lbl_c1_desc)
        c1_layout.addLayout(c1_info, stretch=1)

        btn_c1 = QPushButton("🌐 Open AltairFR XDA Profile")
        btn_c1.setProperty("class", "BtnPrimary")
        btn_c1.setCursor(Qt.PointingHandCursor)
        btn_c1.clicked.connect(lambda: self._open_external_url("https://xdaforums.com/m/altairfr.11572895/"))
        c1_layout.addWidget(btn_c1)
        card_xda.add_widget(c1_frame)

        # Contributor 2: IQINIX
        c2_frame = QFrame()
        c2_frame.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 12px;")
        c2_layout = QHBoxLayout(c2_frame)
        c2_info = QVBoxLayout()
        lbl_c2_title = QLabel("IQINIX")
        lbl_c2_title.setFont(QFont("Segoe UI", 10, QFont.Bold))
        lbl_c2_title.setStyleSheet("color: #1E40AF;")
        lbl_c2_desc = QLabel("Official & Factory Firmware (BD), Raw Scatter Dumps (HTF/XML/BAT) & Decryption Keys Contributor")
        lbl_c2_desc.setStyleSheet("color: #475569; font-size: 11.5px;")
        c2_info.addWidget(lbl_c2_title)
        c2_info.addWidget(lbl_c2_desc)
        c2_layout.addLayout(c2_info, stretch=1)

        btn_c2 = QPushButton("🌐 Open IQINIX XDA Profile")
        btn_c2.setProperty("class", "BtnSuccess")
        btn_c2.setCursor(Qt.PointingHandCursor)
        btn_c2.clicked.connect(lambda: self._open_external_url("https://xdaforums.com/m/iqinix.13248003/"))
        c2_layout.addWidget(btn_c2)
        card_xda.add_widget(c2_frame)

        layout.addWidget(card_xda)

        # Architecture Overview Card
        card_arch = EnterpriseCard("Tri-Tier Cyber-Engineering Architecture", subtitle="System Modularity")
        txt_arch_desc = (
            "1. TIER 1: NATIVE IN-HOUSE CORE\n"
            "   • Pure Python engines for EROFS, OEMINFO rebranding, NVE calibration, and GPT balancing.\n"
            "   • Direct HiSilicon Fastboot RAM register injection for Kirin 710.\n\n"
            "2. TIER 2: STANDALONE GUI COMPANIONS (ZERO-CONFIG HUB)\n"
            "   • Zero bundled third-party binaries. Complete compliance with official developer licenses.\n"
            "   • Automatic background download, unpack, and isolated process launching.\n\n"
            "3. TIER 3: COMMON CLI UTILITIES, FIRMWARE DOWNLOADER & CONSOLE\n"
            "   • Live embedded terminal log streaming without GUI freezing.\n"
            "   • Direct portal to official Huawei/Honor factory firmwares, board software, and GSIs."
        )
        lbl_a = QLabel(txt_arch_desc)
        lbl_a.setStyleSheet("color: #1E293B; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 10px;")
        card_arch.add_widget(lbl_a)
        layout.addWidget(card_arch)

        # Acknowledgments Card
        card_ack = EnterpriseCard("Referenced Projects & Developer Acknowledgments", subtitle="Open Source Attribution")

        projects_data = [
            ("📁 huawei-oeminfo-tool", "ud3v0id", "MIT License", "OEMInfo parsing, unpacking, and repacking algorithms for EMUI & MagicOS devices."),
            ("⚡ KirinBootstrapper", "mashed-potatoes", "GPLv3 License", "Kirin USB Download Mode bootstrap sequences and direct image upload pipelines."),
            ("📦 HuaweiFirmwareExtractor", "Igor Eisberg", "GPLv3 License", "Robust UPDATE.APP binary chunk extraction, CRC verification, and header parsing."),
            ("⚡ FastbootFlasher", "mashed-potatoes", "GPLv3 License", "Fastboot sequential flash automation and partition streaming architectures."),
            ("🛡️ hw-rec", "HW-Rec Team", "Render License", "Huawei recovery partition inspection, safety backup and client protocols."),
            ("🔧 KirinTool.ImageFlasher & Kirin-Tool", "Kethily Daniel & NDXCode", "BSL 1.1 / GPLv3", "Advanced Kirin SoC service protocols, bootloader loaders, and repair operations."),
            ("🔓 Huawei-Unlock-Tool & Linux Port", "Huawei Unlock Team", "AGPLv3 / GPLv3", "Hardware testpoint unlock methodologies, factory boot sequences, and cross-platform UI."),
            ("🧬 Huawei-EMUI-9.x-Early-EROFS-Unpack-Toolkit", "EROFS Team", "MIT License", "Early EMUI 9.x EROFS filesystem unpacking, EXT4 conversion, and partition rebuilders."),
            ("🍳 MIO-KITCHEN", "kemiaojiang / Android Tools", "AGPLv3 / Apache 2.0", "EROFS compression tools, sparse image utilities, and ROM kitchen unpackers."),
            ("🛠️ Android Utility (A-Utility)", "mfl / AndroidUtility Team", "Freeware Utility", "Universal partition servicing, sparse image builders, and ADB stream helpers.")
        ]

        for pname, pauth, plic, pdesc in projects_data:
            p_frame = QFrame()
            p_frame.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px;")
            p_lay = QVBoxLayout(p_frame)
            p_lay.setContentsMargins(8, 6, 8, 6)
            p_lay.setSpacing(2)

            top = QHBoxLayout()
            l1 = QLabel(pname)
            l1.setFont(QFont("Segoe UI", 8.5, QFont.Bold))
            l1.setStyleSheet("color: #1E40AF;")
            l2 = QLabel(f"by {pauth}")
            l2.setStyleSheet("color: #64748B; font-style: italic;")
            l3 = QLabel(plic)
            l3.setProperty("class", "BadgeBlue")
            top.addWidget(l1)
            top.addWidget(l2)
            top.addStretch()
            top.addWidget(l3)
            p_lay.addLayout(top)

            desc = QLabel(f"• {pdesc}")
            desc.setStyleSheet("color: #475569; font-size: 10.5px;")
            p_lay.addWidget(desc)
            card_ack.add_widget(p_frame)

        layout.addWidget(card_ack)
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    # -------------------------------------------------------------------------
    # HELPERS: LOGGING, MULTITHREADING, AND HARDWARE DETECTION
    # -------------------------------------------------------------------------
    def log(self, msg: str):
        """Append log message into console in real time safely."""
        if hasattr(self, "console_edit"):
            self.console_edit.appendPlainText(msg)
            self.console_edit.moveCursor(QTextCursor.End)
        try:
            print(msg)
        except Exception:
            pass

    def _run_async(self, func: Callable, on_done: Optional[Callable[[bool, str], None]] = None):
        """Dispatches long-running worker function in background QThread."""
        worker = GenericWorker(func)
        worker.log_signal.connect(self.log)
        if on_done:
            worker.finished_signal.connect(on_done)
        worker.start()
        # Keep reference so it doesn't get garbage collected
        if not hasattr(self, "_active_workers"):
            self._active_workers = []
        self._active_workers.append(worker)
        worker.finished.connect(lambda: self._active_workers.remove(worker) if worker in self._active_workers else None)

    def _manual_scan_device(self):
        state = DeviceDetector.detect()
        self._on_device_state_updated(state)
        self.log(f"[*] Manual USB Hardware Scan: {state.mode} ({state.identifier or 'N/A'}) - {state.details}")

    @Slot(object)
    def _on_device_state_updated(self, state: DeviceState):
        """Updates top bar hardware indicator pill based on USB detector state."""
        if not hasattr(self, "lbl_device_status"):
            return

        if state.is_connected:
            text = f"● {state.mode}"
            if state.identifier:
                text += f" ({state.identifier})"
            self.lbl_device_status.setText(text)
            self.lbl_device_status.setProperty("class", "BadgeGreen")
        else:
            self.lbl_device_status.setText("○ Disconnected")
            self.lbl_device_status.setProperty("class", "BadgeGray")

        self.lbl_device_status.style().unpolish(self.lbl_device_status)
        self.lbl_device_status.style().polish(self.lbl_device_status)


# =============================================================================
# APPLICATION ENTRY POINT
# =============================================================================
def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(ENTERPRISE_LIGHT_QSS)

    window = UnifiedToolkitWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()