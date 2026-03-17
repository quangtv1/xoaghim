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
from typing import List, Optional, Dict, Set, Tuple


def _parse_page_ranges(text: str) -> Optional[Set[int]]:
    """Parse "1-5, 7, 10-15" → {1,2,3,4,5,7,10,11,12,13,14,15}. Returns None if empty/all."""
    if not text or text.strip().lower() in ('', 'all'):
        return None
    result: Set[int] = set()
    try:
        for part in [p.strip() for p in text.split(',') if p.strip()]:
            if '-' in part:
                a, b = part.split('-', 1)
                lo, hi = int(a), int(b)
                if lo > hi:
                    lo, hi = hi, lo  # guard reverse ranges
                result.update(range(lo, hi + 1))
            else:
                result.add(int(part))
    except ValueError:
        return None  # Invalid input → no range filter
    return result if result else None


class FileItemDelegate(QStyledItemDelegate):
    """Custom delegate to display: checkbox | filename | page count"""

    PAGE_COUNT_WIDTH = 40

    def __init__(self, page_counts: Dict[str, int], active_pages: Dict[str, Set[int]], parent=None):
        super().__init__(parent)
        self._page_counts = page_counts
        self._active_pages = active_pages  # shared dict reference
        self._filter_active_fn = lambda: False

    def set_filter_ref(self, fn):
        """Store callable that returns True when advanced filter is active"""
        self._filter_active_fn = fn

    def paint(self, painter: QPainter, option, index):
        # Draw default (checkbox + text)
        super().paint(painter, option, index)

        # Draw page count on the right
        file_path = index.data(Qt.UserRole)
        if file_path:
            total = self._page_counts.get(file_path, -1)
            if self._filter_active_fn() and file_path in self._active_pages:
                active_count = len(self._active_pages[file_path])
                count_text = f"{active_count}/{total}" if total >= 0 else "..."
            else:
                count_text = str(total) if total >= 0 else "..."

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
    filter_changed = pyqtSignal()  # emitted when filter changes (for preload cancel)
    metadata_filter_updated = pyqtSignal()  # emitted when metadata loaded changes active page filter

    # Batch size for lazy loading page counts
    LAZY_LOAD_BATCH_SIZE = 10

    def __init__(self, parent=None):
        super().__init__(parent)

        self._files: List[str] = []
        self._base_dir: str = ""
        self._filter_text: str = ""
        self._filter_pages: str = ""  # Empty or "All" = no filter, supports: "5", ">5", "<10", ">=3", "<=20", "5-10"
        self._visible_indices: List[int] = []
        self._page_counts: Dict[str, int] = {}
        self._sort_column: str = 'name'  # 'name' or 'pages'
        self._sort_asc: bool = True
        self._skip_row_change: bool = False  # Prevent double file_selected emit

        # Advanced filter state
        self._page_metadata: Dict[str, List[Tuple[str, bool]]] = {}
        # file_path → [(size_cat, is_landscape), ...]
        self._active_pages: Dict[str, Set[int]] = {}
        # file_path → {0-indexed active page indices}
        self._applied_sizes: Set[str] = set()          # empty = no filter
        self._applied_orientations: Set[str] = set()   # empty = no filter
        self._applied_range: Optional[Set[int]] = None  # None = all pages

        # Lazy loading state
        self._lazy_load_index: int = 0  # Next index to load in current filtered list
        self._lazy_load_timer: QTimer = QTimer()
        self._lazy_load_timer.setSingleShot(True)
        self._lazy_load_timer.timeout.connect(self._load_next_batch)
        self._filtered_files: List[str] = []  # Current filtered file list for lazy loading

        # Custom delegate for page count display
        self._delegate = FileItemDelegate(self._page_counts, self._active_pages, self)
        self._delegate.set_filter_ref(self._is_advanced_filter_active)
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
            QListWidget::indicator {
                width: 14px;
                height: 14px;
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
        self._filter_pages = ""
        self._page_counts.clear()
        self._page_metadata.clear()
        self._active_pages.clear()

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
        else:
            # Lazy loading complete - rebuild list if page filter is active
            # This removes files whose actual page count doesn't match the filter
            if self._filter_pages and self._filter_pages.lower() != 'all':
                self._rebuild_list(restart_lazy_load=False)
                self.filter_changed.emit()

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
        self.filter_changed.emit()

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
            # Filter by pages using expression (supports: 5, >5, <10, >=3, <=20, 5-10)
            if self._filter_pages and self._filter_pages.lower() != 'all':
                page_count = self._page_counts.get(file_path, -1)
                if not self._matches_page_filter(page_count):
                    continue
            # Advanced filter: file must have ≥1 active page
            if self._is_advanced_filter_active():
                # Optimistic: metadata not loaded yet → include file
                if file_path in self._page_metadata:
                    active = self._active_pages.get(file_path, set())
                    if len(active) == 0:
                        continue  # No active pages → hide file
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
        self.filter_changed.emit()

    def set_page_filter(self, filter_expr: str):
        """Set page count filter expression.

        Supported formats:
        - "" or "All": no filter (show all)
        - "5": exact match (5 pages)
        - ">5": more than 5 pages
        - "<10": less than 10 pages
        - ">=3": 3 or more pages
        - "<=20": 20 or fewer pages
        - "5-10": between 5 and 10 pages (inclusive)
        """
        self._filter_pages = filter_expr.strip() if filter_expr else ""
        self._rebuild_list(restart_lazy_load=True)
        self.selection_changed.emit(self.get_checked_files())
        self.filter_changed.emit()

    def _matches_page_filter(self, page_count: int) -> bool:
        """Check if page count matches filter expression."""
        if page_count < 0:
            return True  # Page count not loaded yet, include in list

        if not self._filter_pages or self._filter_pages.lower() == 'all':
            return True

        filter_str = self._filter_pages.strip()

        try:
            # Range: "5-10"
            if '-' in filter_str and not filter_str.startswith('-'):
                parts = filter_str.split('-')
                if len(parts) == 2:
                    min_val = int(parts[0])
                    max_val = int(parts[1])
                    return min_val <= page_count <= max_val

            # Operators: >=, <=, >, <
            if filter_str.startswith(">="):
                return page_count >= int(filter_str[2:])
            elif filter_str.startswith("<="):
                return page_count <= int(filter_str[2:])
            elif filter_str.startswith(">"):
                return page_count > int(filter_str[1:])
            elif filter_str.startswith("<"):
                return page_count < int(filter_str[1:])
            else:
                # Exact match
                return page_count == int(filter_str)
        except ValueError:
            return True  # Invalid filter = show all

    def get_unique_page_counts(self) -> List[int]:
        """Get sorted unique page counts for combobox."""
        counts = set(self._page_counts.values())
        counts.discard(-1)  # Remove error values
        return sorted(counts)

    def get_page_count(self, file_path: str) -> int:
        """Get page count for a specific file. Returns -1 if not loaded yet."""
        return self._page_counts.get(file_path, -1)

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

    def get_visible_position(self, original_idx: int) -> int:
        """Get the visible row position for an original index. Returns -1 if not visible."""
        for i in range(self.count()):
            item = self.item(i)
            if item.data(Qt.UserRole + 1) == original_idx:
                return i
        return -1

    def get_prev_file_info(self, original_idx: int) -> tuple:
        """Get (file_path, original_idx) of previous file in visible order.
        Returns (None, -1) if no previous file."""
        visible_pos = self.get_visible_position(original_idx)
        if visible_pos > 0:
            item = self.item(visible_pos - 1)
            return (item.data(Qt.UserRole), item.data(Qt.UserRole + 1))
        return (None, -1)

    def get_next_file_info(self, original_idx: int) -> tuple:
        """Get (file_path, original_idx) of next file in visible order.
        Returns (None, -1) if no next file."""
        visible_pos = self.get_visible_position(original_idx)
        if visible_pos >= 0 and visible_pos < self.count() - 1:
            item = self.item(visible_pos + 1)
            return (item.data(Qt.UserRole), item.data(Qt.UserRole + 1))
        return (None, -1)

    def has_prev_file(self, original_idx: int) -> bool:
        """Check if there's a previous file in visible order."""
        return self.get_visible_position(original_idx) > 0

    def has_next_file(self, original_idx: int) -> bool:
        """Check if there's a next file in visible order."""
        visible_pos = self.get_visible_position(original_idx)
        return visible_pos >= 0 and visible_pos < self.count() - 1

    # ── Advanced filter methods ──

    def _is_advanced_filter_active(self) -> bool:
        """True if any advanced filter is set"""
        return (bool(self._applied_sizes) or bool(self._applied_orientations)
                or (self._applied_range is not None))

    def _compute_active_pages(self, file_path: str) -> Set[int]:
        """Compute 0-indexed active pages for file based on applied filter"""
        meta = self._page_metadata.get(file_path, [])
        active: Set[int] = set()
        for i, (size_cat, is_landscape) in enumerate(meta):
            page_num = i + 1  # 1-indexed for range comparison
            if self._applied_sizes and size_cat not in self._applied_sizes:
                continue
            if self._applied_orientations:
                orient = "landscape" if is_landscape else "portrait"
                if orient not in self._applied_orientations:
                    continue
            if self._applied_range is not None and page_num not in self._applied_range:
                continue
            active.add(i)
        return active

    def get_active_pages(self, file_path: str) -> Optional[Set[int]]:
        """Return active page indices (0-based) for file, or None if no filter active.
        None = all pages active (backward compatible with processor)."""
        if not self._is_advanced_filter_active():
            return None
        # Metadata not yet loaded: return empty set so filter is visually applied
        # (pages will appear once metadata arrives and on_metadata_loaded fires)
        if file_path not in self._page_metadata:
            return set()
        return self._active_pages.get(file_path, set())

    def apply_advanced_filter(self, sizes: set, orientations: set, range_text: str):
        """Apply advanced filter and rebuild sidebar"""
        self._applied_sizes = sizes
        self._applied_orientations = orientations
        self._applied_range = _parse_page_ranges(range_text)

        # Recompute active pages for all files that have metadata
        self._active_pages.clear()
        for fp in self._files:
            if fp in self._page_metadata:
                self._active_pages[fp] = self._compute_active_pages(fp)

        self._rebuild_list(restart_lazy_load=False)
        self.selection_changed.emit(self.get_checked_files())
        self.filter_changed.emit()
        self.viewport().update()

    def reset_advanced_filter(self):
        """Clear advanced filter — show all files"""
        self._applied_sizes = set()
        self._applied_orientations = set()
        self._applied_range = None
        self._active_pages.clear()
        self._rebuild_list(restart_lazy_load=False)
        self.selection_changed.emit(self.get_checked_files())
        self.filter_changed.emit()
        self.viewport().update()

    def on_metadata_loaded(self, file_path: str, metadata: list):
        """Store metadata and recompute active pages for this file if filter active"""
        self._page_metadata[file_path] = metadata
        if self._is_advanced_filter_active():
            new_active = self._compute_active_pages(file_path)
            old_active = self._active_pages.get(file_path)
            self._active_pages[file_path] = new_active
            # If visibility changed, rebuild file list
            was_visible = old_active is None or len(old_active) > 0
            is_visible = len(new_active) > 0
            if was_visible != is_visible:
                self._rebuild_list(restart_lazy_load=False)
                self.filter_changed.emit()
            # Always notify that active page filter may have changed for this file
            # so thumbnail/preview panels can update
            self.metadata_filter_updated.emit()
        self.viewport().update()


class BatchSidebar(QFrame):
    """
    Collapsible sidebar for batch mode file list

    Features:
    - Toggle collapse/expand with icon button
    - Search box for filtering
    - File list with checkbox, filename, page count
    - Toggle all checkbox
    """

    EXPANDED_WIDTH = 280
    MIN_WIDTH = 100  # Minimum width when expanded (prevents hiding hamburger)
    COLLAPSED_WIDTH = 30  # Matches nav button size (22px) + padding

    file_selected = pyqtSignal(str, int)  # (file_path, original_index)
    selection_changed = pyqtSignal(list)  # list of checked files
    close_requested = pyqtSignal()
    collapsed_changed = pyqtSignal(bool)  # emitted when collapsed state changes
    filter_changed = pyqtSignal()  # emitted when filter/sort changes (to update file counter)
    advanced_filter_changed = pyqtSignal()  # emitted when advanced page filter applied/reset


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
        self.setMaximumWidth(16777215)  # Qt QWIDGETSIZE_MAX - allow resize on Windows

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
        self._pages_combo.setEditable(True)
        self._pages_combo.setInsertPolicy(QComboBox.NoInsert)  # Don't add typed text to dropdown
        self._pages_combo.setFixedWidth(70)
        self._pages_combo.setFixedHeight(24)
        self._pages_combo.setToolTip(
            "Lọc theo số trang:\n"
            "• Chọn từ dropdown hoặc gõ tay\n"
            "• 5 = đúng 5 trang\n"
            "• >5 = hơn 5 trang\n"
            "• <10 = dưới 10 trang\n"
            "• >=3, <=20\n"
            "• 5-10 = từ 5 đến 10 trang"
        )
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
        self._file_list.filter_changed.connect(self.filter_changed.emit)
        self._file_list.metadata_filter_updated.connect(self.advanced_filter_changed.emit)
        list_layout.addWidget(self._file_list)

        # Advanced filter panel (at the bottom of list area)
        from ui.sidebar_advanced_filter import SidebarAdvancedFilter
        self._advanced_filter = SidebarAdvancedFilter(self)
        self._advanced_filter.apply_requested.connect(self._on_advanced_filter_apply)
        self._advanced_filter.reset_requested.connect(self._on_advanced_filter_reset)
        list_layout.addWidget(self._advanced_filter)

        content_layout.addWidget(self._list_container)

        # Page metadata loader (lazy loads size+orientation per page)
        from ui.page_metadata_loader import PageMetadataLoader
        self._metadata_loader = PageMetadataLoader(self)
        self._metadata_loader.metadata_loaded.connect(self._file_list.on_metadata_loaded)
        self._metadata_loader.batch_complete.connect(self._on_metadata_batch_complete)

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
        """Handle pages filter change (supports expressions: 5, >5, <10, >=3, <=20, 5-10)"""
        if text.lower() == "all" or not text:
            self._file_list.set_page_filter("")
            self._pages_clear_btn.setVisible(False)
        else:
            self._file_list.set_page_filter(text)
            self._pages_clear_btn.setVisible(True)
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

        # Cancel any in-progress metadata load then restart for new files
        self._metadata_loader.cancel()
        self._metadata_loader.load(files)

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

    def get_page_count(self, file_path: str) -> int:
        """Get page count for a specific file. Returns -1 if not loaded yet."""
        return self._file_list.get_page_count(file_path)

    def select_by_original_index(self, original_idx: int):
        """Select file by original index"""
        self._file_list.select_by_original_index(original_idx)

    def get_prev_file_info(self, original_idx: int) -> tuple:
        """Get (file_path, original_idx) of previous file in visible/sorted order."""
        return self._file_list.get_prev_file_info(original_idx)

    def get_next_file_info(self, original_idx: int) -> tuple:
        """Get (file_path, original_idx) of next file in visible/sorted order."""
        return self._file_list.get_next_file_info(original_idx)

    def has_prev_file(self, original_idx: int) -> bool:
        """Check if there's a previous file in visible order."""
        return self._file_list.has_prev_file(original_idx)

    def has_next_file(self, original_idx: int) -> bool:
        """Check if there's a next file in visible order."""
        return self._file_list.has_next_file(original_idx)

    def get_active_pages(self, file_path: str) -> Optional[Set[int]]:
        """Expose active_pages to main_window. Returns None when no filter active."""
        return self._file_list.get_active_pages(file_path)

    def _on_advanced_filter_apply(self, sizes: set, orientations: set, range_text: str):
        """Delegate apply to file list"""
        self._file_list.apply_advanced_filter(sizes, orientations, range_text)
        self.advanced_filter_changed.emit()

    def _on_advanced_filter_reset(self):
        """Delegate reset to file list"""
        self._file_list.reset_advanced_filter()
        self.advanced_filter_changed.emit()

    def _on_metadata_batch_complete(self):
        """Trigger final rebuild after all metadata loaded"""
        if self._file_list._is_advanced_filter_active():
            self._file_list._rebuild_list(restart_lazy_load=False)
            self.filter_changed.emit()
            self.advanced_filter_changed.emit()

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
