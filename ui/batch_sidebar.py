"""
Batch Sidebar - Collapsible file list sidebar for batch mode
Shows source files with checkbox, filename, and page count
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QLineEdit, QCheckBox, QListWidget, QListWidgetItem,
    QAbstractItemView, QStyledItemDelegate, QStyle, QComboBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QRect, QTimer
from PyQt5.QtGui import QColor, QPainter, QFont

from concurrent.futures import ThreadPoolExecutor, as_completed


class ComboItemDelegate(QStyledItemDelegate):
    """Custom delegate for larger combobox items"""
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(24)  # Set item height to 24px
        return size

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
            count_text = str(page_count) if page_count >= 0 else "..."

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
    page_counts_updated = pyqtSignal()  # emitted when new page counts are loaded

    # Batch size for lazy loading page counts
    LAZY_LOAD_BATCH_SIZE = 10

    def __init__(self, parent=None):
        super().__init__(parent)

        self._files: List[str] = []
        self._base_dir: str = ""
        self._filter_text: str = ""
        self._filter_pages: int = -1  # -1 = all pages (no filter)
        self._visible_indices: List[int] = []
        self._page_counts: Dict[str, int] = {}
        self._sort_column: str = 'name'  # 'name' or 'pages'
        self._sort_asc: bool = True
        self._skip_row_change: bool = False  # Prevent double file_selected emit

        # Lazy loading state
        self._lazy_load_index: int = 0  # Next index to load in current filtered list
        self._lazy_load_timer: QTimer = QTimer()
        self._lazy_load_timer.setSingleShot(True)
        self._lazy_load_timer.timeout.connect(self._load_next_batch)
        self._filtered_files: List[str] = []  # Current filtered file list for lazy loading

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
        """Set file list with lazy page count loading.

        Files are displayed immediately with "..." as page count.
        Page counts are loaded in batches of LAZY_LOAD_BATCH_SIZE.
        """
        # Stop any pending lazy load
        self._lazy_load_timer.stop()

        self._files = files
        self._base_dir = base_dir
        self._filter_text = ""
        self._filter_pages = -1
        self._page_counts.clear()

        # Don't load page counts here - use lazy loading
        # Build filtered list (initially all files)
        self._filtered_files = list(files)
        self._lazy_load_index = 0

        self._rebuild_list()

        # Select first item
        if self.count() > 0:
            # Block currentRowChanged to avoid double emit
            self._skip_row_change = True
            self.setCurrentRow(0)
            first_item = self.item(0)
            if first_item:
                self.file_selected.emit(first_item.data(Qt.UserRole), 0)

        # Start lazy loading page counts
        self._start_lazy_load()

    def _start_lazy_load(self):
        """Start lazy loading page counts for filtered files"""
        self._lazy_load_index = 0
        # Start loading immediately
        self._lazy_load_timer.start(10)  # 10ms delay to allow UI to render

    def _load_next_batch(self):
        """Load page counts for next batch of files using ThreadPool"""
        if self._lazy_load_index >= len(self._filtered_files):
            return  # Done loading

        # Get batch of files to load
        end_index = min(self._lazy_load_index + self.LAZY_LOAD_BATCH_SIZE,
                        len(self._filtered_files))

        # Collect files that need page count loading
        files_to_load = []
        for i in range(self._lazy_load_index, end_index):
            file_path = self._filtered_files[i]
            if file_path not in self._page_counts:
                files_to_load.append(file_path)

        # Load page counts in parallel using ThreadPool
        if files_to_load:
            with ThreadPoolExecutor(max_workers=min(10, len(files_to_load))) as executor:
                futures = {executor.submit(self._get_page_count, fp): fp for fp in files_to_load}
                for future in as_completed(futures):
                    file_path = futures[future]
                    try:
                        self._page_counts[file_path] = future.result()
                    except Exception:
                        self._page_counts[file_path] = -1

        self._lazy_load_index = end_index

        # Update UI to show loaded page counts
        self.viewport().update()

        # Emit signal to update pages combo
        if files_to_load:
            self.page_counts_updated.emit()

        # Schedule next batch if more files to load
        if self._lazy_load_index < len(self._filtered_files):
            self._lazy_load_timer.start(5)  # 5ms between batches for responsive UI

    @staticmethod
    def _get_page_count(file_path: str) -> int:
        """Get PDF page count (thread-safe static method)"""
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

    def _rebuild_list(self, restart_lazy_load: bool = False):
        """Rebuild list with current filter and sort

        Args:
            restart_lazy_load: If True, restart lazy loading for new filtered list
        """
        self.blockSignals(True)
        self.clear()
        self._visible_indices = []

        # Build list of (idx, file_path) tuples for filtering
        filtered = []
        for idx, file_path in enumerate(self._files):
            # Filter by name
            if self._filter_text:
                if self._filter_text.lower() not in file_path.lower():
                    continue
            # Filter by pages (only apply if page count is loaded)
            if self._filter_pages > 0:
                page_count = self._page_counts.get(file_path, -1)
                # If page count not loaded yet, include in list (will be filtered later)
                if page_count >= 0 and page_count != self._filter_pages:
                    continue
            filtered.append((idx, file_path))

        # Sort
        if self._sort_column == 'name':
            filtered.sort(key=lambda x: os.path.basename(x[1]).lower(), reverse=not self._sort_asc)
        else:  # pages
            filtered.sort(key=lambda x: self._page_counts.get(x[1], -1), reverse=not self._sort_asc)

        # Update filtered files list for lazy loading
        self._filtered_files = [fp for _, fp in filtered]

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

        # Restart lazy loading if requested
        if restart_lazy_load:
            self._start_lazy_load()

    def set_filter(self, text: str):
        """Set filter text"""
        self._filter_text = text
        self._rebuild_list(restart_lazy_load=True)
        self.selection_changed.emit(self.get_checked_files())

    def set_page_filter(self, pages: int):
        """Set page count filter. -1 = all."""
        self._filter_pages = pages
        self._rebuild_list(restart_lazy_load=True)
        self.selection_changed.emit(self.get_checked_files())

    def get_unique_page_counts(self) -> List[int]:
        """Get sorted unique page counts for combobox."""
        counts = set(self._page_counts.values())
        counts.discard(-1)  # Remove error values
        return sorted(counts)

    def get_visible_count(self) -> int:
        """Get count of visible (filtered) items."""
        return len(self._visible_indices)

    def _on_item_clicked(self, item: QListWidgetItem):
        """Handle item click"""
        # Set flag to prevent currentRowChanged from also emitting
        self._skip_row_change = True
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
        """Handle keyboard navigation (up/down arrows)

        Note: Mouse clicks trigger BOTH itemClicked AND currentRowChanged.
        We use a flag to prevent double file loading.
        """
        # Skip if this was triggered by a mouse click (already handled by itemClicked)
        if getattr(self, '_skip_row_change', False):
            self._skip_row_change = False
            return

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
        """Select row by original file index (without emitting file_selected)"""
        # Block signal to avoid double file loading
        self._skip_row_change = True
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

        # Title bar with hamburger, title and count (aligns with Preview Gốc title bar)
        self._title_bar = QWidget()
        self._title_bar.setFixedHeight(32)  # Match Preview Gốc title bar height
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
        list_layout.setContentsMargins(4, 0, 4, 4)  # No top margin for alignment
        list_layout.setSpacing(0)  # No spacing between header and line for alignment

        # Header row (chiều cao bằng thumbnail header)
        header = QWidget()
        header.setFixedHeight(28)
        header.setStyleSheet("background-color: #F3F4F6;")
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

        # Line xám 1px (thẳng hàng với line dưới "Trang thu nhỏ")
        header_line = QWidget()
        header_line.setFixedHeight(1)
        header_line.setStyleSheet("background-color: #E5E7EB;")
        list_layout.addWidget(header_line)

        # Spacer 4px between header_line and filter_row
        list_layout.addSpacing(4)

        # Filter row (full width, aligned with table edges)
        filter_row = QWidget()
        filter_row.setFixedHeight(32)
        filter_row.setStyleSheet("background-color: #F9FAFB;")
        filter_layout = QHBoxLayout(filter_row)
        filter_layout.setContentsMargins(0, 4, 0, 4)  # No left/right margin for alignment
        filter_layout.setSpacing(4)

        # Name filter (full width to left edge)
        self._name_filter = QLineEdit()
        self._name_filter.setPlaceholderText("🔍 Lọc tên file...")
        self._name_filter.setStyleSheet("""
            QLineEdit {
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 3px 6px;
                font-size: 12px;
                background: white;
            }
            QLineEdit:focus {
                border-color: #3B82F6;
            }
        """)
        self._name_filter.textChanged.connect(self._on_name_filter_changed)
        filter_layout.addWidget(self._name_filter, 1)

        self._name_clear_btn = QPushButton("✕")
        self._name_clear_btn.setFixedSize(18, 18)
        self._name_clear_btn.setStyleSheet("""
            QPushButton {
                background: #E5E7EB;
                border: none;
                border-radius: 9px;
                color: #6B7280;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #FEE2E2;
                color: #EF4444;
            }
        """)
        self._name_clear_btn.clicked.connect(self._clear_name_filter)
        self._name_clear_btn.setVisible(False)
        filter_layout.addWidget(self._name_clear_btn)

        # Pages filter (like zoom combo - minimal styling to keep default icon)
        self._pages_combo = QComboBox()
        self._pages_combo.addItem("All")
        self._pages_combo.setFixedWidth(58)
        self._pages_combo.setFixedHeight(24)
        self._pages_combo.setToolTip("Lọc theo số trang")
        self._pages_combo.view().setStyleSheet("""
            QListView {
                background-color: white;
                font-size: 10px;
            }
            QListView::item {
                padding: 4px 6px;
            }
            QListView::item:hover {
                background-color: #93C5FD;
            }
            QListView::item:selected {
                background-color: #93C5FD;
            }
        """)
        self._pages_combo.currentTextChanged.connect(self._on_pages_filter_changed)
        self._pages_combo.currentIndexChanged.connect(self._update_pages_combo_style)
        filter_layout.addWidget(self._pages_combo)
        self._update_pages_combo_style(0)  # Initial style for "All"

        self._pages_clear_btn = QPushButton("✕")
        self._pages_clear_btn.setFixedSize(18, 18)
        self._pages_clear_btn.setStyleSheet("""
            QPushButton {
                background: #E5E7EB;
                border: none;
                border-radius: 9px;
                color: #6B7280;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #FEE2E2;
                color: #EF4444;
            }
        """)
        self._pages_clear_btn.clicked.connect(self._clear_pages_filter)
        self._pages_clear_btn.setVisible(False)
        filter_layout.addWidget(self._pages_clear_btn)

        list_layout.addWidget(filter_row)

        # File list
        self._file_list = SidebarFileList()
        self._file_list.file_selected.connect(self._on_file_selected)
        self._file_list.selection_changed.connect(self._on_selection_changed)
        self._file_list.page_counts_updated.connect(self._on_page_counts_updated)
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
        self._update_sort_labels_with_filter()

    def _on_name_filter_changed(self, text: str):
        """Handle name filter text change"""
        self._file_list.set_filter(text)
        self._name_clear_btn.setVisible(bool(text))
        self._update_count()
        self._update_toggle_state()
        self._update_sort_labels_with_filter()

    def _on_pages_filter_changed(self, text: str):
        """Handle pages filter change"""
        if text == "All" or not text:
            self._file_list.set_page_filter(-1)
            self._pages_clear_btn.setVisible(False)
        else:
            try:
                pages = int(text)
                self._file_list.set_page_filter(pages)
                self._pages_clear_btn.setVisible(True)
            except ValueError:
                # Invalid input, reset to all
                self._file_list.set_page_filter(-1)
                self._pages_clear_btn.setVisible(False)
        self._update_count()
        self._update_toggle_state()
        self._update_sort_labels_with_filter()

    def _update_pages_combo_style(self, index: int):
        """Update combobox text color based on selection (All = gray, others = normal)"""
        color = "#9CA3AF" if index == 0 else "#374151"
        # Minimal styling to keep native dropdown icon
        self._pages_combo.setStyleSheet(f"QComboBox {{ color: {color}; font-size: 11px; }}")

    def _clear_name_filter(self):
        """Clear name filter"""
        self._name_filter.clear()

    def _clear_pages_filter(self):
        """Clear pages filter"""
        self._pages_combo.setCurrentIndex(0)  # Back to "All"

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

    def _on_page_counts_updated(self):
        """Handle page counts updated from lazy loading"""
        self._update_pages_combo()

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

        # Check if filter is active
        is_filtered = self._name_filter.text() or (self._pages_combo.currentText() and self._pages_combo.currentText() != "All")
        visible = self._file_list.get_visible_count()
        count_suffix = f" ({visible})" if is_filtered else ""

        if column == 'name':
            self._name_btn.setText(f"Tên file {arrow}{count_suffix}")
            self._pages_btn.setText("Trang")
        else:
            self._name_btn.setText(f"Tên file{count_suffix}")
            self._pages_btn.setText(f"Trang {arrow}")

    def _update_sort_labels_with_filter(self):
        """Update sort labels with current filter count"""
        column, ascending = self._file_list.get_sort_info()
        self._update_sort_labels(column, ascending)

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

    def _update_pages_combo(self):
        """Update pages combo with current unique page counts"""
        current_text = self._pages_combo.currentText()
        self._pages_combo.blockSignals(True)
        self._pages_combo.clear()
        self._pages_combo.addItem("All")
        for page_count in self._file_list.get_unique_page_counts():
            self._pages_combo.addItem(str(page_count))

        # Restore previous selection if still valid
        index = self._pages_combo.findText(current_text)
        if index >= 0:
            self._pages_combo.setCurrentIndex(index)
        else:
            self._pages_combo.setCurrentIndex(0)

        self._pages_combo.blockSignals(False)
        self._update_pages_combo_style(self._pages_combo.currentIndex())

    # Public API

    def set_files(self, files: List[str], base_dir: str):
        """Set file list"""
        self._base_dir = base_dir
        self._file_list.set_files(files, base_dir)

        # Reset filters
        self._name_filter.clear()
        self._pages_combo.blockSignals(True)
        self._pages_combo.clear()
        self._pages_combo.addItem("All")
        # Page counts will be populated dynamically via _on_page_counts_updated
        self._pages_combo.setCurrentIndex(0)  # Select "All"
        self._pages_combo.blockSignals(False)
        self._update_pages_combo_style(0)  # Apply gray style for "All"
        self._name_clear_btn.setVisible(False)
        self._pages_clear_btn.setVisible(False)

        self._update_count()
        self._update_toggle_state()
        self._update_sort_labels_with_filter()

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
