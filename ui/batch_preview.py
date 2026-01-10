"""
Batch Preview - Widget cho xử lý hàng loạt thư mục PDF
Chỉ chứa file list panels, preview sử dụng ContinuousPreviewWidget
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QFrame, QLabel,
    QAbstractItemView, QPushButton, QCheckBox, QLineEdit
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor

import os
from typing import List, Optional


class FileListWidget(QListWidget):
    """Widget danh sách file với checkbox"""

    file_selected = pyqtSignal(str, int)  # Emit (file_path, row_index) khi file được chọn
    selection_changed = pyqtSignal(list)  # Emit danh sách file được check
    filter_changed = pyqtSignal(list)  # Emit visible file indices
    checkbox_changed = pyqtSignal(int, bool)  # Emit (original_index, is_checked) khi checkbox thay đổi
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._files: List[str] = []
        self._base_dir: str = ""
        self._filter_text: str = ""
        self._visible_indices: List[int] = []  # Track which original indices are visible
        
        # Style
        self.setStyleSheet("""
            QListWidget {
                background-color: white;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #E5E7EB;
            }
            QListWidget::item:selected {
                background-color: #DBEAFE;
                color: #1E40AF;
            }
            QListWidget::item:hover {
                background-color: #F3F4F6;
            }
        """)
        
        # Enable multi-selection
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        
        # Connect signals
        self.itemClicked.connect(self._on_item_clicked)
        self.itemChanged.connect(self._on_item_changed)
    
    def set_files(self, files: List[str], base_dir: str):
        """Set danh sách file"""
        self._files = files
        self._base_dir = base_dir
        self._filter_text = ""
        
        self._rebuild_list()
        
        # Select first item
        if self.count() > 0:
            self.setCurrentRow(0)
            first_item = self.item(0)
            if first_item:
                file_path = first_item.data(Qt.UserRole)
                self.file_selected.emit(file_path, 0)
    
    def _rebuild_list(self):
        """Rebuild list with current filter"""
        self.blockSignals(True)
        self.clear()
        self._visible_indices = []
        
        for idx, file_path in enumerate(self._files):
            # Apply filter
            if self._filter_text:
                if self._filter_text.lower() not in file_path.lower():
                    continue
            
            item = QListWidgetItem(file_path)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)  # Mặc định check tất cả
            item.setData(Qt.UserRole, file_path)
            item.setData(Qt.UserRole + 1, idx)  # Store original index
            self.addItem(item)
            self._visible_indices.append(idx)
        
        self.blockSignals(False)
        self.filter_changed.emit(self._visible_indices)
    
    def set_filter(self, text: str):
        """Set filter text"""
        self._filter_text = text
        self._rebuild_list()
        self.selection_changed.emit(self.get_checked_files())
    
    def get_visible_indices(self) -> List[int]:
        """Get list of visible original indices"""
        return self._visible_indices.copy()
    
    def filter_by_indices(self, indices: List[int]):
        """Filter to show only items at given original indices"""
        self.blockSignals(True)
        self.clear()
        self._visible_indices = []
        
        for idx in indices:
            if idx < len(self._files):
                file_path = self._files[idx]
                item = QListWidgetItem(file_path)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                item.setData(Qt.UserRole, file_path)
                item.setData(Qt.UserRole + 1, idx)
                self.addItem(item)
                self._visible_indices.append(idx)
        
        self.blockSignals(False)
    
    def _on_item_clicked(self, item: QListWidgetItem):
        """Khi click vào item"""
        file_path = item.data(Qt.UserRole)
        original_idx = item.data(Qt.UserRole + 1)
        if file_path:
            self.file_selected.emit(file_path, original_idx)
    
    def _on_item_changed(self, item: QListWidgetItem):
        """Khi checkbox thay đổi"""
        original_idx = item.data(Qt.UserRole + 1)
        is_checked = item.checkState() == Qt.Checked
        self.checkbox_changed.emit(original_idx, is_checked)
        self.selection_changed.emit(self.get_checked_files())
    
    def get_checked_files(self) -> List[str]:
        """Lấy danh sách file được check"""
        checked = []
        for i in range(self.count()):
            item = self.item(i)
            if item.checkState() == Qt.Checked:
                checked.append(item.data(Qt.UserRole))
        return checked
    
    def get_selected_file(self) -> Optional[str]:
        """Lấy file đang được select (highlight)"""
        items = self.selectedItems()
        if items:
            return items[0].data(Qt.UserRole)
        return None
    
    def select_row(self, row: int):
        """Select row by index"""
        if 0 <= row < self.count():
            self.setCurrentRow(row)
    
    def select_by_original_index(self, original_idx: int):
        """Select row by original file index"""
        for i in range(self.count()):
            item = self.item(i)
            if item.data(Qt.UserRole + 1) == original_idx:
                self.setCurrentRow(i)
                return
    
    def get_file_count(self) -> tuple:
        """Trả về (checked_count, total_count)"""
        checked = len(self.get_checked_files())
        total = len(self._files)  # Total from original list
        return (checked, total)
    
    def check_all(self):
        """Check tất cả visible items"""
        self.blockSignals(True)
        for i in range(self.count()):
            self.item(i).setCheckState(Qt.Checked)
        self.blockSignals(False)
        self.selection_changed.emit(self.get_checked_files())
    
    def uncheck_all(self):
        """Uncheck tất cả visible items"""
        self.blockSignals(True)
        for i in range(self.count()):
            self.item(i).setCheckState(Qt.Unchecked)
        self.blockSignals(False)
        self.selection_changed.emit(self.get_checked_files())
    
    def is_all_checked(self) -> bool:
        """Check if all visible items are checked"""
        for i in range(self.count()):
            if self.item(i).checkState() != Qt.Checked:
                return False
        return self.count() > 0
    
    def is_all_unchecked(self) -> bool:
        """Check if all visible items are unchecked"""
        for i in range(self.count()):
            if self.item(i).checkState() == Qt.Checked:
                return False
        return True

    def set_item_checked_by_index(self, original_idx: int, checked: bool):
        """Set checkbox state by original index without emitting signal"""
        self.blockSignals(True)
        for i in range(self.count()):
            item = self.item(i)
            if item.data(Qt.UserRole + 1) == original_idx:
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                break
        self.blockSignals(False)


class FileListPanel(QFrame):
    """Panel chứa file list với title bar"""

    file_selected = pyqtSignal(str, int)  # file_path, original_index
    selection_changed = pyqtSignal(list)
    close_requested = pyqtSignal()
    search_changed = pyqtSignal(str)  # Emit search text
    checkbox_changed = pyqtSignal(int, bool)  # (original_index, is_checked)
    toggle_all_changed = pyqtSignal(bool)  # Emit when toggle all checkbox changes
    
    def __init__(self, title: str, show_close_btn: bool = False, 
                 show_search: bool = False, parent=None):
        super().__init__(parent)
        
        self._show_close_btn = show_close_btn
        self._show_search = show_search
        
        self.setFrameStyle(QFrame.NoFrame)
        self.setStyleSheet("background-color: #E5E7EB;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Title bar
        title_bar = QWidget()
        title_bar.setFixedHeight(28)
        title_bar.setStyleSheet("background-color: #D1D5DB;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(8, 0, 8, 0)
        
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 13px; color: #0047AB;")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        
        # Close button
        if show_close_btn:
            self.close_btn = QPushButton("×")
            self.close_btn.setFixedSize(22, 22)
            self.close_btn.setVisible(False)
            self.close_btn.setStyleSheet("""
                QPushButton {
                    background-color: #C9CDD4;
                    border: none;
                    border-radius: 4px;
                    font-size: 16px;
                    font-weight: bold;
                    color: #374151;
                    padding-bottom: 2px;
                }
                QPushButton:hover {
                    background-color: #EF4444;
                    color: white;
                }
            """)
            self.close_btn.clicked.connect(self.close_requested.emit)
            title_layout.addWidget(self.close_btn)
        
        layout.addWidget(title_bar)
        
        # File list container
        list_container = QWidget()
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(4, 4, 4, 4)
        list_layout.setSpacing(4)
        
        # Header row: Checkbox + Count label + Search box
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        header_row.setContentsMargins(10, 0, 0, 0)  # Align with list item checkboxes
        
        # Toggle all checkbox
        self.toggle_checkbox = QCheckBox()
        self.toggle_checkbox.setChecked(True)
        self.toggle_checkbox.setStyleSheet("""
            QCheckBox {
                spacing: 4px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
            }
        """)
        self.toggle_checkbox.clicked.connect(self._on_toggle_all)
        header_row.addWidget(self.toggle_checkbox)
        
        # Count label
        self.count_label = QLabel("0 files")
        self.count_label.setStyleSheet("font-size: 11px; color: #6B7280;")
        header_row.addWidget(self.count_label)
        
        header_row.addStretch()
        
        # Search box (only if enabled)
        if show_search:
            self.search_box = QLineEdit()
            self.search_box.setPlaceholderText("🔍 Tìm kiếm...")
            self.search_box.setFixedWidth(250)  # Wider search box
            self.search_box.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #D1D5DB;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 11px;
                    background-color: white;
                }
                QLineEdit:focus {
                    border-color: #3B82F6;
                }
            """)
            self.search_box.textChanged.connect(self._on_search_changed)
            header_row.addWidget(self.search_box)
        
        list_layout.addLayout(header_row)
        
        # File list
        self.file_list = FileListWidget()
        self.file_list.file_selected.connect(self._on_file_selected)
        self.file_list.selection_changed.connect(self._on_selection_changed)
        self.file_list.checkbox_changed.connect(self._on_checkbox_changed)
        list_layout.addWidget(self.file_list)
        
        layout.addWidget(list_container)
    
    def set_title(self, title: str):
        self.title_label.setText(title)
    
    def set_files(self, files: List[str], base_dir: str):
        self.file_list.set_files(files, base_dir)
        self._update_count()
        self._update_toggle_state()
        
        if self._show_close_btn and hasattr(self, 'close_btn'):
            self.close_btn.setVisible(len(files) > 0)
    
    def _update_count(self):
        checked, total = self.file_list.get_file_count()
        self.count_label.setText(f"Đã chọn: {checked}/{total} files")
    
    def _update_toggle_state(self):
        """Update toggle checkbox state based on list state"""
        self.toggle_checkbox.blockSignals(True)
        if self.file_list.is_all_checked():
            self.toggle_checkbox.setChecked(True)
        elif self.file_list.is_all_unchecked():
            self.toggle_checkbox.setChecked(False)
        else:
            # Partial state - show as checked
            self.toggle_checkbox.setChecked(True)
        self.toggle_checkbox.blockSignals(False)
    
    def _on_toggle_all(self):
        """Toggle all files"""
        if self.file_list.is_all_checked():
            # All checked -> uncheck all
            self.file_list.uncheck_all()
            self.toggle_checkbox.setChecked(False)
            self.toggle_all_changed.emit(False)
        else:
            # Some or none checked -> check all
            self.file_list.check_all()
            self.toggle_checkbox.setChecked(True)
            self.toggle_all_changed.emit(True)
        self._update_count()

    def set_all_checked(self, checked: bool):
        """Set all items checked/unchecked without emitting toggle signal"""
        if checked:
            self.file_list.check_all()
        else:
            self.file_list.uncheck_all()
        self._update_toggle_state()
    
    def _on_search_changed(self, text: str):
        """Filter file list and notify parent"""
        self.file_list.set_filter(text)
        self._update_count()
        self._update_toggle_state()
        self.search_changed.emit(text)
    
    def apply_filter_indices(self, indices: List[int]):
        """Apply filter by showing only specific indices"""
        self.file_list.filter_by_indices(indices)
        self._update_count()
        self._update_toggle_state()
    
    def _on_file_selected(self, file_path: str, original_idx: int):
        self.file_selected.emit(file_path, original_idx)
    
    def _on_selection_changed(self, checked_files: List[str]):
        self._update_count()
        self._update_toggle_state()
        self.selection_changed.emit(checked_files)

    def _on_checkbox_changed(self, original_idx: int, is_checked: bool):
        """Forward checkbox change signal"""
        self.checkbox_changed.emit(original_idx, is_checked)

    def set_item_checked(self, original_idx: int, checked: bool):
        """Set checkbox state by original index"""
        self.file_list.set_item_checked_by_index(original_idx, checked)
        self._update_count()
        self._update_toggle_state()
    
    def select_row(self, row: int):
        self.file_list.select_row(row)
    
    def select_by_original_index(self, original_idx: int):
        self.file_list.select_by_original_index(original_idx)
    
    def get_checked_files(self) -> List[str]:
        return self.file_list.get_checked_files()
    
    def get_selected_file(self) -> Optional[str]:
        return self.file_list.get_selected_file()


class BatchFileListWidget(QWidget):
    """
    Widget chứa 2 file list panels (Gốc | Đích)
    Được đặt phía trên preview widget
    """

    file_selected = pyqtSignal(str)  # file_path from Gốc
    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._base_dir: str = ""
        self._output_dir: str = ""
        self._filename_pattern: str = "{gốc}_clean.pdf"
        self._files: List[str] = []
        self._output_files: List[str] = []
        self._syncing = False

        self._setup_ui()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Splitter for two panels
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: white;
                width: 2px;
            }
        """)
        
        # Gốc panel (with close button and search)
        self.goc_panel = FileListPanel("Gốc:", show_close_btn=True, show_search=True)
        self.goc_panel.file_selected.connect(self._on_goc_file_selected)
        self.goc_panel.close_requested.connect(self.close_requested.emit)
        self.goc_panel.search_changed.connect(self._on_search_changed)
        self.goc_panel.checkbox_changed.connect(self._on_goc_checkbox_changed)
        self.goc_panel.toggle_all_changed.connect(self._on_goc_toggle_all)
        self.splitter.addWidget(self.goc_panel)

        # Đích panel (no search)
        self.dich_panel = FileListPanel("Đích:", show_close_btn=False, show_search=False)
        self.dich_panel.file_selected.connect(self._on_dich_file_selected)
        self.dich_panel.checkbox_changed.connect(self._on_dich_checkbox_changed)
        self.dich_panel.toggle_all_changed.connect(self._on_dich_toggle_all)
        self.splitter.addWidget(self.dich_panel)
        
        # Equal sizes
        self.splitter.setSizes([500, 500])
        
        layout.addWidget(self.splitter)
    
    def set_folder(self, base_dir: str, output_dir: str, files: List[str],
                   filename_pattern: str = "{gốc}_clean.pdf"):
        """Set thư mục và danh sách file"""
        self._base_dir = base_dir
        self._output_dir = output_dir
        self._filename_pattern = filename_pattern
        self._files = files

        # Generate output files
        self._output_files = self._generate_output_files(files)

        # Update panels
        self.goc_panel.set_title(f"Gốc: {base_dir}")
        self.goc_panel.set_files(files, base_dir)

        self.dich_panel.set_title(f"Đích: {output_dir}")
        self.dich_panel.set_files(self._output_files, output_dir)
    
    def _generate_output_files(self, input_files: List[str]) -> List[str]:
        """Generate output file paths using filename pattern"""
        output_files = []
        for f in input_files:
            rel_path = os.path.relpath(f, self._base_dir)
            name, _ = os.path.splitext(rel_path)
            # Apply filename pattern
            output_name = self._filename_pattern.replace('{gốc}', name)
            output_path = os.path.join(self._output_dir, output_name)
            output_files.append(output_path)
        return output_files
    
    def _on_search_changed(self, text: str):
        """When search text changes, sync filter to Đích panel"""
        # Get visible indices from Gốc panel
        visible_indices = self.goc_panel.file_list.get_visible_indices()
        # Apply same filter to Đích panel
        self.dich_panel.apply_filter_indices(visible_indices)
    
    def _on_goc_file_selected(self, file_path: str, original_idx: int):
        """When file selected in Gốc panel"""
        if self._syncing:
            return
        
        self._syncing = True
        self.dich_panel.select_by_original_index(original_idx)
        self._syncing = False
        
        self.file_selected.emit(file_path)
    
    def _on_dich_file_selected(self, file_path: str, original_idx: int):
        """When file selected in Đích panel"""
        if self._syncing:
            return

        self._syncing = True
        self.goc_panel.select_by_original_index(original_idx)
        self._syncing = False

        # Emit corresponding source file
        if 0 <= original_idx < len(self._files):
            self.file_selected.emit(self._files[original_idx])

    def _on_goc_checkbox_changed(self, original_idx: int, is_checked: bool):
        """Sync checkbox from Gốc to Đích"""
        if self._syncing:
            return
        self._syncing = True
        self.dich_panel.set_item_checked(original_idx, is_checked)
        self._syncing = False

    def _on_dich_checkbox_changed(self, original_idx: int, is_checked: bool):
        """Sync checkbox from Đích to Gốc"""
        if self._syncing:
            return
        self._syncing = True
        self.goc_panel.set_item_checked(original_idx, is_checked)
        self._syncing = False

    def _on_goc_toggle_all(self, checked: bool):
        """Sync toggle all from Gốc to Đích"""
        if self._syncing:
            return
        self._syncing = True
        self.dich_panel.set_all_checked(checked)
        self._syncing = False

    def _on_dich_toggle_all(self, checked: bool):
        """Sync toggle all from Đích to Gốc"""
        if self._syncing:
            return
        self._syncing = True
        self.goc_panel.set_all_checked(checked)
        self._syncing = False
    
    def get_checked_files(self) -> List[str]:
        return self.goc_panel.get_checked_files()

    def get_base_dir(self) -> str:
        return self._base_dir

    def get_output_dir(self) -> str:
        return self._output_dir

    def update_output_settings(self, output_dir: str, filename_pattern: str):
        """Cập nhật output settings và regenerate danh sách file đích"""
        if not self._files:
            return

        # Cập nhật settings với validation
        self._output_dir = output_dir if output_dir else self._base_dir

        # Validate filename pattern - phải chứa {gốc} để tránh trùng tên
        if filename_pattern and '{gốc}' in filename_pattern:
            self._filename_pattern = filename_pattern
        else:
            self._filename_pattern = "{gốc}_clean.pdf"

        # Regenerate output files
        self._output_files = self._generate_output_files(self._files)

        # Update Đích panel
        self.dich_panel.set_title(f"Đích: {self._output_dir}")
        self.dich_panel.set_files(self._output_files, self._output_dir)
