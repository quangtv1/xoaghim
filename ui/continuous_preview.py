"""
Continuous Preview - Preview liên tục nhiều trang với nền đen
"""

import os
from pathlib import Path

from .undo_manager import UndoManager, UndoAction
from .page_thumbnail_sidebar import ThumbnailPanel

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsRectItem, QFrame, QSplitter, QScrollArea, QPushButton,
    QGraphicsOpacityEffect, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QTimer, QPointF, QPropertyAnimation, QEasingCurve, QEvent
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QBrush, QPen, QCursor, QPainterPath, QFont


class SpinnerWidget(QWidget):
    """Custom spinning loader widget với gradient arc"""

    def __init__(self, parent=None, size=40, line_width=4):
        super().__init__(parent)
        self._size = size
        self._line_width = line_width
        self._angle = 0
        self.setFixedSize(size, size)

        # Animation timer
        self._timer = QTimer()
        self._timer.timeout.connect(self._rotate)

    def _rotate(self):
        self._angle = (self._angle + 10) % 360
        self.update()

    def start(self):
        self._timer.start(20)  # 50 FPS smooth animation

    def stop(self):
        self._timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Calculate rect for arc
        margin = self._line_width / 2
        rect = QRectF(margin, margin,
                      self._size - self._line_width,
                      self._size - self._line_width)

        # Draw background circle (light gray)
        bg_pen = QPen(QColor("#E5E7EB"), self._line_width)
        bg_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(bg_pen)
        painter.drawEllipse(rect)

        # Draw spinning arc with gradient effect
        # Create gradient from blue to transparent
        from PyQt5.QtGui import QConicalGradient
        gradient = QConicalGradient(self._size / 2, self._size / 2, -self._angle)
        gradient.setColorAt(0, QColor("#2563EB"))      # Blue
        gradient.setColorAt(0.25, QColor("#3B82F6"))   # Lighter blue
        gradient.setColorAt(0.5, QColor("#93C5FD"))    # Even lighter
        gradient.setColorAt(0.75, QColor("#DBEAFE"))   # Very light
        gradient.setColorAt(1, QColor("#2563EB"))      # Back to blue

        arc_pen = QPen(QBrush(gradient), self._line_width)
        arc_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(arc_pen)

        # Draw arc (270 degrees, leaving 90 degree gap)
        start_angle = int(self._angle * 16)  # Qt uses 1/16 degree
        span_angle = 270 * 16
        painter.drawArc(rect, start_angle, span_angle)


class LoadingOverlay(QWidget):
    """Loading overlay với spinning indicator"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background-color: transparent;")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # Container popup - hình chữ nhật xám nhẹ, round bé, 80% opacity
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: rgba(200, 200, 200, 0.8);
                border: none;
                border-radius: 6px;
            }
        """)
        container.setFixedSize(180, 100)
        container_layout = QVBoxLayout(container)
        container_layout.setAlignment(Qt.AlignCenter)
        container_layout.setSpacing(10)

        # Custom spinner widget
        self._spinner = SpinnerWidget(size=36, line_width=4)
        container_layout.addWidget(self._spinner, alignment=Qt.AlignCenter)

        # Loading text - màu xanh cobalt, không nền
        self._loading_label = QLabel("Đang phát hiện layout")
        self._loading_label.setStyleSheet("""
            font-size: 13px;
            color: #0047AB;
            background: transparent;
        """)
        self._loading_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(self._loading_label)

        layout.addWidget(container)
        self.hide()

    def showEvent(self, event):
        super().showEvent(event)
        self._spinner.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._spinner.stop()

    def set_text(self, text: str):
        """Set loading label text"""
        self._loading_label.setText(text)

import numpy as np
import cv2
from typing import List, Optional, Dict, TYPE_CHECKING


from ui.zone_item import ZoneItem
from core.processor import Zone, StapleRemover


import threading


class DetectionRunner:
    """Runner để chạy YOLO detection trong Python thread (không dùng QThread)"""

    def __init__(self, processor, pages, original_indices, callback, progress_callback=None):
        self._processor = processor
        self._pages = pages  # Copy of pages
        self._original_indices = original_indices
        self._callback = callback  # Called when done with results
        self._progress_callback = progress_callback  # Called after each page (current, total)
        self._cancelled = False
        self._thread = None
        self._current_progress = 0  # Current page being processed
        self._total_pages = len(pages)
        self._incremental_results = {}  # Store results incrementally

    def start(self):
        """Start detection in background thread"""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self):
        """Request cancellation"""
        self._cancelled = True

    def is_running(self):
        """Check if thread is running"""
        return self._thread is not None and self._thread.is_alive()

    def wait(self, timeout=None):
        """Wait for thread to finish"""
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            return not self._thread.is_alive()
        return True

    def get_progress(self) -> tuple:
        """Get current progress (current, total)"""
        return (self._current_progress, self._total_pages)

    def get_incremental_results(self) -> dict:
        """Get results detected so far (for incremental display)"""
        return self._incremental_results.copy()

    def _run(self):
        """Run detection (called in background thread)"""
        results = {}

        for i, page in enumerate(self._pages):
            if self._cancelled:
                break

            try:
                original_idx = self._original_indices[i]
                regions = self._processor.detect_protected_regions(page)
                results[original_idx] = regions
                self._incremental_results[original_idx] = regions
            except Exception as e:
                original_idx = self._original_indices[i]
                results[original_idx] = []
                self._incremental_results[original_idx] = []

            # Update progress
            self._current_progress = i + 1
            if self._progress_callback and not self._cancelled:
                self._progress_callback(self._current_progress, self._total_pages)

        # Call callback with results (if not cancelled)
        if not self._cancelled and self._callback:
            self._callback(results)


class ContinuousGraphicsView(QGraphicsView):
    """GraphicsView với nền xám và synchronized scroll"""

    zoom_changed = pyqtSignal(float)
    scroll_changed = pyqtSignal(int, int)
    # rect_drawn: x, y, w, h (as % of page), mode ('remove' or 'protect'), page_idx
    rect_drawn = pyqtSignal(float, float, float, float, str, int)
    # Drag & drop signals
    file_dropped = pyqtSignal(str)
    folder_dropped = pyqtSignal(str)
    files_dropped = pyqtSignal(list)  # Multiple PDF files dropped

    def __init__(self, parent=None):
        super().__init__(parent)

        # Nền xám
        self.setBackgroundBrush(QBrush(QColor(229, 231, 235)))  # Gray #E5E7EB
        self.setStyleSheet("border: none;")

        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)  # Allow zone items to show their cursors
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

        # Enable drag and drop on view
        self.setAcceptDrops(True)

        self._zoom = 1.0
        self._syncing = False

        # Draw mode: None, 'remove', or 'protect'
        self._draw_mode = None
        self._drawing = False
        # Custom crosshair cursors (cached)
        self._crosshair_cursors = {}
        self._draw_start = None
        self._draw_rect_item = None
        self._page_bounds = None  # (x, y, w, h) of current page (fallback)
        self._all_page_bounds = []  # List of (x, y, w, h) for all pages
    
    def wheelEvent(self, event):
        """Zoom với Ctrl+Scroll"""
        if event.modifiers() == Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1/1.15
            self._zoom *= factor
            self._zoom = max(0.1, min(5.0, self._zoom))
            self.setTransform(self.transform().scale(factor, factor))
            self.zoom_changed.emit(self._zoom)
        else:
            super().wheelEvent(event)
    
    def set_zoom(self, zoom: float):
        """Set zoom level"""
        if not self._syncing:
            self._syncing = True
            factor = zoom / self._zoom
            self._zoom = zoom
            self.setTransform(self.transform().scale(factor, factor))
            self._syncing = False
    
    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        if not self._syncing:
            h = self.horizontalScrollBar().value()
            v = self.verticalScrollBar().value()
            self.scroll_changed.emit(h, v)
    
    def sync_scroll(self, h: int, v: int):
        """Sync scroll position"""
        if not self._syncing:
            self._syncing = True
            self.horizontalScrollBar().setValue(h)
            self.verticalScrollBar().setValue(v)
            self._syncing = False

    def dragEnterEvent(self, event):
        """Handle drag enter for file/folder drop"""
        if event.mimeData().hasUrls():
            # Accept any URL - check content in dropEvent
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """Handle drag move"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _get_local_path(self, url):
        """Get local file path from URL, handling Windows format"""
        path = url.toLocalFile()
        # Handle Windows file:///C:/path format
        if not path and url.toString().startswith('file:///'):
            path = url.toString()[8:]  # Remove 'file:///'
        return os.path.normpath(path) if path else ''

    def dropEvent(self, event):
        """Handle file/folder drop"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            pdf_files = []
            folder_path = None

            for url in urls:
                path = self._get_local_path(url)
                if not path:
                    continue
                if os.path.isdir(path):
                    folder_path = path
                elif path.lower().endswith('.pdf'):
                    pdf_files.append(path)

            # Priority: folder > multiple files > single file
            if folder_path:
                self.folder_dropped.emit(folder_path)
                event.acceptProposedAction()
                return
            elif len(pdf_files) > 1:
                self.files_dropped.emit(pdf_files)
                event.acceptProposedAction()
                return
            elif len(pdf_files) == 1:
                self.file_dropped.emit(pdf_files[0])
                event.acceptProposedAction()
                return
        event.ignore()

    def set_draw_mode(self, mode, page_bounds: tuple = None, all_page_bounds: list = None):
        """Enable/disable draw mode

        Args:
            mode: None (off), 'remove' (blue), or 'protect' (pink)
            page_bounds: (x, y, w, h) of current page (fallback)
            all_page_bounds: List of (x, y, w, h) for all pages (for accurate detection)
        """
        old_mode = self._draw_mode
        self._draw_mode = mode
        self._page_bounds = page_bounds
        self._all_page_bounds = all_page_bounds or []
        if mode:
            self.setDragMode(QGraphicsView.NoDrag)
            # Enable mouse tracking
            self.setMouseTracking(True)
            self.viewport().setMouseTracking(True)
            # Install event filter on viewport to catch enter/leave
            self.viewport().installEventFilter(self)
            # Set custom crosshair cursor immediately if mouse is inside viewport
            if self.viewport().underMouse():
                self.viewport().setCursor(self._get_draw_cursor())
        else:
            # Remove event filter and restore cursor
            self.viewport().removeEventFilter(self)
            self.setDragMode(QGraphicsView.NoDrag)
            self.viewport().unsetCursor()
            # Clean up any in-progress drawing
            try:
                if self._draw_rect_item and self._draw_rect_item.scene():
                    self.scene().removeItem(self._draw_rect_item)
            except RuntimeError:
                pass  # Item already deleted
            self._draw_rect_item = None
            self._drawing = False
            self._draw_start = None

    def eventFilter(self, obj, event):
        """Handle viewport events for cursor in draw mode"""
        if obj == self.viewport() and self._draw_mode:
            if event.type() == QEvent.Enter:
                self.viewport().setCursor(self._get_draw_cursor())
            elif event.type() == QEvent.Leave:
                self.viewport().unsetCursor()
            elif event.type() == QEvent.MouseMove:
                # Check if hovering over a zone item
                scene_pos = self.mapToScene(event.pos())
                item = self.scene().itemAt(scene_pos, self.transform()) if self.scene() else None
                from ui.zone_item import ZoneItem
                if isinstance(item, ZoneItem) or (hasattr(item, 'parentItem') and isinstance(item.parentItem(), ZoneItem)):
                    # Over zone - let zone set its own cursor (resize handles, move cursor)
                    self.viewport().unsetCursor()
                else:
                    # Over empty space - show custom crosshair cursor
                    self.viewport().setCursor(self._get_draw_cursor())
        return super().eventFilter(obj, event)

    def _create_crosshair_cursor(self, color: QColor) -> QCursor:
        """Create custom crosshair cursor with specified color (3x longer arms)"""
        line_length = 24  # 3x longer than default ~8px (49x49 total, safe for Linux X11)
        size = line_length * 2 + 1  # Odd size for center pixel
        center = size // 2

        # Handle Retina display
        dpr = QApplication.instance().devicePixelRatio() if QApplication.instance() else 1.0
        actual_size = int(size * dpr)
        actual_center = int(center * dpr)
        actual_length = int(line_length * dpr)

        # Use QImage with premultiplied alpha for proper transparency
        image = QImage(actual_size, actual_size, QImage.Format_ARGB32_Premultiplied)
        image.fill(0)  # Fully transparent (0x00000000)

        # Get color as ARGB with full opacity
        r, g, b = color.red(), color.green(), color.blue()
        argb = (255 << 24) | (r << 16) | (g << 8) | b  # 0xFFrrggbb

        # Line thickness = 1 logical pixel (matches zone border)
        thickness = max(1, int(1 * dpr))
        half_t = thickness // 2

        # Draw horizontal line with thickness
        for x in range(actual_center - actual_length, actual_center + actual_length + 1):
            for t in range(-half_t, half_t + 1):
                y = actual_center + t
                if 0 <= x < actual_size and 0 <= y < actual_size:
                    image.setPixel(x, y, argb)

        # Draw vertical line with thickness
        for y in range(actual_center - actual_length, actual_center + actual_length + 1):
            for t in range(-half_t, half_t + 1):
                x = actual_center + t
                if 0 <= x < actual_size and 0 <= y < actual_size:
                    image.setPixel(x, y, argb)

        image.setDevicePixelRatio(dpr)
        pixmap = QPixmap.fromImage(image)

        # Create mask from transparent pixels for Linux X11 compatibility
        # X11 needs explicit mask for transparency to work
        mask = pixmap.createMaskFromColor(QColor(0, 0, 0, 0), Qt.MaskInColor)
        pixmap.setMask(mask)

        return QCursor(pixmap, center, center)

    def _get_draw_cursor(self) -> QCursor:
        """Get crosshair cursor for current draw mode (cached)"""
        if self._draw_mode == 'protect':
            color_key = 'pink'
            color = QColor(244, 114, 182)  # Pink #F472B6
        else:
            color_key = 'green'
            color = QColor(34, 197, 94)  # Green #22C55E

        if color_key not in self._crosshair_cursors:
            self._crosshair_cursors[color_key] = self._create_crosshair_cursor(color)

        return self._crosshair_cursors[color_key]

    def _get_draw_colors(self):
        """Get pen and brush colors based on draw mode"""
        if self._draw_mode == 'protect':
            # Pink for protection zones
            pen = QPen(QColor(244, 114, 182), 1)  # Pink #F472B6
            brush = QBrush(QColor(244, 114, 182, 50))
        else:
            # Green for Zone Riêng (custom removal zones)
            pen = QPen(QColor(34, 197, 94), 1)  # Green #22C55E
            brush = QBrush(QColor(34, 197, 94, 50))
        return pen, brush

    def mousePressEvent(self, event):
        """Start drawing if in draw mode, or interact with existing zones"""
        if self._draw_mode and event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            # Check if clicking on an existing zone item
            item = self.scene().itemAt(scene_pos, self.transform()) if self.scene() else None
            # Import ZoneItem for type check
            from ui.zone_item import ZoneItem
            if isinstance(item, ZoneItem) or (hasattr(item, 'parentItem') and isinstance(item.parentItem(), ZoneItem)):
                # Clicking on existing zone - let it handle the event (resize/move)
                super().mousePressEvent(event)
                return
            # Not clicking on a zone - start drawing new zone
            page_bounds = self._find_page_at_y(scene_pos.y())
            if page_bounds:
                px, py, pw, ph = page_bounds
                # Clamp start point to page bounds (if outside, use edge)
                clamped_x = max(px, min(scene_pos.x(), px + pw))
                clamped_y = max(py, min(scene_pos.y(), py + ph))
                self._drawing = True
                self._draw_start = QPointF(clamped_x, clamped_y)
                self._draw_rect_item = None
        else:
            # Check if clicking on empty space (no item at click position)
            if event.button() == Qt.LeftButton:
                scene_pos = self.mapToScene(event.pos())
                item = self.scene().itemAt(scene_pos, self.transform()) if self.scene() else None
                # If no item or only page background, deselect all zones
                if item is None or isinstance(item, QGraphicsPixmapItem):
                    # Find parent panel and deselect all zones
                    parent = self.parent()
                    while parent:
                        if hasattr(parent, 'deselect_all_zones'):
                            parent.deselect_all_zones()
                            break
                        parent = parent.parent() if hasattr(parent, 'parent') else None
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Update rectangle while drawing"""
        if self._drawing and self._draw_start:
            current = self.mapToScene(event.pos())

            # Find page bounds to constrain drawing
            page_bounds = self._find_page_at_y(self._draw_start.y())
            if page_bounds:
                px, py, pw, ph = page_bounds
                # Clamp current position to page bounds
                current_x = max(px, min(current.x(), px + pw))
                current_y = max(py, min(current.y(), py + ph))
                # Clamp start position to page bounds
                start_x = max(px, min(self._draw_start.x(), px + pw))
                start_y = max(py, min(self._draw_start.y(), py + ph))
            else:
                current_x, current_y = current.x(), current.y()
                start_x, start_y = self._draw_start.x(), self._draw_start.y()

            x = min(start_x, current_x)
            y = min(start_y, current_y)
            w = abs(current_x - start_x)
            h = abs(current_y - start_y)

            # Only create rect if dragged enough (> 5 pixels)
            if w > 5 or h > 5:
                if not self._draw_rect_item:
                    # Create rectangle item on first significant drag
                    pen, brush = self._get_draw_colors()
                    self._draw_rect_item = QGraphicsRectItem()
                    self._draw_rect_item.setPen(pen)
                    self._draw_rect_item.setBrush(brush)
                    self._draw_rect_item.setZValue(1000)
                    self.scene().addItem(self._draw_rect_item)
                self._draw_rect_item.setRect(x, y, w, h)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Finish drawing and emit signal"""
        if self._drawing and event.button() == Qt.LeftButton:
            self._drawing = False
            # Only process if rect was actually created (dragged, not just clicked)
            if self._draw_rect_item and self._draw_mode:
                rect = self._draw_rect_item.rect()

                # Find which page the rect center is on
                # Use combined method to ensure page_bounds and page_idx are consistent
                rect_center_y = rect.y() + rect.height() / 2
                page_idx, page_bounds = self._find_page_with_index_at_y(rect_center_y)

                if page_bounds:
                    px, py, pw, ph = page_bounds
                    if pw > 0 and ph > 0:
                        # Clamp to page bounds
                        x = max(0, (rect.x() - px) / pw)
                        y = max(0, (rect.y() - py) / ph)
                        w = min(1 - x, rect.width() / pw)
                        h = min(1 - y, rect.height() / ph)
                        # Only emit if reasonable size
                        if w > 0.01 and h > 0.01:
                            self.rect_drawn.emit(x, y, w, h, self._draw_mode, page_idx)

            # Clean up drawing rect but KEEP draw mode active
            try:
                if self._draw_rect_item and self._draw_rect_item.scene():
                    self.scene().removeItem(self._draw_rect_item)
            except RuntimeError:
                pass  # Item already deleted
            self._draw_rect_item = None
            self._draw_start = None
        else:
            super().mouseReleaseEvent(event)

    def _find_page_at_y(self, y: float) -> tuple:
        """Find page bounds containing the given y coordinate"""
        # Try all_page_bounds first (for accurate detection in continuous mode)
        if self._all_page_bounds:
            for bounds in self._all_page_bounds:
                px, py, pw, ph = bounds
                if py <= y <= py + ph:
                    return bounds
        # Fallback to single page_bounds
        return self._page_bounds

    def _find_page_index_at_y(self, y: float) -> int:
        """Find page index containing the given y coordinate (0-based)"""
        if self._all_page_bounds:
            for i, bounds in enumerate(self._all_page_bounds):
                px, py, pw, ph = bounds
                if py <= y <= py + ph:
                    return i
            # No exact match - find the page index for fallback _page_bounds
            # This ensures consistency with _find_page_at_y
            if self._page_bounds:
                for i, bounds in enumerate(self._all_page_bounds):
                    if bounds == self._page_bounds:
                        return i
        return 0  # Default to first page

    def _find_page_with_index_at_y(self, y: float) -> tuple:
        """Find both page bounds and index containing the given y coordinate.

        Returns (page_idx, page_bounds) tuple ensuring consistency.
        """
        if self._all_page_bounds:
            for i, bounds in enumerate(self._all_page_bounds):
                px, py, pw, ph = bounds
                if py <= y <= py + ph:
                    return (i, bounds)
            # No exact match - use fallback _page_bounds and find its index
            if self._page_bounds:
                for i, bounds in enumerate(self._all_page_bounds):
                    if bounds == self._page_bounds:
                        return (i, self._page_bounds)
        # Ultimate fallback
        return (0, self._page_bounds)


class ContinuousPreviewPanel(QFrame):
    """
    Panel preview liên tục nhiều trang
    """

    zone_changed = pyqtSignal(str)  # zone_id
    zone_selected = pyqtSignal(str)  # zone_id
    zone_delete = pyqtSignal(str)  # zone_id - request to delete custom zone
    zone_drag_started = pyqtSignal(str, QRectF)  # zone_id, rect before drag (for undo)
    zone_drag_ended = pyqtSignal(str, QRectF)  # zone_id, rect after drag (for undo)
    placeholder_clicked = pyqtSignal()  # When placeholder "Mở file" is clicked
    folder_placeholder_clicked = pyqtSignal()  # When placeholder "Mở thư mục" is clicked
    file_dropped = pyqtSignal(str)  # When file is dropped (file_path)
    folder_dropped = pyqtSignal(str)  # When folder is dropped (folder_path)
    files_dropped = pyqtSignal(list)  # When multiple PDF files are dropped
    close_requested = pyqtSignal()  # When close button is clicked
    collapse_requested = pyqtSignal()  # When collapse button is clicked (Đích panel)
    # rect_drawn: x, y, w, h (as % of page), mode ('remove' or 'protect'), page_idx
    rect_drawn = pyqtSignal(float, float, float, float, str, int)
    # Batch mode navigation signals
    prev_file_requested = pyqtSignal()  # Navigate to previous file
    next_file_requested = pyqtSignal()  # Navigate to next file
    # Thumbnail panel signals
    thumbnail_page_clicked = pyqtSignal(int)  # page_index - when thumbnail is clicked
    thumbnail_collapsed_changed = pyqtSignal(bool)  # collapsed state changed

    PAGE_SPACING = 20  # Khoảng cách giữa các trang
    
    def __init__(self, title: str, show_overlay: bool = False, parent=None):
        super().__init__(parent)

        self._panel_title = title  # Store for debug
        self.show_overlay = show_overlay
        self._pages: List[np.ndarray] = []  # List of page images (can contain None for unloaded)
        self._page_items: List[QGraphicsPixmapItem] = []  # Graphics items
        self._total_pages: int = 0  # Total pages in file (for sliding window)
        self._page_sizes: List[tuple] = []  # (width, height) for each page (estimated from first loaded)
        self._zones: List[ZoneItem] = []
        self._zone_definitions: List[Zone] = []  # Zone definitions (shared across pages)
        self._last_zone_ids: set = set()  # Track zone IDs from previous set_zone_definitions call
        self._page_positions: List[float] = []  # Y position of each page
        self._has_placeholder = False  # Track if placeholder is shown
        self._placeholder_file_rect = None  # Click area for "Mở file"
        self._placeholder_folder_rect = None  # Click area for "Mở thư mục"
        self._file_icon_normal = []  # Normal file icon items (gray outline)
        self._file_icon_hover = []  # Hover file icon items (blue filled)
        self._folder_icon_normal = []  # Normal folder icon items (gray outline)
        self._folder_icon_hover = []  # Hover folder icon items (blue filled)
        self._view_mode = 'continuous'  # 'continuous' or 'single'
        self._current_page = 0  # Current page index (0-based) for single page mode
        self._page_filter = 'all'  # 'all', 'odd', 'even', 'none'
        # Per-page zone storage for 'none' mode (independent zones per page)
        self._per_page_zones: Dict[int, Dict[str, tuple]] = {}  # {page_idx: {zone_id: (x,y,w,h)}}
        # Per-file zone storage for batch mode (stores _per_page_zones for each file)
        self._per_file_zones: Dict[str, Dict[int, Dict[str, tuple]]] = {}  # {file_path: _per_page_zones}
        self._current_file_path: str = ""  # Currently loaded file path
        self._batch_base_dir: str = ""  # Batch folder for persistence
        self._zones_loading: bool = False  # Flag to prevent saving during initial zone load

        self.setFrameStyle(QFrame.NoFrame)
        self.setStyleSheet("background-color: #E5E7EB;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Title bar with label and close button
        title_bar = QWidget()
        title_bar.setFixedHeight(32)  # Fixed height to ensure button fits
        title_bar.setStyleSheet("background-color: #F3F4F6; border-bottom: 1px solid #D1D5DB;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(4, 0, 4, 0)  # Tight left margin for nav buttons
        title_layout.setSpacing(4)
        
        # Navigation buttons (only for before panel, hidden by default)
        self.prev_btn = None
        self.next_btn = None
        self.file_counter_label = None
        self._batch_mode = False

        if show_overlay:
            # Prev button [←]
            self.prev_btn = QPushButton("◂")
            self.prev_btn.setFixedSize(22, 22)
            self.prev_btn.setCursor(Qt.PointingHandCursor)
            self.prev_btn.setToolTip("File trước ( [ )")
            self.prev_btn.setStyleSheet("""
                QPushButton {
                    background-color: #D1D5DB;
                    border: none;
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: bold;
                    color: #4B5563;
                }
                QPushButton:hover {
                    background-color: #3B82F6;
                    color: white;
                }
                QPushButton:disabled {
                    background-color: #E5E7EB;
                    color: #9CA3AF;
                }
            """)
            self.prev_btn.clicked.connect(self.prev_file_requested.emit)
            self.prev_btn.setVisible(False)
            title_layout.addWidget(self.prev_btn)

            # Next button [→]
            self.next_btn = QPushButton("▸")
            self.next_btn.setFixedSize(22, 22)
            self.next_btn.setCursor(Qt.PointingHandCursor)
            self.next_btn.setToolTip("File tiếp theo ( ] )")
            self.next_btn.setStyleSheet("""
                QPushButton {
                    background-color: #D1D5DB;
                    border: none;
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: bold;
                    color: #4B5563;
                }
                QPushButton:hover {
                    background-color: #3B82F6;
                    color: white;
                }
                QPushButton:disabled {
                    background-color: #E5E7EB;
                    color: #9CA3AF;
                }
            """)
            self.next_btn.clicked.connect(self.next_file_requested.emit)
            self.next_btn.setVisible(False)
            title_layout.addWidget(self.next_btn)

            # File counter label (X/Y)
            self.file_counter_label = QLabel()
            self.file_counter_label.setStyleSheet("""
                QLabel {
                    font-size: 11px;
                    color: #6B7280;
                    background-color: transparent;
                    margin-left: 4px;
                }
            """)
            self.file_counter_label.setVisible(False)
            title_layout.addWidget(self.file_counter_label)

        # Title label
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("""
            QLabel {
                font-weight: normal;
                font-size: 13px;
                color: #374151;
                background-color: transparent;
            }
        """)
        title_layout.addWidget(self.title_label, stretch=1)

        # Close button (X) - only for before panel (show_overlay=True)
        self.close_btn = None
        self.collapse_btn = None
        if show_overlay:
            self.close_btn = QPushButton("×")
            self.close_btn.setFixedSize(22, 22)
            self.close_btn.setCursor(Qt.PointingHandCursor)  # Show hand cursor on button
            self.close_btn.setStyleSheet("""
                QPushButton {
                    background-color: #D1D5DB;
                    border: none;
                    border-radius: 4px;
                    font-size: 16px;
                    font-weight: bold;
                    color: #4B5563;
                    padding: 0;
                    margin: 0;
                    padding-bottom: 2px;
                }
                QPushButton:hover {
                    color: white;
                    background-color: #EF4444;
                }
            """)
            self.close_btn.setToolTip("Đóng file")
            self.close_btn.clicked.connect(self._on_close_clicked)
            self.close_btn.setVisible(False)  # Hidden by default
            title_layout.addWidget(self.close_btn)
        else:
            # Collapse button (>) for after panel (Đích)
            self.collapse_btn = QPushButton("›")
            self.collapse_btn.setFixedSize(22, 22)
            self.collapse_btn.setCursor(Qt.PointingHandCursor)
            self.collapse_btn.setStyleSheet("""
                QPushButton {
                    background-color: #D1D5DB;
                    border: none;
                    border-radius: 4px;
                    font-size: 18px;
                    font-weight: bold;
                    color: #4B5563;
                    padding: 0;
                    margin: 0;
                }
                QPushButton:hover {
                    color: white;
                    background-color: #3B82F6;
                }
            """)
            self.collapse_btn.setToolTip("Ẩn/hiện panel Đích")
            self.collapse_btn.clicked.connect(self._on_collapse_clicked)
            title_layout.addWidget(self.collapse_btn)
        
        layout.addWidget(title_bar)

        # Progress bar container (2px) - holds both page loading and detection bars
        self._progress_bar = None
        self._progress_bar_fill = None
        self._detection_progress_fill = None
        self._page_loading_active = False  # Track if page loading progress is active
        self._detection_active = False  # Track if detection progress is active
        # Smooth animation for detection progress
        self._detection_current_progress = 0.0  # Current displayed progress (float for smooth)
        self._detection_target_progress = 0  # Target progress (int 0-100)
        self._detection_anim_timer = None
        if show_overlay:
            # Container for progress bars
            self._progress_bar = QWidget()
            self._progress_bar.setFixedHeight(2)
            self._progress_bar.setStyleSheet("background-color: #E5E7EB;")  # Gray background

            progress_layout = QHBoxLayout(self._progress_bar)
            progress_layout.setContentsMargins(0, 0, 0, 0)
            progress_layout.setSpacing(0)

            # Page loading progress fill (blue)
            self._progress_bar_fill = QWidget()
            self._progress_bar_fill.setFixedHeight(2)
            self._progress_bar_fill.setStyleSheet("background-color: #3B82F6;")  # Blue fill
            self._progress_bar_fill.setFixedWidth(0)
            progress_layout.addWidget(self._progress_bar_fill)
            progress_layout.addStretch()

            self._progress_bar.setVisible(False)
            layout.addWidget(self._progress_bar)

            # Detection progress fill (red) - overlays blue, child of container
            self._detection_progress_fill = QWidget(self._progress_bar)
            self._detection_progress_fill.setFixedHeight(2)
            self._detection_progress_fill.setStyleSheet("background-color: rgba(220, 38, 38, 0.6);")
            self._detection_progress_fill.setGeometry(0, 0, 0, 2)
            self._detection_progress_fill.setVisible(False)
            self._detection_progress_fill.raise_()

            # Animation timer for smooth progress (8ms = ~120fps for ultra smooth)
            self._detection_anim_timer = QTimer()
            self._detection_anim_timer.setInterval(8)
            self._detection_anim_timer.timeout.connect(self._animate_detection_progress)

        # Content area: [ThumbnailPanel (Gốc only)] + [GraphicsView]
        self._content_widget = QWidget()
        self._content_widget.setStyleSheet("background-color: #E5E7EB;")
        self._content_layout = QHBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)

        # Thumbnail panel (only for Gốc panel = show_overlay=True)
        self._thumbnail_panel = None
        if show_overlay:
            self._thumbnail_panel = ThumbnailPanel()
            self._thumbnail_panel.page_clicked.connect(self._on_thumbnail_page_clicked)
            self._thumbnail_panel.collapsed_changed.connect(self._on_thumbnail_collapsed_changed)
            self._content_layout.addWidget(self._thumbnail_panel)

        # Graphics view - gray background
        self.scene = QGraphicsScene()
        self.scene.setBackgroundBrush(QBrush(QColor(229, 231, 235)))  # Gray #E5E7EB

        self.view = ContinuousGraphicsView()
        self.view.setScene(self.scene)
        self.view.setStyleSheet("background-color: #E5E7EB; border: none;")
        self.view.rect_drawn.connect(self._on_rect_drawn)
        self.view.file_dropped.connect(self.file_dropped.emit)
        self.view.folder_dropped.connect(self.folder_dropped.emit)
        self.view.files_dropped.connect(self.files_dropped.emit)
        self._content_layout.addWidget(self.view)

        layout.addWidget(self._content_widget)

        # Show placeholder only for before panel (show_overlay=True)
        if show_overlay:
            self._add_placeholder()
    
    def set_title(self, title: str):
        """Update the title label text"""
        self.title_label.setText(title)
        # Show close button only when file is open (title contains path)
        # Title format when file open: "Gốc: /path/to/file.pdf"
        has_file = False
        if ": " in title:
            parts = title.split(": ", 1)
            if len(parts) > 1 and parts[1].strip():
                has_file = True
        if self.close_btn is not None:
            self.close_btn.setVisible(has_file)
    
    def _on_close_clicked(self):
        """Handle close button click"""
        self.close_requested.emit()

    def _on_collapse_clicked(self):
        """Handle collapse button click"""
        self.collapse_requested.emit()

    def _on_thumbnail_page_clicked(self, page_index: int):
        """Handle thumbnail click - emit signal to parent, let DualPreviewWidget handle scroll"""
        # Don't scroll here - DualPreviewWidget will handle all scrolling with proper skip flag
        self.thumbnail_page_clicked.emit(page_index)

    def _on_thumbnail_collapsed_changed(self, collapsed: bool):
        """Handle thumbnail panel collapse state change"""
        self.thumbnail_collapsed_changed.emit(collapsed)

    def update_thumbnail_highlight(self, page_index: int, scroll: bool = True):
        """Update thumbnail highlight for current visible page

        Args:
            page_index: Page to highlight
            scroll: If True, scroll thumbnail into view. Default True when called from
                   preview scroll detection. False when called after user clicks thumbnail.
        """
        if self._thumbnail_panel is not None:
            self._thumbnail_panel.set_current_page(page_index, scroll=scroll)

    def is_thumbnail_collapsed(self) -> bool:
        """Check if thumbnail panel is collapsed"""
        if self._thumbnail_panel is not None:
            return self._thumbnail_panel.is_collapsed()
        return True  # No panel = collapsed

    def get_thumbnail_width(self) -> int:
        """Get current thumbnail panel width"""
        if self._thumbnail_panel is not None:
            return self._thumbnail_panel.get_width()
        return 0

    def show_progress_bar(self):
        """Show the page loading progress bar (blue)"""
        self._page_loading_active = True
        if self._progress_bar is not None:
            self._progress_bar.setVisible(True)
            self.set_progress(0)

    def hide_progress_bar(self):
        """Hide the page loading progress bar (blue)"""
        self._page_loading_active = False
        if self._progress_bar_fill is not None:
            self._progress_bar_fill.setFixedWidth(0)
        # Only hide container if detection is also not active
        if self._progress_bar is not None and not self._detection_active:
            self._progress_bar.setVisible(False)

    def set_progress(self, percent: int):
        """Set page loading progress bar percentage (0-100)"""
        if self._progress_bar_fill is not None:
            parent_width = self._progress_bar.width() if self._progress_bar else 100
            fill_width = int(parent_width * percent / 100)
            self._progress_bar_fill.setFixedWidth(fill_width)

    def show_detection_progress(self):
        """Show detection progress bar (red, overlays page loading bar)"""
        self._detection_active = True
        self._detection_current_progress = 0.0  # Reset animation state
        self._detection_target_progress = 0
        if self._progress_bar is not None:
            self._progress_bar.setVisible(True)
        if self._detection_progress_fill is not None:
            self._detection_progress_fill.setVisible(True)
            self._detection_progress_fill.raise_()
            self._detection_progress_fill.setGeometry(0, 0, 0, 2)

    def hide_detection_progress(self):
        """Hide detection progress bar (red)"""
        self._detection_active = False
        # Stop animation timer (guard against Qt already deleting the timer)
        try:
            if self._detection_anim_timer is not None:
                self._detection_anim_timer.stop()
        except RuntimeError:
            pass  # Timer already deleted by Qt
        self._detection_current_progress = 0.0
        self._detection_target_progress = 0
        if self._detection_progress_fill is not None:
            self._detection_progress_fill.setVisible(False)
            self._detection_progress_fill.setGeometry(0, 0, 0, 2)
        # Only hide container if page loading is also not active
        if self._progress_bar is not None and not self._page_loading_active:
            self._progress_bar.setVisible(False)

    def set_detection_progress(self, percent: int):
        """Set detection progress bar percentage (0-100) with smooth animation"""
        self._detection_target_progress = percent
        # Start animation timer if not running
        if self._detection_anim_timer is not None and not self._detection_anim_timer.isActive():
            self._detection_anim_timer.start()

    def _animate_detection_progress(self):
        """Animate progress bar smoothly towards target (called by timer)"""
        if self._detection_progress_fill is None or self._progress_bar is None:
            return

        diff = self._detection_target_progress - self._detection_current_progress
        if abs(diff) < 0.05:
            # Close enough, snap to target
            self._detection_current_progress = self._detection_target_progress
            if self._detection_anim_timer is not None:
                self._detection_anim_timer.stop()
        else:
            # Ultra smooth: fixed step of 0.3% per frame + tiny ease-out
            step = min(0.3, abs(diff) * 0.05)
            if diff > 0:
                self._detection_current_progress += step
            else:
                self._detection_current_progress -= step

        # Update visual
        parent_width = self._progress_bar.width()
        fill_width = int(parent_width * self._detection_current_progress / 100)
        self._detection_progress_fill.setGeometry(0, 0, fill_width, 2)

    def set_collapse_button_icon(self, collapsed: bool):
        """Update collapse button icon based on state"""
        if self.collapse_btn:
            self.collapse_btn.setText("‹" if collapsed else "›")
            self.collapse_btn.setToolTip("Mở rộng panel Đích" if collapsed else "Thu gọn panel Đích")

    def set_batch_mode(self, enabled: bool, current: int = 0, total: int = 0):
        """Show/hide navigation buttons for batch mode"""
        self._batch_mode = enabled
        if self.prev_btn:
            self.prev_btn.setVisible(enabled)
        if self.next_btn:
            self.next_btn.setVisible(enabled)
        if self.file_counter_label:
            self.file_counter_label.setVisible(enabled)
        if enabled:
            self.set_file_index(current, total)

    def set_file_index(self, current: int, total: int):
        """Update file counter and button states. current is 0-based."""
        if self.file_counter_label:
            self.file_counter_label.setText(f"({current + 1}/{total})")
        if self.prev_btn:
            self.prev_btn.setEnabled(current > 0)
        if self.next_btn:
            self.next_btn.setEnabled(current < total - 1)

    def set_view_mode(self, mode: str):
        """Set view mode: 'continuous' or 'single'"""
        if mode not in ('continuous', 'single'):
            return
        if self._view_mode != mode:
            self._view_mode = mode
            self._rebuild_scene()
    
    def set_current_page(self, index: int):
        """Set current page index - scroll in continuous mode, rebuild in single mode"""
        if 0 <= index < len(self._pages):
            self._current_page = index
            if self._view_mode == 'single':
                self._rebuild_scene()
            elif self._view_mode == 'continuous' and index < len(self._page_positions):
                # Scroll to page position in continuous mode
                y_pos = self._page_positions[index]
                self.view.verticalScrollBar().setValue(int(y_pos * self.view._zoom))
    
    def get_current_page(self) -> int:
        """Get current page index"""
        return self._current_page
    
    def set_page_filter(self, filter_mode: str):
        """Set page filter: 'all', 'odd', 'even', 'none'

        Filter only affects where NEW zones are added.
        Existing zones are always displayed (like layers).
        """
        if filter_mode not in ('all', 'odd', 'even', 'none'):
            return
        if self._page_filter != filter_mode:
            self._page_filter = filter_mode
            # Don't clear per_page_zones - keep existing zones (layers)
            # Just update display (which always shows all zones)
            if self.show_overlay:
                if self._view_mode == 'single':
                    self._recreate_zone_overlays_single()
                else:
                    self._recreate_zone_overlays()

    def clear_all_zones(self):
        """Clear all zones from all pages (reset per_page_zones)"""
        self._per_page_zones.clear()
        for page_idx in range(len(self._pages)):
            self._per_page_zones[page_idx] = {}
        # Recreate overlays (will be empty)
        if self.show_overlay:
            if self._view_mode == 'single':
                self._recreate_zone_overlays_single()
            else:
                self._recreate_zone_overlays()

    def clear_current_page_zones(self):
        """Clear zones only for current page (Tự do zones)"""
        page_idx = self._current_page
        if page_idx in self._per_page_zones:
            self._per_page_zones[page_idx] = {}
        # Recreate overlays for current page
        if self.show_overlay:
            if self._view_mode == 'single':
                self._recreate_zone_overlays_single()
            else:
                self._recreate_zone_overlays()

    def clear_zone_rieng(self):
        """Clear only Zone riêng (custom_*, protect_*) from all pages, keep Zone chung (corner_*, margin_*)"""
        for page_idx in list(self._per_page_zones.keys()):
            page_zones = self._per_page_zones[page_idx]
            # Keep only Zone chung (corner_*, margin_*)
            self._per_page_zones[page_idx] = {
                zone_id: zone_data
                for zone_id, zone_data in page_zones.items()
                if zone_id.startswith('corner_') or zone_id.startswith('margin_')
            }
        # Recreate overlays
        if self.show_overlay:
            if self._view_mode == 'single':
                self._recreate_zone_overlays_single()
            else:
                self._recreate_zone_overlays()

    def clear_zone_chung(self):
        """Clear only Zone chung (corner_*, margin_*) from all pages, keep Zone riêng (custom_*, protect_*)"""
        for page_idx in list(self._per_page_zones.keys()):
            page_zones = self._per_page_zones[page_idx]
            # Keep only Zone riêng (custom_*, protect_*)
            self._per_page_zones[page_idx] = {
                zone_id: zone_data
                for zone_id, zone_data in page_zones.items()
                if not zone_id.startswith('corner_') and not zone_id.startswith('margin_')
            }
        # Recreate overlays
        if self.show_overlay:
            if self._view_mode == 'single':
                self._recreate_zone_overlays_single()
            else:
                self._recreate_zone_overlays()
        # Force scene update
        self.scene.update()

    def _init_per_page_zones(self):
        """Initialize per-page zones - start EMPTY for 'none' mode (Tự do)

        In 'none' mode, each page starts empty and zones are added individually
        to the current page when user draws or selects them.
        """
        self._per_page_zones.clear()
        for page_idx in range(len(self._pages)):
            self._per_page_zones[page_idx] = {}
        # Don't copy zone_definitions - start empty, user adds zones per page

    def set_batch_base_dir(self, batch_base_dir: str):
        """Set batch base directory for persistence."""
        self._batch_base_dir = batch_base_dir

    def save_per_file_zones(self, file_path: str = None, persist: bool = True):
        """Save current _per_page_zones to per-file storage.

        Called before switching to a different file to preserve zones.
        Only saves Tự do zones (custom_*, protect_*), NOT Zone Chung (corners, edges).

        Args:
            file_path: File path to save zones for. Uses _current_file_path if None.
            persist: If True, also persist to disk for crash recovery.
        """
        path = file_path or self._current_file_path
        if not path:
            return

        # Don't save during initial zone loading (would overwrite persisted zones)
        if self._zones_loading:
            return

        # Only save Tự do zones (custom_*, protect_*), skip Zone Chung (corner_*, margin_*)
        zones_to_save = {}
        for page_idx, page_zones in self._per_page_zones.items():
            if page_zones:
                # Filter to only Tự do zones
                filtered_zones = {
                    zone_id: zone_data
                    for zone_id, zone_data in page_zones.items()
                    if not zone_id.startswith('corner_') and not zone_id.startswith('margin_')
                }
                if filtered_zones:
                    zones_to_save[page_idx] = filtered_zones

        # Track if we made any changes to _per_file_zones
        changed = False

        if zones_to_save:
            # Has zones to save - update storage
            self._per_file_zones[path] = zones_to_save
            changed = True
        elif path in self._per_file_zones:
            # No zones to save but path exists in storage - remove it
            # This handles the case when user clears all zones
            del self._per_file_zones[path]
            changed = True
        # else: no zones and path not in storage - nothing to do

        # Persist if we actually changed something
        if changed and persist:
            self._persist_zones_to_disk()

    def load_per_file_zones(self, file_path: str) -> bool:
        """Load saved per-page zones for a specific file.

        Called after loading a file to restore previously drawn zones.
        Only loads Tự do zones (custom_*, protect_*), NOT Zone Chung (corners, edges).

        Args:
            file_path: File path to load zones for.

        Returns:
            True if zones were loaded, False if no saved zones exist.
        """
        if file_path not in self._per_file_zones:
            return False

        saved_zones = self._per_file_zones[file_path]

        # Restore only Tự do zones (custom_*, protect_*) to _per_page_zones
        # Skip Zone Chung (corner_*, margin_*) - they use current global values
        # NOTE: Store zones for ALL pages, not just loaded ones. Visual overlays
        # will be created only for loaded pages, and zones for later pages will
        # appear when those pages load and scene rebuilds.
        for page_idx, page_zones in saved_zones.items():
            if page_idx not in self._per_page_zones:
                self._per_page_zones[page_idx] = {}
            for zone_id, zone_data in page_zones.items():
                # Only load Tự do zones, skip Zone Chung
                if not zone_id.startswith('corner_') and not zone_id.startswith('margin_'):
                    self._per_page_zones[page_idx][zone_id] = zone_data

        # Recreate visual overlays for loaded zones
        if self.show_overlay:
            if self._view_mode == 'single':
                self._recreate_zone_overlays_single()
            else:
                self._recreate_zone_overlays()
        # Force scene update
        self.scene.update()

        # Clear loading flag - zones are now fully loaded, safe to save
        self._zones_loading = False

        return True

    def set_current_file_path(self, file_path: str):
        """Set current file path for per-file zone tracking."""
        self._current_file_path = file_path

    def clear_per_file_zones(self, reset_paths: bool = False):
        """Clear all per-file zone storage.

        Args:
            reset_paths: If True, also clear _current_file_path and _batch_base_dir.
                        Use True only when completely closing batch mode.
        """
        self._per_file_zones.clear()
        # Persist the empty state to disk (unless closing batch mode)
        if not reset_paths:
            self._persist_zones_to_disk()
        if reset_paths:
            self._current_file_path = ""
            self._batch_base_dir = ""

    def _persist_zones_to_disk(self):
        """Persist per-file zones to disk (.xoaghim.json)."""
        # Use batch_base_dir or current file's parent folder
        base_dir = self._batch_base_dir
        if not base_dir and self._current_file_path:
            base_dir = str(Path(self._current_file_path).parent)
        if not base_dir:
            return
        from core.config_manager import get_config_manager
        get_config_manager().save_per_file_zones(base_dir, self._per_file_zones)

    def load_persisted_zones(self, batch_base_dir: str):
        """Load persisted zones from disk for crash recovery.

        Called when opening a batch folder to restore previous work.

        Args:
            batch_base_dir: Batch folder to load zones for.
        """
        self._batch_base_dir = batch_base_dir
        self._zones_loading = True  # Prevent saving during load
        # Clear old zones before loading new source
        self._per_file_zones.clear()
        self._per_page_zones.clear()
        from core.config_manager import get_config_manager
        persisted = get_config_manager().get_per_file_zones(batch_base_dir)
        if persisted:
            self._per_file_zones = persisted
        # Reset loading flag - disk load complete, safe to save future changes
        self._zones_loading = False

    def _should_apply_to_page(self, page_idx: int) -> bool:
        """Check if zones should be applied to this page based on filter"""
        # page_idx is 0-based, but user sees 1-based page numbers
        page_num = page_idx + 1
        if self._page_filter == 'all':
            return True
        elif self._page_filter == 'odd':
            return page_num % 2 == 1  # Odd pages: 1, 3, 5, ...
        elif self._page_filter == 'even':
            return page_num % 2 == 0  # Even pages: 2, 4, 6, ...
        elif self._page_filter == 'none':
            return True  # All pages have zones but independent
        return True
    
    def get_zone_rect_for_page(self, zone_id: str, page_idx: int) -> Optional[tuple]:
        """Get zone data for a specific page (used in per-page mode)

        Note: Returns raw storage format which varies by zone type:
        - corner_*: (w_px, h_px)
        - margin_*: (length_pct, depth_px)
        - custom_*: (x_pct, y_pct, w_pct, h_pct)
        """
        base_id = zone_id.rsplit('_', 1)[0] if '_' in zone_id else zone_id

        if self._page_filter == 'none':
            # Per-page mode: get from per_page_zones
            if page_idx in self._per_page_zones:
                return self._per_page_zones[page_idx].get(base_id)

        # Sync mode: get from zone definitions (fallback to percentage format)
        for zdef in self._zone_definitions:
            if zdef.id == base_id:
                return (zdef.x, zdef.y, zdef.width, zdef.height)
        return None
    
    def set_pages(self, pages: List[np.ndarray]):
        """Set danh sách ảnh các trang"""
        # Create own list to avoid reference issues with parent widget
        self._pages = list(pages) if pages else []
        self._total_pages = len(self._pages)
        self._current_page = 0  # Reset to first page
        # Clear per_page_zones when loading new file
        # This ensures zones will be re-added by set_zone_definitions
        self._per_page_zones.clear()
        self._rebuild_scene()

    def init_sliding_window(self, total_pages: int, initial_pages: List[np.ndarray] = None):
        """Initialize sliding window mode with placeholder pages

        Args:
            total_pages: Total number of pages in file
            initial_pages: First few pages already loaded (optional)
        """
        self._total_pages = total_pages
        # Initialize with None placeholders
        self._pages = [None] * total_pages
        # Fill in initial pages if provided
        if initial_pages:
            for i, page in enumerate(initial_pages):
                if i < total_pages:
                    self._pages[i] = page
        self._current_page = 0
        self._per_page_zones.clear()
        self._rebuild_scene()

    def update_window_pages(self, page_updates: dict):
        """Update specific pages in sliding window

        Args:
            page_updates: {page_idx: image} dict, image can be None to unload
        """
        need_recenter = False
        for page_idx, image in page_updates.items():
            if 0 <= page_idx < len(self._pages):
                self._pages[page_idx] = image
                # Update graphics item if exists
                if page_idx < len(self._page_items):
                    old_pixmap = self._page_items[page_idx].pixmap()
                    old_w = old_pixmap.width() if old_pixmap else 0

                    if image is not None:
                        pixmap = self._numpy_to_pixmap(image)
                    else:
                        # Get size from existing item or default
                        w = old_pixmap.width() if old_pixmap else 800
                        h = old_pixmap.height() if old_pixmap else 1100
                        pixmap = self._create_placeholder_pixmap(w, h, page_idx)

                    self._page_items[page_idx].setPixmap(pixmap)

                    # Check if size changed - need to recenter
                    if pixmap.width() != old_w:
                        need_recenter = True

        # Recenter all pages if any page changed size
        if need_recenter:
            self._recenter_all_pages()

        # Update thumbnail panel if exists (Gốc panel only) - only if not using progressive loading
        # When using progressive loading, thumbnails are set separately via set_thumbnail_pages()
        # if self._thumbnail_panel is not None:
        #     self._thumbnail_panel.set_pages(pages)

    def _recenter_all_pages(self):
        """Recenter all pages horizontally after size changes"""
        if not self._page_items:
            return

        # Find max width from ALL page items (loaded + placeholders)
        max_width = 0
        for item in self._page_items:
            pixmap = item.pixmap()
            if pixmap:
                max_width = max(max_width, pixmap.width())

        if max_width == 0:
            return

        # Recenter ALL pages (position calc is fast)
        for item in self._page_items:
            pixmap = item.pixmap()
            if pixmap:
                x = (max_width - pixmap.width()) / 2
                item.setPos(x, item.pos().y())

        # Update scene rect
        scene_rect = self.scene.sceneRect()
        self.scene.setSceneRect(0, 0, max_width, scene_rect.height())

        # Refresh zone overlays after position change (only loaded pages)
        if self.show_overlay:
            self._recreate_zone_overlays()

        # Refresh draw mode bounds
        self._refresh_draw_mode_bounds()

    def set_thumbnail_pages(self, pages: List[np.ndarray]):
        """Set thumbnail images separately (can be different DPI from preview)"""
        if self._thumbnail_panel is not None:
            self._thumbnail_panel.set_pages(pages)

    def start_thumbnail_loading(self, total_pages: int):
        """Start progressive thumbnail loading"""
        if self._thumbnail_panel is not None:
            self._thumbnail_panel.start_loading(total_pages)

    def add_thumbnail(self, index: int, image: np.ndarray):
        """Add single thumbnail during progressive loading"""
        if self._thumbnail_panel is not None:
            self._thumbnail_panel.add_thumbnail(index, image)

    def finish_thumbnail_loading(self):
        """Finish thumbnail loading"""
        if self._thumbnail_panel is not None:
            self._thumbnail_panel.finish_loading()

    def set_thumbnails(self, thumbnails: list):
        """Set all thumbnails at once from cache (optimized bulk loading)"""
        if self._thumbnail_panel is not None:
            self._thumbnail_panel.set_thumbnails_bulk(thumbnails)

    def pause_thumbnail_updates(self):
        """Pause thumbnail updates for bulk loading"""
        if self._thumbnail_panel is not None:
            self._thumbnail_panel.pause_updates()

    def repaint_thumbnails(self):
        """Force immediate repaint of thumbnail panel"""
        if self._thumbnail_panel is not None:
            self._thumbnail_panel.repaint()

    def clear_thumbnails(self):
        """Clear all thumbnails from the thumbnail panel"""
        if self._thumbnail_panel is not None:
            self._thumbnail_panel.set_pages([])

    def add_page(self, page: np.ndarray):
        """Add single page to preview (for background loading)

        This method appends page to list. Scene is rebuilt at the end
        of background loading to avoid visual issues.
        """
        if page is None:
            return
        # Make a copy to ensure numpy array memory is properly managed
        self._pages.append(page.copy())

    def refresh_scene(self):
        """Rebuild scene with all pages. Call at end of background loading."""
        # Ensure zones are applied to all pages (including newly loaded ones)
        # This handles the case when pages are loaded progressively
        self._extend_zones_to_new_pages()
        self._rebuild_scene()

    def _extend_zones_to_new_pages(self):
        """Extend zone data to newly loaded pages.

        When pages are loaded progressively, set_zone_definitions() might only
        apply zones to pages available at that time. This method ensures zones
        with 'all/odd/even' filter are applied to new pages.
        """
        if not self._pages or not self._zone_definitions:
            return

        total_pages = len(self._pages)

        # Ensure _per_page_zones has entries for all pages
        for page_idx in range(total_pages):
            if page_idx not in self._per_page_zones:
                self._per_page_zones[page_idx] = {}

        # Get pages that have zone data (from first zone we find)
        # Zones with 'all' filter should be on all pages
        for zone in self._zone_definitions:
            if not zone.enabled:
                continue

            zone_page_filter = getattr(zone, 'page_filter', 'all')
            target_page = getattr(zone, 'target_page', -1)

            # Skip Zone Riêng (per-page zones) - they have specific target pages
            if target_page >= 0 or zone_page_filter == 'none':
                continue

            # Get which pages should have this zone based on filter
            pages_should_have = self._get_pages_for_zone_filter(zone_page_filter)

            # Add zone to pages that don't have it yet
            for page_idx in pages_should_have:
                if page_idx not in self._per_page_zones:
                    self._per_page_zones[page_idx] = {}
                if zone.id not in self._per_page_zones[page_idx]:
                    zone_data = self._calculate_initial_zone_data(zone, page_idx)
                    self._per_page_zones[page_idx][zone.id] = zone_data

    def _rebuild_scene(self):
        """Xây dựng lại scene với tất cả các trang hoặc 1 trang"""
        self.scene.clear()
        self._page_items.clear()
        self._zones.clear()
        self._page_positions.clear()
        self._has_placeholder = False
        self._placeholder_file_rect = None
        self._placeholder_folder_rect = None
        self._file_icon_normal = []
        self._file_icon_hover = []
        self._folder_icon_normal = []
        self._folder_icon_hover = []
        # Clear protected regions
        if hasattr(self, '_protected_region_items'):
            self._protected_region_items.clear()
        # Reset cursor on both view and viewport
        self.view.unsetCursor()
        self.view.viewport().unsetCursor()
        # Use NoDrag to allow zone items to show their cursors
        self.view.setDragMode(QGraphicsView.NoDrag)
        
        if not self._pages:
            # Show placeholder only for before panel (show_overlay=True)
            if self.show_overlay:
                self._add_placeholder()
            return
        
        if self._view_mode == 'single':
            self._rebuild_scene_single()
        else:
            self._rebuild_scene_continuous()

    def _rebuild_scene_continuous(self):
        """Build scene with all pages (continuous scroll mode)"""
        y_offset = self.PAGE_SPACING
        max_width = 0

        # Get default size from first loaded page or use default
        default_size = (800, 1100)  # A4 approx at 150 DPI
        for page_img in self._pages:
            if page_img is not None:
                default_size = (page_img.shape[1], page_img.shape[0])
                break

        for page_idx, page_img in enumerate(self._pages):
            if page_img is not None:
                # Convert to QPixmap
                pixmap = self._numpy_to_pixmap(page_img)
                page_w, page_h = pixmap.width(), pixmap.height()
            else:
                # Create placeholder for unloaded page
                pixmap = self._create_placeholder_pixmap(default_size[0], default_size[1], page_idx)
                page_w, page_h = default_size

            # Create item
            item = QGraphicsPixmapItem(pixmap)

            # Center horizontally (sẽ điều chỉnh sau)
            item.setPos(0, y_offset)

            self.scene.addItem(item)
            self._page_items.append(item)
            self._page_positions.append(y_offset)

            max_width = max(max_width, page_w)
            y_offset += page_h + self.PAGE_SPACING

        # Center all pages horizontally
        for item in self._page_items:
            x = (max_width - item.pixmap().width()) / 2
            item.setPos(x, item.pos().y())

        # Update scene rect
        self.scene.setSceneRect(0, 0, max_width, y_offset)

        # Recreate zone overlays
        if self.show_overlay:
            self._recreate_zone_overlays()

        # Refresh draw mode bounds after page positions changed
        self._refresh_draw_mode_bounds()

    def _create_placeholder_pixmap(self, width: int, height: int, page_idx: int) -> QPixmap:
        """Create placeholder pixmap for unloaded page"""
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor("#F3F4F6"))  # Light gray background

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw border
        painter.setPen(QPen(QColor("#D1D5DB"), 2))
        painter.drawRect(1, 1, width - 2, height - 2)

        # Draw page number text
        painter.setPen(QColor("#9CA3AF"))
        font = QFont("Arial", 24)
        painter.setFont(font)
        text = f"Trang {page_idx + 1}"
        text_rect = painter.fontMetrics().boundingRect(text)
        x = (width - text_rect.width()) // 2
        y = (height + text_rect.height()) // 2
        painter.drawText(x, y, text)

        # Draw loading hint
        font.setPointSize(12)
        painter.setFont(font)
        hint = "Đang tải..."
        hint_rect = painter.fontMetrics().boundingRect(hint)
        painter.drawText((width - hint_rect.width()) // 2, y + 30, hint)

        painter.end()
        return pixmap

    def _rebuild_scene_single(self):
        """Build scene with single page only"""
        if not self._pages:
            return  # No pages loaded yet
        if self._current_page >= len(self._pages):
            self._current_page = len(self._pages) - 1
        if self._current_page < 0:
            self._current_page = 0

        page_img = self._pages[self._current_page]
        if page_img is not None:
            pixmap = self._numpy_to_pixmap(page_img)
        else:
            # Create placeholder for unloaded page in sliding window mode
            pixmap = self._create_placeholder_pixmap(800, 1000, self._current_page)
        
        # Create item
        item = QGraphicsPixmapItem(pixmap)
        item.setPos(self.PAGE_SPACING, self.PAGE_SPACING)
        
        self.scene.addItem(item)
        self._page_items.append(item)
        self._page_positions.append(self.PAGE_SPACING)
        
        # Update scene rect
        scene_width = pixmap.width() + self.PAGE_SPACING * 2
        scene_height = pixmap.height() + self.PAGE_SPACING * 2
        self.scene.setSceneRect(0, 0, scene_width, scene_height)

        # Recreate zone overlays for current page only
        if self.show_overlay:
            self._recreate_zone_overlays_single()

        # Refresh draw mode bounds after page positions changed
        self._refresh_draw_mode_bounds()

    def _add_placeholder(self):
        """Add placeholder with PDF document icon and Folder icon"""
        self._has_placeholder = True
        
        # Larger placeholder area
        placeholder_width = 500
        placeholder_height = 300
        
        # Spacing between icons
        icon_spacing = 80
        
        # === LEFT ICON: PDF Document (Mở file pdf) ===
        icon_width = 36  # increased 50% from 24
        icon_height = 45  # increased 50% from 30
        file_icon_x = placeholder_width / 2 - icon_spacing - icon_width / 2
        icon_y = placeholder_height / 2 - 30
        corner_size = 11  # increased 50% from 7
        cobalt_blue = QColor(0, 71, 171)
        gray = QColor(140, 140, 140)

        # Create PDF document path (for both normal and hover icons)
        def create_pdf_path():
            path = QPainterPath()
            path.moveTo(file_icon_x, icon_y)
            path.lineTo(file_icon_x, icon_y + icon_height)
            path.lineTo(file_icon_x + icon_width, icon_y + icon_height)
            path.lineTo(file_icon_x + icon_width, icon_y + corner_size)
            path.lineTo(file_icon_x + icon_width - corner_size, icon_y)
            path.closeSubpath()
            # Folded corner
            path.moveTo(file_icon_x + icon_width - corner_size, icon_y)
            path.lineTo(file_icon_x + icon_width - corner_size, icon_y + corner_size)
            path.lineTo(file_icon_x + icon_width, icon_y + corner_size)
            return path

        # Normal icon (gray outline, no fill)
        self._file_icon_normal = []
        gray_pen = QPen(gray, 1)
        pdf_path = create_pdf_path()
        normal_path_item = self.scene.addPath(pdf_path, gray_pen, QBrush(Qt.transparent))
        self._file_icon_normal.append(normal_path_item)

        # Normal PDF text
        pdf_text_normal = self.scene.addText("PDF")
        pdf_font = pdf_text_normal.font()
        pdf_font.setPixelSize(12)  # increased 50% from 8
        pdf_font.setBold(True)
        pdf_text_normal.setFont(pdf_font)
        pdf_text_normal.setDefaultTextColor(gray)
        pdf_rect = pdf_text_normal.boundingRect()
        pdf_text_normal.setPos(
            file_icon_x + (icon_width - pdf_rect.width()) / 2,
            icon_y + (icon_height - pdf_rect.height()) / 2 + 2
        )
        self._file_icon_normal.append(pdf_text_normal)

        # Hover icon (blue filled)
        self._file_icon_hover = []
        hover_path_item = self.scene.addPath(pdf_path, QPen(Qt.NoPen), QBrush(cobalt_blue))
        hover_path_item.setVisible(False)
        self._file_icon_hover.append(hover_path_item)

        # Hover PDF text (white)
        pdf_text_hover = self.scene.addText("PDF")
        pdf_text_hover.setFont(pdf_font)
        pdf_text_hover.setDefaultTextColor(QColor(255, 255, 255))
        pdf_text_hover.setPos(
            file_icon_x + (icon_width - pdf_rect.width()) / 2,
            icon_y + (icon_height - pdf_rect.height()) / 2 + 2
        )
        pdf_text_hover.setVisible(False)
        self._file_icon_hover.append(pdf_text_hover)

        # "Mở file pdf" text
        file_hint = self.scene.addText("Mở file pdf")
        file_hint_font = file_hint.font()
        file_hint_font.setPixelSize(13)  # same as menu font
        file_hint.setFont(file_hint_font)
        file_hint.setDefaultTextColor(gray)
        file_hint_rect = file_hint.boundingRect()
        file_hint.setPos(
            file_icon_x + (icon_width - file_hint_rect.width()) / 2,
            icon_y + icon_height + 8
        )
        self._file_hint_text = file_hint

        # Store click area for "Mở file" (larger area)
        self._placeholder_file_rect = QRectF(
            file_icon_x - 52, icon_y - 30,
            icon_width + 105, icon_height + file_hint_rect.height() + 90
        )
        
        # === RIGHT ICON: Folder (Mở thư mục) - rounded corners, thin line ===
        folder_icon_x = placeholder_width / 2 + icon_spacing - 21
        folder_width = 42  # increased 50% from 28
        folder_height = 30  # increased 50% from 20
        folder_y = icon_y + 8
        tab_width = 15  # increased 50% from 10
        tab_height = 8  # increased 50% from 5
        corner_r = 3  # increased 50% from 2

        # Create folder path (reusable for both normal and hover)
        def create_folder_path():
            path = QPainterPath()
            # Start from bottom-left (after corner)
            path.moveTo(folder_icon_x + corner_r, folder_y + folder_height)
            # Bottom edge
            path.lineTo(folder_icon_x + folder_width - corner_r, folder_y + folder_height)
            # Bottom-right corner
            path.quadTo(folder_icon_x + folder_width, folder_y + folder_height,
                       folder_icon_x + folder_width, folder_y + folder_height - corner_r)
            # Right edge
            path.lineTo(folder_icon_x + folder_width, folder_y + tab_height + corner_r)
            # Top-right corner
            path.quadTo(folder_icon_x + folder_width, folder_y + tab_height,
                       folder_icon_x + folder_width - corner_r, folder_y + tab_height)
            # Top edge (after tab)
            path.lineTo(folder_icon_x + tab_width + 3, folder_y + tab_height)
            # Tab diagonal
            path.lineTo(folder_icon_x + tab_width, folder_y + corner_r)
            # Tab top-right corner
            path.quadTo(folder_icon_x + tab_width, folder_y,
                       folder_icon_x + tab_width - corner_r, folder_y)
            # Tab top edge
            path.lineTo(folder_icon_x + corner_r, folder_y)
            # Top-left corner
            path.quadTo(folder_icon_x, folder_y,
                       folder_icon_x, folder_y + corner_r)
            # Left edge
            path.lineTo(folder_icon_x, folder_y + folder_height - corner_r)
            # Bottom-left corner
            path.quadTo(folder_icon_x, folder_y + folder_height,
                       folder_icon_x + corner_r, folder_y + folder_height)
            return path

        folder_path = create_folder_path()

        # Normal folder icon (gray outline, no fill)
        self._folder_icon_normal = []
        gray_pen = QPen(gray, 1)
        gray_pen.setCapStyle(Qt.RoundCap)
        gray_pen.setJoinStyle(Qt.RoundJoin)
        normal_folder_item = self.scene.addPath(folder_path, gray_pen, QBrush(Qt.transparent))
        self._folder_icon_normal.append(normal_folder_item)

        # Hover folder icon (blue filled)
        self._folder_icon_hover = []
        hover_folder_item = self.scene.addPath(folder_path, QPen(Qt.NoPen), QBrush(cobalt_blue))
        hover_folder_item.setVisible(False)
        self._folder_icon_hover.append(hover_folder_item)

        # "Mở thư mục" text
        folder_hint = self.scene.addText("Mở thư mục")
        folder_hint_font = folder_hint.font()
        folder_hint_font.setPixelSize(13)  # same as menu font
        folder_hint.setFont(folder_hint_font)
        folder_hint.setDefaultTextColor(QColor(140, 140, 140))
        folder_hint_rect = folder_hint.boundingRect()
        folder_hint.setPos(
            folder_icon_x + (folder_width - folder_hint_rect.width()) / 2,
            icon_y + icon_height + 8  # align with "Mở file" text
        )
        self._folder_hint_text = folder_hint
        
        # Store click area for "Mở thư mục" (larger area +80%)
        self._placeholder_folder_rect = QRectF(
            folder_icon_x - 52, icon_y - 30,
            folder_width + 105, icon_height + folder_hint_rect.height() + 90
        )
        
        self.scene.setSceneRect(0, 0, placeholder_width, placeholder_height)

        # Center the scene without scaling (show at 1:1)
        # Use deferred reset to ensure view has correct size (important on app startup)
        def _deferred_reset():
            self.view._zoom = 1.0
            self.view.resetTransform()
            self.view.centerOn(placeholder_width / 2, placeholder_height / 2)

        # Reset immediately AND defer to ensure both startup and file-close work correctly
        self.view._zoom = 1.0
        self.view.resetTransform()
        self.view.centerOn(placeholder_width / 2, placeholder_height / 2)
        QTimer.singleShot(0, _deferred_reset)
        
        # Disable drag mode when placeholder is shown
        self.view.setDragMode(QGraphicsView.NoDrag)
        
        # Enable mouse tracking for cursor updates (hand cursor outside, cross on icons)
        self.view.setMouseTracking(True)
        self.view.viewport().setMouseTracking(True)
        
        # Set cursor to open hand (cross only when hovering on icons)
        self.view.setCursor(Qt.OpenHandCursor)
        self.view.viewport().setCursor(Qt.OpenHandCursor)
        
        # Connect mouse events
        self.view.mousePressEvent = self._on_view_click
        self.view.mouseMoveEvent = self._on_view_mouse_move
        self.view.mouseReleaseEvent = self._on_view_release
        self.view.enterEvent = self._on_view_enter
        self.view.leaveEvent = self._on_view_leave
        
        # Enable drag and drop
        self.setAcceptDrops(True)
    
    def _on_view_enter(self, event):
        """Handle mouse enter to set cursor on placeholder"""
        if self._has_placeholder:
            self.view.setCursor(Qt.OpenHandCursor)
            self.view.viewport().setCursor(Qt.OpenHandCursor)
    
    def _on_view_leave(self, event):
        """Handle mouse leave to reset hover - show normal icons, hide hover icons"""
        if self._has_placeholder:
            gray = QColor(140, 140, 140)
            # Reset file icon - show normal, hide hover
            for item in getattr(self, '_file_icon_normal', []):
                item.setVisible(True)
            for item in getattr(self, '_file_icon_hover', []):
                item.setVisible(False)
            if hasattr(self, '_file_hint_text'):
                self._file_hint_text.setDefaultTextColor(gray)
            # Reset folder icon - show normal, hide hover
            for item in getattr(self, '_folder_icon_normal', []):
                item.setVisible(True)
            for item in getattr(self, '_folder_icon_hover', []):
                item.setVisible(False)
            if hasattr(self, '_folder_hint_text'):
                self._folder_hint_text.setDefaultTextColor(gray)
    
    def _on_view_mouse_move(self, event):
        """Handle mouse move to update cursor and hover effects on placeholder"""
        if self._has_placeholder:
            # Get mouse position in scene coordinates
            scene_pos = self.view.mapToScene(event.pos())

            # Colors
            cobalt_blue = QColor(0, 71, 171)  # Cobalt blue
            gray = QColor(140, 140, 140)

            # Check hover on file icon - toggle visibility of normal/hover icons
            file_hover = self._placeholder_file_rect and self._placeholder_file_rect.contains(scene_pos)
            folder_hover = self._placeholder_folder_rect and self._placeholder_folder_rect.contains(scene_pos)

            # Update cursor based on hover state
            if file_hover or folder_hover:
                self.view.setCursor(Qt.CrossCursor)
                self.view.viewport().setCursor(Qt.CrossCursor)
            else:
                self.view.setCursor(Qt.OpenHandCursor)
                self.view.viewport().setCursor(Qt.OpenHandCursor)

            if file_hover:
                # Show hover icon, hide normal icon
                for item in self._file_icon_normal:
                    item.setVisible(False)
                for item in self._file_icon_hover:
                    item.setVisible(True)
                if hasattr(self, '_file_hint_text'):
                    self._file_hint_text.setDefaultTextColor(cobalt_blue)
            else:
                # Show normal icon, hide hover icon
                for item in self._file_icon_normal:
                    item.setVisible(True)
                for item in self._file_icon_hover:
                    item.setVisible(False)
                if hasattr(self, '_file_hint_text'):
                    self._file_hint_text.setDefaultTextColor(gray)

            # Check hover on folder icon - toggle visibility of normal/hover icons
            if folder_hover:
                # Show hover icon, hide normal icon
                for item in self._folder_icon_normal:
                    item.setVisible(False)
                for item in self._folder_icon_hover:
                    item.setVisible(True)
                if hasattr(self, '_folder_hint_text'):
                    self._folder_hint_text.setDefaultTextColor(cobalt_blue)
            else:
                # Show normal icon, hide hover icon
                for item in self._folder_icon_normal:
                    item.setVisible(True)
                for item in self._folder_icon_hover:
                    item.setVisible(False)
                if hasattr(self, '_folder_hint_text'):
                    self._folder_hint_text.setDefaultTextColor(gray)

            # Force scene update
            self.scene.update()
        else:
            # Call ContinuousGraphicsView's mouseMoveEvent (for draw mode support)
            ContinuousGraphicsView.mouseMoveEvent(self.view, event)

    def _on_view_click(self, event):
        """Handle click on view when placeholder is shown"""
        if self._has_placeholder:
            # Get click position in scene coordinates
            scene_pos = self.view.mapToScene(event.pos())

            # Check which icon was clicked
            if self._placeholder_file_rect and self._placeholder_file_rect.contains(scene_pos):
                self.placeholder_clicked.emit()
            elif self._placeholder_folder_rect and self._placeholder_folder_rect.contains(scene_pos):
                self.folder_placeholder_clicked.emit()
        else:
            # Call ContinuousGraphicsView's mousePressEvent (for draw mode support)
            ContinuousGraphicsView.mousePressEvent(self.view, event)

    def _on_view_release(self, event):
        """Handle mouse release - route to ContinuousGraphicsView for draw mode"""
        # Always call ContinuousGraphicsView's mouseReleaseEvent (for draw mode support)
        ContinuousGraphicsView.mouseReleaseEvent(self.view, event)

    def dragEnterEvent(self, event):
        """Handle drag enter for file/folder drop"""
        if event.mimeData().hasUrls():
            # Accept any URL - check content in dropEvent
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragOverEvent(self, event):
        """Handle drag over"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Handle file/folder drop"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                path = url.toLocalFile()
                # Handle Windows file:///C:/path format
                if not path and url.toString().startswith('file:///'):
                    path = url.toString()[8:]
                if not path:
                    continue
                path = os.path.normpath(path)

                if os.path.isdir(path):
                    # Folder dropped - emit folder signal
                    self.folder_dropped.emit(path)
                    event.acceptProposedAction()
                    return
                elif path.lower().endswith('.pdf'):
                    # PDF file dropped
                    self.file_dropped.emit(path)
                    event.acceptProposedAction()
                    return
        event.ignore()
    
    def _numpy_to_pixmap(self, image: np.ndarray) -> QPixmap:
        """Convert numpy BGR to QPixmap

        IMPORTANT: QImage must be copied BEFORE numpy array goes out of scope.
        The .copy() on QImage copies the underlying buffer, preventing dangling
        pointer issues that cause Windows GDI handle leaks and crashes.
        """
        if len(image.shape) == 3:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            # CRITICAL: Copy QImage buffer immediately to prevent dangling pointer
            qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
        else:
            h, w = image.shape
            # CRITICAL: Copy QImage buffer immediately to prevent dangling pointer
            qimg = QImage(image.data, w, h, w, QImage.Format_Grayscale8).copy()
        return QPixmap.fromImage(qimg)
    
    def set_zone_definitions(self, zones: List[Zone]):
        """Set zone definitions - add new zones to pages based on current filter

        Filter logic (for ADDING new zones):
        - 'all': add to ALL pages
        - 'odd': add to odd pages (1, 3, 5...)
        - 'even': add to even pages (2, 4, 6...)
        - 'none' (Tự do): add to current page only

        Display: always show ALL zones in per_page_zones (no filter)

        IMPORTANT: Only manages Zone chung (global zones). Zone riêng (per-file zones)
        are managed separately and should not be affected by this method.
        """
        # Use stored IDs from previous call (not z.enabled check, since Zone objects are shared references)
        # _emit_zones() only passes enabled zones, so all zones in the list are "enabled"
        old_zone_chung_ids = getattr(self, '_last_zone_ids', set())
        new_zone_ids = {z.id for z in zones}  # All zones passed are enabled (filtered by _emit_zones)
        newly_added = new_zone_ids - old_zone_chung_ids
        # Only remove zones that were previously enabled Zone chung (not Zone riêng)
        newly_removed = old_zone_chung_ids - new_zone_ids
        # Store current zone IDs for next comparison
        self._last_zone_ids = new_zone_ids.copy()

        # Get zones already in _per_page_zones (to detect zones missing after file switch)
        existing_zone_ids = set()
        for page_zones in self._per_page_zones.values():
            existing_zone_ids.update(page_zones.keys())

        # Zones that need to be added: newly enabled OR missing from _per_page_zones
        zones_to_add = newly_added | (new_zone_ids - existing_zone_ids)

        # Ensure per_page_zones is initialized for all pages
        for page_idx in range(len(self._pages)):
            if page_idx not in self._per_page_zones:
                self._per_page_zones[page_idx] = {}

        # Add new zones to pages based on filter or target_page
        for zone in zones:
            if not zone.enabled:
                continue

            # Check if zone has specific target page (for Tự do mode)
            target_page = getattr(zone, 'target_page', -1)
            zone_page_filter = getattr(zone, 'page_filter', 'all')

            if target_page >= 0:
                # Zone has specific target page - ensure page entry exists
                if target_page not in self._per_page_zones:
                    self._per_page_zones[target_page] = {}
                # Add if not already exists (prevents overwriting user modifications)
                # Also add if zone_id is in zones_to_add (new or missing zone)
                if zone.id not in self._per_page_zones[target_page] or zone.id in zones_to_add:
                    # Always store zone data - use current page if target not loaded yet
                    # Zone coordinates are in % so they work regardless of page size
                    page_for_calc = min(target_page, len(self._pages) - 1) if self._pages else 0
                    zone_data = self._calculate_initial_zone_data(zone, page_for_calc)
                    self._per_page_zones[target_page][zone.id] = zone_data
            elif zone_page_filter != 'none' and zone.id in zones_to_add:
                # Global zones (not Tự do) - add to pages based on filter
                pages_to_add = self._get_pages_for_zone_filter(zone_page_filter)
                for page_idx in pages_to_add:
                    zone_data = self._calculate_initial_zone_data(zone, page_idx)
                    self._per_page_zones[page_idx][zone.id] = zone_data
            # else: Zone Riêng with no target_page - skip (shouldn't happen)

        # NOTE: Do NOT update existing zones here - user modifications must be preserved
        # User can reset a zone by disabling and re-enabling it

        # Remove disabled zones from ALL pages (global removal)
        for zone_id in newly_removed:
            for page_idx in self._per_page_zones:
                if zone_id in self._per_page_zones[page_idx]:
                    del self._per_page_zones[page_idx][zone_id]

        self._zone_definitions = zones
        if self.show_overlay:
            if self._view_mode == 'single':
                self._recreate_zone_overlays_single()
            else:
                self._recreate_zone_overlays()

    def _calculate_initial_zone_data(self, zone: Zone, page_idx: int) -> tuple:
        """Calculate initial zone data based on zone type.

        Storage formats (detected by zone_id prefix):
        - corner_*: (w_px, h_px) - 2 elements, position calculated from corner type
        - margin_*: (length_pct, depth_px) - 2 elements, hybrid storage
        - custom_*/protect_*: (x_pct, y_pct, w_pct, h_pct) - 4 elements, full percentage

        Args:
            zone: Zone definition
            page_idx: Index of the page

        Returns:
            tuple: Format depends on zone type
        """
        zone_id = zone.id.lower()

        if zone_id.startswith('corner_'):
            # Corners: store pixel size only (w_px, h_px)
            w_px = zone.width_px if zone.width_px > 0 else 130  # default 130px
            h_px = zone.height_px if zone.height_px > 0 else 130  # default 130px
            return (w_px, h_px)

        elif zone_id.startswith('margin_'):
            # Edges: store (length_pct, depth_px)
            # length_pct: percentage along edge (default 100% = 1.0)
            # depth_px: fixed pixel depth into page
            if zone_id in ('margin_top', 'margin_bottom'):
                length_pct = zone.width if zone.width > 0 else 1.0  # width is the "length" for top/bottom
                depth_px = zone.height_px if zone.height_px > 0 else 50  # default 50px
            else:  # margin_left, margin_right
                length_pct = zone.height if zone.height > 0 else 1.0  # height is the "length" for left/right
                depth_px = zone.width_px if zone.width_px > 0 else 50  # default 50px
            return (length_pct, depth_px)

        else:
            # Custom/protect zones: store (x_pct, y_pct, w_pct, h_pct)
            return (zone.x, zone.y, zone.width, zone.height)

    def _get_pages_for_filter(self) -> List[int]:
        """Get list of page indices based on current UI filter"""
        return self._get_pages_for_zone_filter(self._page_filter)

    def _get_pages_for_zone_filter(self, zone_filter: str) -> List[int]:
        """Get list of page indices based on specified zone filter

        Args:
            zone_filter: 'all', 'odd', 'even', or 'none'

        Returns:
            List of page indices to apply zone to
        """
        if not self._pages:
            return []

        all_pages = list(range(len(self._pages)))

        if zone_filter == 'all':
            return all_pages
        elif zone_filter == 'odd':
            return [i for i in all_pages if (i + 1) % 2 == 1]  # 1, 3, 5... (1-based)
        elif zone_filter == 'even':
            return [i for i in all_pages if (i + 1) % 2 == 0]  # 2, 4, 6... (1-based)
        elif zone_filter == 'none':
            return [self._current_page] if self._current_page < len(self._pages) else []
        return all_pages

    def _find_zone_def(self, zone_id: str) -> Optional[Zone]:
        """Find zone definition by ID"""
        for zd in self._zone_definitions:
            if zd.id == zone_id:
                return zd
        return None

    def _calculate_zone_pixels(self, zone_def: Optional[Zone], zone_coords: tuple,
                               img_w: int, img_h: int) -> tuple:
        """Calculate zone pixel coordinates from stored zone_coords.

        Handles different storage formats:
        - corner_*: (w_px, h_px) - 2 elements
        - margin_*: (length_pct, depth_px) - 2 elements
        - custom_*/protect_*: (x_pct, y_pct, w_pct, h_pct) - 4 elements

        Returns: (x, y, w, h) in pixels
        """
        zone_id = zone_def.id.lower() if zone_def else ''

        if zone_id.startswith('corner_') and len(zone_coords) == 2:
            # Corner: (w_px, h_px) - position calculated from corner type
            w_px, h_px = zone_coords
            if 'corner_tl' in zone_id:
                return (0, 0, w_px, h_px)
            elif 'corner_tr' in zone_id:
                return (img_w - w_px, 0, w_px, h_px)
            elif 'corner_bl' in zone_id:
                return (0, img_h - h_px, w_px, h_px)
            elif 'corner_br' in zone_id:
                return (img_w - w_px, img_h - h_px, w_px, h_px)
            else:
                return (0, 0, w_px, h_px)

        elif zone_id.startswith('margin_') and len(zone_coords) == 2:
            # Edge: (length_pct, depth_px)
            # Match Zone.to_pixels() logic: left/top aligned (no centering)
            length_pct, depth_px = zone_coords
            if zone_id == 'margin_top':
                # Top: width=length%, height=depth_px, at top-left
                w = int(length_pct * img_w)
                return (0, 0, w, depth_px)
            elif zone_id == 'margin_bottom':
                # Bottom: width=length%, height=depth_px, at bottom-left
                w = int(length_pct * img_w)
                return (0, img_h - depth_px, w, depth_px)
            elif zone_id == 'margin_left':
                # Left: width=depth_px, height=length%, at top-left
                h = int(length_pct * img_h)
                return (0, 0, depth_px, h)
            elif zone_id == 'margin_right':
                # Right: width=depth_px, height=length%, at top-right
                h = int(length_pct * img_h)
                return (img_w - depth_px, 0, depth_px, h)
            else:
                return (0, 0, int(length_pct * img_w), depth_px)

        else:
            # Custom/protect or legacy format: (x_pct, y_pct, w_pct, h_pct)
            if len(zone_coords) >= 4:
                return (
                    zone_coords[0] * img_w,
                    zone_coords[1] * img_h,
                    zone_coords[2] * img_w,
                    zone_coords[3] * img_h
                )
            elif len(zone_coords) == 2:
                # Fallback for 2-element format (corner/edge without matching zone_def)
                # Assume it's a corner at top-left
                return (0, 0, zone_coords[0], zone_coords[1])
            else:
                # Invalid format, return empty rect
                return (0, 0, 0, 0)

    def _create_zone_overlay_item(self, zone_id: str, zone_def: Optional[Zone],
                                   rect: QRectF, page_idx: int,
                                   page_pos: QPointF, page_rect: QRectF) -> ZoneItem:
        """Create a ZoneItem and connect its signals."""
        # Get zone_type from zone_def, or infer from zone_id (protect_* = protect, else = remove)
        if zone_def:
            zone_type = getattr(zone_def, 'zone_type', 'remove')
        elif zone_id.startswith('protect_'):
            zone_type = 'protect'
        else:
            zone_type = 'remove'
        zone_item = ZoneItem(f"{zone_id}_{page_idx}", rect, zone_type=zone_type)
        zone_item.setPos(page_pos)
        zone_item.set_bounds(page_rect)
        zone_item.signals.zone_changed.connect(self._on_zone_changed)
        zone_item.signals.zone_selected.connect(self._on_zone_selected)
        zone_item.signals.zone_delete.connect(self._on_zone_delete)
        zone_item.signals.zone_drag_started.connect(self._on_zone_drag_started)
        zone_item.signals.zone_drag_ended.connect(self._on_zone_drag_ended)
        return zone_item

    def _recreate_zone_overlays(self):
        """Tạo lại overlay zones cho tất cả trang (continuous mode)

        Optimization: Only create overlays for loaded pages (non-None in _pages)
        to improve performance with large files in sliding window mode.
        """
        # Only process pages that are actually loaded (not None placeholders)
        loaded_pages = [(i, item) for i, item in enumerate(self._page_items)
                        if i < len(self._pages) and self._pages[i] is not None]
        self._recreate_zone_overlays_for_pages(self._page_items, loaded_pages)

    def _recreate_zone_overlays_single(self):
        """Tạo lại overlay zones cho trang hiện tại (single page mode)"""
        if not self._pages or not self._page_items:
            self._clear_zone_overlays()
            return
        # Single mode: one item, but use current_page index for zone lookup
        self._recreate_zone_overlays_for_pages(
            self._page_items,
            [(self._current_page, self._page_items[0])]
        )

    def _clear_zone_overlays(self):
        """Remove all zone overlay items from scene

        CRITICAL: Must disconnect signals to prevent memory leaks.
        Windows GDI has strict handle limits (~10K per process).
        Signal connections keep references alive, preventing GC.

        Note: ZoneItem inherits from QGraphicsRectItem (not QObject),
        so deleteLater() is not available. Python GC handles cleanup
        after removeItem() and clearing references.
        """
        for zone in self._zones:
            try:
                # Disconnect all signals to prevent slot reference leaks
                zone.signals.zone_changed.disconnect()
                zone.signals.zone_selected.disconnect()
                zone.signals.zone_delete.disconnect()
                zone.signals.zone_drag_started.disconnect()
                zone.signals.zone_drag_ended.disconnect()
            except (RuntimeError, TypeError):
                pass  # Signal already disconnected or never connected

            try:
                if zone.scene():
                    self.scene.removeItem(zone)
            except RuntimeError:
                pass  # Item already deleted
        self._zones.clear()
        # Force scene update to clear any visual artifacts
        self.scene.update()

    def _recreate_zone_overlays_for_pages(self, page_items: list, page_iterator):
        """Create zone overlays for specified pages.

        Args:
            page_items: List of page items (for bounds reference)
            page_iterator: Iterator of (page_idx, page_item) tuples
        """
        self._clear_zone_overlays()

        if not self._pages:
            return

        for page_idx, page_item in page_iterator:
            page_rect = page_item.boundingRect()
            page_pos = page_item.pos()
            img_w, img_h = int(page_rect.width()), int(page_rect.height())

            page_zones = self._per_page_zones.get(page_idx, {})

            for zone_id, zone_coords in page_zones.items():
                zone_def = self._find_zone_def(zone_id)

                if zone_def and not zone_def.enabled:
                    continue

                zx, zy, zw, zh = self._calculate_zone_pixels(zone_def, zone_coords, img_w, img_h)
                rect = QRectF(zx, zy, zw, zh)

                zone_item = self._create_zone_overlay_item(
                    zone_id, zone_def, rect, page_idx, page_pos, page_rect
                )
                self.scene.addItem(zone_item)
                self._zones.append(zone_item)
    
    def update_page(self, page_idx: int, image: np.ndarray):
        """Cập nhật ảnh một trang"""
        print(f"[DEBUG] [{self._panel_title}] update_page: page_idx={page_idx}")
        if 0 <= page_idx < len(self._page_items) and page_idx < len(self._pages):
            pixmap = self._numpy_to_pixmap(image)
            self._page_items[page_idx].setPixmap(pixmap)
            self._pages[page_idx] = image
            print(f"[DEBUG] [{self._panel_title}] UPDATED page {page_idx}")
        else:
            print(f"[DEBUG] [{self._panel_title}] SKIPPED page {page_idx} (out of bounds)")
    
    def _on_zone_changed(self, zone_id: str):
        """Handle zone change - sync to other pages if in sync mode"""
        # zone_id format: "custom_1_0" -> base_id = "custom_1", page_idx = 0
        parts = zone_id.rsplit('_', 1)
        base_id = parts[0]
        page_idx = int(parts[1]) if len(parts) > 1 else 0

        # Find the changed zone item
        changed_zone = None
        for zone_item in self._zones:
            if zone_item.zone_id == zone_id:
                changed_zone = zone_item
                break

        if not changed_zone or page_idx >= len(self._page_items):
            self.zone_changed.emit(zone_id)
            return

        # Get page dimensions and zone pixel rect
        page_rect = self._page_items[page_idx].boundingRect()
        img_w, img_h = int(page_rect.width()), int(page_rect.height())
        zone_rect = changed_zone.rect()

        # Convert to correct storage format based on zone type
        zone_data = self._pixel_rect_to_zone_data(base_id, zone_rect, img_w, img_h)

        if self._page_filter != 'none':
            # Sync mode: sync to all pages
            self._sync_zone_to_pages(base_id, zone_data)
        else:
            # Per-page mode: store independently
            if page_idx not in self._per_page_zones:
                self._per_page_zones[page_idx] = {}
            self._per_page_zones[page_idx][base_id] = zone_data
            # Save immediately for crash recovery (Tự do mode)
            self.save_per_file_zones()

        self.zone_changed.emit(zone_id)

    def _pixel_rect_to_zone_data(self, zone_id: str, rect: QRectF, img_w: int, img_h: int) -> tuple:
        """Convert pixel rect from ZoneItem to correct storage format.

        Args:
            zone_id: Zone ID (e.g., 'corner_tl', 'margin_top', 'custom_1')
            rect: QRectF with pixel coordinates
            img_w, img_h: Page dimensions in pixels

        Returns:
            tuple: Correct format for storage
        """
        zone_id_lower = zone_id.lower()

        if zone_id_lower.startswith('corner_'):
            # Corners: store (w_px, h_px) only
            return (int(rect.width()), int(rect.height()))

        elif zone_id_lower.startswith('margin_'):
            # Edges: store (length_pct, depth_px)
            if zone_id_lower in ('margin_top', 'margin_bottom'):
                # length = width (%), depth = height (px)
                length_pct = rect.width() / img_w
                depth_px = int(rect.height())
                return (length_pct, depth_px)
            else:  # margin_left, margin_right
                # length = height (%), depth = width (px)
                length_pct = rect.height() / img_h
                depth_px = int(rect.width())
                return (length_pct, depth_px)

        else:
            # Custom/protect: store (x_pct, y_pct, w_pct, h_pct)
            return (
                rect.x() / img_w,
                rect.y() / img_h,
                rect.width() / img_w,
                rect.height() / img_h
            )

    def _sync_zone_to_pages(self, base_id: str, zone_data: tuple):
        """Sync zone data to all pages with same zone"""
        # Update _per_page_zones for ALL pages
        for page_idx in self._per_page_zones:
            if base_id in self._per_page_zones[page_idx]:
                self._per_page_zones[page_idx][base_id] = zone_data

        # Find zone_def for calculating pixels
        zone_def = self._find_zone_def(base_id)

        # Update visual zone items
        for zone_item in self._zones:
            zone_base_id = zone_item.zone_id.rsplit('_', 1)[0]
            if zone_base_id == base_id:
                # Get page index for this zone
                page_idx = int(zone_item.zone_id.rsplit('_', 1)[1])
                if page_idx < len(self._page_items):
                    page_rect = self._page_items[page_idx].boundingRect()
                    img_w, img_h = int(page_rect.width()), int(page_rect.height())

                    # Calculate pixel rect using the correct method
                    zx, zy, zw, zh = self._calculate_zone_pixels(zone_def, zone_data, img_w, img_h)
                    new_pixel_rect = QRectF(zx, zy, zw, zh)

                    # Update zone item rect (without triggering signal again)
                    zone_item.signals.blockSignals(True)
                    zone_item.setRect(new_pixel_rect)
                    zone_item._update_handles()
                    zone_item.signals.blockSignals(False)
    
    def _on_zone_selected(self, zone_id: str):
        # Get base zone id (without page index) to select all instances across pages
        base_id = zone_id.rsplit('_', 1)[0] if zone_id.count('_') > 1 else zone_id

        # Highlight all zones with same base_id across all pages
        for zone in self._zones:
            zone_base_id = zone.zone_id.rsplit('_', 1)[0] if zone.zone_id.count('_') > 1 else zone.zone_id
            zone.set_selected(zone_base_id == base_id)
        self.zone_selected.emit(zone_id)

    def deselect_all_zones(self):
        """Deselect all zones - restore z-order"""
        for zone in self._zones:
            zone.set_selected(False)
    
    def _on_zone_delete(self, zone_id: str):
        """Handle zone delete request"""
        self.zone_delete.emit(zone_id)

    def _on_zone_drag_started(self, zone_id: str, rect: QRectF):
        """Handle zone drag start - forward for undo tracking"""
        self.zone_drag_started.emit(zone_id, rect)

    def _on_zone_drag_ended(self, zone_id: str, rect: QRectF):
        """Handle zone drag end - forward for undo tracking"""
        self.zone_drag_ended.emit(zone_id, rect)

    def request_zone_delete(self, zone_id: str):
        """Request zone deletion - called from ZoneItem context menu"""
        # Use QTimer to defer deletion until after menu closes completely
        QTimer.singleShot(50, lambda: self.zone_delete.emit(zone_id))
    
    def get_zone_rect(self, zone_id: str) -> Optional[tuple]:
        """Lấy rect của zone (%) - từ zone item trong scene"""
        # zone_id format: "custom_1_0" -> base_id should be "custom_1"
        base_id = zone_id.rsplit('_', 1)[0]

        # Find the zone item in scene and get its actual rect
        for zone_item in self._zones:
            zone_base_id = zone_item.zone_id.rsplit('_', 1)[0]
            if zone_base_id == base_id:
                # Get the page this zone is on
                page_idx = int(zone_item.zone_id.rsplit('_', 1)[1])
                if page_idx < len(self._page_items):
                    page_rect = self._page_items[page_idx].boundingRect()
                    # Get normalized rect (as percentages)
                    return zone_item.get_normalized_rect(
                        int(page_rect.width()),
                        int(page_rect.height())
                    )
        return None

    def set_protected_regions(self, page_idx: int, regions: list, margin: int = 10):
        """
        Set protected regions to display as overlay for a specific page.

        Args:
            page_idx: Page index (0-based)
            regions: List of ProtectedRegion objects with bbox (x1, y1, x2, y2)
            margin: Padding to add around each bbox (pixels)
        """
        if not hasattr(self, '_protected_region_items'):
            self._protected_region_items: Dict[int, List[QGraphicsRectItem]] = {}

        # Clear existing regions for this page
        if page_idx in self._protected_region_items:
            for item in self._protected_region_items[page_idx]:
                try:
                    self.scene.removeItem(item)
                except RuntimeError:
                    pass  # Item already deleted
            self._protected_region_items[page_idx].clear()
        else:
            self._protected_region_items[page_idx] = []

        if not regions or page_idx >= len(self._page_items):
            return

        # Colors: Red for protected regions (text areas to protect)
        pen = QPen(QColor(220, 38, 38))  # #DC2626 Red
        pen.setWidth(1)
        pen.setCosmetic(True)  # Pen width is in screen pixels
        brush = QBrush(QColor(220, 38, 38, 60))  # ~24% opacity

        page_item = self._page_items[page_idx]
        page_pos = page_item.pos()
        page_rect = page_item.boundingRect()

        for region in regions:
            x1, y1, x2, y2 = region.bbox

            # Add margin/padding to bbox (expand the box)
            x1_expanded = max(0, x1 - margin)
            y1_expanded = max(0, y1 - margin)
            x2_expanded = min(int(page_rect.width()), x2 + margin)
            y2_expanded = min(int(page_rect.height()), y2 + margin)

            # Create rect relative to page position
            scene_x = page_pos.x() + x1_expanded
            scene_y = page_pos.y() + y1_expanded
            width = x2_expanded - x1_expanded
            height = y2_expanded - y1_expanded
            rect = QRectF(scene_x, scene_y, width, height)

            rect_item = QGraphicsRectItem(rect)
            rect_item.setPen(pen)
            rect_item.setBrush(brush)
            rect_item.setZValue(100)  # High z-value to be on top
            self.scene.addItem(rect_item)
            self._protected_region_items[page_idx].append(rect_item)

        # Force view update
        self.view.viewport().update()
        self.scene.update()

    def clear_protected_regions(self):
        """Clear all protected region overlays

        Note: QGraphicsRectItem doesn't inherit from QObject, so deleteLater()
        is not available. Python GC handles cleanup after removeItem().
        """
        if hasattr(self, '_protected_region_items'):
            for page_idx, items in self._protected_region_items.items():
                for item in items:
                    try:
                        if item.scene():
                            self.scene.removeItem(item)
                    except RuntimeError:
                        pass  # Item already deleted
            self._protected_region_items.clear()

    def set_draw_mode(self, mode):
        """Enable/disable draw mode for drawing custom zones

        Args:
            mode: None (off), 'remove' (blue), or 'protect' (pink)
        """
        # If turning off, always allow
        if mode is None:
            self.view.set_draw_mode(None, None, None)
            return

        # Need pages loaded to enable draw mode
        if not self._pages or not self._page_items:
            return

        # Get all page bounds for accurate page detection
        all_page_bounds = []
        for page_item in self._page_items:
            page_rect = page_item.boundingRect()
            page_pos = page_item.pos()
            all_page_bounds.append((page_pos.x(), page_pos.y(), page_rect.width(), page_rect.height()))

        # Get current page bounds as fallback
        page_bounds = None

        if self._view_mode == 'single' and self._page_items:
            page_bounds = all_page_bounds[0] if all_page_bounds else None
        elif self._view_mode == 'continuous' and self._current_page < len(all_page_bounds):
            page_bounds = all_page_bounds[self._current_page]

        # Only enable if we have valid page bounds
        if page_bounds and page_bounds[2] > 0 and page_bounds[3] > 0:
            self.view.set_draw_mode(mode, page_bounds, all_page_bounds)

    def _refresh_draw_mode_bounds(self):
        """Refresh draw mode bounds after scene rebuild.

        When scene is rebuilt (e.g., after progressive loading), page positions may change
        due to centering based on max_width. This method updates the cached bounds in the
        view to match the new page positions, preventing zone coordinate jumping.
        """
        # Check if draw mode is active
        current_mode = getattr(self.view, '_draw_mode', None)
        if current_mode is None:
            return

        # Re-apply draw mode with current page bounds
        self.set_draw_mode(current_mode)

    def _on_rect_drawn(self, x: float, y: float, w: float, h: float, mode: str, page_idx: int):
        """Forward rect_drawn signal - keep draw mode active for continuous drawing"""
        self.rect_drawn.emit(x, y, w, h, mode, page_idx)


class ContinuousPreviewWidget(QWidget):
    """
    Widget preview side-by-side với continuous pages
    TRƯỚC (với overlay) | SAU (kết quả)
    """

    zone_changed = pyqtSignal(str, float, float, float, float, int, int)  # zone_id, x, y, w, h, w_px, h_px
    zone_selected = pyqtSignal(str)  # zone_id
    zone_delete = pyqtSignal(str)  # zone_id - request to delete custom zone
    zone_drag_save_requested = pyqtSignal()  # Request immediate save after drag ends
    # Undo signals - for syncing with settings_panel
    undo_zone_removed = pyqtSignal(str)  # zone_id - zone was removed by undo (undo add)
    undo_zone_restored = pyqtSignal(str, float, float, float, float, str)  # zone_id, x, y, w, h, zone_type - zone was restored by undo (undo delete)
    undo_preset_zone_toggled = pyqtSignal(str, bool)  # zone_id, enabled - preset zone toggle by undo
    open_file_requested = pyqtSignal()  # When placeholder "Mở file" is clicked
    open_folder_requested = pyqtSignal()  # When placeholder "Mở thư mục" is clicked
    file_dropped = pyqtSignal(str)  # When file is dropped (file_path)
    folder_dropped = pyqtSignal(str)  # When folder is dropped (folder_path)
    files_dropped = pyqtSignal(list)  # When multiple PDF files are dropped
    close_requested = pyqtSignal()  # When close button is clicked
    page_changed = pyqtSignal(int)  # Emitted when visible page changes (0-based index)
    # rect_drawn: x, y, w, h (as % of page), mode ('remove' or 'protect'), page_idx
    rect_drawn = pyqtSignal(float, float, float, float, str, int)
    # Batch mode navigation signals
    prev_file_requested = pyqtSignal()  # Navigate to previous file
    next_file_requested = pyqtSignal()  # Navigate to next file
    # Thumbnail panel signals
    thumbnail_collapsed_changed = pyqtSignal(bool)  # collapsed state changed
    page_load_requested = pyqtSignal(int)  # Request loading a specific page (for lazy loading)
    # Zoom signal for saving to config
    zoom_changed = pyqtSignal(float)  # zoom level (e.g., 1.0 = 100%)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._pages: List[np.ndarray] = []  # Original pages
        self._processed_pages: List[np.ndarray] = []  # Processed pages
        self._zones: List[Zone] = []
        self._processor = StapleRemover(protect_red=False)
        self._text_protection_enabled = False
        self._text_protection_margin = 10  # Default margin for protected regions overlay
        self._cached_regions: Dict[int, list] = {}  # Cache protected regions per page

        # Background detection using Python threading (not QThread to avoid crashes)
        self._detection_runner: Optional[DetectionRunner] = None
        self._detection_pending = False  # Track if detection is pending/running
        self._detection_results: Optional[dict] = None  # Store results from thread
        self._detection_total_pages = 0  # Total pages in PDF (for overall progress)
        self._detection_displayed_pages: set = set()  # Track pages already displayed incrementally
        self._detection_progress_shown = False  # Track if progress bar is already shown

        # Timer to check for detection results (cross-thread communication)
        self._result_check_timer = QTimer()
        self._result_check_timer.timeout.connect(self._check_detection_results)
        self._result_check_timer.setInterval(100)  # Check every 100ms

        # Debounce timer
        self._process_timer = QTimer()
        self._process_timer.setSingleShot(True)
        self._process_timer.timeout.connect(self._do_process_all)

        # Track last emitted page to avoid duplicate signals
        self._last_emitted_page = -1
        # Flag to skip page detection when programmatically scrolling
        self._skip_page_detection = False

        # Undo manager for zone operations
        self._undo_manager = UndoManager()
        self._drag_before_rect: Optional[QRectF] = None  # Store rect before drag for undo
        self._drag_zone_id: Optional[str] = None  # Store zone_id being dragged

        self._setup_ui()

    def closeEvent(self, event):
        """Cleanup khi widget bị đóng"""
        self._stop_detection()
        super().closeEvent(event)

    def __del__(self):
        """Destructor - đảm bảo cleanup"""
        try:
            self._stop_detection()
        except (RuntimeError, AttributeError):
            pass  # Qt objects may already be deleted
    
    def _setup_ui(self):
        self.setStyleSheet("background-color: #E5E7EB;")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Splitter with white handle - not draggable (equal widths always)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setStyleSheet("""
            QSplitter {
                background-color: #E5E7EB;
            }
            QSplitter::handle {
                background-color: white;
                width: 2px;
            }
        """)
        self.splitter.setHandleWidth(2)
        # Prevent dragging by resetting sizes when moved
        self.splitter.splitterMoved.connect(self._reset_splitter_sizes)
        
        # Panel TRƯỚC (có overlay)
        self.before_panel = ContinuousPreviewPanel("Gốc:", show_overlay=True)
        self.before_panel.zone_changed.connect(self._on_zone_changed)
        self.before_panel.zone_selected.connect(self._on_zone_selected)
        self.before_panel.zone_delete.connect(self._on_zone_delete)
        self.before_panel.zone_drag_started.connect(self._on_zone_drag_started)
        self.before_panel.zone_drag_ended.connect(self._on_zone_drag_ended)
        self.before_panel.placeholder_clicked.connect(self._on_placeholder_clicked)
        self.before_panel.folder_placeholder_clicked.connect(self._on_folder_placeholder_clicked)
        self.before_panel.file_dropped.connect(self._on_file_dropped)
        self.before_panel.folder_dropped.connect(self._on_folder_dropped)
        self.before_panel.files_dropped.connect(self._on_files_dropped)
        self.before_panel.close_requested.connect(self._on_close_requested)
        self.before_panel.rect_drawn.connect(self._on_rect_drawn)
        # Batch mode navigation signals
        self.before_panel.prev_file_requested.connect(self.prev_file_requested.emit)
        self.before_panel.next_file_requested.connect(self.next_file_requested.emit)
        # Thumbnail panel signals - click thumbnail to scroll both panels
        self.before_panel.thumbnail_page_clicked.connect(self._on_thumbnail_page_clicked)
        self.before_panel.thumbnail_collapsed_changed.connect(self._on_thumbnail_collapsed_changed)
        self.splitter.addWidget(self.before_panel)
        
        # Panel SAU (chỉ kết quả)
        self.after_panel = ContinuousPreviewPanel("Đích:", show_overlay=False)
        self.after_panel.placeholder_clicked.connect(self._on_placeholder_clicked)
        self.after_panel.folder_placeholder_clicked.connect(self._on_folder_placeholder_clicked)
        self.after_panel.file_dropped.connect(self._on_file_dropped)
        self.after_panel.folder_dropped.connect(self._on_folder_dropped)
        self.after_panel.files_dropped.connect(self._on_files_dropped)
        self.after_panel.collapse_requested.connect(self._toggle_after_panel)
        self.splitter.addWidget(self.after_panel)

        # Track collapse state
        self._after_panel_collapsed = False
        self._after_panel_width = 0  # Store width before collapse

        # Expand button (appears when after panel is collapsed) - positioned at top right
        self._expand_btn = QPushButton("‹")
        self._expand_btn.setFixedSize(22, 22)
        self._expand_btn.setCursor(Qt.PointingHandCursor)
        self._expand_btn.setStyleSheet("""
            QPushButton {
                background-color: #D1D5DB;
                border: none;
                border-radius: 4px;
                font-size: 18px;
                font-weight: bold;
                color: #4B5563;
                padding: 0;
                margin: 0;
            }
            QPushButton:hover {
                color: white;
                background-color: #3B82F6;
            }
        """)
        self._expand_btn.setToolTip("Mở rộng panel Đích")
        self._expand_btn.clicked.connect(self._toggle_after_panel)
        self._expand_btn.setParent(self)
        self._expand_btn.hide()  # Hidden by default
        
        # Sync zoom/scroll
        self.before_panel.view.zoom_changed.connect(self._sync_zoom)
        self.after_panel.view.zoom_changed.connect(self._sync_zoom)
        self.before_panel.view.scroll_changed.connect(self._sync_scroll_from_before)
        self.after_panel.view.scroll_changed.connect(self._sync_scroll_from_after)
        # Forward zoom_changed to parent (main_window) for saving to config
        self.before_panel.view.zoom_changed.connect(self.zoom_changed.emit)
        
        # Set equal stretch factors so both panels resize equally
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([1, 1])
        layout.addWidget(self.splitter)

        # Loading overlay (centered on widget)
        self._loading_overlay = LoadingOverlay(self)
        self._loading_overlay.hide()

    def _reset_splitter_sizes(self):
        """Reset splitter so that Preview Gốc (main area) = Preview Đích width

        Formula:
        - thumbnail_width = before_panel thumbnail panel width (80 or 24)
        - total_width = Gốc + Đích
        - Đích = (total_width - thumbnail_width) / 2
        - Gốc = Đích + thumbnail_width
        """
        # Skip if after panel is collapsed
        if self._after_panel_collapsed:
            return

        sizes = self.splitter.sizes()
        total = sum(sizes)

        # Get thumbnail panel width
        thumbnail_width = self.before_panel.get_thumbnail_width()

        # Calculate sizes so that Gốc main area = Đích width
        dest_width = (total - thumbnail_width) // 2
        source_width = dest_width + thumbnail_width

        # Only update if changed
        if sizes[0] != source_width or sizes[1] != dest_width:
            self.splitter.setSizes([source_width, dest_width])

    def _toggle_after_panel(self):
        """Toggle collapse/expand of after panel (Đích)"""
        sizes = self.splitter.sizes()
        total_width = sum(sizes)

        if self._after_panel_collapsed:
            # Expand - restore with correct width ratio
            thumbnail_width = self.before_panel.get_thumbnail_width()
            dest_width = (total_width - thumbnail_width) // 2
            source_width = dest_width + thumbnail_width
            self.after_panel.setVisible(True)
            self.splitter.setSizes([source_width, dest_width])
            self._expand_btn.hide()
            self._after_panel_collapsed = False
        else:
            # Collapse - hide after panel completely
            self._after_panel_width = sizes[1]
            self.after_panel.setVisible(False)
            self.splitter.setSizes([total_width, 0])
            # Show expand button at top right
            self._expand_btn.move(self.width() - 28, 5)
            self._expand_btn.raise_()
            self._expand_btn.show()
            self._after_panel_collapsed = True

    def resizeEvent(self, event):
        """Resize loading overlay and scale content proportionally"""
        super().resizeEvent(event)
        self._update_loading_overlay_geometry()

        # Reposition expand button if visible
        if self._after_panel_collapsed and self._expand_btn.isVisible():
            self._expand_btn.move(self.width() - 28, 5)

        # Get old and new width
        old_width = event.oldSize().width() if event.oldSize().isValid() else 0
        new_width = event.size().width()

        # Scale content proportionally if pages are loaded (only if not collapsed)
        if not self._after_panel_collapsed and old_width > 0 and self._pages and new_width > 0 and old_width != new_width:
            ratio = new_width / old_width
            current_zoom = self.before_panel.view._zoom
            new_zoom = current_zoom * ratio
            new_zoom = max(0.1, min(5.0, new_zoom))
            # Use weak reference to avoid crash if widget is deleted before timer fires
            import weakref
            weak_self = weakref.ref(self)
            def safe_set_zoom():
                obj = weak_self()
                if obj is not None:
                    obj.set_zoom(new_zoom)
            QTimer.singleShot(10, safe_set_zoom)

    def showEvent(self, event):
        """Set correct splitter sizes when widget becomes visible"""
        super().showEvent(event)
        # Delay to ensure widget has proper size
        QTimer.singleShot(0, self._reset_splitter_sizes)

    def _update_loading_overlay_geometry(self):
        """Position loading overlay centered on before_panel (Gốc)"""
        # Map before_panel position to this widget's coordinates
        pos = self.before_panel.mapTo(self, self.before_panel.rect().topLeft())
        size = self.before_panel.size()
        self._loading_overlay.setGeometry(pos.x(), pos.y(), size.width(), size.height())

    def _show_loading(self):
        """Show loading overlay centered on before_panel"""
        self._update_loading_overlay_geometry()
        self._loading_overlay.show()
        self._loading_overlay.raise_()
        # Force repaint
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

    def _hide_loading(self):
        """Hide loading overlay"""
        self._loading_overlay.hide()

    def _on_placeholder_clicked(self):
        """Handle placeholder click - request to open file"""
        self.open_file_requested.emit()
    
    def _on_folder_placeholder_clicked(self):
        """Handle folder placeholder click - request to open folder"""
        self.open_folder_requested.emit()
    
    def _on_close_requested(self):
        """Handle close button click - forward to parent"""
        self.close_requested.emit()

    def set_batch_mode(self, enabled: bool, current: int = 0, total: int = 0):
        """Enable/disable batch mode navigation in before_panel"""
        self.before_panel.set_batch_mode(enabled, current, total)

    def set_file_index(self, current: int, total: int):
        """Update file counter and navigation button states"""
        self.before_panel.set_file_index(current, total)

    def _on_file_dropped(self, file_path: str):
        """Handle file dropped - forward to parent"""
        self.file_dropped.emit(file_path)

    def _on_folder_dropped(self, folder_path: str):
        """Handle folder dropped - forward to parent"""
        self.folder_dropped.emit(folder_path)

    def _on_files_dropped(self, file_paths: list):
        """Handle multiple files dropped - forward to parent"""
        self.files_dropped.emit(file_paths)

    def set_file_paths(self, source_path: str, dest_path: str):
        """Update title labels with file paths"""
        self.before_panel.set_title(f"Gốc: {source_path}")
        self.after_panel.set_title(f"Đích: {dest_path}")
    
    def clear_file_paths(self):
        """Reset titles to default"""
        self.before_panel.set_title("Gốc:")
        self.after_panel.set_title("Đích:")

    def clear_thumbnails(self):
        """Clear thumbnails from the before panel"""
        self.before_panel.clear_thumbnails()

    def set_pages(self, pages: List[np.ndarray], from_cache: bool = False):
        """Set danh sách ảnh các trang

        Args:
            pages: List of page images as numpy arrays
            from_cache: If True, skip deep copy for _pages (read-only) to improve
                        performance when loading from preload cache. _processed_pages
                        still gets copied since it's modified during processing.
        """
        # Stop any running detection first
        self._stop_detection()
        self._hide_loading()

        if from_cache:
            # Optimized: keep reference for _pages (read-only)
            # Only copy _processed_pages since it gets modified
            self._pages = list(pages)
            self._processed_pages = [p.copy() for p in pages]
        else:
            # Normal mode: deep copy both for safety
            self._pages = [p.copy() for p in pages]
            self._processed_pages = [p.copy() for p in pages]

        # Clear cached regions khi load pages mới
        self._cached_regions.clear()
        self._detection_displayed_pages.clear()
        self._detection_progress_shown = False

        # Clear undo history when loading new file
        self._undo_manager.clear()

        # Reset page tracking state for new file
        self._last_emitted_page = -1
        self._skip_page_detection = False

        self.before_panel.set_pages(pages)
        self.after_panel.set_pages(self._processed_pages)

        # If empty pages (closing file), ensure zoom is reset for placeholder icons
        if not pages:
            self.before_panel.view._zoom = 1.0
            self.before_panel.view.resetTransform()
            self.after_panel.view._zoom = 1.0
            self.after_panel.view.resetTransform()

        self._schedule_process()

    # === Progressive Loading Methods ===

    def start_thumbnail_loading(self, total_pages: int):
        """Start progressive thumbnail loading"""
        self.before_panel.start_thumbnail_loading(total_pages)

    def add_thumbnail(self, index: int, image: np.ndarray):
        """Add single thumbnail during progressive loading"""
        self.before_panel.add_thumbnail(index, image)

    def finish_thumbnail_loading(self):
        """Finish thumbnail loading"""
        self.before_panel.finish_thumbnail_loading()

    def set_thumbnails(self, thumbnails: list):
        """Set all thumbnails at once from cache (optimized bulk loading)"""
        self.before_panel.set_thumbnails(thumbnails)

    def pause_thumbnail_updates(self):
        """Pause thumbnail updates for bulk loading"""
        self.before_panel.pause_thumbnail_updates()

    def repaint_thumbnails(self):
        """Force immediate repaint of thumbnail panel"""
        self.before_panel.repaint_thumbnails()

    def show_progress_bar(self):
        """Show loading progress bar"""
        self.before_panel.show_progress_bar()

    def hide_progress_bar(self):
        """Hide loading progress bar"""
        self.before_panel.hide_progress_bar()

    def set_progress(self, percent: int):
        """Set progress bar percentage (0-100)"""
        self.before_panel.set_progress(percent)

    # === Sliding Window Methods ===

    def init_sliding_window(self, total_pages: int, initial_pages: List[np.ndarray] = None):
        """Initialize sliding window mode with placeholder pages"""
        # Stop any running detection
        self._stop_detection()
        self._hide_loading()

        self._pages = [None] * total_pages
        self._processed_pages = [None] * total_pages

        # Fill in initial pages
        if initial_pages:
            for i, page in enumerate(initial_pages):
                if i < total_pages and page is not None:
                    self._pages[i] = page.copy()
                    self._processed_pages[i] = page.copy()

        # Clear cached regions
        self._cached_regions.clear()
        self._detection_displayed_pages.clear()
        self._detection_progress_shown = False

        # Clear undo history
        self._undo_manager.clear()

        # Initialize panels
        self.before_panel.init_sliding_window(total_pages, initial_pages)
        self.after_panel.init_sliding_window(total_pages, initial_pages)

        self._schedule_process()

    def update_window_pages(self, page_updates: dict):
        """Update specific pages in sliding window

        Args:
            page_updates: {page_idx: image} dict, image can be None to unload
        """
        # Update internal lists - only _pages (raw), NOT _processed_pages
        # _processed_pages will be updated by _schedule_process
        for page_idx, image in page_updates.items():
            if 0 <= page_idx < len(self._pages):
                if image is not None:
                    self._pages[page_idx] = image.copy()
                    # Temporarily set processed to raw, will be replaced by processing
                    self._processed_pages[page_idx] = image.copy()
                else:
                    self._pages[page_idx] = None
                    self._processed_pages[page_idx] = None

        # Update before_panel only (shows raw image with zone overlays)
        self.before_panel.update_window_pages(page_updates)

        # DON'T update after_panel directly - let _schedule_process handle it
        # This ensures zones are applied before showing in after_panel
        self._schedule_process()

    def show_detection_progress(self):
        """Show detection progress bar (red)"""
        self.before_panel.show_detection_progress()

    def hide_detection_progress(self):
        """Hide detection progress bar"""
        self.before_panel.hide_detection_progress()

    def set_detection_progress(self, percent: int):
        """Set detection progress bar percentage (0-100)"""
        self.before_panel.set_detection_progress(percent)

    def add_preview_page(self, page: np.ndarray):
        """Add single page to both before and after panels"""
        if page is None:
            return
        page_copy = page.copy()
        page_idx = len(self._pages)  # Index of new page
        # Add to our own lists for tracking loaded count and processing
        self._pages.append(page_copy)
        self._processed_pages.append(page_copy.copy())  # Keep in sync for processing
        # Also add to panels - they will append to their _pages lists
        self.before_panel.add_page(page_copy)
        self.after_panel.add_page(page_copy.copy())

        # If text protection enabled, detect this page immediately
        if self._text_protection_enabled and page_idx not in self._cached_regions:
            self._detect_single_page(page_idx, page_copy)

    def get_loaded_page_count(self) -> int:
        """Get number of pages currently loaded in preview"""
        return len(self._pages)

    def refresh_scene(self):
        """Rebuild scenes with all pages. Call at end of background loading."""
        self.before_panel.refresh_scene()
        self.after_panel.refresh_scene()

        # Re-display protection regions that were already detected (scene.clear() removed them)
        if self._text_protection_enabled and self._detection_displayed_pages:
            for page_idx in self._detection_displayed_pages:
                if page_idx in self._cached_regions:
                    regions = self._cached_regions[page_idx]
                    self.before_panel.set_protected_regions(page_idx, regions, margin=self._text_protection_margin)

        # Check if all pages are detected - hide progress bar
        if self._text_protection_enabled:
            if self._detection_total_pages > 0 and len(self._cached_regions) >= self._detection_total_pages:
                # All pages detected, hide progress bar and process
                self.hide_detection_progress()
                self._detection_progress_shown = False
                self._process_pages_with_cached_regions()
            else:
                # Some pages not yet detected, continue detection
                self._schedule_process()
        else:
            # Text protection off - still need to process zones on all pages
            self._schedule_process()

    def set_view_mode(self, mode: str):
        """Set view mode: 'continuous' or 'single'"""
        self.before_panel.set_view_mode(mode)
        self.after_panel.set_view_mode(mode)
    
    def set_current_page(self, index: int, scroll_thumbnail: bool = True):
        """Set current page index - scroll in continuous mode, rebuild in single mode

        Args:
            index: Page index (0-based)
            scroll_thumbnail: If True, scroll thumbnail to show current page.
                            Set False when action was initiated by clicking thumbnail.
        """
        # Skip page detection during programmatic scroll to prevent jumping
        self._skip_page_detection = True
        self._last_emitted_page = index
        self.before_panel.set_current_page(index)
        self.after_panel.set_current_page(index)
        # Update thumbnail highlight
        self.before_panel.update_thumbnail_highlight(index, scroll=scroll_thumbnail)
        # Reset flag after scroll completes (use timer to allow scroll event to finish)
        QTimer.singleShot(1000, lambda: setattr(self, '_skip_page_detection', False))
    
    def get_current_page(self) -> int:
        """Get current page index"""
        return self.before_panel.get_current_page()
    
    def set_page_filter(self, filter_mode: str):
        """Set page filter: 'all', 'odd', 'even'"""
        self.before_panel.set_page_filter(filter_mode)
        # Reprocess with new filter
        self._schedule_process()

    def clear_all_zones(self):
        """Clear all zones from all pages (reset per_page_zones)"""
        self.before_panel.clear_all_zones()
        self._schedule_process()

    def clear_current_page_zones(self):
        """Clear zones only for current page"""
        self.before_panel.clear_current_page_zones()
        self._schedule_process()

    def clear_zone_rieng(self):
        """Clear only Zone riêng, keep Zone chung"""
        self.before_panel.clear_zone_rieng()
        self._schedule_process()

    def clear_zone_chung(self):
        """Clear only Zone chung, keep Zone riêng"""
        self.before_panel.clear_zone_chung()
        self._schedule_process()

    def save_per_file_zones(self, file_path: str = None, persist: bool = True):
        """Save current per-page zones for a file (before switching files)."""
        self.before_panel.save_per_file_zones(file_path, persist=persist)

    def _persist_zones_to_disk(self):
        """Force persist all per-file zones to disk."""
        self.before_panel._persist_zones_to_disk()

    def load_per_file_zones(self, file_path: str) -> bool:
        """Load saved per-page zones for a file (after loading file).

        Returns True if zones were loaded and UI needs refresh.
        """
        loaded = self.before_panel.load_per_file_zones(file_path)
        if loaded:
            # Recreate zone overlays to show loaded zones
            if self.before_panel.show_overlay:
                if self.before_panel._view_mode == 'single':
                    self.before_panel._recreate_zone_overlays_single()
                else:
                    self.before_panel._recreate_zone_overlays()
            self._schedule_process()
        return loaded

    def set_current_file_path(self, file_path: str):
        """Set current file path for per-file zone tracking."""
        self.before_panel.set_current_file_path(file_path)

    def clear_per_file_zones(self, reset_paths: bool = False):
        """Clear all per-file zone storage."""
        self.before_panel.clear_per_file_zones(reset_paths=reset_paths)

    def set_batch_base_dir(self, batch_base_dir: str):
        """Set batch base directory for persistence."""
        self.before_panel.set_batch_base_dir(batch_base_dir)

    def load_persisted_zones(self, batch_base_dir: str):
        """Load persisted zones from disk for crash recovery."""
        self.before_panel.load_persisted_zones(batch_base_dir)

    def set_zones(self, zones: List[Zone]):
        """Set danh sách zones"""
        self._zones = zones
        self.before_panel.set_zone_definitions(zones)
        self._schedule_process()
    
    def update_zone(self, zone: Zone):
        """Cập nhật một zone"""
        for i, z in enumerate(self._zones):
            if z.id == zone.id:
                self._zones[i] = zone
                break
        
        self.before_panel.set_zone_definitions(self._zones)
        self._schedule_process()
    
    def _on_zone_changed(self, zone_id: str):
        """Khi zone bị thay đổi"""
        rect = self.before_panel.get_zone_rect(zone_id)
        if rect:
            x, y, w, h = rect
            # zone_id format: "custom_1_0" -> base_id should be "custom_1"
            parts = zone_id.rsplit('_', 1)
            base_id = parts[0]
            page_idx = int(parts[1]) if len(parts) > 1 else 0

            page_filter = self.before_panel._page_filter

            # Get zone_data from _per_page_zones (has correct format: pixels for corners/edges)
            w_px, h_px = 0, 0
            zone_data = self.before_panel._per_page_zones.get(page_idx, {}).get(base_id)
            if zone_data and len(zone_data) == 2:
                # Corner or edge zone: zone_data is (w_px, h_px) or (length_pct, depth_px)
                if base_id.startswith('corner_'):
                    w_px, h_px = int(zone_data[0]), int(zone_data[1])
                elif base_id.startswith('margin_'):
                    # Edge: (length_pct, depth_px)
                    if base_id in ('margin_top', 'margin_bottom'):
                        h_px = int(zone_data[1])  # depth is height
                    else:  # margin_left, margin_right
                        w_px = int(zone_data[1])  # depth is width

            # Emit signal to update Zone object in settings_panel (for both sync and 'none' mode)
            # This ensures Zone object coordinates are updated for proper saving
            self.zone_changed.emit(base_id, x, y, w, h, w_px, h_px)

            # Update internal zone definitions
            for zone in self._zones:
                if zone.id == base_id:
                    zone.x = x
                    zone.y = y
                    zone.width = w
                    zone.height = h
                    if w_px > 0:
                        zone.width_px = w_px
                    if h_px > 0:
                        zone.height_px = h_px
                    break

            # Note: In 'none' mode, per-page zones are stored independently in before_panel._per_page_zones
            # Zone object update above ensures proper saving to _per_file_custom_zones

            self._schedule_process()
    
    def _on_zone_selected(self, zone_id: str):
        # zone_id format: "custom_1_0" -> base_id should be "custom_1"
        base_id = zone_id.rsplit('_', 1)[0]
        self.zone_selected.emit(base_id)
    
    def _on_zone_delete(self, zone_id: str):
        """Handle zone delete request - forward to main window"""
        # zone_id format: "custom_1_0" -> base_id should be "custom_1"
        # Use rsplit to get everything except the last part (page index)
        base_id = zone_id.rsplit('_', 1)[0]
        self.zone_delete.emit(base_id)

    def _on_zone_drag_started(self, zone_id: str, rect: QRectF):
        """Store zone rect before drag for undo"""
        self._drag_zone_id = zone_id
        self._drag_before_rect = QRectF(rect)  # Copy rect

    def _on_zone_drag_ended(self, zone_id: str, after_rect: QRectF):
        """Record undo when zone drag ends"""
        if self._drag_zone_id != zone_id or self._drag_before_rect is None:
            return

        # zone_id format: "custom_1_0" -> base_id = "custom_1", page_idx = 0
        parts = zone_id.rsplit('_', 1)
        base_id = parts[0]
        page_idx = int(parts[1]) if len(parts) > 1 else 0

        # Get page dimensions for conversion
        if page_idx < len(self.before_panel._page_items):
            page_rect = self.before_panel._page_items[page_idx].boundingRect()
            img_w, img_h = int(page_rect.width()), int(page_rect.height())

            # Convert both rects to storage format
            before_data = self.before_panel._pixel_rect_to_zone_data(
                base_id, self._drag_before_rect, img_w, img_h)
            after_data = self.before_panel._pixel_rect_to_zone_data(
                base_id, after_rect, img_w, img_h)

            # Record undo if data actually changed
            self.record_zone_edit(base_id, page_idx, before_data, after_data)

        # Clear drag tracking
        self._drag_zone_id = None
        self._drag_before_rect = None

        # Emit signal to trigger immediate save (crash recovery)
        self.zone_drag_save_requested.emit()

    def record_zone_add(self, zone_id: str, page_idx: int, zone_data: tuple, zone_type: str = 'remove'):
        """Record zone add action for undo"""
        action = UndoAction(
            action_type='add',
            zone_id=zone_id,
            page_idx=page_idx,
            before_data=None,
            after_data=zone_data,
            zone_type=zone_type
        )
        self._undo_manager.push(action)

    def record_zone_delete(self, zone_id: str, page_idx: int, zone_data: tuple, zone_type: str = 'remove'):
        """Record zone delete action for undo"""
        action = UndoAction(
            action_type='delete',
            zone_id=zone_id,
            page_idx=page_idx,
            before_data=zone_data,
            after_data=None,
            zone_type=zone_type
        )
        self._undo_manager.push(action)

    def record_zone_edit(self, zone_id: str, page_idx: int, before_data: tuple, after_data: tuple):
        """Record zone edit action for undo"""
        # Only record if data actually changed
        if before_data != after_data:
            action = UndoAction(
                action_type='edit',
                zone_id=zone_id,
                page_idx=page_idx,
                before_data=before_data,
                after_data=after_data
            )
            self._undo_manager.push(action)

    def undo(self) -> bool:
        """Perform undo - returns True if undo was performed"""
        action = self._undo_manager.undo()
        if not action:
            return False

        # Disable undo recording while restoring
        self._undo_manager.set_enabled(False)

        try:
            if action.action_type == 'add':
                # Undo add = delete the zone
                self._undo_remove_zone(action.zone_id, action.page_idx)
            elif action.action_type == 'delete':
                # Undo delete = restore the zone
                self._undo_restore_zone(action.zone_id, action.page_idx,
                                        action.before_data, action.zone_type)
            elif action.action_type == 'edit':
                # Undo edit = restore previous data
                self._undo_restore_zone_data(action.zone_id, action.page_idx,
                                              action.before_data)
            return True
        finally:
            self._undo_manager.set_enabled(True)

    def _undo_remove_zone(self, zone_id: str, page_idx: int):
        """Remove zone from per_page_zones (undo add)"""
        # Check if it's a preset zone (corner or edge)
        is_preset = zone_id.startswith('corner_') or zone_id.startswith('margin_')

        if is_preset:
            # Preset zone: just emit signal to toggle in settings_panel
            # settings_panel.toggle_preset_zone() will handle the rest
            self.undo_preset_zone_toggled.emit(zone_id, False)
        else:
            # Custom zone: remove from per_page_zones
            per_page_zones = self.before_panel._per_page_zones
            if page_idx == -1:
                # Remove from all pages
                for pg_idx in per_page_zones:
                    if zone_id in per_page_zones[pg_idx]:
                        del per_page_zones[pg_idx][zone_id]
            else:
                if page_idx in per_page_zones and zone_id in per_page_zones[page_idx]:
                    del per_page_zones[page_idx][zone_id]

            # Remove from _zones list
            self._zones = [z for z in self._zones if z.id != zone_id]

            # Emit signal to sync with settings_panel
            self.undo_zone_removed.emit(zone_id)

            self.before_panel._rebuild_scene()
            self._schedule_process()

    def _undo_restore_zone(self, zone_id: str, page_idx: int, zone_data: tuple, zone_type: str):
        """Restore zone to per_page_zones (undo delete)"""
        # Check if it's a preset zone (corner or edge)
        is_preset = zone_id.startswith('corner_') or zone_id.startswith('margin_')

        if is_preset:
            # Preset zone: just emit signal to toggle in settings_panel
            # settings_panel.toggle_preset_zone() will handle the rest
            self.undo_preset_zone_toggled.emit(zone_id, True)
        else:
            # Custom zone: restore to per_page_zones
            per_page_zones = self.before_panel._per_page_zones
            if page_idx == -1:
                # Restore to all pages
                for pg_idx in per_page_zones:
                    per_page_zones[pg_idx][zone_id] = zone_data
            else:
                if page_idx not in per_page_zones:
                    per_page_zones[page_idx] = {}
                per_page_zones[page_idx][zone_id] = zone_data

            # Emit signal to sync with settings_panel
            # zone_data is (x, y, w, h) for custom zones
            if len(zone_data) == 4:
                x, y, w, h = zone_data
                self.undo_zone_restored.emit(zone_id, x, y, w, h, zone_type)

            self.before_panel._rebuild_scene()
            self._schedule_process()

    def _undo_restore_zone_data(self, zone_id: str, page_idx: int, zone_data: tuple):
        """Restore zone data (undo edit)"""
        per_page_zones = self.before_panel._per_page_zones
        page_filter = self.before_panel._page_filter

        if page_filter != 'none':
            # Sync mode: restore to all pages
            for pg_idx in per_page_zones:
                if zone_id in per_page_zones[pg_idx]:
                    per_page_zones[pg_idx][zone_id] = zone_data
        else:
            # Per-page mode: restore to specific page
            if page_idx in per_page_zones:
                per_page_zones[page_idx][zone_id] = zone_data

        self.before_panel._rebuild_scene()
        self._schedule_process()

    def can_undo(self) -> bool:
        """Check if undo is available"""
        return self._undo_manager.can_undo()

    def clear_undo_history(self):
        """Clear undo history (when loading new file)"""
        self._undo_manager.clear()

    def _schedule_process(self):
        """Schedule processing với minimal debounce cho response nhanh"""
        print("[DEBUG] _schedule_process called")
        self._process_timer.start(30)  # Fast response for zone drawing
    
    def _do_process_all(self):
        """Xử lý tất cả các trang"""
        print(f"[DEBUG] _do_process_all called, _pages len={len(self._pages) if self._pages else 0}")
        if not self._pages:
            print("[DEBUG] _do_process_all: _pages is empty, returning")
            return

        # Check if we need YOLO detection (when text protection enabled and pages not cached)
        pages_to_detect = []
        if self._text_protection_enabled:
            for i in range(len(self._pages)):
                if i not in self._cached_regions and self._pages[i] is not None:
                    pages_to_detect.append(i)

        print(f"[DEBUG] _do_process_all: text_protection={self._text_protection_enabled}, pages_to_detect={pages_to_detect}")

        # If detection needed, run in background thread
        if pages_to_detect:
            self._start_background_detection(pages_to_detect)
            return  # Will continue processing after detection finishes

        # No detection needed, process directly
        print("[DEBUG] _do_process_all: calling _process_pages_with_cached_regions")
        self._process_pages_with_cached_regions()

    def set_detection_total_pages(self, total: int):
        """Set total page count for detection progress calculation (call before loading)"""
        self._detection_total_pages = total

    def _detect_single_page(self, page_idx: int, page: np.ndarray):
        """Detect protection regions for a single page (runs synchronously during page load)"""
        # Show progress bar if not shown yet
        if not self._detection_progress_shown:
            self._detection_progress_shown = True
            self.show_detection_progress()

        try:
            # Run detection
            regions = self._processor.detect_protected_regions(page)
            # Cache result
            self._cached_regions[page_idx] = regions
            self._detection_displayed_pages.add(page_idx)
            # Display regions on before panel
            self.before_panel.set_protected_regions(page_idx, regions, margin=self._text_protection_margin)
            # Update progress
            if self._detection_total_pages > 0:
                percent = int(len(self._cached_regions) * 100 / self._detection_total_pages)
                self.set_detection_progress(percent)
        except Exception:
            self._cached_regions[page_idx] = []

    def _start_background_detection(self, pages_to_detect: List[int]):
        """Bắt đầu detection trong background thread (Python threading)"""
        # Stop any existing detection (but keep progress bar if continuing)
        was_pending = self._detection_pending
        self._stop_detection()

        self._detection_pending = True
        self._detection_results = None
        # Total pages = all pages in PDF (for overall progress tracking)
        self._detection_total_pages = len(self._pages)
        # Don't clear displayed pages - they're already shown from previous batch
        # self._detection_displayed_pages.clear()

        # Show progress bar only if not already shown (first batch)
        if not self._detection_progress_shown:
            self._detection_progress_shown = True
            self.show_detection_progress()

        # Update progress based on already cached pages
        if self._detection_total_pages > 0:
            initial_progress = int(len(self._cached_regions) * 100 / self._detection_total_pages)
            self.set_detection_progress(initial_progress)

        # Create a copy of pages for the thread to avoid thread safety issues
        # Filter to only valid indices AND pages that are actually loaded (not None)
        valid_indices = [i for i in pages_to_detect if i < len(self._pages) and self._pages[i] is not None]
        if not valid_indices:
            return
        pages_copy = [self._pages[i].copy() for i in valid_indices]

        # Create runner with callback (progress callback not used - we poll from timer)
        self._detection_runner = DetectionRunner(
            self._processor,
            pages_copy,
            pages_to_detect,  # Original indices
            self._on_detection_complete  # Callback when done
        )

        # Start detection thread
        self._detection_runner.start()

        # Start timer to check for results and update progress
        self._result_check_timer.start()

    def _on_detection_complete(self, results: dict):
        """Callback from detection thread - store results for main thread to pick up"""
        self._detection_results = results

    def _check_detection_results(self):
        """Check if detection results are ready (called by timer in main thread)"""
        # Update progress bar and display incremental results while detection is running
        if self._detection_runner is not None and self._detection_pending:
            # Get incremental results and display newly detected pages immediately
            incremental = self._detection_runner.get_incremental_results()
            for page_idx, regions in incremental.items():
                if page_idx not in self._detection_displayed_pages:
                    # Cache the regions
                    self._cached_regions[page_idx] = regions
                    # Display regions on before panel immediately
                    self.before_panel.set_protected_regions(page_idx, regions, margin=self._text_protection_margin)
                    self._detection_displayed_pages.add(page_idx)

            # Update progress based on TOTAL pages detected (not just this batch)
            if self._detection_total_pages > 0:
                percent = int(len(self._cached_regions) * 100 / self._detection_total_pages)
                self.set_detection_progress(percent)

        if self._detection_results is not None and self._detection_pending:
            # Stop the timer
            self._result_check_timer.stop()

            # Only hide progress bar if ALL pages are detected
            all_pages_detected = len(self._cached_regions) >= self._detection_total_pages
            if all_pages_detected:
                self.hide_detection_progress()
                self._detection_progress_shown = False  # Reset for next file

            # Process results in main thread (any remaining)
            results = self._detection_results
            self._detection_results = None

            # Update cache (ensure all results are cached)
            for page_idx, regions in results.items():
                if page_idx < len(self._pages):
                    self._cached_regions[page_idx] = regions

            self._detection_pending = False
            self._detection_runner = None

            # Process all pages for after panel (with zones applied)
            self._process_pages_after_detection()

    def _stop_detection(self):
        """Stop any running detection"""
        self._detection_pending = False
        self._detection_results = None
        try:
            self._result_check_timer.stop()
        except RuntimeError:
            pass  # Timer already deleted during shutdown

        # Hide detection progress bar
        self.hide_detection_progress()

        if self._detection_runner is not None:
            self._detection_runner.cancel()
            # Don't wait - let daemon thread die naturally
            self._detection_runner = None

    def _process_pages_after_detection(self):
        """Process pages for after panel after incremental detection complete.

        Unlike _process_pages_with_cached_regions, this does NOT clear
        protected regions display (already shown incrementally).
        """
        if not self._pages:
            return

        # Ensure _processed_pages has correct length
        if len(self._processed_pages) != len(self._pages):
            self._processed_pages = [None] * len(self._pages)

        # Track which pages were processed for incremental update
        processed_updates = {}

        for i, page in enumerate(self._pages):
            # Skip None pages (unloaded in sliding window mode)
            if page is None:
                continue

            page_zones = self._get_zones_for_page(i)

            if page_zones:
                if self._text_protection_enabled:
                    regions = self._cached_regions.get(i, [])
                    processed = self._processor.process_image(page, page_zones, protected_regions=regions)
                    self._processed_pages[i] = processed
                    processed_updates[i] = processed
                else:
                    processed = self._processor.process_image(page, page_zones)
                    self._processed_pages[i] = processed
                    processed_updates[i] = processed
            else:
                self._processed_pages[i] = page.copy()
                processed_updates[i] = self._processed_pages[i]

        # Update after_panel incrementally instead of full rebuild
        need_recenter = False
        for page_idx, processed_img in processed_updates.items():
            # Check if size changed
            if page_idx < len(self.after_panel._page_items):
                old_pixmap = self.after_panel._page_items[page_idx].pixmap()
                old_w = old_pixmap.width() if old_pixmap else 0
                self.after_panel.update_page(page_idx, processed_img)
                new_pixmap = self.after_panel._page_items[page_idx].pixmap()
                if new_pixmap and new_pixmap.width() != old_w:
                    need_recenter = True
            else:
                self.after_panel.update_page(page_idx, processed_img)

        # Recenter after_panel if any page changed size
        if need_recenter:
            self.after_panel._recenter_all_pages()

        # Force UI refresh
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

    def _process_pages_with_cached_regions(self):
        """Xử lý tất cả trang với cached regions (không blocking)

        Each page is processed with its own zones from per_page_zones.
        Zones are added to pages based on filter when drawn (like layers).
        """
        if not self._pages:
            self._hide_loading()
            return

        # Ensure _processed_pages has correct length
        if len(self._processed_pages) != len(self._pages):
            self._processed_pages = [None] * len(self._pages)

        # Clear protected regions display before processing
        self.before_panel.clear_protected_regions()

        # Track which pages were processed for incremental update
        processed_updates = {}

        # Debug: print sliding window state
        loaded_pages = [i for i, p in enumerate(self._pages) if p is not None]
        print(f"[DEBUG] _process_pages_with_cached_regions: loaded_pages={loaded_pages}")
        print(f"[DEBUG] before_panel._per_page_zones keys: {list(self.before_panel._per_page_zones.keys())}")

        for i, page in enumerate(self._pages):
            # Skip None pages (unloaded in sliding window mode)
            if page is None:
                continue

            # Get zones for this specific page from per_page_zones
            page_zones = self._get_zones_for_page(i)
            print(f"[DEBUG] Page {i}: zones count = {len(page_zones)}")

            # Always display protected regions overlay if text protection is enabled
            if self._text_protection_enabled:
                regions = self._cached_regions.get(i, [])
                self.before_panel.set_protected_regions(i, regions, margin=self._text_protection_margin)

            if page_zones:
                if self._text_protection_enabled:
                    regions = self._cached_regions.get(i, [])
                    processed = self._processor.process_image(page, page_zones, protected_regions=regions)
                    self._processed_pages[i] = processed
                    processed_updates[i] = processed
                else:
                    processed = self._processor.process_image(page, page_zones)
                    self._processed_pages[i] = processed
                    processed_updates[i] = processed
            else:
                # No zones for this page - keep original
                self._processed_pages[i] = page.copy()
                processed_updates[i] = self._processed_pages[i]

        # Update after_panel incrementally instead of full rebuild
        need_recenter = False
        for page_idx, processed_img in processed_updates.items():
            # Check if size changed
            if page_idx < len(self.after_panel._page_items):
                old_pixmap = self.after_panel._page_items[page_idx].pixmap()
                old_w = old_pixmap.width() if old_pixmap else 0
                self.after_panel.update_page(page_idx, processed_img)
                new_pixmap = self.after_panel._page_items[page_idx].pixmap()
                if new_pixmap and new_pixmap.width() != old_w:
                    need_recenter = True
            else:
                self.after_panel.update_page(page_idx, processed_img)

        # Recenter after_panel if any page changed size
        if need_recenter:
            self.after_panel._recenter_all_pages()

        # Force UI refresh on Windows (Mac does this automatically)
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

        # Hide loading overlay after processing complete
        self._hide_loading()

    def _get_cached_regions(self, page_idx: int, page: 'np.ndarray') -> list:
        """Lấy cached regions hoặc detect mới nếu chưa có"""
        if page_idx not in self._cached_regions:
            regions = self._processor.detect_protected_regions(page)
            self._cached_regions[page_idx] = regions
        return self._cached_regions[page_idx]

    def clear_cached_regions(self):
        """Xóa cache khi cần detect lại (thay đổi settings, load PDF mới)"""
        self._cached_regions.clear()
            
    def _get_zones_for_page(self, page_idx: int, convert_to_percent: bool = False,
                            set_target_page: bool = False) -> List[Zone]:
        """Get zones for a specific page from per_page_zones

        Returns only zones that exist in per_page_zones[page_idx].
        Handles different storage formats:
        - corner_*: (w_px, h_px) -> Zone with size_mode='fixed' or 'percent' if convert_to_percent
        - margin_*: (length_pct, depth_px) -> Zone with size_mode='hybrid' or 'percent' if convert_to_percent
        - custom_*/protect_*: (x_pct, y_pct, w_pct, h_pct) -> Zone with size_mode='percent'

        Args:
            page_idx: Page index
            convert_to_percent: If True, convert all zones to percent mode for DPI-independent output
            set_target_page: If True, set target_page=page_idx and page_filter='none' on each zone
        """
        from core.processor import Zone

        page_zones = []
        per_page_zones = self.before_panel._per_page_zones

        if page_idx not in per_page_zones:
            return []

        # Get preview page dimensions for pixel-to-percent conversion
        img_w, img_h = 1, 1  # Defaults for non-convert mode (not used in calculations)
        if convert_to_percent:
            img_w, img_h = 0, 0  # Reset to detect if we got valid dimensions
            # Try to get dimensions from page_items first (QGraphicsPixmapItem)
            if page_idx < len(self.before_panel._page_items):
                page_rect = self.before_panel._page_items[page_idx].boundingRect()
                img_w, img_h = int(page_rect.width()), int(page_rect.height())
            # Fallback to _pages numpy array if page_items not available
            elif page_idx < len(self._pages) and self._pages[page_idx] is not None:
                img_h, img_w = self._pages[page_idx].shape[:2]

            # Safety check: if we can't get valid dimensions, return empty
            # This prevents garbage percentage values like 10000%
            if img_w <= 0 or img_h <= 0:
                print(f"[WARNING] Cannot get page dimensions for page {page_idx}, skipping zone conversion")
                return []

        for zone_id, zone_data in per_page_zones[page_idx].items():
            # Find zone_def for this zone_id to get threshold and other properties
            # self._zones contains both preset (corners, edges) and custom zones
            zone_def = None
            for z in self._zones:
                if z.id == zone_id:
                    zone_def = z
                    break

            if zone_def and not zone_def.enabled:
                continue  # Skip disabled zones

            zone_id_lower = zone_id.lower()

            if zone_id_lower.startswith('corner_') and len(zone_data) == 2:
                w_px, h_px = zone_data

                if convert_to_percent:
                    # Convert to percent for DPI-independent output
                    w_pct = w_px / img_w if img_w > 0 else 0.12
                    h_pct = h_px / img_h if img_h > 0 else 0.12

                    # Calculate position based on corner type
                    if zone_id_lower == 'corner_tl':
                        x_pct, y_pct = 0.0, 0.0
                    elif zone_id_lower == 'corner_tr':
                        x_pct, y_pct = 1.0 - w_pct, 0.0
                    elif zone_id_lower == 'corner_bl':
                        x_pct, y_pct = 0.0, 1.0 - h_pct
                    elif zone_id_lower == 'corner_br':
                        x_pct, y_pct = 1.0 - w_pct, 1.0 - h_pct
                    else:
                        x_pct, y_pct = 0.0, 0.0

                    page_zone = Zone(
                        id=zone_id,
                        name=zone_def.name if zone_def else zone_id,
                        x=x_pct, y=y_pct,
                        width=w_pct, height=h_pct,
                        threshold=zone_def.threshold if zone_def else 7,
                        enabled=True,
                        zone_type=getattr(zone_def, 'zone_type', 'remove') if zone_def else 'remove',
                        size_mode='percent'
                    )
                else:
                    # Original fixed mode for preview
                    page_zone = Zone(
                        id=zone_id,
                        name=zone_def.name if zone_def else zone_id,
                        x=0.0, y=0.0,
                        width=0.12, height=0.12,
                        threshold=zone_def.threshold if zone_def else 7,
                        enabled=True,
                        zone_type=getattr(zone_def, 'zone_type', 'remove') if zone_def else 'remove',
                        size_mode='fixed',
                        width_px=w_px,
                        height_px=h_px
                    )

            elif zone_id_lower.startswith('margin_') and len(zone_data) == 2:
                length_pct, depth_px = zone_data

                if convert_to_percent:
                    # Convert to percent for DPI-independent output
                    # Match Zone.to_pixels() logic: left/top aligned (no centering)
                    if zone_id_lower in ('margin_top', 'margin_bottom'):
                        w_pct = length_pct
                        h_pct = depth_px / img_h if img_h > 0 else 0.08
                        x_pct = 0.0
                        y_pct = 0.0 if zone_id_lower == 'margin_top' else (1.0 - h_pct)
                    else:  # margin_left, margin_right
                        w_pct = depth_px / img_w if img_w > 0 else 0.08
                        h_pct = length_pct
                        x_pct = 0.0 if zone_id_lower == 'margin_left' else (1.0 - w_pct)
                        y_pct = 0.0

                    page_zone = Zone(
                        id=zone_id,
                        name=zone_def.name if zone_def else zone_id,
                        x=x_pct, y=y_pct,
                        width=w_pct, height=h_pct,
                        threshold=zone_def.threshold if zone_def else 7,
                        enabled=True,
                        zone_type=getattr(zone_def, 'zone_type', 'remove') if zone_def else 'remove',
                        size_mode='percent'
                    )
                else:
                    # Original hybrid mode for preview
                    if zone_id_lower in ('margin_top', 'margin_bottom'):
                        page_zone = Zone(
                            id=zone_id,
                            name=zone_def.name if zone_def else zone_id,
                            x=0.0, y=0.0,
                            width=length_pct, height=0.08,
                            threshold=zone_def.threshold if zone_def else 7,
                            enabled=True,
                            zone_type=getattr(zone_def, 'zone_type', 'remove') if zone_def else 'remove',
                            size_mode='hybrid',
                            width_px=0,
                            height_px=depth_px
                        )
                    else:
                        page_zone = Zone(
                            id=zone_id,
                            name=zone_def.name if zone_def else zone_id,
                            x=0.0, y=0.0,
                            width=0.08, height=length_pct,
                            threshold=zone_def.threshold if zone_def else 7,
                            enabled=True,
                            zone_type=getattr(zone_def, 'zone_type', 'remove') if zone_def else 'remove',
                            size_mode='hybrid',
                            width_px=depth_px,
                            height_px=0
                        )

            else:
                # Custom/protect or legacy format: (x_pct, y_pct, w_pct, h_pct)
                threshold_val = zone_def.threshold if zone_def else 7
                # Infer zone_type from zone_id if zone_def is None (persisted zones)
                if zone_def:
                    zone_type_val = getattr(zone_def, 'zone_type', 'remove')
                elif zone_id_lower.startswith('protect_'):
                    zone_type_val = 'protect'
                else:
                    zone_type_val = 'remove'
                page_zone = Zone(
                    id=zone_id,
                    name=zone_def.name if zone_def else zone_id,
                    x=zone_data[0],
                    y=zone_data[1],
                    width=zone_data[2],
                    height=zone_data[3],
                    threshold=threshold_val,
                    enabled=True,
                    zone_type=zone_type_val,
                    size_mode='percent'
                )

            # Set target_page for per-page zone filtering (used in batch mode)
            if set_target_page:
                page_zone.page_filter = 'none'
                page_zone.target_page = page_idx

            page_zones.append(page_zone)

        return page_zones

    def get_zones_for_processing(self) -> List[Zone]:
        """Get zones with user-modified coordinates for Clean process.

        Returns zones from page 0 (or first available page) since in sync mode
        all pages share the same zone coordinates after user modifications.
        This ensures Clean uses the exact same zones shown in preview Đích.

        Uses convert_to_percent=False to preserve hybrid mode with width_px/height_px.
        DPI scaling is handled in processor.py via render_dpi parameter.
        """
        per_page_zones = self.before_panel._per_page_zones

        # Find first page with zones
        for page_idx in sorted(per_page_zones.keys()):
            # convert_to_percent=False preserves hybrid mode for DPI scaling
            zones = self._get_zones_for_page(page_idx, convert_to_percent=False)
            if zones:
                return zones

        # Fallback: return zones from _zones (definitions)
        return [z for z in self._zones if z.enabled]

    def get_page_filter(self) -> str:
        """Get current page filter mode: 'all', 'odd', 'even', 'none'"""
        return self.before_panel._page_filter

    def get_zones_for_page_processing(self, page_idx: int) -> List[Zone]:
        """Get zones for a specific page in Clean process.

        Always uses per-page zones from _per_page_zones[page_idx].
        This ensures zones are only applied to pages they were added to.

        Args:
            page_idx: 0-based page index

        Returns:
            List of Zone objects for this page, or empty list if no zones
        """
        page_filter = self.before_panel._page_filter

        # Check if this page should be processed based on filter
        if page_filter != 'none':
            if not self.before_panel._should_apply_to_page(page_idx):
                return []

        # Always use per-page zones - preserve hybrid mode for DPI scaling
        per_page_zones = self.before_panel._per_page_zones
        zones = self._get_zones_for_page(page_idx, convert_to_percent=False)
        return zones

    def get_all_zones_for_batch_processing(self) -> List[Zone]:
        """Get ALL zones from ALL pages for batch Clean processing.

        Collects zones from all pages in _per_page_zones and sets target_page
        on each zone so _get_applicable_zones can filter correctly.

        Returns:
            List of Zone objects with target_page set to their source page
        """
        all_zones = []
        per_page_zones = self.before_panel._per_page_zones

        for page_idx in sorted(per_page_zones.keys()):
            # Get zones with target_page set
            page_zones = self._get_zones_for_page(page_idx, convert_to_percent=False,
                                                   set_target_page=True)
            all_zones.extend(page_zones)

        return all_zones

    def get_per_file_zones_for_batch(self) -> dict:
        """Get per-file zones storage for batch processing.

        Returns _per_file_zones dict so batch processing can use
        file-specific Zone Riêng (custom zones).

        Returns:
            Dict mapping file_path -> {page_idx: {zone_id: zone_data}}
        """
        return self.before_panel._per_file_zones.copy()

    def _sync_zoom(self, zoom: float):
        """Sync zoom"""
        self.before_panel.view.set_zoom(zoom)
        self.after_panel.view.set_zoom(zoom)
    
    def _sync_scroll_from_before(self, h: int, v: int):
        self.after_panel.view.sync_scroll(h, v)
        # Detect visible page and emit signal if changed
        self._detect_and_emit_page_change()

    def _sync_scroll_from_after(self, h: int, v: int):
        self.before_panel.view.sync_scroll(h, v)
        # Detect visible page and emit signal if changed
        self._detect_and_emit_page_change()

    def _on_thumbnail_page_clicked(self, page_index: int):
        """Handle thumbnail click - scroll both panels to page and update page number"""
        # Check if page is loaded (for lazy loading support)
        loaded_count = len(self._pages)
        if page_index >= loaded_count:
            # Page not loaded yet - request loading
            self.page_load_requested.emit(page_index)
            return

        # Skip page detection to prevent thumbnail from scrolling again
        self._skip_page_detection = True
        self._last_emitted_page = page_index

        # Scroll both panels to same page
        self.before_panel.set_current_page(page_index)
        self.after_panel.set_current_page(page_index)
        # Emit page_changed to update bottom bar page number
        self.page_changed.emit(page_index)

        # Reset skip flag after scroll events are processed
        QTimer.singleShot(1000, lambda: setattr(self, '_skip_page_detection', False))

    def _on_thumbnail_collapsed_changed(self, collapsed: bool):
        """Handle thumbnail panel collapse state change - reset splitter sizes"""
        # Reset splitter sizes to maintain equal main preview widths
        self._reset_splitter_sizes()
        self.thumbnail_collapsed_changed.emit(collapsed)

    def is_thumbnail_collapsed(self) -> bool:
        """Check if thumbnail panel is collapsed (Gốc panel only)"""
        return self.before_panel.is_thumbnail_collapsed()

    def toggle_thumbnail_panel(self):
        """Toggle thumbnail panel collapsed state (Gốc panel only)"""
        if self.before_panel._thumbnail_panel is not None:
            self.before_panel._thumbnail_panel._toggle_collapsed()

    def get_thumbnail_width(self) -> int:
        """Get current thumbnail panel width"""
        return self.before_panel.get_thumbnail_width()

    def _detect_and_emit_page_change(self):
        """Detect current visible page from scroll position and emit page_changed if changed"""
        # Skip detection when programmatically scrolling (e.g., user input page number)
        if self._skip_page_detection:
            return
        if not self._pages or not self.before_panel._page_positions:
            return

        # Get current vertical scroll position in scene coordinates
        v_scroll = self.before_panel.view.verticalScrollBar().value()
        zoom = self.before_panel.view._zoom

        # Convert scroll position to scene coordinates
        scene_y = v_scroll / zoom if zoom > 0 else v_scroll

        # Add viewport height / 3 to find page that's mostly visible (not just at top)
        viewport_height = self.before_panel.view.viewport().height()
        scene_y += (viewport_height / zoom / 3) if zoom > 0 else 0

        # Find which page is at this position
        page_positions = self.before_panel._page_positions
        current_page = 0

        for i, pos in enumerate(page_positions):
            if scene_y >= pos:
                current_page = i
            else:
                break

        # Clamp to valid page range (defensive)
        max_page = len(self._pages) - 1
        if current_page > max_page:
            current_page = max_page

        # Emit signal if page changed
        if current_page != self._last_emitted_page:
            self._last_emitted_page = current_page
            self.before_panel._current_page = current_page  # Update internal state
            self.after_panel._current_page = current_page
            # Update thumbnail highlight - scroll=True to follow preview scroll
            self.before_panel.update_thumbnail_highlight(current_page, scroll=True)
            self.page_changed.emit(current_page)
    
    def zoom_in(self):
        zoom = self.before_panel.view._zoom * 1.2
        self._sync_zoom(zoom)
    
    def zoom_out(self):
        zoom = self.before_panel.view._zoom / 1.2
        self._sync_zoom(zoom)
    
    def zoom_fit(self):
        """Fit toàn bộ scene vào view"""
        self.before_panel.view.fitInView(
            self.before_panel.scene.sceneRect(),
            Qt.KeepAspectRatio
        )
        self.after_panel.view.fitInView(
            self.after_panel.scene.sceneRect(),
            Qt.KeepAspectRatio
        )
    
    def zoom_fit_width(self, page_index: int = None, scroll_to_page: bool = False):
        """Fit vừa chiều rộng trang và căn giữa trang trong view

        Args:
            page_index: Index của trang cần fit. None = trang hiện tại
            scroll_to_page: True = scroll vertical đến TOP của trang (dùng khi mở file mới)
                           False = giữ trang hiện tại visible (scroll đến trang đó)
        """
        if not self._pages:
            return

        # Xác định trang cần fit
        if page_index is None:
            page_index = self.before_panel.get_current_page()
        page_index = max(0, min(page_index, len(self._pages) - 1))

        # Đảm bảo page items đã được tạo
        if not self.before_panel._page_items or page_index >= len(self.before_panel._page_items):
            # Retry after short delay if page items not ready
            QTimer.singleShot(50, lambda: self.zoom_fit_width(page_index, scroll_to_page))
            return

        # Lấy page item và vị trí trong scene
        page_item = self.before_panel._page_items[page_index]
        page_rect = page_item.boundingRect()
        page_pos = page_item.pos()
        page_width = page_rect.width()

        if page_width <= 0:
            return

        # Lấy viewport width thực tế (trừ scrollbar nếu visible)
        viewport = self.before_panel.view.viewport()
        viewport_width = viewport.width()

        # Nếu viewport quá nhỏ (chưa layout xong), dùng parent width
        if viewport_width < 100:
            viewport_width = self.before_panel.view.width() - 20

        # Trừ scrollbar width nếu visible
        v_scrollbar = self.before_panel.view.verticalScrollBar()
        if v_scrollbar.isVisible():
            viewport_width -= v_scrollbar.width()

        # Margin nhỏ để tránh tràn
        viewport_width -= 4

        if viewport_width <= 0:
            # Retry if viewport not ready
            QTimer.singleShot(50, lambda: self.zoom_fit_width(page_index, scroll_to_page))
            return

        # Tính zoom để fit chiều rộng trang vào viewport
        new_zoom = viewport_width / page_width
        new_zoom = max(0.1, min(new_zoom, 2.0))

        # Reset và apply zoom đồng bộ cho cả 2 panel
        self.before_panel.view.resetTransform()
        self.before_panel.view.scale(new_zoom, new_zoom)
        self.before_panel.view._zoom = new_zoom

        self.after_panel.view.resetTransform()
        self.after_panel.view.scale(new_zoom, new_zoom)
        self.after_panel.view._zoom = new_zoom

        # Skip page detection during programmatic scroll
        self._skip_page_detection = True
        self._last_emitted_page = page_index

        # Scroll đến trang hiện tại để giữ nó visible
        # scroll_to_page=True: scroll đến TOP của trang
        # scroll_to_page=False: scroll đến trang (giữ trang visible)
        self._scroll_to_page(page_index, align_top=scroll_to_page)

        # Reset skip flag after scroll events are processed
        QTimer.singleShot(500, lambda: setattr(self, '_skip_page_detection', False))

    def _scroll_to_page(self, page_index: int, align_top: bool = False):
        """Scroll view đến trang chỉ định

        Args:
            page_index: Index của trang
            align_top: True = căn top của trang với top của viewport
                      False = căn trang sao cho visible (center nếu có thể)
        """
        if page_index >= len(self.before_panel._page_items):
            return

        # Lấy page item
        page_item = self.before_panel._page_items[page_index]
        page_rect = page_item.boundingRect()
        page_pos = page_item.pos()
        zoom = self.before_panel.view._zoom

        # Tính vị trí vertical scroll
        page_top_scaled = page_pos.y() * zoom

        if align_top:
            # Căn top của trang với top của viewport
            target_v_scroll = int(page_top_scaled)
        else:
            # Căn trang ở giữa viewport (hoặc gần top nếu trang cao)
            viewport_height = self.before_panel.view.viewport().height()
            page_height_scaled = page_rect.height() * zoom

            if page_height_scaled <= viewport_height:
                # Trang nhỏ hơn viewport: center trang trong viewport
                target_v_scroll = int(page_top_scaled - (viewport_height - page_height_scaled) / 2)
            else:
                # Trang lớn hơn viewport: căn top với một chút margin
                target_v_scroll = int(page_top_scaled - 20)

            target_v_scroll = max(0, target_v_scroll)

        # Apply vertical scroll
        self.before_panel.view.verticalScrollBar().setValue(target_v_scroll)
        self.after_panel.view.verticalScrollBar().setValue(target_v_scroll)

        # Căn giữa horizontal
        viewport_width = self.before_panel.view.viewport().width()
        page_center_x_scaled = (page_pos.x() + page_rect.width() / 2) * zoom
        target_h_scroll = int(page_center_x_scaled - viewport_width / 2)
        target_h_scroll = max(0, target_h_scroll)

        self.before_panel.view.horizontalScrollBar().setValue(target_h_scroll)
        self.after_panel.view.horizontalScrollBar().setValue(target_h_scroll)

    def zoom_fit_height(self, page_index: int = None):
        """Fit chiều cao trang vào viewport

        Args:
            page_index: Index của trang cần fit. None = trang hiện tại
        """
        if not self._pages:
            return

        # Xác định trang cần fit
        if page_index is None:
            page_index = self.before_panel.get_current_page()
        page_index = max(0, min(page_index, len(self._pages) - 1))

        # Đảm bảo page items đã được tạo
        if not self.before_panel._page_items or page_index >= len(self.before_panel._page_items):
            # Retry after short delay if page items not ready
            QTimer.singleShot(50, lambda: self.zoom_fit_height(page_index))
            return

        # Lấy page item và kích thước
        page_item = self.before_panel._page_items[page_index]
        page_rect = page_item.boundingRect()
        page_height = page_rect.height()

        if page_height <= 0:
            return

        # Lấy viewport height thực tế (trừ scrollbar nếu visible)
        viewport = self.before_panel.view.viewport()
        viewport_height = viewport.height()

        # Nếu viewport quá nhỏ (chưa layout xong), dùng parent height
        if viewport_height < 100:
            viewport_height = self.before_panel.view.height() - 20

        # Trừ scrollbar height nếu visible
        h_scrollbar = self.before_panel.view.horizontalScrollBar()
        if h_scrollbar.isVisible():
            viewport_height -= h_scrollbar.height()

        # Margin nhỏ để tránh tràn
        viewport_height -= 4

        if viewport_height <= 0:
            # Retry if viewport not ready
            QTimer.singleShot(50, lambda: self.zoom_fit_height(page_index))
            return

        # Tính zoom để fit chiều cao trang vào viewport
        new_zoom = viewport_height / page_height
        new_zoom = max(0.1, min(new_zoom, 2.0))

        # Reset và apply zoom đồng bộ cho cả 2 panel
        self.before_panel.view.resetTransform()
        self.before_panel.view.scale(new_zoom, new_zoom)
        self.before_panel.view._zoom = new_zoom

        self.after_panel.view.resetTransform()
        self.after_panel.view.scale(new_zoom, new_zoom)
        self.after_panel.view._zoom = new_zoom

        # Scroll đến trang và căn giữa
        self._scroll_to_page(page_index, align_top=False)

    def set_zoom(self, zoom: float):
        """Set zoom level"""
        zoom = max(0.1, min(5.0, zoom))

        # Reset và set zoom mới
        self.before_panel.view.resetTransform()
        self.before_panel.view.scale(zoom, zoom)
        self.before_panel.view._zoom = zoom

        self.after_panel.view.resetTransform()
        self.after_panel.view.scale(zoom, zoom)
        self.after_panel.view._zoom = zoom

        # Sync scroll positions after zoom change
        h = self.before_panel.view.horizontalScrollBar().value()
        v = self.before_panel.view.verticalScrollBar().value()
        self.after_panel.view.sync_scroll(h, v)
    
    def get_processed_pages(self) -> List[np.ndarray]:
        """Lấy danh sách ảnh đã xử lý"""
        return self._processed_pages

    def set_text_protection(self, options):
        """Set text protection options"""
        from core.processor import TextProtectionOptions
        self._text_protection_enabled = options.enabled
        self._text_protection_margin = options.margin  # Store margin for overlay display

        # Clear cache and reset progress tracking for fresh detection
        self._cached_regions.clear()
        self._detection_displayed_pages.clear()
        self._detection_progress_shown = False

        # Clear protection regions display if disabling
        if not options.enabled:
            self.before_panel.clear_protected_regions()

        # Loading overlay will be shown automatically in _start_background_detection
        self._processor.set_text_protection(options)
        self._schedule_process()

    def set_draw_mode(self, mode):
        """Enable/disable draw mode on before panel for drawing custom zones

        Args:
            mode: None (off), 'remove' (blue), or 'protect' (pink)
        """
        self.before_panel.set_draw_mode(mode)

    def _on_rect_drawn(self, x: float, y: float, w: float, h: float, mode: str, page_idx: int):
        """Forward rect_drawn signal from before_panel"""
        self.rect_drawn.emit(x, y, w, h, mode, page_idx)
