"""
Settings Panel - Panel cài đặt ở top (có thể thu gọn)
Sử dụng ZoneSelector với icon trang giấy
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QComboBox, QPushButton,
    QFrame, QGridLayout, QLineEdit,
    QFileDialog, QCheckBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor

from typing import List, Dict, Set
from core.processor import Zone, PRESET_ZONES, TextProtectionOptions
from ui.zone_selector import ZoneSelectorWidget
from ui.text_protection_dialog import TextProtectionDialog


# Thêm preset cho margin_top và margin_bottom
EXTENDED_PRESET_ZONES = {
    **PRESET_ZONES,
    'margin_top': Zone(
        id='margin_top',
        name='Viền trên',
        x=0.0, y=0.0,
        width=1.0, height=0.05,
        threshold=5
    ),
    'margin_bottom': Zone(
        id='margin_bottom',
        name='Viền dưới',
        x=0.0, y=0.95,
        width=1.0, height=0.05,
        threshold=5
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
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._zones: Dict[str, Zone] = {}
        self._custom_zones: Dict[str, Zone] = {}
        self._custom_zone_counter = 0
        self._selected_zone_id = None
        self._zone_selection_history: List[str] = []  # Track order of zone selections
        
        self._setup_ui()
        self._init_preset_zones()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(0)
        
        # Force white background on this widget and all children
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(255, 255, 255))
        self.setPalette(palette)
        
        # Global stylesheet for consistent styling - ALL white backgrounds
        self.setStyleSheet("""
            SettingsPanel {
                background-color: #FFFFFF;
                border-bottom: 1px solid #D1D5DB;
            }
            SettingsPanel QWidget {
                background-color: #FFFFFF;
            }
            QFrame {
                background-color: #FFFFFF;
                border: none;
            }
            QLabel {
                background-color: #FFFFFF;
                font-size: 12px;
                color: #374151;
            }
            QCheckBox {
                background-color: #FFFFFF;
                font-size: 12px;
                color: #374151;
            }
            QComboBox {
                font-size: 12px;
                background-color: #FFFFFF;
            }
            QLineEdit {
                font-size: 12px;
                background-color: #FFFFFF;
            }
            QPushButton {
                font-size: 12px;
                background-color: #FFFFFF;
            }
            QSlider {
                background-color: #FFFFFF;
            }
            QSlider::groove:horizontal {
                background: #E5E7EB;
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #0043a5;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
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
        
        zone_title = QLabel("Vùng xử lý")
        zone_title.setStyleSheet("""
            font-weight: 600; 
            color: #374151; 
            font-size: 12px;
            padding-bottom: 6px;
            border-bottom: 1px solid #E5E7EB;
            background-color: #FFFFFF;
        """)
        zone_container.addWidget(zone_title)
        
        # Row with zone selector icons and apply checkboxes
        zone_row = QHBoxLayout()
        zone_row.setSpacing(12)
        
        # Zone icons column with labels
        zone_icons_widget = QWidget()
        zone_icons_widget.setStyleSheet("background-color: #FFFFFF;")
        zone_icons_col = QVBoxLayout(zone_icons_widget)
        zone_icons_col.setContentsMargins(0, 0, 0, 0)
        zone_icons_col.setSpacing(4)
        
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
        labels_row.setSpacing(12)
        
        for label_text in ["Góc", "Cạnh", "Tùy biến"]:
            lbl = QLabel(label_text)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedWidth(100)
            lbl.setStyleSheet("color: #6B7280; font-size: 12px; background-color: #FFFFFF;")
            labels_row.addWidget(lbl)
        
        zone_icons_col.addWidget(labels_widget)
        zone_row.addWidget(zone_icons_widget)
        
        # Apply checkboxes
        apply_widget = QWidget()
        apply_widget.setStyleSheet("background-color: #FFFFFF;")
        apply_layout = QVBoxLayout(apply_widget)
        apply_layout.setContentsMargins(0, 0, 0, 0)
        apply_layout.setSpacing(4)
        
        apply_label = QLabel("Áp dụng:")
        apply_label.setStyleSheet("color: #6B7280; font-size: 12px; background-color: #FFFFFF;")
        apply_layout.addWidget(apply_label)
        
        self.apply_all_cb = QCheckBox("Tất cả các trang")
        self.apply_all_cb.setChecked(True)
        self.apply_all_cb.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        self.apply_all_cb.stateChanged.connect(self._on_apply_all_changed)
        apply_layout.addWidget(self.apply_all_cb)
        
        self.apply_odd_cb = QCheckBox("Các trang lẻ")
        self.apply_odd_cb.setChecked(False)
        self.apply_odd_cb.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        self.apply_odd_cb.stateChanged.connect(self._on_apply_odd_changed)
        apply_layout.addWidget(self.apply_odd_cb)
        
        self.apply_even_cb = QCheckBox("Các trang chẵn")
        self.apply_even_cb.setChecked(False)
        self.apply_even_cb.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        self.apply_even_cb.stateChanged.connect(self._on_apply_even_changed)
        apply_layout.addWidget(self.apply_even_cb)
        
        apply_layout.addStretch()
        zone_row.addWidget(apply_widget)
        zone_row.addStretch()
        
        zone_container.addLayout(zone_row)
        zone_container.addStretch()
        main_row.addWidget(zone_widget, stretch=1)  # Smaller width
        
        # ========== Column 2: THÔNG SỐ ==========
        params_widget = QWidget()
        params_widget.setStyleSheet("background-color: #FFFFFF;")
        params_container = QVBoxLayout(params_widget)
        params_container.setContentsMargins(0, 0, 0, 0)
        params_container.setSpacing(8)
        
        params_title = QLabel("Thông số")
        params_title.setStyleSheet("""
            font-weight: 600; 
            color: #374151; 
            font-size: 12px;
            padding-bottom: 6px;
            border-bottom: 1px solid #E5E7EB;
            background-color: #FFFFFF;
        """)
        params_container.addWidget(params_title)
        
        params_layout = QGridLayout()
        params_layout.setSpacing(6)
        
        # Chọn zone để chỉnh
        lbl_vung = QLabel("Vùng:")
        lbl_vung.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        params_layout.addWidget(lbl_vung, 0, 0)
        self.zone_combo = QComboBox()
        self.zone_combo.setMinimumWidth(120)
        self.zone_combo.currentTextChanged.connect(self._on_zone_selected)
        params_layout.addWidget(self.zone_combo, 0, 1, 1, 2)
        
        # Kích thước
        lbl_rong = QLabel("Rộng:")
        lbl_rong.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        params_layout.addWidget(lbl_rong, 1, 0)
        self.width_slider = QSlider(Qt.Horizontal)
        self.width_slider.setRange(1, 50)
        self.width_slider.setValue(12)
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
        self.height_slider.valueChanged.connect(self._on_zone_size_changed)
        params_layout.addWidget(self.height_slider, 2, 1)
        self.height_label = QLabel("12%")
        self.height_label.setFixedWidth(32)
        self.height_label.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        params_layout.addWidget(self.height_label, 2, 2)
        
        # Độ nhạy
        lbl_nhay = QLabel("Độ nhạy:")
        lbl_nhay.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        params_layout.addWidget(lbl_nhay, 3, 0)
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(1, 15)
        self.threshold_slider.setValue(5)
        self.threshold_slider.valueChanged.connect(self._on_settings_changed)
        params_layout.addWidget(self.threshold_slider, 3, 1)
        self.threshold_label = QLabel("5")
        self.threshold_label.setFixedWidth(32)
        self.threshold_label.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        params_layout.addWidget(self.threshold_label, 3, 2)
        
        params_container.addLayout(params_layout)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #E5E7EB; margin: 8px 0;")
        sep.setFixedHeight(1)
        params_container.addWidget(sep)

        # Text protection section - simplified with settings button
        protection_row = QHBoxLayout()
        protection_row.setSpacing(8)

        self.text_protection_cb = QCheckBox("Bảo vệ văn bản (AI)")
        self.text_protection_cb.setChecked(True)  # Mặc định bật
        self.text_protection_cb.setToolTip(
            "Sử dụng AI để phát hiện và bảo vệ vùng văn bản,\n"
            "bảng biểu khỏi bị xóa nhầm."
        )
        self.text_protection_cb.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        self.text_protection_cb.stateChanged.connect(self._on_text_protection_checkbox_changed)
        protection_row.addWidget(self.text_protection_cb)

        self.text_protection_settings_btn = QPushButton("⚙")
        self.text_protection_settings_btn.setFixedSize(24, 24)
        self.text_protection_settings_btn.setToolTip("Cài đặt bảo vệ văn bản")
        self.text_protection_settings_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                background-color: #F3F4F6;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        self.text_protection_settings_btn.clicked.connect(self._open_text_protection_dialog)
        protection_row.addWidget(self.text_protection_settings_btn)

        protection_row.addStretch()
        params_container.addLayout(protection_row)

        # Store current text protection options
        self._text_protection_options = TextProtectionOptions()

        params_container.addStretch()
        main_row.addWidget(params_widget, stretch=1)
        
        # ========== Column 3: ĐẦU RA ==========
        output_widget = QWidget()
        output_widget.setStyleSheet("background-color: #FFFFFF;")
        output_container = QVBoxLayout(output_widget)
        output_container.setContentsMargins(0, 0, 0, 0)
        output_container.setSpacing(8)
        
        output_title = QLabel("Đầu ra")
        output_title.setStyleSheet("""
            font-weight: 600; 
            color: #374151; 
            font-size: 12px;
            padding-bottom: 6px;
            border-bottom: 1px solid #E5E7EB;
            background-color: #FFFFFF;
        """)
        output_container.addWidget(output_title)
        
        output_layout = QGridLayout()
        output_layout.setSpacing(6)
        
        # DPI (độ phân giải)
        lbl_dpi = QLabel("Độ phân giải:")
        lbl_dpi.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        output_layout.addWidget(lbl_dpi, 0, 0)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["300 dpi", "250 dpi", "200 dpi", "100 dpi", "72 dpi"])
        self.quality_combo.setCurrentIndex(2)  # Default 200 dpi
        output_layout.addWidget(self.quality_combo, 0, 1, 1, 2)

        # JPEG Quality (chất lượng nén)
        lbl_jpeg = QLabel("Nén JPEG:")
        lbl_jpeg.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        output_layout.addWidget(lbl_jpeg, 1, 0)
        self.jpeg_quality_combo = QComboBox()
        self.jpeg_quality_combo.addItems(["Gốc (100%)", "90%", "80%", "70%"])
        self.jpeg_quality_combo.setCurrentIndex(1)  # Default: 90%
        output_layout.addWidget(self.jpeg_quality_combo, 1, 1, 1, 2)

        # Optimize size checkbox
        self.optimize_size_cb = QCheckBox("Nén siêu nhẹ (đen trắng)")
        self.optimize_size_cb.setChecked(False)  # Default: disabled
        self.optimize_size_cb.setToolTip(
            "Chuyển ảnh thành đen trắng 1-bit với CCITT Group 4.\n"
            "Dung lượng giảm ~90% nhưng mất màu xám/gradient."
        )
        self.optimize_size_cb.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        output_layout.addWidget(self.optimize_size_cb, 2, 0, 1, 3)

        lbl_tm = QLabel("Thư mục:")
        lbl_tm.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        output_layout.addWidget(lbl_tm, 3, 0)
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("Chọn thư mục...")
        output_layout.addWidget(self.output_path, 3, 1)

        self.browse_btn = QPushButton("📁")
        self.browse_btn.setFixedSize(36, 28)
        self.browse_btn.setToolTip("Chọn thư mục đầu ra")
        self.browse_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px;
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
        output_layout.addWidget(self.browse_btn, 3, 2)

        lbl_tf = QLabel("Tên file:")
        lbl_tf.setStyleSheet("font-size: 12px; background-color: #FFFFFF;")
        output_layout.addWidget(lbl_tf, 4, 0)
        self.filename_pattern = QLineEdit("{gốc}_clean.pdf")
        output_layout.addWidget(self.filename_pattern, 4, 1, 1, 2)

        # Connect output settings changes
        self.output_path.textChanged.connect(self._on_output_settings_changed)
        self.filename_pattern.textChanged.connect(self._on_output_settings_changed)

        output_container.addLayout(output_layout)
        output_container.addStretch()
        main_row.addWidget(output_widget, stretch=2)  # Wider width
        
        layout.addLayout(main_row)
    
    def _init_preset_zones(self):
        """Khởi tạo preset zones"""
        for zone_id, zone in EXTENDED_PRESET_ZONES.items():
            self._zones[zone_id] = Zone(
                id=zone.id,
                name=zone.name,
                x=zone.x,
                y=zone.y,
                width=zone.width,
                height=zone.height,
                threshold=zone.threshold,
                enabled=False
            )
        
        # Enable góc trên trái mặc định
        self._zones['corner_tl'].enabled = True
        self._zone_selection_history.append('corner_tl')  # Add to history
        self._update_zone_combo()
    
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
    
    def _on_zone_clicked(self, zone_id: str, enabled: bool):
        """Khi click vào zone - cập nhật combo box và lưu lịch sử"""
        if enabled:
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
    
    def _update_size_labels(self):
        self.width_label.setText(f"{self.width_slider.value()}%")
        self.height_label.setText(f"{self.height_slider.value()}%")
    
    def _on_draw_mode_changed(self, mode):
        """Forward draw mode signal to MainWindow (mode: 'remove', 'protect', or None)"""
        print(f"[DrawMode] SettingsPanel._on_draw_mode_changed: mode={mode}")
        self.draw_mode_changed.emit(mode)

    def add_custom_zone_from_rect(self, x: float, y: float, width: float, height: float, zone_type: str = 'remove'):
        """Add custom zone from drawn rectangle (coordinates as % 0.0-1.0)

        Args:
            x, y, width, height: Zone coordinates as percentages (0.0-1.0)
            zone_type: 'remove' for removal zone, 'protect' for protection zone
        """
        print(f"[DrawMode] add_custom_zone_from_rect: x={x:.3f}, y={y:.3f}, w={width:.3f}, h={height:.3f}, type={zone_type}")
        self._custom_zone_counter += 1

        if zone_type == 'protect':
            zone_id = f'protect_{self._custom_zone_counter}'
            zone_name = f'Bảo vệ {self._custom_zone_counter}'
        else:
            zone_id = f'custom_{self._custom_zone_counter}'
            zone_name = f'Xóa ghim {self._custom_zone_counter}'

        self._custom_zones[zone_id] = Zone(
            id=zone_id,
            name=zone_name,
            x=x,
            y=y,
            width=width,
            height=height,
            threshold=self.threshold_slider.value(),
            enabled=True,
            zone_type=zone_type  # 'remove' or 'protect'
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
            if base_id in self._custom_zones:
                del self._custom_zones[base_id]
            # Update combo and emit for custom zones
            self._update_zone_combo()
            if self._zone_selection_history:
                self._select_zone_in_combo(self._zone_selection_history[-1])
            self._emit_zones()
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
    
    def get_settings(self) -> dict:
        """Lấy settings"""
        dpi_map = {0: 300, 1: 250, 2: 200, 3: 100, 4: 72}
        jpeg_quality_map = {0: 100, 1: 90, 2: 80, 3: 70}  # Gốc=100, 90%, 80%, 70%

        # Determine apply_pages from checkboxes
        if self.apply_all_cb.isChecked():
            apply_pages = 'all'
        elif self.apply_odd_cb.isChecked():
            apply_pages = 'odd'
        elif self.apply_even_cb.isChecked():
            apply_pages = 'even'
        else:
            apply_pages = 'all'

        return {
            'threshold': self.threshold_slider.value(),
            'dpi': dpi_map.get(self.quality_combo.currentIndex(), 200),
            'jpeg_quality': jpeg_quality_map.get(self.jpeg_quality_combo.currentIndex(), 90),
            'optimize_size': self.optimize_size_cb.isChecked(),
            'output_path': self.output_path.text(),
            'filename_pattern': self.filename_pattern.text(),
            'apply_pages': apply_pages,
            'text_protection': self.get_text_protection_options(),
        }
    
    def _on_apply_all_changed(self, state):
        """Handle all pages checkbox"""
        if state:
            self.apply_odd_cb.setChecked(False)
            self.apply_even_cb.setChecked(False)
            self.page_filter_changed.emit('all')
        else:
            self._check_emit_none()
    
    def _on_apply_odd_changed(self, state):
        """Handle odd pages checkbox"""
        if state:
            self.apply_all_cb.setChecked(False)
            self.apply_even_cb.setChecked(False)
            self.page_filter_changed.emit('odd')
        else:
            self._check_emit_none()
    
    def _on_apply_even_changed(self, state):
        """Handle even pages checkbox"""
        if state:
            self.apply_all_cb.setChecked(False)
            self.apply_odd_cb.setChecked(False)
            self.page_filter_changed.emit('even')
        else:
            self._check_emit_none()
    
    def _check_emit_none(self):
        """Check if all checkboxes are unchecked and emit 'none'"""
        if not self.apply_all_cb.isChecked() and \
           not self.apply_odd_cb.isChecked() and \
           not self.apply_even_cb.isChecked():
            self.page_filter_changed.emit('none')
    
    def set_output_path(self, path: str):
        self.output_path.setText(path)
    
    def update_zone_from_preview(self, zone_id: str, x: float, y: float, w: float, h: float):
        """Cập nhật zone từ preview (khi kéo thả)"""
        zone = self._zones.get(zone_id) or self._custom_zones.get(zone_id)
        if zone:
            zone.x = x
            zone.y = y
            zone.width = w
            zone.height = h
            
            if zone_id == self._selected_zone_id:
                self.width_slider.blockSignals(True)
                self.height_slider.blockSignals(True)
                
                self.width_slider.setValue(int(w * 100))
                self.height_slider.setValue(int(h * 100))
                
                self.width_slider.blockSignals(False)
                self.height_slider.blockSignals(False)
                
                self._update_size_labels()
