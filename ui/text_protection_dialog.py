"""
Text Protection Dialog - Popup cài đặt bảo vệ văn bản AI

Chứa các cài đặt:
- Bật/tắt bảo vệ văn bản
- Chọn loại nội dung bảo vệ (văn bản, bảng, công thức)
- Lề an toàn và độ tin cậy
- Server mode (Local/Remote GPU)
- API URL cho remote server
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QComboBox, QPushButton, QCheckBox,
    QLineEdit, QGroupBox, QMessageBox, QFrame,
    QDialogButtonBox, QStyledItemDelegate
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QFont

from typing import Set
from core.processor import TextProtectionOptions


class ComboItemDelegate(QStyledItemDelegate):
    """Custom delegate for larger combobox items"""
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(24)  # Set item height to 24px
        return size


class TextProtectionDialog(QDialog):
    """Dialog cài đặt bảo vệ văn bản AI"""

    # Signal khi settings thay đổi
    settings_changed = pyqtSignal(object)  # TextProtectionOptions

    def __init__(self, parent=None, current_options: TextProtectionOptions = None):
        super().__init__(parent)
        self._current_options = current_options or TextProtectionOptions()
        self._setup_ui()
        self._load_options()

    def _setup_ui(self):
        self.setWindowTitle("Cài đặt Nhận diện vùng bảo vệ")
        self.setMinimumWidth(400)
        self.setModal(True)

        # Global stylesheet for combobox hover effect (match bottom_bar style)
        self.setStyleSheet("""
            QComboBox {
                background-color: white;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px 6px;
                padding-right: 24px;
                color: #374151;
            }
            QComboBox QAbstractItemView {
                background-color: white;
                color: #374151;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                background-color: white;
                color: #374151;
                padding: 10px 8px 10px 18px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #93C5FD;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #93C5FD;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # === Header ===
        header = QLabel("Nhận diện vùng bảo vệ (tự động)")
        header.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #1F2937;
            padding-bottom: 8px;
        """)
        layout.addWidget(header)

        desc = QLabel(
            "Sử dụng YOLO DocLayNet để phát hiện và bảo vệ\n"
            "vùng văn bản, bảng biểu khỏi bị xóa nhầm."
        )
        desc.setStyleSheet("color: #6B7280; font-size: 12px;")
        layout.addWidget(desc)

        # === Enable checkbox ===
        self.enable_cb = QCheckBox("Bật bảo vệ văn bản")
        self.enable_cb.setStyleSheet("font-size: 13px; font-weight: 500;")
        self.enable_cb.stateChanged.connect(self._on_enable_changed)
        layout.addWidget(self.enable_cb)

        # === Options container ===
        self.options_widget = QFrame()
        self.options_widget.setStyleSheet("""
            QFrame {
                background-color: #F9FAFB;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        options_layout = QVBoxLayout(self.options_widget)
        options_layout.setSpacing(12)

        # --- Loại nội dung bảo vệ ---
        content_group = QGroupBox("Loại nội dung bảo vệ")
        content_group.setStyleSheet("""
            QGroupBox {
                font-weight: 600;
                font-size: 12px;
                border: none;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 0px;
            }
        """)
        content_layout = QHBoxLayout(content_group)
        content_layout.setSpacing(16)

        self.protect_text_cb = QCheckBox("Văn bản")
        self.protect_text_cb.setChecked(True)
        content_layout.addWidget(self.protect_text_cb)

        self.protect_table_cb = QCheckBox("Bảng biểu")
        self.protect_table_cb.setChecked(True)
        content_layout.addWidget(self.protect_table_cb)

        self.protect_formula_cb = QCheckBox("Công thức")
        self.protect_formula_cb.setChecked(True)
        content_layout.addWidget(self.protect_formula_cb)

        content_layout.addStretch()
        options_layout.addWidget(content_group)

        # --- Thông số ---
        params_group = QGroupBox("Thông số")
        params_group.setStyleSheet("""
            QGroupBox {
                font-weight: 600;
                font-size: 12px;
                border: none;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 0px;
            }
        """)
        params_layout = QVBoxLayout(params_group)
        params_layout.setSpacing(8)

        # Style for parameter labels
        param_label_style = """
            QLabel {
                font-size: 12px;
                color: #374151;
                min-width: 70px;
            }
        """
        value_label_style = """
            QLabel {
                font-size: 12px;
                font-weight: 600;
                color: #1F2937;
                background-color: #E5E7EB;
                border-radius: 4px;
                padding: 2px 8px;
                min-width: 50px;
            }
        """

        # Margin slider
        margin_row = QHBoxLayout()
        margin_label_title = QLabel("Lề an toàn:")
        margin_label_title.setStyleSheet(param_label_style)
        margin_row.addWidget(margin_label_title)
        self.margin_slider = QSlider(Qt.Horizontal)
        self.margin_slider.setRange(0, 50)  # 0-50px
        self.margin_slider.setValue(5)  # Default 5px
        self.margin_slider.setFixedWidth(150)
        self.margin_slider.valueChanged.connect(self._update_labels)
        margin_row.addWidget(self.margin_slider)
        self.margin_label = QLabel("5 px")
        self.margin_label.setStyleSheet(value_label_style)
        self.margin_label.setAlignment(Qt.AlignCenter)
        margin_row.addWidget(self.margin_label)
        margin_row.addStretch()
        params_layout.addLayout(margin_row)

        # Confidence slider
        conf_row = QHBoxLayout()
        conf_label_title = QLabel("Độ tin cậy:")
        conf_label_title.setStyleSheet(param_label_style)
        conf_row.addWidget(conf_label_title)
        self.conf_slider = QSlider(Qt.Horizontal)
        self.conf_slider.setRange(5, 90)  # Allow very low confidence (5%)
        self.conf_slider.setValue(10)  # Default 10%
        self.conf_slider.setFixedWidth(150)
        self.conf_slider.valueChanged.connect(self._update_labels)
        conf_row.addWidget(self.conf_slider)
        self.conf_label = QLabel("10%")
        self.conf_label.setStyleSheet(value_label_style)
        self.conf_label.setAlignment(Qt.AlignCenter)
        conf_row.addWidget(self.conf_label)
        conf_row.addStretch()
        params_layout.addLayout(conf_row)

        options_layout.addWidget(params_group)

        # --- Server settings ---
        server_group = QGroupBox("Server xử lý")
        server_group.setStyleSheet("""
            QGroupBox {
                font-weight: 600;
                font-size: 12px;
                border: none;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 0px;
            }
        """)
        server_layout = QVBoxLayout(server_group)
        server_layout.setSpacing(8)

        # Server mode (editable for custom popup styling on macOS)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Chế độ:"))
        self.server_mode_combo = QComboBox()
        self.server_mode_combo.addItems(["Local (CPU)", "Remote GPU"])
        self.server_mode_combo.setCurrentIndex(0)  # Default: Local (CPU)
        self.server_mode_combo.setFixedWidth(120)
        self.server_mode_combo.setEditable(True)
        self.server_mode_combo.lineEdit().setReadOnly(True)  # Prevent typing
        self.server_mode_combo.lineEdit().setTextMargins(0, 0, 0, 0)
        # Use custom delegate for larger item height
        self.server_mode_combo.setItemDelegate(ComboItemDelegate(self.server_mode_combo))
        # Apply view stylesheet directly for dropdown items
        self.server_mode_combo.view().setStyleSheet("""
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
        self.server_mode_combo.currentIndexChanged.connect(self._on_server_mode_changed)
        mode_row.addWidget(self.server_mode_combo)
        mode_row.addStretch()
        server_layout.addLayout(mode_row)

        # Remote URL
        self.url_widget = QFrame()
        url_layout = QHBoxLayout(self.url_widget)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(8)

        url_layout.addWidget(QLabel("API URL:"))
        self.url_input = QLineEdit("http://10.20.0.36:8765")
        self.url_input.setPlaceholderText("http://10.20.0.36:8765")
        self.url_input.setMinimumWidth(200)
        url_layout.addWidget(self.url_input)

        self.test_btn = QPushButton("Test kết nối")
        self.test_btn.setFixedWidth(90)
        self.test_btn.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        self.test_btn.clicked.connect(self._on_test_connection)
        url_layout.addWidget(self.test_btn)

        server_layout.addWidget(self.url_widget)

        # Server info label
        self.server_info = QLabel("")
        self.server_info.setStyleSheet("color: #6B7280; font-size: 11px;")
        server_layout.addWidget(self.server_info)

        options_layout.addWidget(server_group)
        layout.addWidget(self.options_widget)

        # === Buttons ===
        button_box = QDialogButtonBox()
        self.save_btn = button_box.addButton("Lưu", QDialogButtonBox.AcceptRole)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 24px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)
        self.cancel_btn = button_box.addButton("Hủy", QDialogButtonBox.RejectRole)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 8px 24px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_options(self):
        """Load current options to UI"""
        opts = self._current_options

        self.enable_cb.setChecked(opts.enabled)
        self.margin_slider.setValue(opts.margin)
        self.conf_slider.setValue(int(opts.confidence * 100))

        # Protected labels
        labels = opts.protected_labels
        self.protect_text_cb.setChecked(
            'plain_text' in labels or 'title' in labels
        )
        self.protect_table_cb.setChecked('table' in labels)
        self.protect_formula_cb.setChecked('isolate_formula' in labels)

        # Server settings
        self.server_mode_combo.setCurrentIndex(1 if opts.use_remote else 0)
        self.url_input.setText(opts.remote_url)

        self._on_enable_changed()
        self._on_server_mode_changed()
        self._update_labels()

    def _on_enable_changed(self):
        """Handle enable checkbox change"""
        enabled = self.enable_cb.isChecked()
        self.options_widget.setEnabled(enabled)
        self.options_widget.setStyleSheet(f"""
            QFrame {{
                background-color: {'#F9FAFB' if enabled else '#F3F4F6'};
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                padding: 12px;
            }}
        """)

    def _on_server_mode_changed(self):
        """Handle server mode change"""
        is_remote = self.server_mode_combo.currentIndex() == 1
        self.url_widget.setVisible(is_remote)
        self.server_info.setVisible(is_remote)

        if is_remote:
            self.server_info.setText("Sử dụng GPU server từ xa để xử lý nhanh hơn")
        else:
            self.server_info.setText("")

    def _update_labels(self):
        """Update slider labels"""
        self.margin_label.setText(f"{self.margin_slider.value()} px")
        self.conf_label.setText(f"{self.conf_slider.value()}%")

    def _on_test_connection(self):
        """Test remote server connection"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Lỗi", "Vui lòng nhập URL server")
            return

        try:
            import urllib.request
            import json

            req = urllib.request.Request(f"{url.rstrip('/')}/health", method='GET')
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))

                if data.get('status') == 'ok':
                    cuda_device = data.get('cuda_device', 'Unknown')
                    cuda_memory = data.get('cuda_memory', 'Unknown')
                    QMessageBox.information(
                        self,
                        "Kết nối thành công",
                        f"Server hoạt động bình thường!\n\n"
                        f"GPU: {cuda_device}\n"
                        f"Memory: {cuda_memory}"
                    )
                else:
                    QMessageBox.warning(self, "Lỗi", "Server phản hồi không hợp lệ")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Lỗi kết nối",
                f"Không thể kết nối tới server:\n{url}\n\nLỗi: {str(e)}"
            )

    def _on_save(self):
        """Save settings and close"""
        # Validate if remote mode
        is_remote = self.server_mode_combo.currentIndex() == 1
        if self.enable_cb.isChecked() and is_remote:
            url = self.url_input.text().strip()
            if not url:
                QMessageBox.warning(
                    self,
                    "Thiếu URL",
                    "Vui lòng nhập URL của GPU server."
                )
                return

        # Emit settings
        options = self.get_options()
        self.settings_changed.emit(options)
        self.accept()

    def get_options(self) -> TextProtectionOptions:
        """Get current options from UI"""
        # Build protected labels
        protected_labels: Set[str] = set()

        if self.protect_text_cb.isChecked():
            # YOLO DocLayNet: text, title, section-header, list-item, caption
            protected_labels.update({'title', 'plain_text', 'figure_caption'})

        if self.protect_table_cb.isChecked():
            # YOLO DocLayNet: table, footnote
            protected_labels.update({'table', 'table_footnote'})

        if self.protect_formula_cb.isChecked():
            # YOLO DocLayNet: formula
            protected_labels.update({'isolate_formula'})

        # Default if empty (YOLO DocLayNet labels)
        if not protected_labels:
            protected_labels = {
                'title', 'plain_text', 'table',
                'table_footnote', 'figure_caption', 'isolate_formula'
            }

        return TextProtectionOptions(
            enabled=self.enable_cb.isChecked(),
            protected_labels=protected_labels,
            margin=self.margin_slider.value(),
            confidence=self.conf_slider.value() / 100.0,
            use_remote=self.server_mode_combo.currentIndex() == 1,
            remote_url=self.url_input.text().strip() or "http://10.20.0.36:8765"
        )

    def set_options(self, options: TextProtectionOptions):
        """Set options from external source"""
        self._current_options = options
        self._load_options()
