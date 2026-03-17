"""Sidebar Advanced Filter Widget - collapsible panel for page size/orientation/range filter"""
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QCheckBox, QLineEdit, QGridLayout
)
from PyQt5.QtCore import Qt, pyqtSignal

ALL_SIZES = ["A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7"]

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
_CHECK_DARK = os.path.join(_ASSETS_DIR, "check-dark.svg").replace("\\", "/")
_CHECK_GRAY = os.path.join(_ASSETS_DIR, "check-gray.svg").replace("\\", "/")

PANEL_STYLE = """
QFrame#filter_panel {
    background-color: white;
    border-top: 1px solid #E5E7EB;
}
"""
CHECKBOX_STYLE = f"""
QCheckBox {{
    font-size: 12px;
    color: #374151;
    spacing: 4px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 13px;
    height: 13px;
    border: 1px solid #9CA3AF;
    border-radius: 2px;
    background: white;
}}
QCheckBox::indicator:checked {{
    border-color: #6B7280;
    background: white;
    image: url({_CHECK_DARK});
}}
QCheckBox::indicator:unchecked {{
    border-color: #9CA3AF;
    background: white;
}}
QCheckBox:disabled {{
    color: #C0C0C0;
}}
QCheckBox::indicator:disabled {{
    border-color: #D1D5DB;
    background: #F3F4F6;
}}
QCheckBox::indicator:checked:disabled {{
    border-color: #D1D5DB;
    background: #F3F4F6;
    image: url({_CHECK_GRAY});
}}
"""
LABEL_STYLE = "font-size: 11px; color: #6B7280; font-weight: bold; background: transparent;"
RANGE_STYLE = """
QLineEdit {
    border: 1px solid #D1D5DB;
    border-radius: 3px;
    padding: 2px 5px;
    font-size: 11px;
    background: white;
}
QLineEdit:focus { border-color: #3B82F6; }
"""
RANGE_ERROR_STYLE = """
QLineEdit {
    border: 1px solid #EF4444;
    border-radius: 3px;
    padding: 2px 5px;
    font-size: 11px;
    background: white;
}
"""
BTN_APPLY_STYLE = """
QPushButton {
    background: #3B82F6;
    border: none;
    border-radius: 3px;
    font-size: 11px;
    color: white;
    padding: 3px 10px;
    font-weight: bold;
}
QPushButton:hover { background: #2563EB; }
"""
COLLAPSE_BTN_STYLE = """
QPushButton {
    font-size: 11px;
    color: #6B7280;
    background: transparent;
    border: none;
    padding: 2px 4px;
}
QPushButton:hover { color: #1D4ED8; }
"""


def _validate_range_text(text: str) -> bool:
    """Return True if text is empty/all or a valid page range like '1-5, 7, 10-15'"""
    text = text.strip()
    if not text or text.lower() == 'all':
        return True
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            segments = part.split("-")
            if len(segments) != 2:
                return False
            try:
                a, b = int(segments[0].strip()), int(segments[1].strip())
                if a < 1 or b < a:
                    return False
            except ValueError:
                return False
        else:
            try:
                if int(part) < 1:
                    return False
            except ValueError:
                return False
    return True


class SidebarAdvancedFilter(QWidget):
    """Collapsible advanced filter panel for sidebar bottom"""

    apply_requested = pyqtSignal(set, set, str)  # (sizes, orientations, range_text)
    reset_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._collapsed = False
        self._updating_master = False
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Header row: [☑ all] [Lọc nâng cao] [stretch] [▼/▶] ──
        header_widget = QWidget()
        header_widget.setStyleSheet("background-color: white;")
        header_widget.setFixedHeight(26)
        header_row = QHBoxLayout(header_widget)
        header_row.setContentsMargins(4, 2, 4, 2)
        header_row.setSpacing(4)

        self._cb_all = QCheckBox()
        self._cb_all.setTristate(True)
        self._cb_all.setCheckState(Qt.Checked)
        self._cb_all.setToolTip("Chọn tất cả / Bỏ chọn tất cả")
        self._cb_all.setStyleSheet(CHECKBOX_STYLE)
        self._cb_all.stateChanged.connect(self._on_master_changed)
        header_row.addWidget(self._cb_all)

        title_lbl = QLabel("Lọc nâng cao")
        title_lbl.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #374151; background: transparent;"
        )
        header_row.addWidget(title_lbl)
        header_row.addStretch()

        self._collapse_btn = QPushButton("▼")
        self._collapse_btn.setStyleSheet(COLLAPSE_BTN_STYLE)
        self._collapse_btn.setFixedSize(20, 20)
        self._collapse_btn.setToolTip("Thu gọn / Mở rộng")
        self._collapse_btn.clicked.connect(self._toggle_collapse)
        header_row.addWidget(self._collapse_btn)

        main_layout.addWidget(header_widget)

        # ── Body panel (collapsible) ──
        self._panel = QFrame()
        self._panel.setObjectName("filter_panel")
        self._panel.setStyleSheet(PANEL_STYLE)
        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(8, 6, 8, 6)
        panel_layout.setSpacing(6)

        size_label = QLabel("Kích thước trang:")
        size_label.setStyleSheet(LABEL_STYLE)
        panel_layout.addWidget(size_label)

        grid = QGridLayout()
        grid.setSpacing(2)
        self._size_checks: dict = {}
        for i, size in enumerate(ALL_SIZES):
            cb = QCheckBox(size)
            cb.setStyleSheet(CHECKBOX_STYLE)
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_child_changed)
            self._size_checks[size] = cb
            grid.addWidget(cb, i // 4, i % 4)
        panel_layout.addLayout(grid)

        orient_label = QLabel("Chiều trang:")
        orient_label.setStyleSheet(LABEL_STYLE)
        panel_layout.addWidget(orient_label)

        orient_row = QHBoxLayout()
        orient_row.setSpacing(8)
        self._cb_landscape = QCheckBox("Ngang")
        self._cb_portrait = QCheckBox("Dọc")
        for cb in (self._cb_landscape, self._cb_portrait):
            cb.setStyleSheet(CHECKBOX_STYLE)
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_child_changed)
        orient_row.addWidget(self._cb_landscape)
        orient_row.addWidget(self._cb_portrait)
        orient_row.addStretch()
        panel_layout.addLayout(orient_row)

        range_label = QLabel("Dải trang:")
        range_label.setStyleSheet(LABEL_STYLE)
        panel_layout.addWidget(range_label)

        self._range_input = QLineEdit()
        self._range_input.setPlaceholderText("all  (vd: 1-5, 7, 10-15)")
        self._range_input.setStyleSheet(RANGE_STYLE)
        self._range_input.textChanged.connect(self._on_range_text_changed)
        panel_layout.addWidget(self._range_input)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_apply = QPushButton("Áp dụng")
        self._btn_apply.setStyleSheet(BTN_APPLY_STYLE)
        self._btn_apply.clicked.connect(self._on_apply)
        btn_row.addWidget(self._btn_apply)
        panel_layout.addLayout(btn_row)

        main_layout.addWidget(self._panel)

    def _enabled_size_checks(self):
        """Return only enabled (available) size checkboxes"""
        return [cb for cb in self._size_checks.values() if cb.isEnabled()]

    def _enabled_orient_checks(self):
        """Return only enabled orientation checkboxes"""
        cbs = []
        if self._cb_landscape.isEnabled():
            cbs.append(self._cb_landscape)
        if self._cb_portrait.isEnabled():
            cbs.append(self._cb_portrait)
        return cbs

    def _on_master_changed(self, state: int):
        if self._updating_master:
            return
        checked = (state == Qt.Checked)
        self._updating_master = True
        for cb in self._enabled_size_checks():
            cb.setChecked(checked)
        for cb in self._enabled_orient_checks():
            cb.setChecked(checked)
        self._updating_master = False
        if not checked:
            self._range_input.clear()
            self.reset_requested.emit()

    def _on_child_changed(self):
        if self._updating_master:
            return
        enabled_size = self._enabled_size_checks()
        enabled_orient = self._enabled_orient_checks()
        enabled_all = enabled_size + enabled_orient
        if not enabled_all:
            return
        all_checked = all(cb.isChecked() for cb in enabled_all)
        none_checked = not any(cb.isChecked() for cb in enabled_all)
        self._updating_master = True
        if all_checked:
            self._cb_all.setCheckState(Qt.Checked)
        elif none_checked:
            self._cb_all.setCheckState(Qt.Unchecked)
        else:
            self._cb_all.setCheckState(Qt.PartiallyChecked)
        self._updating_master = False

    def reset_availability(self):
        """Re-enable all checkboxes to default state (call when loading new folder)."""
        self._updating_master = True
        for cb in self._size_checks.values():
            cb.setEnabled(True)
            cb.setChecked(True)
        self._cb_landscape.setEnabled(True)
        self._cb_landscape.setChecked(True)
        self._cb_portrait.setEnabled(True)
        self._cb_portrait.setChecked(True)
        self._cb_all.setCheckState(Qt.Checked)
        self._updating_master = False

    def update_available_options(self, existing_sizes: set, has_landscape: bool, has_portrait: bool):
        """Enable/disable size and orientation checkboxes based on what actually exists.

        Checkboxes for sizes/orientations not present in any loaded file are disabled
        (grayed out). Disabled checkboxes are reset to checked (their default).
        If no standard sizes found (all pages are non-standard), keep all enabled.
        """
        # If no standard A-sizes detected at all, keep all size checkboxes enabled
        no_size_data = len(existing_sizes) == 0
        # If no orientation data at all, keep both orientation checkboxes enabled
        no_orient_data = not has_landscape and not has_portrait

        self._updating_master = True
        for size, cb in self._size_checks.items():
            available = no_size_data or (size in existing_sizes)
            cb.setEnabled(available)
            if not available:
                cb.setChecked(True)  # Reset disabled ones to default checked
        landscape_enabled = no_orient_data or has_landscape
        portrait_enabled = no_orient_data or has_portrait
        self._cb_landscape.setEnabled(landscape_enabled)
        self._cb_portrait.setEnabled(portrait_enabled)
        if not landscape_enabled:
            self._cb_landscape.setChecked(True)
        if not portrait_enabled:
            self._cb_portrait.setChecked(True)
        self._updating_master = False
        self._on_child_changed()  # Sync master checkbox state

    def _toggle_collapse(self):
        self._collapsed = not self._collapsed
        self._panel.setVisible(not self._collapsed)
        self._collapse_btn.setText("▶" if self._collapsed else "▼")

    def _on_range_text_changed(self, text: str):
        if text.strip() and not _validate_range_text(text):
            self._range_input.setStyleSheet(RANGE_ERROR_STYLE)
        else:
            self._range_input.setStyleSheet(RANGE_STYLE)

    def _on_apply(self):
        range_text = self._range_input.text().strip()
        if not _validate_range_text(range_text):
            self._range_input.setStyleSheet(RANGE_ERROR_STYLE)
            return
        sizes = {s for s, cb in self._size_checks.items() if cb.isChecked()}
        # All 8 sizes checked = no size filter (include non-standard sizes too)
        if len(sizes) == len(ALL_SIZES):
            sizes = set()
        orientations = set()
        if self._cb_landscape.isChecked():
            orientations.add("landscape")
        if self._cb_portrait.isChecked():
            orientations.add("portrait")
        # Both orientations checked = no orientation filter
        if len(orientations) == 2:
            orientations = set()
        self.apply_requested.emit(sizes, orientations, range_text)

    def get_state(self) -> tuple:
        """Return current filter state as (sizes, orientations, range_text)"""
        sizes = {s for s, cb in self._size_checks.items() if cb.isChecked()}
        orientations = set()
        if self._cb_landscape.isChecked():
            orientations.add("landscape")
        if self._cb_portrait.isChecked():
            orientations.add("portrait")
        return sizes, orientations, self._range_input.text().strip()
