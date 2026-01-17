"""
Batch Sidebar - Collapsible file list sidebar for batch mode
Shows source files with checkbox, filename, and page count
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QLineEdit, QCheckBox, QListWidget, QListWidgetItem,
    QAbstractItemView, QStyledItemDelegate, QStyle
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QRect
from PyQt5.QtGui import QColor, QPainter, QFont

import os
import fitz  # PyMuPDF for page count
from typing import List, Optional, Dict


class FileItemDelegate(QStyledItemDelegate):
    """Custom delegate to display: checkbox | filename | page count"""

    PAGE_COUNT_WIDTH = 40

    def __init__(self, page_counts: Dict[str, int], parent=None):
        super().__init__(parent)
        self._page_counts = page_counts

    def paint(self, painter: QPainter, option, index):
        # Draw default (checkbox + text)
        super().paint(painter, option, index)

        # Draw page count on the right
        file_path = index.data(Qt.UserRole)
        if file_path:
            page_count = self._page_counts.get(file_path, -1)
            count_text = str(page_count) if page_count >= 0 else "?"

            painter.save()

            # Page count rect on right side with margin
            right_margin = 8
            count_rect = QRect(
                option.rect.right() - self.PAGE_COUNT_WIDTH - right_margin,
                option.rect.top(),
                self.PAGE_COUNT_WIDTH,
                option.rect.height()
            )

            # Draw count text (same font size as filename: 12px)
            painter.setPen(QColor("#6B7280"))
            font = painter.font()
            font.setPixelSize(12)
            painter.setFont(font)
            painter.drawText(count_rect, Qt.AlignRight | Qt.AlignVCenter, count_text)

            painter.restore()


class SidebarFileList(QListWidget):
    """File list widget with page count display"""

    file_selected = pyqtSignal(str, int)  # (file_path, original_index)
    selection_changed = pyqtSignal(list)  # list of checked files
    checkbox_changed = pyqtSignal(int, bool)  # (original_index, is_checked)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._files: List[str] = []
        self._base_dir: str = ""
        self._filter_text: str = ""
        self._visible_indices: List[int] = []
        self._page_counts: Dict[str, int] = {}
        self._sort_column: str = 'name'  # 'name' or 'pages'
        self._sort_asc: bool = True

        # Custom delegate for page count display
        self._delegate = FileItemDelegate(self._page_counts, self)
        self.setItemDelegate(self._delegate)

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

        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.itemClicked.connect(self._on_item_clicked)
        self.itemChanged.connect(self._on_item_changed)
        # Keyboard navigation (up/down arrows)
        self.currentRowChanged.connect(self._on_current_row_changed)

    def set_files(self, files: List[str], base_dir: str):
        """Set file list and load page counts"""
        self._files = files
        self._base_dir = base_dir
        self._filter_text = ""
        self._page_counts.clear()

        # Load page counts
        for file_path in files:
            self._page_counts[file_path] = self._get_page_count(file_path)

        self._rebuild_list()

        # Select first item
        if self.count() > 0:
            self.setCurrentRow(0)
            first_item = self.item(0)
            if first_item:
                self.file_selected.emit(first_item.data(Qt.UserRole), 0)

    def _get_page_count(self, file_path: str) -> int:
        """Get PDF page count quickly"""
        try:
            doc = fitz.open(file_path)
            count = doc.page_count
            doc.close()
            return count
        except Exception:
            return -1

    def set_sort(self, column: str, ascending: bool):
        """Set sort column and order, then rebuild"""
        self._sort_column = column
        self._sort_asc = ascending
        self._rebuild_list()

    def get_sort_info(self) -> tuple:
        """Get current sort info"""
        return (self._sort_column, self._sort_asc)

    def _rebuild_list(self):
        """Rebuild list with current filter and sort"""
        self.blockSignals(True)
        self.clear()
        self._visible_indices = []

        # Build list of (idx, file_path) tuples for filtering
        filtered = []
        for idx, file_path in enumerate(self._files):
            if self._filter_text:
                if self._filter_text.lower() not in file_path.lower():
                    continue
            filtered.append((idx, file_path))

        # Sort
        if self._sort_column == 'name':
            filtered.sort(key=lambda x: os.path.basename(x[1]).lower(), reverse=not self._sort_asc)
        else:  # pages
            filtered.sort(key=lambda x: self._page_counts.get(x[1], -1), reverse=not self._sort_asc)

        # Add items in sorted order
        for idx, file_path in filtered:
            filename = os.path.basename(file_path)

            item = QListWidgetItem(filename)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, file_path)
            item.setData(Qt.UserRole + 1, idx)
            self.addItem(item)
            self._visible_indices.append(idx)

        self.blockSignals(False)

    def set_filter(self, text: str):
        """Set filter text"""
        self._filter_text = text
        self._rebuild_list()
        self.selection_changed.emit(self.get_checked_files())

    def _on_item_clicked(self, item: QListWidgetItem):
        """Handle item click"""
        file_path = item.data(Qt.UserRole)
        original_idx = item.data(Qt.UserRole + 1)
        if file_path:
            self.file_selected.emit(file_path, original_idx)

    def _on_item_changed(self, item: QListWidgetItem):
        """Handle checkbox change"""
        original_idx = item.data(Qt.UserRole + 1)
        is_checked = item.checkState() == Qt.Checked
        self.checkbox_changed.emit(original_idx, is_checked)
        self.selection_changed.emit(self.get_checked_files())

    def _on_current_row_changed(self, row: int):
        """Handle keyboard navigation (up/down arrows)"""
        if row >= 0:
            item = self.item(row)
            if item:
                file_path = item.data(Qt.UserRole)
                original_idx = item.data(Qt.UserRole + 1)
                if file_path:
                    self.file_selected.emit(file_path, original_idx)

    def get_checked_files(self) -> List[str]:
        """Get list of checked files"""
        checked = []
        for i in range(self.count()):
            item = self.item(i)
            if item.checkState() == Qt.Checked:
                checked.append(item.data(Qt.UserRole))
        return checked

    def get_file_count(self) -> tuple:
        """Return (checked_count, total_count)"""
        checked = len(self.get_checked_files())
        total = len(self._files)
        return (checked, total)

    def get_page_counts(self) -> Dict[str, int]:
        """Return dict of {file_path: page_count}"""
        return self._page_counts.copy()

    def check_all(self):
        """Check all visible items"""
        self.blockSignals(True)
        for i in range(self.count()):
            self.item(i).setCheckState(Qt.Checked)
        self.blockSignals(False)
        self.selection_changed.emit(self.get_checked_files())

    def uncheck_all(self):
        """Uncheck all visible items"""
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

    def select_by_original_index(self, original_idx: int):
        """Select row by original file index"""
        for i in range(self.count()):
            item = self.item(i)
            if item.data(Qt.UserRole + 1) == original_idx:
                self.setCurrentRow(i)
                return


class BatchSidebar(QFrame):
    """
    Collapsible sidebar for batch mode file list

    Features:
    - Toggle collapse/expand with icon button
    - Search box for filtering
    - File list with checkbox, filename, page count
    - Toggle all checkbox
    """

    EXPANDED_WIDTH = 200
    MIN_WIDTH = 100  # Minimum width when expanded (prevents hiding hamburger)
    COLLAPSED_WIDTH = 30  # Matches nav button size (22px) + padding

    file_selected = pyqtSignal(str, int)  # (file_path, original_index)
    selection_changed = pyqtSignal(list)  # list of checked files
    close_requested = pyqtSignal()
    collapsed_changed = pyqtSignal(bool)  # emitted when collapsed state changes

    def __init__(self, parent=None):
        super().__init__(parent)

        self._collapsed = False
        self._base_dir = ""

        self._setup_ui()
        self._load_collapsed_state()

    def _setup_ui(self):
        """Setup UI components"""
        self.setFrameStyle(QFrame.NoFrame)
        self.setMinimumWidth(self.COLLAPSED_WIDTH)

        # Main layout
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # Content widget (hidden when collapsed)
        self._content = QWidget()
        self._content.setStyleSheet("background-color: #F3F4F6;")
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Title bar with hamburger, title and count (aligns with Gốc/Đích titles)
        self._title_bar = QWidget()
        self._title_bar.setFixedHeight(32)  # Match preview panel title bar height
        self._title_bar.setStyleSheet("background-color: #F3F4F6; border-bottom: 1px solid #D1D5DB;")
        title_layout = QHBoxLayout(self._title_bar)
        title_layout.setContentsMargins(4, 0, 4, 0)
        title_layout.setSpacing(4)

        # Toggle button (hamburger icon) with title
        self._toggle_btn = QPushButton("☰")
        self._toggle_btn.setFixedSize(22, 22)
        self._toggle_btn.setToolTip("Thu gọn danh sách")
        self._toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                font-size: 12px;
                color: #6B7280;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
                border-radius: 4px;
            }
        """)
        self._toggle_btn.clicked.connect(self._toggle_collapsed)
        title_layout.addWidget(self._toggle_btn)

        # Title label
        self._title_label = QLabel("Danh sách")
        self._title_label.setStyleSheet("font-size: 13px; color: #374151;")
        title_layout.addWidget(self._title_label)

        # Count label
        self._count_label = QLabel("(0/0)")
        self._count_label.setStyleSheet("font-size: 12px; color: #6B7280;")
        title_layout.addWidget(self._count_label)

        title_layout.addStretch()

        content_layout.addWidget(self._title_bar)

        # List container (same background as title bar)
        self._list_container = QWidget()
        self._list_container.setStyleSheet("background-color: #F3F4F6;")
        list_layout = QVBoxLayout(self._list_container)
        list_layout.setContentsMargins(4, 4, 4, 4)
        list_layout.setSpacing(4)

        # Header row
        header = QWidget()
        header.setFixedHeight(24)
        header.setStyleSheet("background-color: white;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 0, 8, 0)
        header_layout.setSpacing(4)

        # Header checkbox (toggle all)
        self._header_checkbox = QCheckBox()
        self._header_checkbox.setChecked(True)
        self._header_checkbox.setToolTip("Chọn/bỏ chọn tất cả")
        self._header_checkbox.clicked.connect(self._on_header_checkbox_clicked)
        header_layout.addWidget(self._header_checkbox)

        # Filename header (clickable for sort)
        self._name_btn = QPushButton("Tên file ↑")
        self._name_btn.setFlat(True)
        self._name_btn.setCursor(Qt.PointingHandCursor)
        self._name_btn.setStyleSheet("""
            QPushButton { text-align: left; font-size: 12px; color: #374151; border: none; padding: 0; }
            QPushButton:hover { color: #1D4ED8; }
        """)
        self._name_btn.clicked.connect(lambda: self._on_sort_clicked('name'))
        header_layout.addWidget(self._name_btn, 1)

        # Page count header (clickable for sort)
        self._pages_btn = QPushButton("Trang")
        self._pages_btn.setFlat(True)
        self._pages_btn.setCursor(Qt.PointingHandCursor)
        self._pages_btn.setFixedWidth(50)
        self._pages_btn.setStyleSheet("""
            QPushButton { text-align: right; font-size: 12px; color: #374151; border: none; padding: 0; }
            QPushButton:hover { color: #1D4ED8; }
        """)
        self._pages_btn.clicked.connect(lambda: self._on_sort_clicked('pages'))
        header_layout.addWidget(self._pages_btn)

        list_layout.addWidget(header)

        # File list
        self._file_list = SidebarFileList()
        self._file_list.file_selected.connect(self._on_file_selected)
        self._file_list.selection_changed.connect(self._on_selection_changed)
        list_layout.addWidget(self._file_list)

        content_layout.addWidget(self._list_container)

        self._main_layout.addWidget(self._content)

        # Collapsed widget (shown when collapsed - fills sidebar)
        self._collapsed_widget = QWidget()
        self._collapsed_widget.setStyleSheet("background-color: #F3F4F6;")
        collapsed_layout = QVBoxLayout(self._collapsed_widget)
        collapsed_layout.setContentsMargins(4, 4, 4, 4)
        collapsed_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        # Expand button (hamburger icon) - same size as nav buttons
        self._expand_btn = QPushButton("☰")
        self._expand_btn.setFixedSize(22, 22)
        self._expand_btn.setToolTip("Mở rộng danh sách")
        self._expand_btn.setStyleSheet("""
            QPushButton {
                background-color: #D1D5DB;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                color: #374151;
            }
            QPushButton:hover {
                background-color: #9CA3AF;
            }
        """)
        self._expand_btn.clicked.connect(self._toggle_collapsed)
        collapsed_layout.addWidget(self._expand_btn)

        self._collapsed_widget.setVisible(False)
        self._main_layout.addWidget(self._collapsed_widget)

    def _load_collapsed_state(self):
        """Load collapsed state from config"""
        try:
            from core.config_manager import get_config_manager
            config = get_config_manager()
            self._collapsed = config.get("sidebar_collapsed", False)
            self._apply_collapsed_state()
        except Exception:
            pass

    def _save_collapsed_state(self):
        """Save collapsed state to config"""
        try:
            from core.config_manager import get_config_manager
            config = get_config_manager()
            config.set("sidebar_collapsed", self._collapsed)
        except Exception:
            pass

    def _toggle_collapsed(self):
        """Toggle collapsed state"""
        self._collapsed = not self._collapsed
        self._apply_collapsed_state()
        self._save_collapsed_state()
        self.collapsed_changed.emit(self._collapsed)

    def _apply_collapsed_state(self):
        """Apply current collapsed state to UI"""
        if self._collapsed:
            # First set the fixed width to prevent splitter from shrinking further
            self.setMinimumWidth(self.COLLAPSED_WIDTH)
            self.setMaximumWidth(self.COLLAPSED_WIDTH)
            # Then update visibility
            self._content.setVisible(False)
            self._collapsed_widget.setVisible(True)
        else:
            # First reset size constraints
            self.setMinimumWidth(self.MIN_WIDTH)
            self.setMaximumWidth(16777215)  # Reset max width
            # Then update visibility
            self._collapsed_widget.setVisible(False)
            self._content.setVisible(True)
            self.resize(self.EXPANDED_WIDTH, self.height())

    def set_search_filter(self, text: str):
        """Filter file list by search text (called from compact toolbar)"""
        self._file_list.set_filter(text)
        self._update_count()
        self._update_toggle_state()

    def _on_header_checkbox_clicked(self):
        """Toggle all files (from header checkbox)"""
        if self._file_list.is_all_checked():
            self._file_list.uncheck_all()
        else:
            self._file_list.check_all()
        self._update_count()
        self._update_toggle_state()

    def _on_file_selected(self, file_path: str, original_idx: int):
        """Forward file selection signal"""
        self.file_selected.emit(file_path, original_idx)

    def _on_selection_changed(self, checked_files: List[str]):
        """Handle selection change"""
        self._update_count()
        self._update_toggle_state()
        self.selection_changed.emit(checked_files)

    def _on_sort_clicked(self, column: str):
        """Handle sort header click"""
        current_col, current_asc = self._file_list.get_sort_info()

        if current_col == column:
            # Toggle direction
            new_asc = not current_asc
        else:
            # New column, default ascending
            new_asc = True

        self._file_list.set_sort(column, new_asc)
        self._update_sort_labels(column, new_asc)

    def _update_sort_labels(self, column: str, ascending: bool):
        """Update header button labels with sort indicator"""
        arrow = "↑" if ascending else "↓"
        if column == 'name':
            self._name_btn.setText(f"Tên file {arrow}")
            self._pages_btn.setText("Trang")
        else:
            self._name_btn.setText("Tên file")
            self._pages_btn.setText(f"Trang {arrow}")

    def _update_count(self):
        """Update file count label"""
        checked, total = self._file_list.get_file_count()
        self._count_label.setText(f"({checked}/{total})")

    def _update_toggle_state(self):
        """Update header checkbox state"""
        all_checked = self._file_list.is_all_checked()
        all_unchecked = self._file_list.is_all_unchecked()

        self._header_checkbox.blockSignals(True)
        if all_checked:
            self._header_checkbox.setChecked(True)
        elif all_unchecked:
            self._header_checkbox.setChecked(False)
        else:
            self._header_checkbox.setChecked(True)
        self._header_checkbox.blockSignals(False)

    # Public API

    def set_files(self, files: List[str], base_dir: str):
        """Set file list"""
        self._base_dir = base_dir
        self._file_list.set_files(files, base_dir)
        self._update_count()
        self._update_toggle_state()

    def get_checked_files(self) -> List[str]:
        """Get list of checked files"""
        return self._file_list.get_checked_files()

    def get_file_count(self) -> tuple:
        """Return (checked_count, total_count)"""
        return self._file_list.get_file_count()

    def get_page_counts(self) -> Dict[str, int]:
        """Return dict of {file_path: page_count}"""
        return self._file_list.get_page_counts()

    def select_by_original_index(self, original_idx: int):
        """Select file by original index"""
        self._file_list.select_by_original_index(original_idx)

    def resizeEvent(self, event):
        """Auto-collapse when dragged too small"""
        super().resizeEvent(event)
        # If not collapsed and width goes below threshold, auto-collapse
        # Defer to avoid race condition with splitter drag
        if not self._collapsed and not getattr(self, '_auto_collapsing', False) and event.size().width() < self.MIN_WIDTH:
            self._auto_collapsing = True
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, self._do_auto_collapse)

    def _do_auto_collapse(self):
        """Execute auto-collapse after resize event completes"""
        if not self._collapsed:
            self._collapsed = True
            self._apply_collapsed_state()
            self._save_collapsed_state()
            self.collapsed_changed.emit(True)
        self._auto_collapsing = False

    def is_collapsed(self) -> bool:
        """Return collapsed state"""
        return self._collapsed

    def set_collapsed(self, collapsed: bool):
        """Set collapsed state"""
        if self._collapsed != collapsed:
            self._collapsed = collapsed
            self._apply_collapsed_state()
            self._save_collapsed_state()
