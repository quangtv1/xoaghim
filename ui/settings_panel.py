"""
Settings Panel - Panel cài đặt ở top (có thể thu gọn)
Sử dụng ZoneSelector với icon trang giấy
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QComboBox, QPushButton,
    QFrame, QGridLayout, QLineEdit,
    QFileDialog, QCheckBox, QRadioButton, QButtonGroup, QMessageBox,
    QStyledItemDelegate, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QPoint, QPropertyAnimation, QEasingCurve, QTimer
from PyQt5.QtGui import QColor, QPixmap, QPainter, QPolygon

from typing import List, Dict, Set
from dataclasses import replace as dataclass_replace
from core.processor import Zone, PRESET_ZONES, TextProtectionOptions, DEFAULT_EDGE_DEPTH_PX
from core.config_manager import get_config_manager
from ui.zone_selector import ZoneSelectorWidget
from ui.text_protection_dialog import TextProtectionDialog
from ui.compact_settings_toolbar import CompactSettingsToolbar


class ComboItemDelegate(QStyledItemDelegate):
    """Custom delegate for larger combobox items"""
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(24)  # Set item height to 24px
        return size


# Thêm preset cho margin_top và margin_bottom với hybrid sizing
EXTENDED_PRESET_ZONES = {
    **PRESET_ZONES,
    'margin_top': Zone(
        id='margin_top',
        name='Viền trên',
        x=0.0, y=0.0,
        width=1.0, height=0.05,  # 100% width + overflow, fallback height
        threshold=5,
        size_mode='hybrid',
        width_px=0,  # Use % for width (along edge)
        height_px=DEFAULT_EDGE_DEPTH_PX  # Fixed depth into page
    ),
    'margin_bottom': Zone(
        id='margin_bottom',
        name='Viền dưới',
        x=0.0, y=0.95,
        width=1.0, height=0.05,  # 100% width + overflow
        threshold=5,
        size_mode='hybrid',
        width_px=0,
        height_px=DEFAULT_EDGE_DEPTH_PX
    ),
}


class SettingsPanel(QWidget):
    """Panel cài đặt ở top"""

    zones_changed = pyqtSignal(list)  # List[Zone]
    settings_changed = pyqtSignal(dict)
    process_clicked = pyqtSignal()
    page_filter_changed = pyqtSignal(str)  # 'all', 'odd', 'even'
    output_settings_changed = pyqtSignal(str, str)  # output_dir, filename_pattern
    text_protection_changed = pyqtSignal(object)  # TextProtectionOptions
    # Draw mode signal: None = off, 'remove' = draw removal zone, 'protect' = draw protection zone
    draw_mode_changed = pyqtSignal(object)  # str or None
    zones_reset = pyqtSignal(str, str)  # scope, reset_type - 'page'/'folder', 'manual'/'auto'/'all'
    # Undo signal for preset zones (corners/edges): zone_id, enabled, zone_data (w_px, h_px) or (length_pct, depth_px)
    zone_preset_toggled = pyqtSignal(str, bool, tuple)
    # Batch render toggle (render 10 pages at once)
    batch_render_changed = pyqtSignal(bool)  # enabled

    def __init__(self, parent=None):
        super().__init__(parent)

        self._zones: Dict[str, Zone] = {}
        self._custom_zones: Dict[str, Zone] = {}
        self._custom_zone_counter = 0
        self._selected_zone_id = None
        self._zone_selection_history: List[str] = []  # Track order of zone selections
        self._collapsed = False
        self._current_draw_mode = None  # Track current draw mode
        # Per-file storage for custom zones with 'none' filter (Tự do mode)
        self._per_file_custom_zones: Dict[str, Dict[str, Zone]] = {}  # {file_path: {zone_id: Zone}}
        self._current_file_path: str = ""
        self._batch_base_dir: str = ""  # Batch folder for persistence

        # Debounce timer for saving zone config (reduce I/O during drag operations)
        self._save_config_timer = QTimer()
        self._save_config_timer.setSingleShot(True)
        self._save_config_timer.timeout.connect(self._save_zone_config)

        self._setup_ui()
        self._setup_compact_toolbar()
        self._init_preset_zones()
        self._load_saved_config()
        self._load_collapsed_state()

    def _load_saved_config(self):
        """Load saved zone configuration from config file"""
        config = get_config_manager().get_zone_config()
        if not config:
            return  # No saved config, use defaults

        # Restore enabled zones
        enabled_zones = config.get('enabled_zones', [])
        for zone_id in self._zones:
            self._zones[zone_id].enabled = (zone_id in enabled_zones)

        # Restore zone sizes (including hybrid sizing fields)
        zone_sizes = config.get('zone_sizes', {})
        for zone_id, size in zone_sizes.items():
            if zone_id in self._zones:
                self._zones[zone_id].width = size.get('width', self._zones[zone_id].width)
                self._zones[zone_id].height = size.get('height', self._zones[zone_id].height)
                # Hybrid sizing fields
                if 'width_px' in size:
                    self._zones[zone_id].width_px = size['width_px']
                if 'height_px' in size:
                    self._zones[zone_id].height_px = size['height_px']
                if 'size_mode' in size:
                    self._zones[zone_id].size_mode = size['size_mode']
                # Page filter for preset zones (odd/even/all)
                if 'page_filter' in size:
                    self._zones[zone_id].page_filter = size['page_filter']

        # Restore custom zones (Tùy biến Chung - non-'none' filter)
        custom_zones_config = config.get('custom_zones', {})
        for zone_id, zone_data in custom_zones_config.items():
            # Find the highest custom zone counter
            if zone_id.startswith('custom_') or zone_id.startswith('protect_'):
                try:
                    num = int(zone_id.split('_')[1])
                    if num > self._custom_zone_counter:
                        self._custom_zone_counter = num
                except (IndexError, ValueError):
                    pass

            # Recreate Zone object
            self._custom_zones[zone_id] = Zone(
                id=zone_data['id'],
                name=zone_data['name'],
                x=zone_data['x'],
                y=zone_data['y'],
                width=zone_data['width'],
                height=zone_data['height'],
                threshold=zone_data.get('threshold', 5),
                enabled=zone_data.get('enabled', True),
                zone_type=zone_data.get('zone_type', 'remove'),
                page_filter=zone_data.get('page_filter', 'all'),
            )
            # Add to selection history
            if zone_id not in enabled_zones:
                enabled_zones.append(zone_id)

        # Restore threshold
        threshold = config.get('threshold', 5)
        self.threshold_slider.setValue(threshold)

        # Restore filter mode
        filter_mode = config.get('filter_mode', 'all')
        filter_map = {
            'all': self.apply_all_rb,
            'odd': self.apply_odd_rb,
            'even': self.apply_even_rb,
            'none': self.apply_free_rb
        }
        if filter_mode in filter_map:
            filter_map[filter_mode].setChecked(True)

        # Restore text protection
        text_protection = config.get('text_protection', True)
        self.text_protection_cb.setChecked(text_protection)

        # Restore preload cache setting
        batch_render = config.get('batch_render', True)  # Default: enabled
        self.batch_render_cb.setChecked(batch_render)

        # Update zone selector UI to match
        self.zone_selector.blockSignals(True)
        self.zone_selector.reset_all()
        for zone_id in enabled_zones:
            if zone_id.startswith('corner_'):
                self.zone_selector.corner_icon.set_zone_selected(zone_id, True)
            elif zone_id.startswith('margin_'):
                self.zone_selector.edge_icon.set_zone_selected(zone_id, True)
        self.zone_selector.blockSignals(False)

        # Update zone combo
        self._update_zone_combo()

        # Update selection history
        self._zone_selection_history = enabled_zones.copy()
        if enabled_zones:
            self._selected_zone_id = enabled_zones[-1]

    def _save_zone_config(self):
        """Save current zone configuration to config file (including hybrid sizing)"""
        enabled_zones = [z.id for z in self._zones.values() if z.enabled]

        zone_sizes = {}
        for zone_id, zone in self._zones.items():
            zone_sizes[zone_id] = {
                'width': zone.width,
                'height': zone.height,
                # Hybrid sizing fields
                'width_px': zone.width_px,
                'height_px': zone.height_px,
                'size_mode': zone.size_mode,
                # Page filter for preset zones (odd/even/all)
                'page_filter': zone.page_filter,
            }

        # Save custom zones with non-'none' filter (Tùy biến Chung)
        # Zones with 'none' filter are per-file and saved separately
        custom_zones_config = {}
        for zone_id, zone in self._custom_zones.items():
            if zone.page_filter != 'none':  # Only save global custom zones
                custom_zones_config[zone_id] = {
                    'id': zone.id,
                    'name': zone.name,
                    'x': zone.x,
                    'y': zone.y,
                    'width': zone.width,
                    'height': zone.height,
                    'threshold': zone.threshold,
                    'enabled': zone.enabled,
                    'zone_type': zone.zone_type,
                    'page_filter': zone.page_filter,
                }

        config = {
            'enabled_zones': enabled_zones,
            'zone_sizes': zone_sizes,
            'custom_zones': custom_zones_config,  # Add custom zones
            'threshold': self.threshold_slider.value(),
            'filter_mode': self._get_current_filter(),
            'text_protection': self.text_protection_cb.isChecked(),
            'batch_render': self.batch_render_cb.isChecked(),
        }

        get_config_manager().save_zone_config(config)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Force white background on this widget and all children
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(255, 255, 255))
        self.setPalette(palette)

        # Create dropdown arrow image (same as bottom bar)
        import tempfile
        import os
        arrow_pixmap = QPixmap(12, 12)
        arrow_pixmap.fill(Qt.transparent)
        painter = QPainter(arrow_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(100, 107, 128))
        points = [QPoint(2, 3), QPoint(10, 3), QPoint(6, 8)]
        painter.drawPolygon(QPolygon(points))
        painter.end()
        self._arrow_file = os.path.join(tempfile.gettempdir(), "settings_dropdown_arrow.png")
        arrow_pixmap.save(self._arrow_file)
        arrow_url = self._arrow_file.replace("\\", "/")

        # Global stylesheet for consistent styling - ALL white backgrounds
        self.setStyleSheet(f"""
            SettingsPanel {{
                background-color: #FFFFFF;
                border-bottom: 1px solid #D1D5DB;
            }}
            SettingsPanel QWidget {{
                background-color: #FFFFFF;
            }}
            QFrame {{
                background-color: #FFFFFF;
                border: none;
            }}
            QLabel {{
                background-color: #FFFFFF;
                font-size: 12px;
                color: #374151;
            }}
            QCheckBox {{
                background-color: #FFFFFF;
                font-size: 12px;
                color: #374151;
            }}
            QComboBox {{
                font-size: 12px;
                background-color: white;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px 6px;
                padding-right: 24px;
                color: #374151;
            }}
            QComboBox QAbstractItemView {{
                background-color: white;
                color: #374151;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                background-color: white;
                color: #374151;
                padding: 10px 8px 10px 18px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: #93C5FD;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: #93C5FD;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px;
                border: none;
                background: transparent;
            }}
            QComboBox::down-arrow {{
                image: url({arrow_url});
                width: 10px;
                height: 10px;
            }}
            QLineEdit {{
                font-size: 12px;
                background-color: #FFFFFF;
            }}
            QPushButton {{
                font-size: 12px;
                background-color: #FFFFFF;
            }}
            QSlider {{
                background-color: #FFFFFF;
            }}
            QSlider::groove:horizontal {{
                background: #E5E7EB;
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: #0043a5;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
        """)

        # === 3 COLUMNS LAYOUT ===
        main_row = QHBoxLayout()
        main_row.setSpacing(24)
        main_row.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        # ========== Column 1: ZONE SELECTOR ==========
        zone_widget = QWidget()
        zone_widget.setStyleSheet("background-color: #FFFFFF;")
        zone_container = QVBoxLayout(zone_widget)
        zone_container.setContentsMargins(0, 0, 0, 0)
        zone_container.setSpacing(8)

        # Row with zone selector icons and apply checkboxes
        zone_row = QHBoxLayout()
        zone_row.setSpacing(12)
        zone_row.setAlignment(Qt.AlignTop)
        
        # Zone icons column with labels
        zone_icons_widget = QWidget()
        zone_icons_widget.setStyleSheet("background-color: #FFFFFF;")
        zone_icons_col = QVBoxLayout(zone_icons_widget)
        zone_icons_col.setContentsMargins(0, 0, 0, 0)
        zone_icons_col.setSpacing(4)
        zone_icons_col.setAlignment(Qt.AlignTop)
        
        # Zone selector
        self.zone_selector = ZoneSelectorWidget()
        self.zone_selector.zones_changed.connect(self._on_zone_selector_changed)
        self.zone_selector.zone_clicked.connect(self._on_zone_clicked)
        self.zone_selector.draw_mode_changed.connect(self._on_draw_mode_changed)
        self.zone_selector.setStyleSheet("background-color: #FFFFFF; border: none;")
        zone_icons_col.addWidget(self.zone_selector)
        
        # Labels row under icons
        labels_widget = QWidget()
        labels_widget.setStyleSheet("background-color: #FFFFFF;")
        labels_row = QHBoxLayout(labels_widget)
        labels_row.setContentsMargins(0, 0, 0, 0)
        labels_row.setSpacing(4)

        for label_text in ["Góc", "Cạnh", "Tùy biến"]:
            lbl = QLabel(label_text)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedWidth(80)
            lbl.setStyleSheet("color: #6B7280; font-size: 12px; background-color: #FFFFFF;")
            labels_row.addWidget(lbl)

        zone_icons_col.addWidget(labels_widget)
        zone_row.addWidget(zone_icons_widget)
        
        # Apply radio buttons (choice - only one can be selected)
        apply_widget = QWidget()
        apply_widget.setStyleSheet("background-color: #FFFFFF;")
        apply_layout = QVBoxLayout(apply_widget)
        apply_layout.setContentsMargins(0, 0, 0, 0)
        apply_layout.setSpacing(4)
        apply_layout.setAlignment(Qt.AlignTop)

        # Radio button group for exclusive selection
        self.apply_group = QButtonGroup(self)

        self.apply_all_rb = QRadioButton("Tất cả")
        self.apply_all_rb.setChecked(True)
        self.apply_all_rb.setToolTip("Vùng vẽ mới được thêm vào tất cả các trang")
        self.apply_all_rb.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        self.apply_group.addButton(self.apply_all_rb, 0)
        apply_layout.addWidget(self.apply_all_rb)

        self.apply_odd_rb = QRadioButton("Trang lẻ")
        self.apply_odd_rb.setToolTip("Vùng vẽ mới chỉ thêm vào các trang 1, 3, 5...")
        self.apply_odd_rb.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        self.apply_group.addButton(self.apply_odd_rb, 1)
        apply_layout.addWidget(self.apply_odd_rb)

        self.apply_even_rb = QRadioButton("Trang chẵn")
        self.apply_even_rb.setToolTip("Vùng vẽ mới chỉ thêm vào các trang 2, 4, 6...")
        self.apply_even_rb.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        self.apply_group.addButton(self.apply_even_rb, 2)
        apply_layout.addWidget(self.apply_even_rb)

        self.apply_free_rb = QRadioButton("Từng trang")
        self.apply_free_rb.setToolTip("Vùng vẽ mới chỉ thêm vào trang đang xem")
        self.apply_free_rb.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        self.apply_group.addButton(self.apply_free_rb, 3)
        apply_layout.addWidget(self.apply_free_rb)

        # Connect button group signal
        self.apply_group.buttonClicked.connect(self._on_apply_filter_changed)

        apply_layout.addStretch()

        # Reset button (aligned with Góc, Cạnh, Tùy biến labels)
        self.reset_zones_btn = QPushButton("Xóa vùng chọn")
        self.reset_zones_btn.setToolTip("Xóa tất cả vùng đã chọn")
        self.reset_zones_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #0047AB;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 12px;
                font-weight: normal;
            }
            QPushButton:hover {
                background-color: #FEE2E2;
                color: #DC2626;
                border-color: #FECACA;
            }
            QPushButton:pressed {
                background-color: #FECACA;
                color: #B91C1C;
            }
        """)
        self.reset_zones_btn.clicked.connect(self._on_reset_zones_clicked)
        apply_layout.addWidget(self.reset_zones_btn)

        zone_row.addWidget(apply_widget)

        # ========== Thông số (side by side in zone_row) ==========
        params_widget = QWidget()
        params_widget.setStyleSheet("background-color: #FFFFFF;")
        params_container = QVBoxLayout(params_widget)
        params_container.setAlignment(Qt.AlignTop)
        params_container.setContentsMargins(0, 0, 0, 0)
        params_container.setSpacing(6)

        params_layout = QGridLayout()
        params_layout.setSpacing(6)
        params_layout.setColumnStretch(1, 1)  # Sliders expand to right edge

        # Chọn zone để chỉnh (editable for custom popup styling on macOS)
        lbl_vung = QLabel("Vùng:")
        lbl_vung.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        params_layout.addWidget(lbl_vung, 0, 0)
        self.zone_combo = QComboBox()
        self.zone_combo.setMinimumWidth(180)
        self.zone_combo.setEditable(True)
        self.zone_combo.lineEdit().setReadOnly(True)  # Prevent typing
        self.zone_combo.lineEdit().setTextMargins(0, 0, 0, 0)
        # Use custom delegate for larger item height
        self.zone_combo.setItemDelegate(ComboItemDelegate(self.zone_combo))
        # Apply view stylesheet directly for dropdown items
        self.zone_combo.view().setStyleSheet("""
            QListView::item {
                padding: 8px 8px 8px 8px;
            }
            QListView::item:hover {
                background-color: #93C5FD;
            }
            QListView::item:selected {
                background-color: #93C5FD;
            }
        """)
        self.zone_combo.currentTextChanged.connect(self._on_zone_selected)
        params_layout.addWidget(self.zone_combo, 0, 1, 1, 2)

        # Simple flat slider style
        slider_style = """
            QSlider::groove:horizontal {
                border: 1px solid #D1D5DB;
                height: 4px;
                background: #E5E7EB;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #3B82F6;
                border: none;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #2563EB;
            }
            QSlider::sub-page:horizontal {
                background: #93C5FD;
                border-radius: 2px;
            }
        """

        # Kích thước
        lbl_rong = QLabel("Rộng:")
        lbl_rong.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        params_layout.addWidget(lbl_rong, 1, 0)
        self.width_slider = QSlider(Qt.Horizontal)
        self.width_slider.setRange(1, 50)
        self.width_slider.setValue(12)
        self.width_slider.setStyleSheet(slider_style)
        self.width_slider.valueChanged.connect(self._on_zone_size_changed)
        params_layout.addWidget(self.width_slider, 1, 1)
        self.width_label = QLabel("12%")
        self.width_label.setFixedWidth(32)
        self.width_label.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        params_layout.addWidget(self.width_label, 1, 2)

        lbl_cao = QLabel("Cao:")
        lbl_cao.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        params_layout.addWidget(lbl_cao, 2, 0)
        self.height_slider = QSlider(Qt.Horizontal)
        self.height_slider.setRange(1, 50)
        self.height_slider.setValue(12)
        self.height_slider.setStyleSheet(slider_style)
        self.height_slider.valueChanged.connect(self._on_zone_size_changed)
        params_layout.addWidget(self.height_slider, 2, 1)
        self.height_label = QLabel("12%")
        self.height_label.setFixedWidth(32)
        self.height_label.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        params_layout.addWidget(self.height_label, 2, 2)

        # Ngưỡng
        lbl_nhay = QLabel("Ngưỡng:")
        lbl_nhay.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        params_layout.addWidget(lbl_nhay, 3, 0)
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(1, 15)
        self.threshold_slider.setValue(5)
        self.threshold_slider.setStyleSheet(slider_style)
        self.threshold_slider.valueChanged.connect(self._on_settings_changed)
        params_layout.addWidget(self.threshold_slider, 3, 1)
        self.threshold_label = QLabel("5")
        self.threshold_label.setFixedWidth(32)
        self.threshold_label.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        params_layout.addWidget(self.threshold_label, 3, 2)

        params_container.addLayout(params_layout)

        # Text protection section
        protection_row = QHBoxLayout()
        protection_row.setSpacing(8)

        self.text_protection_cb = QCheckBox("Nhận diện vùng bảo vệ (tự động)")
        self.text_protection_cb.setChecked(True)
        self.text_protection_cb.setToolTip(
            "Sử dụng AI để phát hiện và bảo vệ vùng văn bản,\n"
            "bảng biểu khỏi bị xóa nhầm."
        )
        self.text_protection_cb.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        self.text_protection_cb.stateChanged.connect(self._on_text_protection_checkbox_changed)
        protection_row.addWidget(self.text_protection_cb)

        self.text_protection_settings_btn = QPushButton("⚙")
        self.text_protection_settings_btn.setFixedSize(28, 28)
        self.text_protection_settings_btn.setToolTip("Cài đặt bảo vệ văn bản")
        self.text_protection_settings_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                background-color: #F3F4F6;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        self.text_protection_settings_btn.clicked.connect(self._open_text_protection_dialog)
        protection_row.addWidget(self.text_protection_settings_btn)

        # Batch render checkbox (same row)
        protection_row.addSpacing(16)
        self.batch_render_cb = QCheckBox("Render 10 trang một")
        self.batch_render_cb.setChecked(True)  # Default: enabled
        self.batch_render_cb.setToolTip(
            "Chỉ giữ 10 trang trong bộ nhớ Preview (trang hiện tại ± 5).\n"
            "Tiết kiệm RAM cho file lớn. Scroll ra ngoài cửa sổ\n"
            "sẽ tự động load trang mới và giải phóng trang cũ."
        )
        self.batch_render_cb.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        self.batch_render_cb.stateChanged.connect(self._on_batch_render_changed)
        protection_row.addWidget(self.batch_render_cb)

        protection_row.addStretch()
        params_container.addLayout(protection_row)

        # Store current text protection options
        self._text_protection_options = TextProtectionOptions()

        params_container.addStretch()
        zone_row.addWidget(params_widget, stretch=1)  # Expand to right edge

        zone_container.addLayout(zone_row)
        zone_container.addStretch()
        main_row.addWidget(zone_widget, stretch=2)  # 2/3 width

        # Separator between Vùng xử lý and Đầu ra
        sep_col = QFrame()
        sep_col.setFrameShape(QFrame.VLine)
        sep_col.setStyleSheet("background-color: #E5E7EB;")
        sep_col.setFixedWidth(1)
        main_row.addWidget(sep_col)

        # ========== Column 2: ĐẦU RA ==========
        output_widget = QWidget()
        output_widget.setStyleSheet("background-color: #FFFFFF;")
        output_container = QVBoxLayout(output_widget)
        output_container.setContentsMargins(0, 0, 0, 0)
        output_container.setSpacing(8)

        output_layout = QVBoxLayout()
        output_layout.setSpacing(6)

        # Row 0: DPI, JPEG, Nén đen trắng on same line
        quality_row = QHBoxLayout()
        quality_row.setSpacing(6)

        # Dropdown item style for all comboboxes
        dropdown_item_style = """
            QListView::item {
                padding: 8px 8px 8px 8px;
            }
            QListView::item:hover {
                background-color: #93C5FD;
            }
            QListView::item:selected {
                background-color: #93C5FD;
            }
        """

        lbl_dpi = QLabel("DPI:")
        lbl_dpi.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        lbl_dpi.setFixedWidth(55)
        quality_row.addWidget(lbl_dpi)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["300 dpi", "250 dpi", "200 dpi", "100 dpi", "72 dpi"])
        self.quality_combo.setCurrentIndex(0)  # Default 300 dpi
        self.quality_combo.setMinimumWidth(100)
        self.quality_combo.setEditable(True)
        self.quality_combo.lineEdit().setReadOnly(True)  # Prevent typing
        self.quality_combo.lineEdit().setTextMargins(0, 0, 0, 0)
        self.quality_combo.setItemDelegate(ComboItemDelegate(self.quality_combo))
        self.quality_combo.view().setStyleSheet(dropdown_item_style)
        quality_row.addWidget(self.quality_combo)

        quality_row.addSpacing(12)

        lbl_jpeg = QLabel("Nén:")
        lbl_jpeg.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        quality_row.addWidget(lbl_jpeg)
        self.jpeg_quality_combo = QComboBox()
        self.jpeg_quality_combo.addItems(["100%", "90%", "80%", "70%"])
        self.jpeg_quality_combo.setCurrentIndex(1)  # Default: 90%
        self.jpeg_quality_combo.setMinimumWidth(100)
        self.jpeg_quality_combo.setEditable(True)
        self.jpeg_quality_combo.lineEdit().setReadOnly(True)  # Prevent typing
        self.jpeg_quality_combo.lineEdit().setTextMargins(0, 0, 0, 0)
        self.jpeg_quality_combo.setItemDelegate(ComboItemDelegate(self.jpeg_quality_combo))
        self.jpeg_quality_combo.view().setStyleSheet(dropdown_item_style)
        quality_row.addWidget(self.jpeg_quality_combo)

        quality_row.addSpacing(12)

        # Optimize size checkbox (same row)
        self.optimize_size_cb = QCheckBox("Nén đen trắng")
        self.optimize_size_cb.setChecked(False)  # Default: disabled
        self.optimize_size_cb.setToolTip(
            "Chuyển ảnh thành đen trắng 1-bit với CCITT Group 4.\n"
            "Dung lượng giảm ~90% nhưng mất màu xám/gradient."
        )
        self.optimize_size_cb.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        quality_row.addWidget(self.optimize_size_cb)
        quality_row.addStretch()

        output_layout.addLayout(quality_row)

        # Row 2: Thư mục
        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)

        lbl_tm = QLabel("Thư mục:")
        lbl_tm.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        lbl_tm.setFixedWidth(55)
        folder_row.addWidget(lbl_tm)
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("Chọn thư mục lưu kết quả...")
        folder_row.addWidget(self.output_path, 1)  # stretch=1 to expand

        self.browse_btn = QPushButton("📁")
        self.browse_btn.setFixedSize(32, 26)
        self.browse_btn.setToolTip("Chọn thư mục đầu ra")
        self.browse_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 0px;
                background-color: #FFFFFF;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
            }
        """)
        self.browse_btn.clicked.connect(self._on_browse_output)
        folder_row.addWidget(self.browse_btn)

        output_layout.addLayout(folder_row)

        # Row 3: Tên file
        file_row = QHBoxLayout()
        file_row.setSpacing(6)

        lbl_tf = QLabel("File đích:")
        lbl_tf.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        lbl_tf.setFixedWidth(55)
        file_row.addWidget(lbl_tf)
        self.filename_pattern = QLineEdit("{gốc}_clean.pdf")
        file_row.addWidget(self.filename_pattern, 1)  # stretch=1 to expand

        output_layout.addLayout(file_row)

        # Connect output settings changes
        self.output_path.textChanged.connect(self._on_output_settings_changed)
        self.filename_pattern.textChanged.connect(self._on_output_settings_changed)

        output_container.addLayout(output_layout)
        output_container.addStretch()
        main_row.addWidget(output_widget, stretch=1)  # 1/3 width

        # Store reference to main content for collapse/expand
        self.main_content = QWidget()
        main_content_layout = QVBoxLayout(self.main_content)
        main_content_layout.setContentsMargins(12, 8, 12, 12)
        main_content_layout.setSpacing(0)

        # Move main_row into main_content widget
        temp_widget = QWidget()
        temp_widget.setLayout(main_row)
        main_content_layout.addWidget(temp_widget)

        layout.addWidget(self.main_content)
    
    def _init_preset_zones(self):
        """Khởi tạo preset zones với hybrid sizing support"""
        for zone_id, zone in EXTENDED_PRESET_ZONES.items():
            self._zones[zone_id] = Zone(
                id=zone.id,
                name=zone.name,
                x=zone.x,
                y=zone.y,
                width=zone.width,
                height=zone.height,
                threshold=zone.threshold,
                enabled=False,
                # Hybrid sizing fields
                size_mode=zone.size_mode,
                width_px=zone.width_px,
                height_px=zone.height_px
            )
        
        self._update_zone_combo()

    def _setup_compact_toolbar(self):
        """Create and connect compact toolbar"""
        self.compact_toolbar = CompactSettingsToolbar()
        self.compact_toolbar.setVisible(False)

        # Insert at top of main layout
        self.layout().insertWidget(0, self.compact_toolbar)

        # Connect signals from compact toolbar
        self.compact_toolbar.zone_toggled.connect(self._on_compact_zone_toggled)
        self.compact_toolbar.filter_changed.connect(self._on_compact_filter_changed)
        self.compact_toolbar.draw_mode_changed.connect(self._on_compact_draw_mode_changed)
        self.compact_toolbar.clear_zones.connect(self._on_reset_zones_clicked)
        self.compact_toolbar.ai_detect_toggled.connect(self._on_compact_ai_detect_toggled)

    def _on_compact_zone_toggled(self, zone_id: str, enabled: bool):
        """Handle zone toggle from compact toolbar"""
        if zone_id in self._zones:
            self._zones[zone_id].enabled = enabled

            # Sync with zone selector widget
            self.zone_selector.blockSignals(True)
            if zone_id.startswith('corner_'):
                self.zone_selector.corner_icon.set_zone_selected(zone_id, enabled)
            elif zone_id.startswith('margin_'):
                self.zone_selector.edge_icon.set_zone_selected(zone_id, enabled)
            self.zone_selector.blockSignals(False)

            self._update_zone_combo()
            self._emit_zones()
            self._save_zone_config()

            # Emit undo signal for preset zones
            zone = self._zones.get(zone_id)
            if zone:
                if zone_id.startswith('corner_'):
                    zone_data = (zone.width_px, zone.height_px)
                else:
                    zone_data = (zone.width, zone.height_px)
                self.zone_preset_toggled.emit(zone_id, enabled, zone_data)

    def _on_compact_filter_changed(self, filter_mode: str):
        """Handle filter change from compact toolbar"""
        filter_map = {'all': self.apply_all_rb, 'odd': self.apply_odd_rb,
                      'even': self.apply_even_rb, 'none': self.apply_free_rb}
        if filter_mode in filter_map:
            filter_map[filter_mode].setChecked(True)
            self._on_apply_filter_changed(filter_map[filter_mode])

    def _on_compact_draw_mode_changed(self, mode):
        """Handle draw mode change from compact toolbar

        When entering draw mode (Tùy biến), auto-switch to "Tự do" filter.
        """
        self._current_draw_mode = mode
        # Sync with zone selector draw buttons
        self.zone_selector.set_draw_mode(mode)
        if mode is not None:
            # Entering draw mode → auto-switch to "Tự do" filter
            self.apply_free_rb.setChecked(True)
        self.draw_mode_changed.emit(mode)

    def _on_compact_ai_detect_toggled(self, enabled: bool):
        """Handle AI detect toggle from compact toolbar"""
        self.text_protection_cb.setChecked(enabled)

    def _toggle_collapse(self):
        """Toggle between collapsed and expanded state"""
        self._collapsed = not self._collapsed
        self._animate_collapse()
        self._save_collapsed_state()

    def _animate_collapse(self):
        """Animate height transition - compact toolbar is now in main layout"""
        if self._collapsed:
            # Sync state to compact toolbar
            self._sync_to_compact_toolbar()
            # Hide expanded content (compact toolbar is in main layout)
            self.main_content.setVisible(False)
            # Collapse to zero height
            self.setMaximumHeight(0)
            self.setVisible(False)
        else:
            # Show expanded content
            self.main_content.setVisible(True)
            self.setVisible(True)
            # No margin change - header_widget has its own margins
            self.setMaximumHeight(16777215)  # Max height (no limit)

    def _sync_to_compact_toolbar(self):
        """Sync current state to compact toolbar"""
        enabled_zones = [z.id for z in self._zones.values() if z.enabled]
        filter_mode = self._get_current_filter()
        ai_detect = self.text_protection_cb.isChecked()
        self.compact_toolbar.sync_from_settings(
            enabled_zones, filter_mode, self._current_draw_mode, ai_detect
        )

    def _load_collapsed_state(self):
        """Load collapsed state from config - compact toolbar is now in main layout"""
        ui_config = get_config_manager().get_ui_config()
        self._collapsed = ui_config.get('toolbar_collapsed', False)
        if self._collapsed:
            self._sync_to_compact_toolbar()
            self.main_content.setVisible(False)
            self.setMaximumHeight(0)
            self.setVisible(False)

    def _save_collapsed_state(self):
        """Save collapsed state to config"""
        ui_config = get_config_manager().get_ui_config()
        ui_config['toolbar_collapsed'] = self._collapsed
        get_config_manager().save_ui_config(ui_config)

    def _update_zone_combo(self):
        """Cập nhật combo box zones"""
        self.zone_combo.blockSignals(True)
        self.zone_combo.clear()
        
        # Add enabled preset zones
        for zone_id, zone in self._zones.items():
            if zone.enabled:
                self.zone_combo.addItem(zone.name, zone_id)
        
        # Add custom zones
        for zone_id, zone in self._custom_zones.items():
            if zone.enabled:
                self.zone_combo.addItem(zone.name, zone_id)
        
        self.zone_combo.blockSignals(False)
        
        # Select first if available
        if self.zone_combo.count() > 0:
            self._on_zone_selected(self.zone_combo.currentText())
    
    def _on_zone_selector_changed(self, selected_zones: set):
        """Khi chọn zones từ icon"""
        # Update zone states
        for zone_id in self._zones:
            self._zones[zone_id].enabled = (zone_id in selected_zones)

        self._update_zone_combo()
        self._emit_zones()
        self._save_zone_config()  # Save config when zones change
    
    def _get_current_filter(self) -> str:
        """Lấy filter hiện tại: 'all', 'odd', 'even', 'none'"""
        filter_map = {0: 'all', 1: 'odd', 2: 'even', 3: 'none'}
        return filter_map.get(self.apply_group.checkedId(), 'all')

    def _on_zone_clicked(self, zone_id: str, enabled: bool):
        """Khi click vào zone - cập nhật combo box và lưu lịch sử"""
        if enabled:
            # Góc/Cạnh chỉ dùng được với filter Tất cả/Lẻ/Chẵn (không dùng với "Không")
            # Nếu filter đang là "Không" (ID=3), tự động chuyển sang "Tất cả" (ID=0)
            if zone_id.startswith('corner_') or zone_id.startswith('margin_'):
                if self.apply_group.checkedId() == 3:  # "Không" filter
                    self.apply_all_rb.setChecked(True)
                    self._on_apply_filter_changed(self.apply_all_rb)

            # Reset zone size to default when re-selecting
            if zone_id in self._zones and zone_id in EXTENDED_PRESET_ZONES:
                default_zone = EXTENDED_PRESET_ZONES[zone_id]
                self._zones[zone_id].width = default_zone.width
                self._zones[zone_id].height = default_zone.height
                self._zones[zone_id].x = default_zone.x
                self._zones[zone_id].y = default_zone.y
                # Reset pixel sizes for corners/edges
                self._zones[zone_id].width_px = default_zone.width_px
                self._zones[zone_id].height_px = default_zone.height_px
                # Emit zones to update preview with reset values
                # (zones_changed was already emitted with old values)
                self._emit_zones()

            # Lưu filter hiện tại vào zone
            if zone_id in self._zones:
                self._zones[zone_id].page_filter = self._get_current_filter()

            # Zone được chọn -> thêm vào lịch sử và hiển thị zone này
            # Xóa zone này khỏi lịch sử nếu đã có (để đưa lên đầu)
            if zone_id in self._zone_selection_history:
                self._zone_selection_history.remove(zone_id)
            self._zone_selection_history.append(zone_id)
            self._select_zone_in_combo(zone_id)
        else:
            # Zone bị bỏ chọn -> xóa khỏi lịch sử và hiển thị zone trước đó
            if zone_id in self._zone_selection_history:
                self._zone_selection_history.remove(zone_id)
            
            # Tìm zone gần nhất trong lịch sử mà vẫn đang được chọn
            selected_zones = self.zone_selector.get_all_selected_zones()
            for z_id in reversed(self._zone_selection_history):
                if z_id in selected_zones:
                    self._select_zone_in_combo(z_id)
                    return
            
            # Nếu không có trong lịch sử, lấy zone đầu tiên đang chọn
            if selected_zones:
                first_zone = next(iter(selected_zones))
                self._select_zone_in_combo(first_zone)

        # Emit undo signal for preset zones (corners/edges)
        if zone_id.startswith('corner_') or zone_id.startswith('margin_'):
            zone = self._zones.get(zone_id)
            if zone:
                if zone_id.startswith('corner_'):
                    # Corners: (width_px, height_px)
                    zone_data = (zone.width_px, zone.height_px)
                else:
                    # Edges: (length_pct, depth_px)
                    zone_data = (zone.width, zone.height_px)
                self.zone_preset_toggled.emit(zone_id, enabled, zone_data)

    def _select_zone_in_combo(self, zone_id: str):
        """Chọn zone trong combo box theo zone_id"""
        for i in range(self.zone_combo.count()):
            if self.zone_combo.itemData(i) == zone_id:
                self.zone_combo.setCurrentIndex(i)
                break
    
    def _on_zone_selected(self, text):
        """Khi chọn zone trong combo"""
        zone_id = self.zone_combo.currentData()
        if not zone_id:
            return
        
        self._selected_zone_id = zone_id
        
        # Get zone
        zone = self._zones.get(zone_id) or self._custom_zones.get(zone_id)
        if not zone:
            return
        
        # Update sliders
        self.width_slider.blockSignals(True)
        self.height_slider.blockSignals(True)
        
        self.width_slider.setValue(int(zone.width * 100))
        self.height_slider.setValue(int(zone.height * 100))
        
        self.width_slider.blockSignals(False)
        self.height_slider.blockSignals(False)
        
        self._update_size_labels()
    
    def _on_zone_size_changed(self):
        """Khi thay đổi kích thước zone"""
        if not self._selected_zone_id:
            return

        zone = self._zones.get(self._selected_zone_id) or self._custom_zones.get(self._selected_zone_id)
        if not zone:
            return

        zone.width = self.width_slider.value() / 100.0
        zone.height = self.height_slider.value() / 100.0

        self._update_size_labels()
        self._emit_zones()
        self._save_zone_config()  # Save config when size changes
    
    def _update_size_labels(self):
        self.width_label.setText(f"{self.width_slider.value()}%")
        self.height_label.setText(f"{self.height_slider.value()}%")
    
    def _on_draw_mode_changed(self, mode):
        """Forward draw mode signal to MainWindow (mode: 'remove', 'protect', or None)

        When entering draw mode (Tùy biến), auto-switch to "Tự do" filter.
        """
        self._current_draw_mode = mode
        if mode is not None:
            # Entering draw mode → auto-switch to "Tự do" filter
            self.apply_free_rb.setChecked(True)
        self.draw_mode_changed.emit(mode)

    def add_custom_zone_from_rect(self, x: float, y: float, width: float, height: float,
                                   zone_type: str = 'remove', page_idx: int = -1):
        """Add custom zone from drawn rectangle (coordinates as % 0.0-1.0)

        Args:
            x, y, width, height: Zone coordinates as percentages (0.0-1.0)
            zone_type: 'remove' for removal zone, 'protect' for protection zone
            page_idx: Target page index (0-based). -1 means use page_filter
        """
        self._custom_zone_counter += 1

        if zone_type == 'protect':
            zone_id = f'protect_{self._custom_zone_counter}'
            zone_name = f'Bảo vệ {self._custom_zone_counter}'
        else:
            zone_id = f'custom_{self._custom_zone_counter}'
            zone_name = f'Xóa ghim {self._custom_zone_counter}'

        current_filter = self._get_current_filter()

        self._custom_zones[zone_id] = Zone(
            id=zone_id,
            name=zone_name,
            x=x,
            y=y,
            width=width,
            height=height,
            threshold=self.threshold_slider.value(),
            enabled=True,
            zone_type=zone_type,  # 'remove' or 'protect'
            page_filter=current_filter,
            target_page=page_idx if current_filter == 'none' else -1  # Use target_page in 'none' mode
        )

        # Add to selection history
        self._zone_selection_history.append(zone_id)

        self._update_zone_combo()
        self._emit_zones()

        # Select the new zone
        idx = self.zone_combo.findData(zone_id)
        if idx >= 0:
            self.zone_combo.setCurrentIndex(idx)
        # Keep draw mode active - user can continue drawing more zones

        # Save immediately for crash recovery
        if current_filter == 'none':
            # Tự do mode: save per-file zones
            self.save_per_file_custom_zones()
        else:
            # Global custom zone: save to config
            self._save_zone_config()

    def set_draw_mode(self, mode):
        """Set draw mode state (mode: 'remove', 'protect', or None)"""
        self.zone_selector.set_draw_mode(mode)
    
    def delete_zone(self, zone_id: str):
        """Xóa vùng (bất kỳ loại nào: góc, cạnh, tùy biến)"""
        # Get base zone id (without page index)
        base_id = zone_id.rsplit('_', 1)[0] if zone_id.count('_') > 1 else zone_id

        # Remove from selection history first
        if base_id in self._zone_selection_history:
            self._zone_selection_history.remove(base_id)

        if base_id.startswith('custom') or base_id.startswith('protect'):
            # Custom/Protect zone - remove from custom_zones dict
            zone = self._custom_zones.get(base_id)
            zone_filter = zone.page_filter if zone else 'all'
            if base_id in self._custom_zones:
                del self._custom_zones[base_id]
            # Update combo and emit for custom zones
            self._update_zone_combo()
            if self._zone_selection_history:
                self._select_zone_in_combo(self._zone_selection_history[-1])
            self._emit_zones()
            # Save immediately for crash recovery
            if zone_filter == 'none':
                self.save_per_file_custom_zones()
            else:
                self._save_zone_config()
        elif base_id.startswith('corner_') or base_id.startswith('margin_'):
            # Corner/Margin zone - uncheck in zone selector
            # This will trigger zones_changed signal which updates everything
            self.zone_selector.set_zone_selected(base_id, False)
        else:
            # Other preset zones
            if base_id in self._zones:
                del self._zones[base_id]
            self._update_zone_combo()
            if self._zone_selection_history:
                self._select_zone_in_combo(self._zone_selection_history[-1])
            self._emit_zones()
    
    def delete_custom_zone(self, zone_id: str):
        """Backward compatibility - calls delete_zone"""
        self.delete_zone(zone_id)

    def restore_custom_zone(self, zone_id: str, x: float, y: float, width: float, height: float, zone_type: str = 'remove'):
        """Restore a custom zone (for undo delete operation)

        Args:
            zone_id: Zone ID (e.g., 'custom_1', 'protect_2')
            x, y, width, height: Zone coordinates as percentages (0.0-1.0)
            zone_type: 'remove' or 'protect'
        """
        # Determine zone name from id
        if zone_type == 'protect' or zone_id.startswith('protect_'):
            zone_name = f'Bảo vệ {zone_id.split("_")[-1]}'
        else:
            zone_name = f'Xóa ghim {zone_id.split("_")[-1]}'

        self._custom_zones[zone_id] = Zone(
            id=zone_id,
            name=zone_name,
            x=x,
            y=y,
            width=width,
            height=height,
            threshold=self.threshold_slider.value(),
            enabled=True,
            zone_type=zone_type,
            page_filter=self._get_current_filter()
        )

        # Add to selection history if not present
        if zone_id not in self._zone_selection_history:
            self._zone_selection_history.append(zone_id)

        self._update_zone_combo()
        self._emit_zones()

    def toggle_preset_zone(self, zone_id: str, enabled: bool, emit_signal: bool = False):
        """Toggle a preset zone (corner/edge) enabled state.

        Used by undo to restore zone state without triggering another undo record.

        Args:
            zone_id: Zone ID (e.g., 'corner_tl', 'margin_top')
            enabled: Whether to enable or disable the zone
            emit_signal: Whether to emit zone_preset_toggled signal (default False for undo)
        """
        if zone_id not in self._zones:
            return

        self._zones[zone_id].enabled = enabled

        # Sync with zone selector widget
        self.zone_selector.blockSignals(True)
        if zone_id.startswith('corner_'):
            self.zone_selector.corner_icon.set_zone_selected(zone_id, enabled)
        elif zone_id.startswith('margin_'):
            self.zone_selector.edge_icon.set_zone_selected(zone_id, enabled)
        self.zone_selector.blockSignals(False)

        # Sync with compact toolbar if visible
        if hasattr(self, 'compact_toolbar') and self.compact_toolbar.isVisible():
            self.compact_toolbar.set_zone_state(zone_id, enabled)

        # Update selection history
        if enabled:
            if zone_id in self._zone_selection_history:
                self._zone_selection_history.remove(zone_id)
            self._zone_selection_history.append(zone_id)
        else:
            if zone_id in self._zone_selection_history:
                self._zone_selection_history.remove(zone_id)

        self._update_zone_combo()
        self._emit_zones()
        self._save_zone_config()

        # Optionally emit signal for redo scenario
        if emit_signal:
            zone = self._zones.get(zone_id)
            if zone:
                if zone_id.startswith('corner_'):
                    zone_data = (zone.width_px, zone.height_px)
                else:
                    zone_data = (zone.width, zone.height_px)
                self.zone_preset_toggled.emit(zone_id, enabled, zone_data)

    def clear_custom_zones_with_free_filter(self, emit_signal: bool = False):
        """Clear custom zones that have page_filter='none' (Tự do mode).

        Called when switching files in batch mode. Zones are saved to per-file
        storage before clearing, so they can be restored when switching back.

        Args:
            emit_signal: If True, emit zones_changed signal. Default False since
                        caller will typically call set_zones() after loading new file.
        """
        zones_to_remove = [
            zone_id for zone_id, zone in self._custom_zones.items()
            if zone.page_filter == 'none'
        ]

        if not zones_to_remove:
            return False  # No zones removed

        for zone_id in zones_to_remove:
            del self._custom_zones[zone_id]
            if zone_id in self._zone_selection_history:
                self._zone_selection_history.remove(zone_id)

        # Update UI
        self._update_zone_combo()
        if self._zone_selection_history:
            self._select_zone_in_combo(self._zone_selection_history[-1])

        if emit_signal:
            self._emit_zones()

        return True  # Zones were removed

    def set_batch_base_dir(self, batch_base_dir: str):
        """Set batch base directory for persistence."""
        self._batch_base_dir = batch_base_dir

    def save_per_file_custom_zones(self, file_path: str = None, persist: bool = True):
        """Save custom zones with 'none' filter for a specific file.

        Args:
            file_path: File path to save zones for. Uses _current_file_path if None.
            persist: If True, also persist to disk for crash recovery.
        """
        path = file_path or self._current_file_path
        if not path:
            return

        # Get zones with 'none' filter - deep copy each Zone to avoid reference issues
        zones_to_save = {
            zone_id: dataclass_replace(zone)
            for zone_id, zone in self._custom_zones.items()
            if zone.page_filter == 'none'
        }

        if zones_to_save:
            self._per_file_custom_zones[path] = zones_to_save
        elif path in self._per_file_custom_zones:
            # Remove entry if no Tự do zones remain (important for deletion)
            del self._per_file_custom_zones[path]

        # Persist to disk for crash recovery
        if persist and self._batch_base_dir:
            self._persist_custom_zones_to_disk()

    def load_per_file_custom_zones(self, file_path: str) -> bool:
        """Load custom zones with 'none' filter for a specific file.

        Args:
            file_path: File path to load zones for.

        Returns:
            True if zones were loaded.
        """
        if file_path not in self._per_file_custom_zones:
            return False

        saved_zones = self._per_file_custom_zones[file_path]

        # Restore zones - deep copy to avoid reference issues
        for zone_id, zone in saved_zones.items():
            self._custom_zones[zone_id] = dataclass_replace(zone)
            if zone_id not in self._zone_selection_history:
                self._zone_selection_history.append(zone_id)

        # Update UI
        self._update_zone_combo()
        self._emit_zones()

        return True

    def set_current_file_path(self, file_path: str):
        """Set current file path for per-file zone tracking."""
        self._current_file_path = file_path

    def clear_per_file_custom_zones(self, reset_paths: bool = False):
        """Clear all per-file custom zone storage.

        Args:
            reset_paths: If True, also clear _current_file_path and _batch_base_dir.
                        Use True only when completely closing batch mode.
        """
        self._per_file_custom_zones.clear()
        if reset_paths:
            self._current_file_path = ""
            self._batch_base_dir = ""

    def _persist_custom_zones_to_disk(self):
        """Persist per-file custom zones to disk (.xoaghim.json)."""
        # Use batch_base_dir or current file's parent folder
        base_dir = self._batch_base_dir
        if not base_dir and self._current_file_path:
            from pathlib import Path
            base_dir = str(Path(self._current_file_path).parent)
        if not base_dir:
            return
        from core.config_manager import get_config_manager
        # Convert Zone objects to serializable dicts
        serializable = {}
        for file_path, zones in self._per_file_custom_zones.items():
            serializable[file_path] = {
                zone_id: self._zone_to_dict(zone)
                for zone_id, zone in zones.items()
            }
        get_config_manager().save_per_file_custom_zones(base_dir, serializable)

    def _zone_to_dict(self, zone: Zone) -> dict:
        """Convert Zone to serializable dict."""
        return {
            'id': zone.id,
            'name': zone.name,
            'x': zone.x,
            'y': zone.y,
            'width': zone.width,
            'height': zone.height,
            'threshold': zone.threshold,
            'enabled': zone.enabled,
            'zone_type': zone.zone_type,
            'page_filter': zone.page_filter,
            'target_page': zone.target_page,
            'width_px': zone.width_px,
            'height_px': zone.height_px,
        }

    def _dict_to_zone(self, d: dict) -> Zone:
        """Convert dict back to Zone object."""
        return Zone(
            id=d['id'],
            name=d['name'],
            x=d['x'],
            y=d['y'],
            width=d['width'],
            height=d['height'],
            threshold=d.get('threshold', 5),
            enabled=d.get('enabled', True),
            zone_type=d.get('zone_type', 'remove'),
            page_filter=d.get('page_filter', 'all'),
            target_page=d.get('target_page', -1),
            width_px=d.get('width_px', 0),
            height_px=d.get('height_px', 0),
        )

    def load_persisted_custom_zones(self, batch_base_dir: str):
        """Load persisted custom zones from disk for crash recovery.

        Called when opening a batch folder to restore previous work.

        Args:
            batch_base_dir: Batch folder to load zones for.
        """
        self._batch_base_dir = batch_base_dir
        # Clear old zones before loading new source
        self._per_file_custom_zones.clear()
        self._custom_zones.clear()
        from core.config_manager import get_config_manager
        persisted = get_config_manager().get_per_file_custom_zones(batch_base_dir)
        if persisted:
            # Convert dicts back to Zone objects
            for file_path, zones in persisted.items():
                self._per_file_custom_zones[file_path] = {
                    zone_id: self._dict_to_zone(zone_dict)
                    for zone_id, zone_dict in zones.items()
                }

    def _on_settings_changed(self):
        """Khi thay đổi settings"""
        self.threshold_label.setText(str(self.threshold_slider.value()))

        # Update threshold cho tất cả zones
        threshold = self.threshold_slider.value()
        for zone in self._zones.values():
            zone.threshold = threshold
        for zone in self._custom_zones.values():
            zone.threshold = threshold

        settings = self.get_settings()
        self.settings_changed.emit(settings)
        self._emit_zones()
        self._save_zone_config()  # Save config when threshold changes
    
    def _on_browse_output(self):
        """Chọn thư mục đầu ra"""
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục đầu ra"
        )
        if folder:
            self.output_path.setText(folder)

    def _on_output_settings_changed(self):
        """Emit signal khi output settings thay đổi"""
        output_dir = self.output_path.text()
        filename_pattern = self.filename_pattern.text()
        self.output_settings_changed.emit(output_dir, filename_pattern)

    def _on_text_protection_checkbox_changed(self):
        """Handle text protection checkbox change"""
        enabled = self.text_protection_cb.isChecked()
        self._text_protection_options.enabled = enabled

        # Emit signal with current options
        self.text_protection_changed.emit(self._text_protection_options)
        self._save_zone_config()  # Save config when text protection changes

    def _on_batch_render_changed(self):
        """Handle batch render checkbox change"""
        enabled = self.batch_render_cb.isChecked()
        self.batch_render_changed.emit(enabled)
        self._save_zone_config()  # Save config

    def is_batch_render_enabled(self) -> bool:
        """Check if batch render is enabled"""
        return self.batch_render_cb.isChecked()

    def _open_text_protection_dialog(self):
        """Open text protection settings dialog"""
        dialog = TextProtectionDialog(self, self._text_protection_options)
        dialog.settings_changed.connect(self._on_text_protection_dialog_saved)
        dialog.exec_()

    def _on_text_protection_dialog_saved(self, options: TextProtectionOptions):
        """Handle text protection dialog save"""
        self._text_protection_options = options

        # Update checkbox state
        self.text_protection_cb.blockSignals(True)
        self.text_protection_cb.setChecked(options.enabled)
        self.text_protection_cb.blockSignals(False)

        # Emit signal
        self.text_protection_changed.emit(options)

    def get_text_protection_options(self) -> TextProtectionOptions:
        """Get current text protection options"""
        return self._text_protection_options

    def _emit_zones(self):
        """Emit signal zones changed"""
        enabled_zones = [z for z in self._zones.values() if z.enabled]
        enabled_zones.extend([z for z in self._custom_zones.values() if z.enabled])
        self.zones_changed.emit(enabled_zones)
    
    def get_zones(self) -> List[Zone]:
        """Lấy danh sách zones đang enabled"""
        zones = [z for z in self._zones.values() if z.enabled]
        zones.extend([z for z in self._custom_zones.values() if z.enabled])
        return zones

    def get_zone_by_id(self, zone_id: str):
        """Lấy zone theo ID (bao gồm cả preset và custom)"""
        # Remove page index suffix if present (e.g., "corner_tl_0" -> "corner_tl")
        base_id = zone_id.rsplit('_', 1)[0] if zone_id.count('_') > 1 else zone_id
        if base_id in self._zones:
            return self._zones[base_id]
        if base_id in self._custom_zones:
            return self._custom_zones[base_id]
        return None

    def set_filter(self, filter_mode: str):
        """Chuyển filter radio button: 'all', 'odd', 'even', 'none'"""
        filter_buttons = {
            'all': self.apply_all_rb,
            'odd': self.apply_odd_rb,
            'even': self.apply_even_rb,
            'none': self.apply_free_rb
        }
        if filter_mode in filter_buttons:
            filter_buttons[filter_mode].setChecked(True)
            self._on_apply_filter_changed(filter_buttons[filter_mode])

    def get_settings(self) -> dict:
        """Lấy settings"""
        dpi_map = {0: 300, 1: 250, 2: 200, 3: 100, 4: 72}
        jpeg_quality_map = {0: 100, 1: 90, 2: 80, 3: 70}  # 100%, 90%, 80%, 70%

        # Determine apply_pages from radio buttons
        checked_id = self.apply_group.checkedId()
        apply_pages_map = {0: 'all', 1: 'odd', 2: 'even', 3: 'none'}
        apply_pages = apply_pages_map.get(checked_id, 'all')

        return {
            'threshold': self.threshold_slider.value(),
            'dpi': dpi_map.get(self.quality_combo.currentIndex(), 300),
            'jpeg_quality': jpeg_quality_map.get(self.jpeg_quality_combo.currentIndex(), 90),
            'optimize_size': self.optimize_size_cb.isChecked(),
            'output_path': self.output_path.text(),
            'filename_pattern': self.filename_pattern.text(),
            'apply_pages': apply_pages,
            'text_protection': self.get_text_protection_options(),
        }
    
    def _on_apply_filter_changed(self, button):
        """Handle radio button selection for page filter"""
        filter_map = {
            self.apply_all_rb: 'all',
            self.apply_odd_rb: 'odd',
            self.apply_even_rb: 'even',
            self.apply_free_rb: 'none'
        }
        filter_mode = filter_map.get(button, 'all')
        self.page_filter_changed.emit(filter_mode)
        self._save_zone_config()  # Save config when filter changes

    def _on_reset_zones_clicked(self):
        """Handle reset zones button - show popup with zone type options"""
        from PyQt5.QtWidgets import QDialog, QGroupBox, QFrame

        # Styles
        group_style = """
            QGroupBox {
                font-size: 12px; font-weight: 600; color: #374151;
                border: 1px solid #E5E7EB; border-radius: 8px;
                margin-top: 8px; padding: 8px; background-color: #FAFAFA;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 12px;
                padding: 0 6px; background-color: #FAFAFA;
            }
        """
        btn_style = """
            QPushButton {
                background-color: #FFFFFF; color: #374151;
                border: 1px solid #D1D5DB; border-radius: 6px;
                padding: 6px 12px; font-size: 12px;
            }
            QPushButton:hover { background-color: #DBEAFE; color: #1D4ED8; border-color: #93C5FD; }
            QPushButton:pressed { background-color: #BFDBFE; }
            QPushButton:disabled { background-color: #F3F4F6; color: #9CA3AF; border-color: #E5E7EB; }
        """
        btn_danger_style = """
            QPushButton {
                background-color: #FEF2F2; color: #DC2626;
                border: 1px solid #FECACA; border-radius: 6px;
                padding: 6px 12px; font-size: 12px;
            }
            QPushButton:hover { background-color: #FEE2E2; border-color: #F87171; }
            QPushButton:pressed { background-color: #FECACA; }
            QPushButton:disabled { background-color: #F3F4F6; color: #9CA3AF; border-color: #E5E7EB; }
        """
        desc_style = "font-size: 11px; color: #6B7280; margin-bottom: 4px;"

        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Xóa vùng chọn")
        dialog.setMinimumWidth(320)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Helper to check Zone chung custom zones (page_filter != 'none')
        def has_zone_chung_custom():
            return any(
                getattr(z, 'page_filter', 'all') != 'none'
                for z in self._custom_zones.values()
            )

        # Helper to check Zone riêng for current file only
        def has_zone_rieng_current_file():
            parent = self.parent()
            while parent:
                if hasattr(parent, 'preview') and hasattr(parent.preview, 'before_panel'):
                    before_panel = parent.preview.before_panel
                    per_page_zones = getattr(before_panel, '_per_page_zones', {})
                    for page_zones in per_page_zones.values():
                        for zone_id in page_zones.keys():
                            if not zone_id.startswith('corner_') and not zone_id.startswith('margin_'):
                                return True
                    return False
                parent = parent.parent() if hasattr(parent, 'parent') else None
            return False

        # Helper to check if in batch (folder) mode
        def is_batch_mode():
            parent = self.parent()
            while parent:
                if hasattr(parent, '_batch_mode'):
                    return parent._batch_mode
                parent = parent.parent() if hasattr(parent, 'parent') else None
            return False

        # State tracking
        state = {
            'has_zone_chung': any(z.enabled for z in self._zones.values()) or has_zone_chung_custom(),
            'has_zone_rieng_file': has_zone_rieng_current_file(),
            'has_zone_rieng_folder': self._has_per_file_zones(),
            'is_batch_mode': is_batch_mode()
        }
        buttons = {}

        # Faded button style (disabled state)
        btn_faded_style = """
            QPushButton {
                background-color: #F9FAFB; color: #D1D5DB;
                border: 1px solid #E5E7EB; border-radius: 6px;
                padding: 6px 12px; font-size: 12px;
            }
        """
        btn_danger_faded_style = """
            QPushButton {
                background-color: #FEF2F2; color: #F9A8A8;
                border: 1px solid #FECACA; border-radius: 6px;
                padding: 6px 12px; font-size: 12px;
            }
        """

        def update_buttons():
            """Update button styles after deletion - fade when no zones"""
            state['has_zone_chung'] = any(z.enabled for z in self._zones.values()) or has_zone_chung_custom()
            state['has_zone_rieng_file'] = has_zone_rieng_current_file()
            state['has_zone_rieng_folder'] = self._has_per_file_zones()

            # Zone chung button: fade when no zones
            if state['has_zone_chung']:
                buttons['btn_chung'].setStyleSheet(btn_style)
                buttons['btn_chung'].setEnabled(True)
            else:
                buttons['btn_chung'].setStyleSheet(btn_faded_style)
                buttons['btn_chung'].setEnabled(False)

            # "File hiện tại" button: fade when no zones for current file
            if state['has_zone_rieng_file']:
                buttons['btn_file'].setStyleSheet(btn_style)
                buttons['btn_file'].setEnabled(True)
            else:
                buttons['btn_file'].setStyleSheet(btn_faded_style)
                buttons['btn_file'].setEnabled(False)

            # "Cả thư mục" button: fade if single file or no zones
            if state['is_batch_mode'] and state['has_zone_rieng_folder']:
                buttons['btn_folder'].setStyleSheet(btn_style)
                buttons['btn_folder'].setEnabled(True)
            else:
                buttons['btn_folder'].setStyleSheet(btn_faded_style)
                buttons['btn_folder'].setEnabled(False)

            # "Xóa tất cả" button: fade when no zones at all
            has_any = state['has_zone_chung'] or state['has_zone_rieng_file'] or state['has_zone_rieng_folder']
            if has_any:
                buttons['btn_all'].setStyleSheet(btn_danger_style)
                buttons['btn_all'].setEnabled(True)
            else:
                buttons['btn_all'].setStyleSheet(btn_danger_faded_style)
                buttons['btn_all'].setEnabled(False)

        def on_reset_chung():
            self._reset_zone_chung()
            update_buttons()

        def on_reset_rieng(scope):
            self._reset_zone_rieng(scope)
            update_buttons()

        def on_reset_all():
            self._reset_all_zone_types()
            update_buttons()

        # Zone chung section
        chung_group = QGroupBox("Zone chung")
        chung_group.setStyleSheet(group_style)
        chung_layout = QVBoxLayout(chung_group)
        chung_layout.setContentsMargins(8, 12, 8, 8)
        chung_layout.setSpacing(6)

        desc = QLabel("Góc, Cạnh, Tùy biến chung (áp dụng cho tất cả)")
        desc.setStyleSheet(desc_style)
        chung_layout.addWidget(desc)

        buttons['btn_chung'] = QPushButton("Xóa Zone chung")
        buttons['btn_chung'].setStyleSheet(btn_style if state['has_zone_chung'] else btn_faded_style)
        buttons['btn_chung'].setEnabled(state['has_zone_chung'])
        buttons['btn_chung'].clicked.connect(on_reset_chung)
        chung_layout.addWidget(buttons['btn_chung'])
        layout.addWidget(chung_group)

        # Zone riêng section
        rieng_group = QGroupBox("Zone riêng")
        rieng_group.setStyleSheet(group_style)
        rieng_layout = QVBoxLayout(rieng_group)
        rieng_layout.setContentsMargins(8, 12, 8, 8)
        rieng_layout.setSpacing(6)

        desc = QLabel("Vùng vẽ riêng theo từng file")
        desc.setStyleSheet(desc_style)
        rieng_layout.addWidget(desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        buttons['btn_file'] = QPushButton("File hiện tại")
        buttons['btn_file'].setStyleSheet(btn_style if state['has_zone_rieng_file'] else btn_faded_style)
        buttons['btn_file'].setEnabled(state['has_zone_rieng_file'])
        buttons['btn_file'].clicked.connect(lambda: on_reset_rieng('file'))
        btn_row.addWidget(buttons['btn_file'])

        buttons['btn_folder'] = QPushButton("Cả thư mục")
        folder_enabled = state['is_batch_mode'] and state['has_zone_rieng_folder']
        buttons['btn_folder'].setStyleSheet(btn_style if folder_enabled else btn_faded_style)
        buttons['btn_folder'].setEnabled(folder_enabled)
        buttons['btn_folder'].clicked.connect(lambda: on_reset_rieng('folder'))
        btn_row.addWidget(buttons['btn_folder'])

        rieng_layout.addLayout(btn_row)
        layout.addWidget(rieng_group)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #E5E7EB;")
        separator.setFixedHeight(1)
        layout.addWidget(separator)

        # Bottom row
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        has_any = state['has_zone_chung'] or state['has_zone_rieng_file'] or state['has_zone_rieng_folder']
        buttons['btn_all'] = QPushButton("Xóa tất cả")
        buttons['btn_all'].setToolTip("Zone chung + Zone riêng")
        buttons['btn_all'].setStyleSheet(btn_danger_style if has_any else btn_danger_faded_style)
        buttons['btn_all'].setEnabled(has_any)
        buttons['btn_all'].clicked.connect(on_reset_all)
        bottom_row.addWidget(buttons['btn_all'])

        bottom_row.addStretch()

        btn_close = QPushButton("Đóng")
        btn_close.setStyleSheet(btn_style)
        btn_close.clicked.connect(dialog.reject)
        bottom_row.addWidget(btn_close)

        layout.addLayout(bottom_row)

        dialog.exec_()

    def _reset_manual_zones(self):
        """Reset manual zones (thủ công = Góc, Cạnh, Tùy biến)"""
        # Disable all preset zones (corners, edges)
        for zone in self._zones.values():
            zone.enabled = False

        # Clear custom zones
        self._custom_zones.clear()
        self._custom_zone_counter = 0

        # Clear selection history
        self._zone_selection_history.clear()
        self._selected_zone_id = None

        # Update zone selector UI
        self.zone_selector.reset_all()

        # Update zone combo
        self._update_zone_combo()

        # Emit signal to update preview
        self._emit_zones()

        # Emit signal to clear per_page_zones in preview (folder scope, manual type)
        self.zones_reset.emit('folder', 'manual')

        # Save config to persist zone removal
        self._save_zone_config()

    def _reset_auto_detection(self):
        """Reset auto detection (tự động - nhận diện vùng bảo vệ)"""
        if not self.text_protection_cb.isChecked():
            return

        # Uncheck the text protection checkbox
        self.text_protection_cb.setChecked(False)
        # This will trigger _on_text_protection_checkbox_changed which emits signal

    def _reset_all_zones(self):
        """Reset all zones (both manual and auto detection)"""
        # Reset manual zones
        self._reset_manual_zones()

        # Disable auto detection
        if self.text_protection_cb.isChecked():
            self.text_protection_cb.setChecked(False)

    def _has_per_file_zones(self) -> bool:
        """Check if there are per-file zones (Zone riêng)

        Zone riêng = custom_* zones with page_filter == 'none'
        NOT Zone chung (corner_*, margin_*, custom zones with page_filter != 'none')
        """
        # Check via parent main_window's preview
        parent = self.parent()
        while parent:
            if hasattr(parent, 'preview') and hasattr(parent.preview, 'before_panel'):
                before_panel = parent.preview.before_panel

                # Check current file's Zone riêng from _per_page_zones
                per_page_zones = getattr(before_panel, '_per_page_zones', {})
                for page_zones in per_page_zones.values():
                    for zone_id in page_zones.keys():
                        # Zone riêng = custom_* or protect_* (not preset zones)
                        if not zone_id.startswith('corner_') and not zone_id.startswith('margin_'):
                            return True

                # Check other files' Zone riêng from _per_file_zones
                per_file_zones = getattr(before_panel, '_per_file_zones', {})
                for file_zones in per_file_zones.values():
                    for page_zones in file_zones.values():
                        for zone_id in page_zones.keys():
                            if not zone_id.startswith('corner_') and not zone_id.startswith('margin_'):
                                return True

                return False
            parent = parent.parent() if hasattr(parent, 'parent') else None
        return False

    def _reset_zone_chung(self):
        """Reset Zone chung (Góc, Cạnh, Tùy biến chung)

        Zone chung = preset zones + custom zones with page_filter != 'none'
        Zone riêng = custom zones with page_filter == 'none' (Tự do mode)
        """
        # Disable all preset zones (corners, edges)
        for zone in self._zones.values():
            zone.enabled = False

        # Only clear Zone chung custom zones (page_filter != 'none')
        # Keep Zone riêng (Tự do zones with page_filter == 'none')
        zone_rieng_ids = [
            zone_id for zone_id, zone in self._custom_zones.items()
            if getattr(zone, 'page_filter', 'all') == 'none'
        ]
        zone_chung_ids = [
            zone_id for zone_id in self._custom_zones.keys()
            if zone_id not in zone_rieng_ids
        ]

        # Remove only Zone chung custom zones
        for zone_id in zone_chung_ids:
            del self._custom_zones[zone_id]

        # Clear selection history for removed zones
        self._zone_selection_history = [
            z for z in self._zone_selection_history if z in self._custom_zones
        ]
        if self._selected_zone_id not in self._custom_zones:
            self._selected_zone_id = None

        # Update zone selector UI
        self.zone_selector.reset_all()

        # Update zone combo
        self._update_zone_combo()

        # Emit signal to update preview
        self._emit_zones()

        # Save config to persist zone removal
        self._save_zone_config()

        # Emit signal to clear Zone chung overlays in preview
        self.zones_reset.emit('folder', 'chung')

    def _reset_zone_rieng(self, scope: str = 'folder'):
        """Reset Zone riêng (per-file zones)

        Args:
            scope: 'file' for current file, 'folder' for entire folder
        """
        # Clear Zone riêng from _custom_zones (zones with page_filter == 'none')
        zone_rieng_ids = [
            zone_id for zone_id, zone in self._custom_zones.items()
            if getattr(zone, 'page_filter', 'all') == 'none'
        ]
        for zone_id in zone_rieng_ids:
            del self._custom_zones[zone_id]

        # Clear from selection history
        self._zone_selection_history = [
            z for z in self._zone_selection_history if z in self._custom_zones or z in self._zones
        ]
        if self._selected_zone_id not in self._custom_zones and self._selected_zone_id not in self._zones:
            self._selected_zone_id = None

        # Update UI
        self._update_zone_combo()
        self._emit_zones()

        # Clear from per-file storage
        if scope == 'file' and self._current_file_path:
            if self._current_file_path in self._per_file_custom_zones:
                del self._per_file_custom_zones[self._current_file_path]
        elif scope == 'folder':
            self._per_file_custom_zones.clear()

        # Persist to disk (works for both batch and single file mode)
        # _batch_base_dir is set to folder path (batch) or file path (single)
        if self._batch_base_dir:
            self._persist_custom_zones_to_disk()

        # Emit signal for main_window to clear per-page zones in preview
        self.zones_reset.emit(scope, 'rieng')

    def _reset_all_zone_types(self):
        """Reset all zone types (Zone chung + Zone riêng)"""
        self._reset_zone_chung()
        self._reset_zone_rieng()

    def _reset_zones_with_scope(self, scope: str, reset_type: str):
        """Reset zones with specified scope and type

        Args:
            scope: 'page' for current page only, 'folder' for entire folder
            reset_type: 'manual' for Thủ công, 'all' for Tất cả
        """
        if scope == 'folder':
            # Folder scope - reset all (current behavior)
            if reset_type == 'manual':
                self._reset_manual_zones()
            else:  # 'all'
                self._reset_all_zones()
        else:
            # Page scope - emit signal for main_window to handle
            # For page scope, we don't reset global settings (preset zones, auto detection)
            # We only clear per-page zones via the signal
            self.zones_reset.emit(scope, reset_type)

            # For 'all' reset type, also disable auto detection
            if reset_type == 'all' and self.text_protection_cb.isChecked():
                self.text_protection_cb.setChecked(False)

    def reset_to_default_zones(self):
        """Reset zones to default state:
        - Corner TL enabled
        - Filter: Tất cả (all)
        - Text protection enabled
        Called when opening a NEW folder
        """
        # Disable all preset zones
        for zone in self._zones.values():
            zone.enabled = False

        # Enable only corner_tl (default)
        self._zones['corner_tl'].enabled = True

        # Clear custom zones
        self._custom_zones.clear()
        self._custom_zone_counter = 0

        # Clear selection history and set corner_tl
        self._zone_selection_history.clear()
        self._zone_selection_history.append('corner_tl')
        self._selected_zone_id = 'corner_tl'

        # Block signals to prevent reset_all() from triggering _on_zone_selector_changed
        self.zone_selector.blockSignals(True)
        self.zone_selector.reset_all()
        self.zone_selector.corner_icon.set_zone_selected('corner_tl', True)
        self.zone_selector.blockSignals(False)

        # Reset filter to "Tất cả" (all)
        self.apply_all_rb.setChecked(True)
        self._on_apply_filter_changed(self.apply_all_rb)

        # Enable text protection (auto detection) by default
        if not self.text_protection_cb.isChecked():
            self.text_protection_cb.setChecked(True)

        # Update zone combo
        self._update_zone_combo()

        # Don't emit zones_reset or _emit_zones here
        # Zones will be set by _load_pdf() after pages are loaded
        # This avoids the issue where zones are set before preview has pages

    def set_output_path(self, path: str):
        self.output_path.setText(path)
    
    def update_zone_from_preview(self, zone_id: str, x: float, y: float, w: float, h: float,
                                   w_px: int = 0, h_px: int = 0):
        """Cập nhật zone từ preview (khi kéo thả)

        Args:
            zone_id: Zone ID
            x, y, w, h: Percentage values (0.0-1.0)
            w_px, h_px: Pixel values for corners/edges (0 means not applicable)
        """
        zone = self._zones.get(zone_id) or self._custom_zones.get(zone_id)
        if zone:
            zone.x = x
            zone.y = y
            zone.width = w
            zone.height = h

            # Update pixel values for corners/edges
            if w_px > 0:
                zone.width_px = w_px
            if h_px > 0:
                zone.height_px = h_px

            if zone_id == self._selected_zone_id:
                self.width_slider.blockSignals(True)
                self.height_slider.blockSignals(True)

                self.width_slider.setValue(int(w * 100))
                self.height_slider.setValue(int(h * 100))

                self.width_slider.blockSignals(False)
                self.height_slider.blockSignals(False)

                self._update_size_labels()

            # Debounced save for all zones (reduces I/O during drag)
            self._save_config_timer.start(300)

            # Also save Zone Riêng (per-file zones) if applicable
            # _save_zone_config skips zones with page_filter == 'none', so we need to save them separately
            if zone.page_filter == 'none':
                self.save_per_file_custom_zones()
