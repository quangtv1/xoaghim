"""
Page Thumbnail Sidebar - Collapsible page thumbnails panel for PDF preview
Shows miniature thumbnails of all pages with click-to-navigate functionality
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QPushButton, QSizePolicy, QSplitter
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QPen

import numpy as np
from typing import List, Optional


class ThumbnailItem(QWidget):
    """Single page thumbnail with page number label"""

    clicked = pyqtSignal(int)  # page_index (0-based)

    BORDER_WIDTH = 1  # Thin border for highlight only
    HIGHLIGHT_COLOR = "#3B82F6"  # Blue
    NORMAL_BORDER_COLOR = "transparent"  # No border when not selected

    def __init__(self, page_index: int, thumbnail_width: int = 70, parent=None):
        super().__init__(parent)
        self._page_index = page_index
        self._highlighted = False
        self._pixmap: Optional[QPixmap] = None
        self._thumbnail_width = thumbnail_width

        # Set fixed width to ensure centering works during loading
        self.setFixedWidth(thumbnail_width + 14)  # +14 for margins

        self._setup_ui()

    def _setup_ui(self):
        """Setup thumbnail UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 4)  # Wider padding
        layout.setSpacing(4)

        # Thumbnail image container - transparent, used for centering and border
        self._image_frame = QFrame()
        self._image_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._image_frame.setStyleSheet(f"""
            QFrame {{
                border: none;
                background-color: transparent;
            }}
        """)
        image_layout = QHBoxLayout(self._image_frame)  # HBox for horizontal centering
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setAlignment(Qt.AlignCenter)

        # Thumbnail image - gray background only around the actual image
        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignCenter)
        self._image_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._image_label.setScaledContents(False)
        self._image_label.setStyleSheet(f"""
            QLabel {{
                border: {self.BORDER_WIDTH}px solid {self.NORMAL_BORDER_COLOR};
                background-color: #E5E7EB;
            }}
        """)
        image_layout.addWidget(self._image_label)

        layout.addWidget(self._image_frame)

        # Page number label container
        self._page_label_container = QWidget()
        self._page_label_container.setFixedHeight(18)
        page_label_layout = QHBoxLayout(self._page_label_container)
        page_label_layout.setContentsMargins(0, 0, 0, 0)
        page_label_layout.setAlignment(Qt.AlignCenter)

        self._page_label = QLabel(str(self._page_index + 1))
        self._page_label.setAlignment(Qt.AlignCenter)
        self._page_label.setFixedHeight(16)
        self._page_label.setMinimumWidth(20)
        self._page_label.setStyleSheet("""
            QLabel {
                font-size: 10px;
                color: #6B7280;
                background: transparent;
                padding: 1px 4px;
            }
        """)
        page_label_layout.addWidget(self._page_label)

        layout.addWidget(self._page_label_container)

        # Make clickable
        self.setCursor(Qt.PointingHandCursor)

    def set_pixmap(self, pixmap: QPixmap):
        """Set thumbnail image"""
        self._pixmap = pixmap
        self._update_pixmap()

    def _update_pixmap(self):
        """Update pixmap: scale to fit within square bounding box, keeping aspect ratio.
        This ensures portrait A4 rotated 90° looks same as landscape A4.
        """
        if self._pixmap and not self._pixmap.isNull():
            # Available size for thumbnail (account for margins)
            available_size = self.width() - 14
            if available_size < 40:
                available_size = self._thumbnail_width

            # Scale to fit within square bounding box (available_size x available_size)
            # Portrait pages will be tall & narrow, landscape will be wide & short
            scaled = self._pixmap.scaled(
                available_size, available_size,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )

            # Set label to exact size of scaled image to prevent clipping
            self._image_label.setFixedSize(scaled.width(), scaled.height())
            self._image_label.setPixmap(scaled)

    def resizeEvent(self, event):
        """Handle resize - rescale pixmap"""
        super().resizeEvent(event)
        self._update_pixmap()

    def set_highlighted(self, highlighted: bool):
        """Set highlight state (current page)"""
        self._highlighted = highlighted
        border_color = self.HIGHLIGHT_COLOR if highlighted else self.NORMAL_BORDER_COLOR
        # Border on label (around actual thumbnail image)
        self._image_label.setStyleSheet(f"""
            QLabel {{
                border: {self.BORDER_WIDTH}px solid {border_color};
                background-color: #E5E7EB;
            }}
        """)
        # Update page label style - blue background with white text when highlighted
        if highlighted:
            self._page_label.setStyleSheet("""
                QLabel {
                    font-size: 10px;
                    color: white;
                    font-weight: bold;
                    background-color: #3B82F6;
                    border-radius: 3px;
                    padding: 1px 6px;
                }
            """)
        else:
            self._page_label.setStyleSheet("""
                QLabel {
                    font-size: 10px;
                    color: #6B7280;
                    background: transparent;
                    padding: 1px 4px;
                }
            """)

    def mousePressEvent(self, event):
        """Handle click - emit page index"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._page_index)
        super().mousePressEvent(event)


class ThumbnailPanel(QWidget):
    """Resizable panel containing page thumbnails (min 50px, max 160px)"""

    page_clicked = pyqtSignal(int)  # page_index (0-based)
    collapsed_changed = pyqtSignal(bool)  # collapsed state

    DEFAULT_WIDTH = 100
    MIN_WIDTH = 50
    MAX_WIDTH = 160
    COLLAPSED_WIDTH = 24

    def __init__(self, parent=None):
        super().__init__(parent)

        self._collapsed = False
        self._current_page = 0
        self._items: List[ThumbnailItem] = []
        self._pages: List[np.ndarray] = []
        self._expanded_width = self.DEFAULT_WIDTH
        self._loading = False  # True during progressive loading
        self._total_pages = 0

        self._setup_ui()
        self._load_state()

    def _setup_ui(self):
        """Setup panel UI"""
        # Allow resizing between min and max
        self.setMinimumWidth(self.MIN_WIDTH)
        self.setMaximumWidth(self.MAX_WIDTH)
        self.resize(self.DEFAULT_WIDTH, self.height())
        self.setStyleSheet("background-color: #F3F4F6;")  # Same as title bar

        # Main layout
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # === Expanded content ===
        self._content = QWidget()
        self._content.setStyleSheet("background-color: #F3F4F6;")
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Header with title and toggle button
        header_container = QWidget()
        header_container.setFixedHeight(28)
        header_container.setStyleSheet("background-color: #F3F4F6;")
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(4, 3, 4, 3)
        header_layout.setSpacing(4)

        self._toggle_btn = QPushButton("☰")
        self._toggle_btn.setFixedSize(20, 20)
        self._toggle_btn.setToolTip("Thu gọn thumbnails")
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                font-size: 11px;
                color: #6B7280;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
                border-radius: 3px;
            }
        """)
        self._toggle_btn.clicked.connect(self._toggle_collapsed)
        header_layout.addWidget(self._toggle_btn)

        # Title label
        self._title_label = QLabel("Trang thu nhỏ")
        self._title_label.setStyleSheet("""
            QLabel {
                color: #374151;
                font-size: 12px;
                font-weight: normal;
                background: transparent;
            }
        """)
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        content_layout.addWidget(header_container)

        # Progress bar (1px) - ngay dưới header
        self._progress_bar = QWidget()
        self._progress_bar.setFixedHeight(1)
        self._progress_bar.setStyleSheet("background-color: #E5E7EB;")

        progress_layout = QHBoxLayout(self._progress_bar)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(0)

        self._progress_bar_fill = QWidget()
        self._progress_bar_fill.setFixedHeight(1)
        self._progress_bar_fill.setStyleSheet("background-color: #3B82F6;")
        self._progress_bar_fill.setFixedWidth(0)
        progress_layout.addWidget(self._progress_bar_fill)
        progress_layout.addStretch()

        # Progress bar luôn hiển thị (đường xám), fill xanh khi loading
        content_layout.addWidget(self._progress_bar)

        # Scroll area for thumbnails
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #F3F4F6;
            }
            QScrollBar:vertical {
                width: 6px;
                background: #F3F4F6;
            }
            QScrollBar::handle:vertical {
                background: #D1D5DB;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #9CA3AF;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # Container for thumbnail items
        self._thumbnail_container = QWidget()
        self._thumbnail_container.setStyleSheet("background-color: #F3F4F6;")
        self._thumbnail_layout = QVBoxLayout(self._thumbnail_container)
        self._thumbnail_layout.setContentsMargins(4, 6, 4, 6)
        self._thumbnail_layout.setSpacing(8)
        self._thumbnail_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)  # Center horizontally

        self._scroll_area.setWidget(self._thumbnail_container)
        content_layout.addWidget(self._scroll_area)

        # Bottom separator line (1px gray)
        bottom_line = QFrame()
        bottom_line.setFixedHeight(1)
        bottom_line.setStyleSheet("background-color: #D1D5DB;")
        content_layout.addWidget(bottom_line)

        self._main_layout.addWidget(self._content)

        # === Collapsed widget ===
        self._collapsed_widget = QWidget()
        self._collapsed_widget.setStyleSheet("background-color: #F3F4F6;")
        self._collapsed_widget.setFixedWidth(self.COLLAPSED_WIDTH)
        collapsed_layout = QVBoxLayout(self._collapsed_widget)
        collapsed_layout.setContentsMargins(0, 0, 0, 0)
        collapsed_layout.setSpacing(0)

        # Header với chiều cao bằng thumbnail header (28px)
        collapsed_header = QWidget()
        collapsed_header.setFixedHeight(28)
        collapsed_header.setStyleSheet("background-color: #F3F4F6;")
        collapsed_header_layout = QHBoxLayout(collapsed_header)
        collapsed_header_layout.setContentsMargins(2, 4, 2, 4)
        collapsed_header_layout.setAlignment(Qt.AlignCenter)

        self._expand_btn = QPushButton("☰")
        self._expand_btn.setFixedSize(20, 20)
        self._expand_btn.setToolTip("Mở rộng thumbnails")
        self._expand_btn.setCursor(Qt.PointingHandCursor)
        self._expand_btn.setStyleSheet("""
            QPushButton {
                background-color: #D1D5DB;
                border: none;
                border-radius: 3px;
                font-size: 11px;
                color: #374151;
            }
            QPushButton:hover {
                background-color: #9CA3AF;
            }
        """)
        self._expand_btn.clicked.connect(self._toggle_collapsed)
        collapsed_header_layout.addWidget(self._expand_btn)
        collapsed_layout.addWidget(collapsed_header)

        # Line xám 1px (thẳng hàng với line dưới "Trang thu nhỏ")
        collapsed_line = QWidget()
        collapsed_line.setFixedHeight(1)
        collapsed_line.setStyleSheet("background-color: #E5E7EB;")
        collapsed_layout.addWidget(collapsed_line)

        # Spacer để đẩy nội dung còn lại xuống
        collapsed_layout.addStretch()

        self._collapsed_widget.setVisible(False)
        self._main_layout.addWidget(self._collapsed_widget)

    def _load_state(self):
        """Load collapsed state and width from config"""
        try:
            from core.config_manager import get_config_manager
            config = get_config_manager()
            self._collapsed = config.get("thumbnail_panel_collapsed", False)
            self._expanded_width = config.get("thumbnail_panel_width", self.DEFAULT_WIDTH)
            # Clamp to valid range
            self._expanded_width = max(self.MIN_WIDTH, min(self.MAX_WIDTH, self._expanded_width))
            self._apply_collapsed_state()
        except Exception:
            pass

    def _save_state(self):
        """Save collapsed state and width to config"""
        try:
            from core.config_manager import get_config_manager
            config = get_config_manager()
            config.set("thumbnail_panel_collapsed", self._collapsed)
            config.set("thumbnail_panel_width", self._expanded_width)
        except Exception:
            pass

    def _toggle_collapsed(self):
        """Toggle collapsed state"""
        if not self._collapsed:
            # Save current width before collapsing
            self._expanded_width = self.width()
        self._collapsed = not self._collapsed
        self._apply_collapsed_state()
        self._save_state()
        self.collapsed_changed.emit(self._collapsed)

    def _apply_collapsed_state(self):
        """Apply current collapsed state to UI"""
        if self._collapsed:
            self.setFixedWidth(self.COLLAPSED_WIDTH)
            self._content.setVisible(False)
            self._collapsed_widget.setVisible(True)
        else:
            self.setMinimumWidth(self.MIN_WIDTH)
            self.setMaximumWidth(self.MAX_WIDTH)
            self.resize(self._expanded_width, self.height())
            self._collapsed_widget.setVisible(False)
            self._content.setVisible(True)

    def set_pages(self, pages: List[np.ndarray]):
        """Set page images and create thumbnails"""
        self._pages = pages

        # Clear existing items
        for item in self._items:
            item.deleteLater()
        self._items.clear()

        # Clear layout
        while self._thumbnail_layout.count():
            child = self._thumbnail_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Create new thumbnail items
        for i, page in enumerate(pages):
            item = ThumbnailItem(i, thumbnail_width=self.width() - 20)
            item.clicked.connect(self._on_item_clicked)

            # Convert numpy array to QPixmap
            pixmap = self._numpy_to_pixmap(page)
            item.set_pixmap(pixmap)

            self._thumbnail_layout.addWidget(item)
            self._items.append(item)

        # Add stretch at bottom
        self._thumbnail_layout.addStretch()

        # Highlight first page
        if self._items:
            self.set_current_page(0)

    def start_loading(self, total_pages: int):
        """Prepare for progressive thumbnail loading"""
        self._loading = True
        self._total_pages = total_pages
        self._pages = []
        self._current_page = -1  # Reset to no selection, so first thumbnail will be highlighted

        # Show progress bar
        self.show_progress_bar()

        # Clear existing items
        for item in self._items:
            item.deleteLater()
        self._items.clear()

        # Clear layout (remove stretch too)
        while self._thumbnail_layout.count():
            child = self._thumbnail_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def pause_updates(self):
        """Pause visual updates for bulk loading. Call before loading remaining thumbnails."""
        self._scroll_area.setUpdatesEnabled(False)

    def add_thumbnail(self, index: int, image: np.ndarray):
        """Add single thumbnail during progressive loading"""
        if image is None:
            return

        item = ThumbnailItem(index, thumbnail_width=self.width() - 20)
        item.clicked.connect(self._on_item_clicked)

        # Convert numpy array to QPixmap
        pixmap = self._numpy_to_pixmap(image)
        item.set_pixmap(pixmap)

        self._thumbnail_layout.addWidget(item)
        self._items.append(item)
        self._pages.append(image)

        # Update progress bar
        if self._total_pages > 0:
            percent = int((index + 1) * 100 / self._total_pages)
            self.set_progress(percent)

        # Highlight first page
        if index == 0:
            self.set_current_page(0)

    def finish_loading(self):
        """Mark loading complete, enable full interaction"""
        self._loading = False
        # Hide progress bar
        self.hide_progress_bar()
        # Add stretch at bottom
        self._thumbnail_layout.addStretch()
        # Re-enable visual updates and repaint once (single update instead of flickering)
        self._scroll_area.setUpdatesEnabled(True)
        self._scroll_area.update()

    def set_thumbnails_bulk(self, thumbnails: list):
        """Set all thumbnails at once from cache (optimized for fast loading).

        This method is optimized for loading from preload cache:
        - Pauses visual updates during widget creation
        - Creates all widgets in a single batch
        - Single repaint at the end

        Args:
            thumbnails: List of numpy arrays (thumbnail images)
        """
        if not thumbnails:
            return

        # Clear and prepare
        self._loading = True
        self._total_pages = len(thumbnails)
        self._pages = []
        self._current_page = -1

        # Clear existing items
        for item in self._items:
            item.deleteLater()
        self._items.clear()

        # Clear layout
        while self._thumbnail_layout.count():
            item = self._thumbnail_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Pause updates during bulk creation
        self._scroll_area.setUpdatesEnabled(False)

        # Create all items without individual updates
        thumb_width = self.width() - 20
        for idx, img in enumerate(thumbnails):
            if img is None:
                continue
            item = ThumbnailItem(idx, thumbnail_width=thumb_width)
            item.clicked.connect(self._on_item_clicked)
            pixmap = self._numpy_to_pixmap(img)
            item.set_pixmap(pixmap)
            self._thumbnail_layout.addWidget(item)
            self._items.append(item)
            self._pages.append(img)

        # Add stretch and finalize
        self._thumbnail_layout.addStretch()
        self._loading = False

        # Single repaint at end
        self._scroll_area.setUpdatesEnabled(True)
        self._scroll_area.update()

        # Highlight first page
        if self._items:
            self.set_current_page(0)

    def _numpy_to_pixmap(self, img: np.ndarray) -> QPixmap:
        """Convert numpy array (BGR or RGB) to QPixmap

        Note: Must copy the QImage to avoid memory issues when numpy array
        goes out of scope. QImage(data, ...) references the data buffer,
        so we need .copy() to make QImage own its data.
        """
        if img is None:
            return QPixmap()

        # Handle different formats
        if len(img.shape) == 2:
            # Grayscale
            h, w = img.shape
            img_copy = img.copy()  # Ensure contiguous memory
            qimg = QImage(img_copy.data, w, h, w, QImage.Format_Grayscale8).copy()
        elif img.shape[2] == 3:
            # BGR -> RGB
            rgb = img[:, :, ::-1].copy()
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
        elif img.shape[2] == 4:
            # BGRA -> RGBA
            rgba = img[:, :, [2, 1, 0, 3]].copy()
            h, w, ch = rgba.shape
            bytes_per_line = ch * w
            qimg = QImage(rgba.data, w, h, bytes_per_line, QImage.Format_RGBA8888).copy()
        else:
            return QPixmap()

        return QPixmap.fromImage(qimg)

    def _on_item_clicked(self, page_index: int):
        """Handle thumbnail click - highlight only, don't scroll"""
        self.set_current_page(page_index, scroll=False)
        self.page_clicked.emit(page_index)

    def set_current_page(self, index: int, scroll: bool = True):
        """Set current page and update highlight

        Args:
            index: Page index (0-based)
            scroll: If True, scroll thumbnail into view. Default True for external calls,
                   False when user clicks directly on a thumbnail.
        """
        if 0 <= index < len(self._items):
            # Skip if already on this page (avoid unnecessary scroll)
            if index == self._current_page:
                return

            # Remove highlight from previous
            if 0 <= self._current_page < len(self._items):
                self._items[self._current_page].set_highlighted(False)

            # Highlight new
            self._current_page = index
            self._items[index].set_highlighted(True)

            # Scroll to visible only if requested
            if scroll:
                self._scroll_to_item(index)

    def _scroll_to_item(self, index: int):
        """Scroll to make item visible"""
        if 0 <= index < len(self._items):
            item = self._items[index]
            self._scroll_area.ensureWidgetVisible(item, 10, 10)

    def show_progress_bar(self):
        """Start showing progress (reset fill to 0)"""
        self.set_progress(0)

    def hide_progress_bar(self):
        """Hide progress fill (reset to 0, gray line remains)"""
        self.set_progress(0)

    def set_progress(self, percent: int):
        """Set progress bar percentage (0-100)"""
        if self._progress_bar_fill is not None:
            parent_width = self._progress_bar.width() if self._progress_bar else 100
            fill_width = int(parent_width * percent / 100)
            self._progress_bar_fill.setFixedWidth(fill_width)

    def is_collapsed(self) -> bool:
        """Return collapsed state"""
        return self._collapsed

    def get_width(self) -> int:
        """Return current width (for layout calculations)"""
        if self._collapsed:
            return self.COLLAPSED_WIDTH
        return self.width()

    def resizeEvent(self, event):
        """Save width when resized"""
        super().resizeEvent(event)
        if not self._collapsed and event.size().width() >= self.MIN_WIDTH:
            self._expanded_width = event.size().width()
