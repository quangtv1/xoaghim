"""
Compact Settings Toolbar - Icon-only toolbar for collapsed settings panel state
"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QButtonGroup
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor

from ui.compact_toolbar_icons import CompactIconButton, CompactIconSeparator


class CompactSettingsToolbar(QWidget):
    """Icon-only toolbar for collapsed state of settings panel"""

    # Signals to sync with main SettingsPanel
    zone_toggled = pyqtSignal(str, bool)      # zone_id, enabled
    filter_changed = pyqtSignal(str)          # filter_mode: 'all', 'odd', 'even', 'none'
    draw_mode_changed = pyqtSignal(object)    # mode: 'remove', 'protect', or None
    clear_zones = pyqtSignal()
    ai_detect_toggled = pyqtSignal(bool)      # AI detect protect zones

    def __init__(self, parent=None):
        super().__init__(parent)
        self._zone_buttons = {}
        self._filter_buttons = {}
        self._draw_buttons = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(1)
        layout.setAlignment(Qt.AlignVCenter)

        # Set fixed height to prevent clipping
        self.setFixedHeight(42)

        # Set white background
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(255, 255, 255))
        self.setPalette(palette)

        self.setStyleSheet("""
            CompactSettingsToolbar {
                background-color: #FFFFFF;
                border-bottom: 1px solid #D1D5DB;
            }
        """)

        # === Góc group (4 corners) ===
        self._add_corner_icons(layout)
        layout.addWidget(CompactIconSeparator())

        # === Cạnh group (4 edges) ===
        self._add_edge_icons(layout)
        layout.addWidget(CompactIconSeparator())

        # === Tùy biến group (draw modes) ===
        self._add_custom_icons(layout)
        layout.addWidget(CompactIconSeparator())

        # === Filter group ===
        self._add_filter_icons(layout)

        # === Clear button ===
        self._add_clear_button(layout)
        layout.addWidget(CompactIconSeparator())

        # === AI Detect button ===
        self._add_ai_detect_button(layout)

        # Stretch for spacing
        layout.addStretch()

    def _add_corner_icons(self, layout: QHBoxLayout):
        """Add 4 corner zone toggle buttons"""
        corners = [
            ('corner_tl', 'Góc trên trái'),
            ('corner_tr', 'Góc trên phải'),
            ('corner_bl', 'Góc dưới trái'),
            ('corner_br', 'Góc dưới phải'),
        ]

        for zone_id, tooltip in corners:
            btn = CompactIconButton(zone_id, tooltip)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, zid=zone_id: self._on_zone_clicked(zid, checked))
            self._zone_buttons[zone_id] = btn
            layout.addWidget(btn)

    def _add_edge_icons(self, layout: QHBoxLayout):
        """Add 4 edge/margin zone toggle buttons"""
        edges = [
            ('margin_top', 'Cạnh trên'),
            ('margin_bottom', 'Cạnh dưới'),
            ('margin_left', 'Cạnh trái'),
            ('margin_right', 'Cạnh phải'),
        ]

        for zone_id, tooltip in edges:
            btn = CompactIconButton(zone_id, tooltip)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, zid=zone_id: self._on_zone_clicked(zid, checked))
            self._zone_buttons[zone_id] = btn
            layout.addWidget(btn)

    def _add_custom_icons(self, layout: QHBoxLayout):
        """Add draw mode buttons (remove/protect)"""
        draw_modes = [
            ('draw_remove', 'Vẽ vùng xóa ghim'),
            ('draw_protect', 'Vẽ vùng bảo vệ'),
        ]

        for mode_id, tooltip in draw_modes:
            btn = CompactIconButton(mode_id, tooltip)
            btn.setCheckable(True)
            mode = 'remove' if mode_id == 'draw_remove' else 'protect'
            btn.clicked.connect(lambda checked, m=mode: self._on_draw_mode_clicked(m, checked))
            self._draw_buttons[mode_id] = btn
            layout.addWidget(btn)

    def _add_filter_icons(self, layout: QHBoxLayout):
        """Add page filter buttons (exclusive selection)"""
        filters = [
            ('filter_all', 'Áp dụng tất cả trang', 'all'),
            ('filter_odd', 'Chỉ trang lẻ (1, 3, 5...)', 'odd'),
            ('filter_even', 'Chỉ trang chẵn (2, 4, 6...)', 'even'),
            ('filter_free', 'Chỉ trang đang xem', 'none'),
        ]

        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)

        for btn_id, tooltip, filter_mode in filters:
            btn = CompactIconButton(btn_id, tooltip)
            btn.setCheckable(True)
            btn.setProperty('filter_mode', filter_mode)
            self._filter_group.addButton(btn)
            self._filter_buttons[filter_mode] = btn
            layout.addWidget(btn)

        # Connect group signal
        self._filter_group.buttonClicked.connect(self._on_filter_clicked)

        # Default selection
        self._filter_buttons['all'].setChecked(True)

    def _add_clear_button(self, layout: QHBoxLayout):
        """Add clear zones button"""
        self.clear_btn = CompactIconButton('clear', 'Xóa tất cả vùng đã chọn')
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        layout.addWidget(self.clear_btn)

    def _add_ai_detect_button(self, layout: QHBoxLayout):
        """Add AI detect protect zones button"""
        self.ai_detect_btn = CompactIconButton('ai_detect', 'Nhận diện vùng bảo vệ')
        self.ai_detect_btn.setCheckable(True)
        self.ai_detect_btn.clicked.connect(self._on_ai_detect_clicked)
        layout.addWidget(self.ai_detect_btn)

    # === Event handlers ===

    def _on_zone_clicked(self, zone_id: str, checked: bool):
        """Handle zone toggle"""
        self.zone_toggled.emit(zone_id, checked)

    def _on_draw_mode_clicked(self, mode: str, checked: bool):
        """Handle draw mode toggle"""
        # Uncheck other draw mode
        for btn_id, btn in self._draw_buttons.items():
            expected_mode = 'remove' if btn_id == 'draw_remove' else 'protect'
            if expected_mode != mode:
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.blockSignals(False)

        # Emit signal
        if checked:
            self.draw_mode_changed.emit(mode)
        else:
            self.draw_mode_changed.emit(None)

    def _on_filter_clicked(self, btn):
        """Handle filter selection"""
        filter_mode = btn.property('filter_mode')
        self.filter_changed.emit(filter_mode)

    def _on_clear_clicked(self):
        """Handle clear zones"""
        self.clear_zones.emit()

    def _on_ai_detect_clicked(self, checked: bool):
        """Handle AI detect toggle"""
        self.ai_detect_toggled.emit(checked)

    # === Public API for syncing state ===

    def set_zone_state(self, zone_id: str, enabled: bool):
        """Update zone button state"""
        if zone_id in self._zone_buttons:
            self._zone_buttons[zone_id].blockSignals(True)
            self._zone_buttons[zone_id].setChecked(enabled)
            self._zone_buttons[zone_id].blockSignals(False)

    def set_filter_state(self, filter_mode: str):
        """Update filter button state"""
        if filter_mode in self._filter_buttons:
            self._filter_buttons[filter_mode].blockSignals(True)
            self._filter_buttons[filter_mode].setChecked(True)
            self._filter_buttons[filter_mode].blockSignals(False)

    def set_draw_mode_state(self, mode):
        """Update draw mode button state"""
        for btn_id, btn in self._draw_buttons.items():
            expected_mode = 'remove' if btn_id == 'draw_remove' else 'protect'
            btn.blockSignals(True)
            btn.setChecked(mode == expected_mode)
            btn.blockSignals(False)

    def set_ai_detect_state(self, enabled: bool):
        """Update AI detect button state"""
        self.ai_detect_btn.blockSignals(True)
        self.ai_detect_btn.setChecked(enabled)
        self.ai_detect_btn.blockSignals(False)

    def sync_from_settings(self, enabled_zones: list, filter_mode: str, draw_mode, ai_detect: bool = False):
        """Sync all states from settings panel"""
        # Sync zone states
        all_zones = ['corner_tl', 'corner_tr', 'corner_bl', 'corner_br',
                     'margin_top', 'margin_bottom', 'margin_left', 'margin_right']
        for zone_id in all_zones:
            self.set_zone_state(zone_id, zone_id in enabled_zones)

        # Sync filter
        self.set_filter_state(filter_mode)

        # Sync draw mode
        self.set_draw_mode_state(draw_mode)

        # Sync AI detect
        self.set_ai_detect_state(ai_detect)
