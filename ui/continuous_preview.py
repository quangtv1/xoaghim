"""
Continuous Preview - Preview liên tục nhiều trang với nền đen
"""

import os

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsRectItem, QFrame, QSplitter, QScrollArea, QPushButton,
    QGraphicsOpacityEffect
)
from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QTimer, QPointF, QPropertyAnimation, QEasingCurve
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
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0.15);")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # Container cho loading indicator
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: #F9FAFB;
                border-radius: 12px;
            }
        """)
        container.setFixedSize(100, 90)
        container_layout = QVBoxLayout(container)
        container_layout.setAlignment(Qt.AlignCenter)
        container_layout.setSpacing(10)

        # Custom spinner widget
        self._spinner = SpinnerWidget(size=36, line_width=4)
        container_layout.addWidget(self._spinner, alignment=Qt.AlignCenter)

        # Loading text (smaller, below)
        self._loading_label = QLabel("Đang phát hiện")
        self._loading_label.setStyleSheet("""
            font-size: 11px;
            color: #6B7280;
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

import numpy as np
import cv2
from typing import List, Optional, Dict, TYPE_CHECKING


from ui.zone_item import ZoneItem
from core.processor import Zone, StapleRemover


import threading


class DetectionRunner:
    """Runner để chạy YOLO detection trong Python thread (không dùng QThread)"""

    def __init__(self, processor, pages, original_indices, callback):
        self._processor = processor
        self._pages = pages  # Copy of pages
        self._original_indices = original_indices
        self._callback = callback  # Called when done with results
        self._cancelled = False
        self._thread = None

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
                print(f"[Detection] Page {original_idx}: {len(regions)} regions found")
            except Exception as e:
                original_idx = self._original_indices[i]
                results[original_idx] = []
                print(f"[Detection] Error on page {original_idx}: {e}")
                import traceback
                traceback.print_exc()

        # Call callback with results (if not cancelled)
        if not self._cancelled and self._callback:
            self._callback(results)


class ContinuousGraphicsView(QGraphicsView):
    """GraphicsView với nền xám và synchronized scroll"""

    zoom_changed = pyqtSignal(float)
    scroll_changed = pyqtSignal(int, int)
    # rect_drawn: x, y, w, h (as % of page), mode ('remove' or 'protect')
    rect_drawn = pyqtSignal(float, float, float, float, str)
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
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

        # Enable drag and drop on view
        self.setAcceptDrops(True)

        self._zoom = 1.0
        self._syncing = False

        # Draw mode: None, 'remove', or 'protect'
        self._draw_mode = None
        self._drawing = False
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
        print(f"[DrawMode] ContinuousGraphicsView.set_draw_mode: mode={mode}, page_bounds={page_bounds}")
        self._draw_mode = mode
        self._page_bounds = page_bounds
        self._all_page_bounds = all_page_bounds or []
        if mode:
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(Qt.CrossCursor)
            self.viewport().setCursor(Qt.CrossCursor)
            print(f"[DrawMode] Cursor set to CrossCursor")
        else:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.setCursor(Qt.ArrowCursor)
            self.viewport().setCursor(Qt.ArrowCursor)
            # Clean up any in-progress drawing
            if self._draw_rect_item and self._draw_rect_item.scene():
                self.scene().removeItem(self._draw_rect_item)
            self._draw_rect_item = None
            self._drawing = False
            self._draw_start = None

    def _get_draw_colors(self):
        """Get pen and brush colors based on draw mode"""
        if self._draw_mode == 'protect':
            # Pink/Red for protection
            pen = QPen(QColor(244, 114, 182), 2)  # Pink #F472B6
            brush = QBrush(QColor(244, 114, 182, 50))
        else:
            # Blue for removal (default)
            pen = QPen(QColor(59, 130, 246), 2)  # Blue #3B82F6
            brush = QBrush(QColor(59, 130, 246, 50))
        return pen, brush

    def mousePressEvent(self, event):
        """Start drawing if in draw mode"""
        if self._draw_mode and event.button() == Qt.LeftButton:
            self._drawing = True
            self._draw_start = self.mapToScene(event.pos())
            # Don't create rect yet - wait for actual dragging
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
            x = min(self._draw_start.x(), current.x())
            y = min(self._draw_start.y(), current.y())
            w = abs(current.x() - self._draw_start.x())
            h = abs(current.y() - self._draw_start.y())

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
                rect_center_y = rect.y() + rect.height() / 2
                page_bounds = self._find_page_at_y(rect_center_y)

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
                            self.rect_drawn.emit(x, y, w, h, self._draw_mode)

            # Clean up drawing rect but KEEP draw mode active
            if self._draw_rect_item and self._draw_rect_item.scene():
                self.scene().removeItem(self._draw_rect_item)
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


class ContinuousPreviewPanel(QFrame):
    """
    Panel preview liên tục nhiều trang
    """

    zone_changed = pyqtSignal(str)  # zone_id
    zone_selected = pyqtSignal(str)  # zone_id
    zone_delete = pyqtSignal(str)  # zone_id - request to delete custom zone
    placeholder_clicked = pyqtSignal()  # When placeholder "Mở file" is clicked
    folder_placeholder_clicked = pyqtSignal()  # When placeholder "Mở thư mục" is clicked
    file_dropped = pyqtSignal(str)  # When file is dropped (file_path)
    folder_dropped = pyqtSignal(str)  # When folder is dropped (folder_path)
    files_dropped = pyqtSignal(list)  # When multiple PDF files are dropped
    close_requested = pyqtSignal()  # When close button is clicked
    # rect_drawn: x, y, w, h (as % of page), mode ('remove' or 'protect')
    rect_drawn = pyqtSignal(float, float, float, float, str)
    
    PAGE_SPACING = 20  # Khoảng cách giữa các trang
    
    def __init__(self, title: str, show_overlay: bool = False, parent=None):
        super().__init__(parent)
        
        self.show_overlay = show_overlay
        self._pages: List[np.ndarray] = []  # List of page images
        self._page_items: List[QGraphicsPixmapItem] = []  # Graphics items
        self._zones: List[ZoneItem] = []
        self._zone_definitions: List[Zone] = []  # Zone definitions (shared across pages)
        self._page_positions: List[float] = []  # Y position of each page
        self._has_placeholder = False  # Track if placeholder is shown
        self._placeholder_file_rect = None  # Click area for "Mở file"
        self._placeholder_folder_rect = None  # Click area for "Mở thư mục"
        self._file_hover_bg = None  # Hover background for file icon
        self._folder_hover_bg = None  # Hover background for folder icon
        self._view_mode = 'continuous'  # 'continuous' or 'single'
        self._current_page = 0  # Current page index (0-based) for single page mode
        self._page_filter = 'all'  # 'all', 'odd', 'even', 'none'
        # Per-page zone storage for 'none' mode (independent zones per page)
        self._per_page_zones: Dict[int, Dict[str, tuple]] = {}  # {page_idx: {zone_id: (x,y,w,h)}}
        
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
        title_layout.setContentsMargins(8, 0, 4, 0)  # Reduce right margin
        title_layout.setSpacing(4)
        
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
        
        layout.addWidget(title_bar)
        
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
        layout.addWidget(self.view)
        
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

    def _init_per_page_zones(self):
        """Initialize per-page zones - start EMPTY for 'none' mode (Tự do)

        In 'none' mode, each page starts empty and zones are added individually
        to the current page when user draws or selects them.
        """
        self._per_page_zones.clear()
        for page_idx in range(len(self._pages)):
            self._per_page_zones[page_idx] = {}
        # Don't copy zone_definitions - start empty, user adds zones per page
    
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
        """Get zone rect for a specific page (used in per-page mode)"""
        base_id = zone_id.rsplit('_', 1)[0] if '_' in zone_id else zone_id
        
        if self._page_filter == 'none':
            # Per-page mode: get from per_page_zones
            if page_idx in self._per_page_zones:
                return self._per_page_zones[page_idx].get(base_id)
        
        # Sync mode: get from zone definitions
        for zdef in self._zone_definitions:
            if zdef.id == base_id:
                return (zdef.x, zdef.y, zdef.width, zdef.height)
        return None
    
    def set_pages(self, pages: List[np.ndarray]):
        """Set danh sách ảnh các trang"""
        self._pages = pages
        self._current_page = 0  # Reset to first page
        # Clear per_page_zones when loading new file
        # This ensures zones will be re-added by set_zone_definitions
        self._per_page_zones.clear()
        self._rebuild_scene()
    
    def _rebuild_scene(self):
        """Xây dựng lại scene với tất cả các trang hoặc 1 trang"""
        self.scene.clear()
        self._page_items.clear()
        self._zones.clear()
        self._page_positions.clear()
        self._has_placeholder = False
        self._placeholder_file_rect = None
        self._placeholder_folder_rect = None
        self._file_hover_bg = None
        self._folder_hover_bg = None
        # Clear protected regions
        if hasattr(self, '_protected_region_items'):
            self._protected_region_items.clear()
        # Reset cursor on both view and viewport
        self.view.setCursor(Qt.ArrowCursor)
        self.view.viewport().setCursor(Qt.ArrowCursor)
        # Restore drag mode
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        
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
        
        for page_idx, page_img in enumerate(self._pages):
            # Convert to QPixmap
            pixmap = self._numpy_to_pixmap(page_img)
            
            # Create item
            item = QGraphicsPixmapItem(pixmap)
            
            # Center horizontally (sẽ điều chỉnh sau)
            item.setPos(0, y_offset)
            
            self.scene.addItem(item)
            self._page_items.append(item)
            self._page_positions.append(y_offset)
            
            max_width = max(max_width, pixmap.width())
            y_offset += pixmap.height() + self.PAGE_SPACING
        
        # Center all pages horizontally
        for item in self._page_items:
            x = (max_width - item.pixmap().width()) / 2
            item.setPos(x, item.pos().y())
        
        # Update scene rect
        self.scene.setSceneRect(0, 0, max_width, y_offset)
        
        # Recreate zone overlays
        if self.show_overlay:
            self._recreate_zone_overlays()
    
    def _rebuild_scene_single(self):
        """Build scene with single page only"""
        if self._current_page >= len(self._pages):
            self._current_page = len(self._pages) - 1
        if self._current_page < 0:
            self._current_page = 0
        
        page_img = self._pages[self._current_page]
        pixmap = self._numpy_to_pixmap(page_img)
        
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
    
    def _add_placeholder(self):
        """Add placeholder with PDF document icon and Folder icon"""
        self._has_placeholder = True
        
        # Larger placeholder area
        placeholder_width = 500
        placeholder_height = 300
        
        # Spacing between icons
        icon_spacing = 80
        
        # === LEFT ICON: PDF Document (Mở file) ===
        icon_width = 24
        icon_height = 30
        file_icon_x = placeholder_width / 2 - icon_spacing - icon_width / 2
        icon_y = placeholder_height / 2 - 35
        
        # Hover background for "Mở file" - add first so it's behind icon (larger area +80%)
        file_hover_rect = QRectF(
            file_icon_x - 52, icon_y - 30,
            icon_width + 105, icon_height + 112
        )
        self._file_hover_bg = self.scene.addRect(file_hover_rect, 
            QPen(Qt.NoPen), QBrush(Qt.transparent))
        self._file_hover_bg.setZValue(-1)
        
        pen = QPen(QColor(140, 140, 140))
        pen.setWidth(1)
        pen.setCapStyle(Qt.SquareCap)
        pen.setJoinStyle(Qt.MiterJoin)
        
        # Document outline (with folded corner)
        corner_size = 7
        self.scene.addLine(file_icon_x, icon_y, file_icon_x, icon_y + icon_height, pen)
        self.scene.addLine(file_icon_x, icon_y + icon_height, file_icon_x + icon_width, icon_y + icon_height, pen)
        self.scene.addLine(file_icon_x + icon_width, icon_y + icon_height, file_icon_x + icon_width, icon_y + corner_size, pen)
        self.scene.addLine(file_icon_x, icon_y, file_icon_x + icon_width - corner_size, icon_y, pen)
        self.scene.addLine(file_icon_x + icon_width - corner_size, icon_y, file_icon_x + icon_width, icon_y + corner_size, pen)
        self.scene.addLine(file_icon_x + icon_width - corner_size, icon_y, file_icon_x + icon_width - corner_size, icon_y + corner_size, pen)
        self.scene.addLine(file_icon_x + icon_width - corner_size, icon_y + corner_size, file_icon_x + icon_width, icon_y + corner_size, pen)
        
        # "PDF" text inside document
        pdf_text = self.scene.addText("PDF")
        pdf_font = pdf_text.font()
        pdf_font.setPixelSize(8)
        pdf_font.setBold(True)
        pdf_text.setFont(pdf_font)
        pdf_text.setDefaultTextColor(QColor(140, 140, 140))
        pdf_rect = pdf_text.boundingRect()
        pdf_text.setPos(
            file_icon_x + (icon_width - pdf_rect.width()) / 2,
            icon_y + (icon_height - pdf_rect.height()) / 2 + 2
        )
        
        # "Mở file" text
        file_hint = self.scene.addText("Mở file")
        file_hint_font = file_hint.font()
        file_hint_font.setPixelSize(13)
        file_hint.setFont(file_hint_font)
        file_hint.setDefaultTextColor(QColor(140, 140, 140))
        file_hint_rect = file_hint.boundingRect()
        file_hint.setPos(
            file_icon_x + (icon_width - file_hint_rect.width()) / 2,
            icon_y + icon_height + 8
        )
        
        # Store click area for "Mở file" (larger area +80%)
        self._placeholder_file_rect = QRectF(
            file_icon_x - 52, icon_y - 30,
            icon_width + 105, icon_height + file_hint_rect.height() + 90
        )
        
        # === RIGHT ICON: Folder (Mở thư mục) - rounded corners, thin line ===
        folder_icon_x = placeholder_width / 2 + icon_spacing - 12
        folder_width = 28
        folder_height = 20
        folder_y = icon_y + 5
        tab_width = 10
        tab_height = 5
        corner_r = 2  # Small corner radius
        
        # Hover background for "Mở thư mục" - add first so it's behind icon (larger area +80%)
        folder_hover_rect = QRectF(
            folder_icon_x - 52, icon_y - 30,
            folder_width + 105, icon_height + 112
        )
        self._folder_hover_bg = self.scene.addRect(folder_hover_rect,
            QPen(Qt.NoPen), QBrush(Qt.transparent))
        self._folder_hover_bg.setZValue(-1)
        
        # Pen for folder - thin line
        folder_pen = QPen(QColor(140, 140, 140))
        folder_pen.setWidth(1)
        folder_pen.setCapStyle(Qt.RoundCap)
        folder_pen.setJoinStyle(Qt.RoundJoin)
        
        # Draw folder using QPainterPath for rounded corners
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
        
        self.scene.addPath(path, folder_pen)
        
        # "Mở thư mục" text
        folder_hint = self.scene.addText("Mở thư mục")
        folder_hint_font = folder_hint.font()
        folder_hint_font.setPixelSize(13)
        folder_hint.setFont(folder_hint_font)
        folder_hint.setDefaultTextColor(QColor(140, 140, 140))
        folder_hint_rect = folder_hint.boundingRect()
        folder_hint.setPos(
            folder_icon_x + (folder_width - folder_hint_rect.width()) / 2,
            icon_y + icon_height + 8  # align with "Mở file" text
        )
        
        # Store click area for "Mở thư mục" (larger area +80%)
        self._placeholder_folder_rect = QRectF(
            folder_icon_x - 52, icon_y - 30,
            folder_width + 105, icon_height + folder_hint_rect.height() + 90
        )
        
        self.scene.setSceneRect(0, 0, placeholder_width, placeholder_height)
        
        # Center the scene without scaling (show at 1:1)
        self.view.resetTransform()
        self.view.centerOn(placeholder_width / 2, placeholder_height / 2)
        
        # Disable drag mode when placeholder is shown
        self.view.setDragMode(QGraphicsView.NoDrag)
        
        # Enable mouse tracking for cursor updates
        self.view.setMouseTracking(True)
        self.view.viewport().setMouseTracking(True)
        
        # Set cursor to cross (+) for "add" hint
        self.view.setCursor(Qt.CrossCursor)
        self.view.viewport().setCursor(Qt.CrossCursor)
        
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
            self.view.setCursor(Qt.CrossCursor)
            self.view.viewport().setCursor(Qt.CrossCursor)
    
    def _on_view_leave(self, event):
        """Handle mouse leave to reset hover backgrounds"""
        if self._has_placeholder:
            if self._file_hover_bg:
                self._file_hover_bg.setBrush(QBrush(Qt.transparent))
            if self._folder_hover_bg:
                self._folder_hover_bg.setBrush(QBrush(Qt.transparent))
    
    def _on_view_mouse_move(self, event):
        """Handle mouse move to update cursor and hover effects on placeholder"""
        if self._has_placeholder:
            # Always show cross cursor when placeholder is visible
            self.view.setCursor(Qt.CrossCursor)
            self.view.viewport().setCursor(Qt.CrossCursor)
            
            # Get mouse position in scene coordinates
            scene_pos = self.view.mapToScene(event.pos())
            
            # Hover color (blue like Run button)
            hover_color = QColor(37, 99, 235, 40)  # #2563EB with alpha
            
            # Check hover on file icon
            if self._placeholder_file_rect and self._placeholder_file_rect.contains(scene_pos):
                if self._file_hover_bg:
                    self._file_hover_bg.setBrush(QBrush(hover_color))
            else:
                if self._file_hover_bg:
                    self._file_hover_bg.setBrush(QBrush(Qt.transparent))
            
            # Check hover on folder icon
            if self._placeholder_folder_rect and self._placeholder_folder_rect.contains(scene_pos):
                if self._folder_hover_bg:
                    self._folder_hover_bg.setBrush(QBrush(hover_color))
            else:
                if self._folder_hover_bg:
                    self._folder_hover_bg.setBrush(QBrush(Qt.transparent))
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
        """Convert numpy BGR to QPixmap"""
        if len(image.shape) == 3:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        else:
            h, w = image.shape
            qimg = QImage(image.data, w, h, w, QImage.Format_Grayscale8)
        return QPixmap.fromImage(qimg.copy())
    
    def set_zone_definitions(self, zones: List[Zone]):
        """Set zone definitions - add new zones to pages based on current filter

        Filter logic (for ADDING new zones):
        - 'all': add to ALL pages
        - 'odd': add to odd pages (1, 3, 5...)
        - 'even': add to even pages (2, 4, 6...)
        - 'none' (Tự do): add to current page only

        Display: always show ALL zones in per_page_zones (no filter)
        """
        # Get currently displayed zones from per_page_zones (more reliable than _zone_definitions)
        old_zone_ids = set()
        for page_zones in self._per_page_zones.values():
            old_zone_ids.update(page_zones.keys())
        new_zone_ids = {z.id for z in zones if z.enabled}
        newly_added = new_zone_ids - old_zone_ids
        newly_removed = old_zone_ids - new_zone_ids

        # Ensure per_page_zones is initialized for all pages
        for page_idx in range(len(self._pages)):
            if page_idx not in self._per_page_zones:
                self._per_page_zones[page_idx] = {}

        # Build zone data map for comparison
        zone_data_map = {z.id: (z.x, z.y, z.width, z.height) for z in zones if z.enabled}

        # Add new zones to pages based on filter
        for zone in zones:
            if zone.id in newly_added and zone.enabled:
                zone_data = (zone.x, zone.y, zone.width, zone.height)
                pages_to_add = self._get_pages_for_filter()
                for page_idx in pages_to_add:
                    self._per_page_zones[page_idx][zone.id] = zone_data

        # Update existing zones if their data changed (for reset functionality)
        # Only update zones that exist and have different values
        existing_zones = new_zone_ids & old_zone_ids
        for zone_id in existing_zones:
            new_data = zone_data_map.get(zone_id)
            if new_data:
                pages_to_update = self._get_pages_for_filter()
                for page_idx in pages_to_update:
                    if page_idx in self._per_page_zones and zone_id in self._per_page_zones[page_idx]:
                        old_data = self._per_page_zones[page_idx][zone_id]
                        if old_data != new_data:
                            self._per_page_zones[page_idx][zone_id] = new_data

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

    def _get_pages_for_filter(self) -> List[int]:
        """Get list of page indices based on current filter"""
        if not self._pages:
            return []

        all_pages = list(range(len(self._pages)))

        if self._page_filter == 'all':
            return all_pages
        elif self._page_filter == 'odd':
            return [i for i in all_pages if (i + 1) % 2 == 1]  # 1, 3, 5... (1-based)
        elif self._page_filter == 'even':
            return [i for i in all_pages if (i + 1) % 2 == 0]  # 2, 4, 6... (1-based)
        elif self._page_filter == 'none':
            return [self._current_page] if self._current_page < len(self._pages) else []
        return all_pages
    
    def _recreate_zone_overlays(self):
        """Tạo lại overlay zones cho tất cả trang

        Display: Always show ALL zones in per_page_zones (no filter)
        Each page shows its own zones from per_page_zones[page_idx]
        """
        # Remove existing zones
        for zone in self._zones:
            self.scene.removeItem(zone)
        self._zones.clear()

        if not self._pages:
            return

        # Create zones for each page - show ALL zones (no filter)
        for page_idx, page_item in enumerate(self._page_items):
            page_rect = page_item.boundingRect()
            page_pos = page_item.pos()

            # Get zones for this page from per_page_zones
            page_zones = self._per_page_zones.get(page_idx, {})

            for zone_id, zone_coords in page_zones.items():
                # Find zone_def for this zone_id to get zone_type
                zone_def = None
                for zd in self._zone_definitions:
                    if zd.id == zone_id:
                        zone_def = zd
                        break

                if zone_def and not zone_def.enabled:
                    continue  # Skip disabled zones

                # Calculate pixel coordinates
                zx = zone_coords[0] * page_rect.width()
                zy = zone_coords[1] * page_rect.height()
                zw = zone_coords[2] * page_rect.width()
                zh = zone_coords[3] * page_rect.height()

                # Create zone item with zone_type for correct color
                rect = QRectF(zx, zy, zw, zh)
                zone_type = getattr(zone_def, 'zone_type', 'remove') if zone_def else 'remove'
                zone_item = ZoneItem(f"{zone_id}_{page_idx}", rect, zone_type=zone_type)
                zone_item.setPos(page_pos)
                zone_item.set_bounds(page_rect)

                zone_item.signals.zone_changed.connect(self._on_zone_changed)
                zone_item.signals.zone_selected.connect(self._on_zone_selected)
                zone_item.signals.zone_delete.connect(self._on_zone_delete)

                self.scene.addItem(zone_item)
                self._zones.append(zone_item)

    def _recreate_zone_overlays_single(self):
        """Tạo lại overlay zones cho trang hiện tại (single page mode)

        Display: Always show ALL zones in per_page_zones for current page (no filter)
        """
        # Remove existing zones
        for zone in self._zones:
            self.scene.removeItem(zone)
        self._zones.clear()

        if not self._pages or not self._page_items:
            return

        # Create zones for current page only
        page_item = self._page_items[0]  # Only one item in single mode
        page_rect = page_item.boundingRect()
        page_pos = page_item.pos()
        page_idx = self._current_page

        # Get zones for this page from per_page_zones
        page_zones = self._per_page_zones.get(page_idx, {})

        for zone_id, zone_coords in page_zones.items():
            # Find zone_def for this zone_id to get zone_type
            zone_def = None
            for zd in self._zone_definitions:
                if zd.id == zone_id:
                    zone_def = zd
                    break

            if zone_def and not zone_def.enabled:
                continue  # Skip disabled zones

            # Calculate pixel coordinates
            zx = zone_coords[0] * page_rect.width()
            zy = zone_coords[1] * page_rect.height()
            zw = zone_coords[2] * page_rect.width()
            zh = zone_coords[3] * page_rect.height()

            # Create zone item with zone_type for correct color
            rect = QRectF(zx, zy, zw, zh)
            zone_type = getattr(zone_def, 'zone_type', 'remove') if zone_def else 'remove'
            zone_item = ZoneItem(f"{zone_id}_{page_idx}", rect, zone_type=zone_type)
            zone_item.setPos(page_pos)
            zone_item.set_bounds(page_rect)

            zone_item.signals.zone_changed.connect(self._on_zone_changed)
            zone_item.signals.zone_selected.connect(self._on_zone_selected)
            zone_item.signals.zone_delete.connect(self._on_zone_delete)

            self.scene.addItem(zone_item)
            self._zones.append(zone_item)
    
    def update_page(self, page_idx: int, image: np.ndarray):
        """Cập nhật ảnh một trang"""
        if 0 <= page_idx < len(self._page_items):
            pixmap = self._numpy_to_pixmap(image)
            self._page_items[page_idx].setPixmap(pixmap)
            self._pages[page_idx] = image
    
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
        
        # Get the new rect as percentages
        page_rect = self._page_items[page_idx].boundingRect()
        new_rect = changed_zone.get_normalized_rect(
            int(page_rect.width()), 
            int(page_rect.height())
        )
        
        if self._page_filter != 'none':
            # Sync mode: update zone_definitions and sync to all pages
            for zdef in self._zone_definitions:
                if zdef.id == base_id:
                    zdef.x, zdef.y, zdef.width, zdef.height = new_rect
                    break
            
            # Sync to all other zone items with same base_id
            self._sync_zone_to_pages(base_id, new_rect)
        else:
            # Per-page mode: store independently
            if page_idx not in self._per_page_zones:
                self._per_page_zones[page_idx] = {}
            self._per_page_zones[page_idx][base_id] = new_rect
        
        self.zone_changed.emit(zone_id)
    
    def _sync_zone_to_pages(self, base_id: str, rect: tuple):
        """Sync zone rect to all pages with same zone"""
        x, y, w, h = rect
        
        for zone_item in self._zones:
            zone_base_id = zone_item.zone_id.rsplit('_', 1)[0]
            if zone_base_id == base_id:
                # Get page index for this zone
                page_idx = int(zone_item.zone_id.rsplit('_', 1)[1])
                if page_idx < len(self._page_items):
                    page_rect = self._page_items[page_idx].boundingRect()
                    # Convert percentages to pixels for this page
                    new_pixel_rect = QRectF(
                        x * page_rect.width(),
                        y * page_rect.height(),
                        w * page_rect.width(),
                        h * page_rect.height()
                    )
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
                self.scene.removeItem(item)
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
        """Clear all protected region overlays"""
        if hasattr(self, '_protected_region_items'):
            for page_idx, items in self._protected_region_items.items():
                for item in items:
                    self.scene.removeItem(item)
            self._protected_region_items.clear()

    def set_draw_mode(self, mode):
        """Enable/disable draw mode for drawing custom zones

        Args:
            mode: None (off), 'remove' (blue), or 'protect' (pink)
        """
        print(f"[DrawMode] set_draw_mode called: mode={mode}")

        # If turning off, always allow
        if mode is None:
            self.view.set_draw_mode(None, None, None)
            return

        # Need pages loaded to enable draw mode
        if not self._pages or not self._page_items:
            print(f"[DrawMode] No pages loaded: _pages={len(self._pages) if self._pages else 0}, _page_items={len(self._page_items) if self._page_items else 0}")
            return

        # Get all page bounds for accurate page detection
        all_page_bounds = []
        for page_item in self._page_items:
            page_rect = page_item.boundingRect()
            page_pos = page_item.pos()
            all_page_bounds.append((page_pos.x(), page_pos.y(), page_rect.width(), page_rect.height()))

        # Get current page bounds as fallback
        page_bounds = None
        print(f"[DrawMode] view_mode={self._view_mode}, current_page={self._current_page}, page_items={len(self._page_items)}")

        if self._view_mode == 'single' and self._page_items:
            page_bounds = all_page_bounds[0] if all_page_bounds else None
        elif self._view_mode == 'continuous' and self._current_page < len(all_page_bounds):
            page_bounds = all_page_bounds[self._current_page]

        print(f"[DrawMode] page_bounds={page_bounds}, all_page_bounds count={len(all_page_bounds)}")

        # Only enable if we have valid page bounds
        if page_bounds and page_bounds[2] > 0 and page_bounds[3] > 0:
            print(f"[DrawMode] Enabling draw mode on view")
            self.view.set_draw_mode(mode, page_bounds, all_page_bounds)
        else:
            print(f"[DrawMode] Invalid page_bounds, not enabling")

    def _on_rect_drawn(self, x: float, y: float, w: float, h: float, mode: str):
        """Forward rect_drawn signal - keep draw mode active for continuous drawing"""
        self.rect_drawn.emit(x, y, w, h, mode)


class ContinuousPreviewWidget(QWidget):
    """
    Widget preview side-by-side với continuous pages
    TRƯỚC (với overlay) | SAU (kết quả)
    """

    zone_changed = pyqtSignal(str, float, float, float, float)  # zone_id, x, y, w, h
    zone_selected = pyqtSignal(str)  # zone_id
    zone_delete = pyqtSignal(str)  # zone_id - request to delete custom zone
    open_file_requested = pyqtSignal()  # When placeholder "Mở file" is clicked
    open_folder_requested = pyqtSignal()  # When placeholder "Mở thư mục" is clicked
    file_dropped = pyqtSignal(str)  # When file is dropped (file_path)
    folder_dropped = pyqtSignal(str)  # When folder is dropped (folder_path)
    files_dropped = pyqtSignal(list)  # When multiple PDF files are dropped
    close_requested = pyqtSignal()  # When close button is clicked
    page_changed = pyqtSignal(int)  # Emitted when visible page changes (0-based index)
    # rect_drawn: x, y, w, h (as % of page), mode ('remove' or 'protect')
    rect_drawn = pyqtSignal(float, float, float, float, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._pages: List[np.ndarray] = []  # Original pages
        self._processed_pages: List[np.ndarray] = []  # Processed pages
        self._zones: List[Zone] = []
        self._processor = StapleRemover(protect_red=True)
        self._text_protection_enabled = False
        self._text_protection_margin = 10  # Default margin for protected regions overlay
        self._cached_regions: Dict[int, list] = {}  # Cache protected regions per page

        # Background detection using Python threading (not QThread to avoid crashes)
        self._detection_runner: Optional[DetectionRunner] = None
        self._detection_pending = False  # Track if detection is pending/running
        self._detection_results: Optional[dict] = None  # Store results from thread

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

        self._setup_ui()

    def closeEvent(self, event):
        """Cleanup khi widget bị đóng"""
        self._stop_detection()
        super().closeEvent(event)

    def __del__(self):
        """Destructor - đảm bảo cleanup"""
        self._stop_detection()
    
    def _setup_ui(self):
        self.setStyleSheet("background-color: #E5E7EB;")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Splitter with white handle
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("""
            QSplitter {
                background-color: #E5E7EB;
            }
            QSplitter::handle {
                background-color: white;
                width: 2px;
            }
        """)
        splitter.setHandleWidth(2)
        
        # Panel TRƯỚC (có overlay)
        self.before_panel = ContinuousPreviewPanel("Gốc:", show_overlay=True)
        self.before_panel.zone_changed.connect(self._on_zone_changed)
        self.before_panel.zone_selected.connect(self._on_zone_selected)
        self.before_panel.zone_delete.connect(self._on_zone_delete)
        self.before_panel.placeholder_clicked.connect(self._on_placeholder_clicked)
        self.before_panel.folder_placeholder_clicked.connect(self._on_folder_placeholder_clicked)
        self.before_panel.file_dropped.connect(self._on_file_dropped)
        self.before_panel.folder_dropped.connect(self._on_folder_dropped)
        self.before_panel.files_dropped.connect(self._on_files_dropped)
        self.before_panel.close_requested.connect(self._on_close_requested)
        self.before_panel.rect_drawn.connect(self._on_rect_drawn)
        splitter.addWidget(self.before_panel)
        
        # Panel SAU (chỉ kết quả)
        self.after_panel = ContinuousPreviewPanel("Đích:", show_overlay=False)
        self.after_panel.placeholder_clicked.connect(self._on_placeholder_clicked)
        self.after_panel.folder_placeholder_clicked.connect(self._on_folder_placeholder_clicked)
        self.after_panel.file_dropped.connect(self._on_file_dropped)
        self.after_panel.folder_dropped.connect(self._on_folder_dropped)
        self.after_panel.files_dropped.connect(self._on_files_dropped)
        splitter.addWidget(self.after_panel)
        
        # Sync zoom/scroll
        self.before_panel.view.zoom_changed.connect(self._sync_zoom)
        self.after_panel.view.zoom_changed.connect(self._sync_zoom)
        self.before_panel.view.scroll_changed.connect(self._sync_scroll_from_before)
        self.after_panel.view.scroll_changed.connect(self._sync_scroll_from_after)
        
        splitter.setSizes([1, 1])
        layout.addWidget(splitter)

        # Loading overlay (centered on widget)
        self._loading_overlay = LoadingOverlay(self)
        self._loading_overlay.hide()

    def resizeEvent(self, event):
        """Resize loading overlay to match widget size"""
        super().resizeEvent(event)
        self._loading_overlay.setGeometry(self.rect())

    def _show_loading(self):
        """Show loading overlay"""
        self._loading_overlay.setGeometry(self.rect())
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
    
    def set_pages(self, pages: List[np.ndarray]):
        """Set danh sách ảnh các trang"""
        # Stop any running detection first
        self._stop_detection()
        self._hide_loading()

        self._pages = [p.copy() for p in pages]
        self._processed_pages = [p.copy() for p in pages]

        # Clear cached regions khi load pages mới
        self._cached_regions.clear()

        self.before_panel.set_pages(pages)
        self.after_panel.set_pages(self._processed_pages)

        self._schedule_process()
    
    def set_view_mode(self, mode: str):
        """Set view mode: 'continuous' or 'single'"""
        self.before_panel.set_view_mode(mode)
        self.after_panel.set_view_mode(mode)
    
    def set_current_page(self, index: int):
        """Set current page index - scroll in continuous mode, rebuild in single mode"""
        self.before_panel.set_current_page(index)
        self.after_panel.set_current_page(index)
    
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
            base_id = zone_id.rsplit('_', 1)[0]
            
            page_filter = self.before_panel._page_filter
            
            if page_filter != 'none':
                # Sync mode: update internal zone and emit signal
                self.zone_changed.emit(base_id, x, y, w, h)
                
                # Update internal zone definitions
                for zone in self._zones:
                    if zone.id == base_id:
                        zone.x = x
                        zone.y = y
                        zone.width = w
                        zone.height = h
                        break
            # In 'none' mode, per-page zones are already stored in before_panel._per_page_zones
            
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
    
    def _schedule_process(self):
        """Schedule processing với debounce"""
        self._process_timer.start(300)
    
    def _do_process_all(self):
        """Xử lý tất cả các trang"""
        if not self._pages:
            return

        # Check if we need YOLO detection (when text protection enabled and pages not cached)
        pages_to_detect = []
        if self._text_protection_enabled:
            for i in range(len(self._pages)):
                if i not in self._cached_regions:
                    pages_to_detect.append(i)

        # If detection needed, run in background thread
        if pages_to_detect:
            self._start_background_detection(pages_to_detect)
            return  # Will continue processing after detection finishes

        # No detection needed, process directly
        self._process_pages_with_cached_regions()

    def _start_background_detection(self, pages_to_detect: List[int]):
        """Bắt đầu detection trong background thread (Python threading)"""
        # Stop any existing detection
        self._stop_detection()

        self._detection_pending = True
        self._detection_results = None
        self._show_loading()

        # Create a copy of pages for the thread to avoid thread safety issues
        pages_copy = [self._pages[i].copy() for i in pages_to_detect]

        # Create runner with callback
        self._detection_runner = DetectionRunner(
            self._processor,
            pages_copy,
            pages_to_detect,  # Original indices
            self._on_detection_complete  # Callback when done
        )

        # Start detection thread
        self._detection_runner.start()

        # Start timer to check for results
        self._result_check_timer.start()

    def _on_detection_complete(self, results: dict):
        """Callback from detection thread - store results for main thread to pick up"""
        self._detection_results = results

    def _check_detection_results(self):
        """Check if detection results are ready (called by timer in main thread)"""
        if self._detection_results is not None and self._detection_pending:
            # Stop the timer
            self._result_check_timer.stop()

            # Process results in main thread
            results = self._detection_results
            self._detection_results = None

            # Update cache
            for page_idx, regions in results.items():
                if page_idx < len(self._pages):
                    self._cached_regions[page_idx] = regions

            self._detection_pending = False
            self._detection_runner = None

            # Continue processing
            self._process_pages_with_cached_regions()

    def _stop_detection(self):
        """Stop any running detection"""
        self._detection_pending = False
        self._detection_results = None
        try:
            self._result_check_timer.stop()
        except RuntimeError:
            pass  # Timer already deleted during shutdown

        if self._detection_runner is not None:
            self._detection_runner.cancel()
            # Don't wait - let daemon thread die naturally
            self._detection_runner = None

    def _process_pages_with_cached_regions(self):
        """Xử lý tất cả trang với cached regions (không blocking)

        Each page is processed with its own zones from per_page_zones.
        Zones are added to pages based on filter when drawn (like layers).
        """
        if not self._pages:
            self._hide_loading()
            return

        # Clear protected regions display before processing
        self.before_panel.clear_protected_regions()

        for i, page in enumerate(self._pages):
            # Get zones for this specific page from per_page_zones
            page_zones = self._get_zones_for_page(i)

            # Always display protected regions overlay if text protection is enabled
            if self._text_protection_enabled:
                regions = self._cached_regions.get(i, [])
                self.before_panel.set_protected_regions(i, regions, margin=self._text_protection_margin)

            if page_zones:
                if self._text_protection_enabled:
                    regions = self._cached_regions.get(i, [])
                    processed = self._processor.process_image(page, page_zones, protected_regions=regions)
                    self._processed_pages[i] = processed
                else:
                    processed = self._processor.process_image(page, page_zones)
                    self._processed_pages[i] = processed
            else:
                # No zones for this page - keep original
                self._processed_pages[i] = page.copy()

        self.after_panel.set_pages(self._processed_pages)

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
            
    def _get_zones_for_page(self, page_idx: int) -> List[Zone]:
        """Get zones for a specific page from per_page_zones

        Returns only zones that exist in per_page_zones[page_idx].
        Each page has its own set of zones (like layers).
        """
        from core.processor import Zone

        page_zones = []
        per_page_zones = self.before_panel._per_page_zones

        if page_idx not in per_page_zones:
            return []

        for zone_id, zone_coords in per_page_zones[page_idx].items():
            # Find zone_def for this zone_id to get threshold and other properties
            zone_def = None
            for z in self._zones:
                if z.id == zone_id:
                    zone_def = z
                    break

            if zone_def and not zone_def.enabled:
                continue  # Skip disabled zones

            # Create zone with page-specific coordinates
            page_zone = Zone(
                id=zone_id,
                name=zone_def.name if zone_def else zone_id,
                x=zone_coords[0],
                y=zone_coords[1],
                width=zone_coords[2],
                height=zone_coords[3],
                threshold=zone_def.threshold if zone_def else 7,
                enabled=True,
                zone_type=getattr(zone_def, 'zone_type', 'remove') if zone_def else 'remove'
            )
            page_zones.append(page_zone)

        return page_zones
    
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

    def _detect_and_emit_page_change(self):
        """Detect current visible page from scroll position and emit page_changed if changed"""
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

        # Emit signal if page changed
        if current_page != self._last_emitted_page:
            self._last_emitted_page = current_page
            self.before_panel._current_page = current_page  # Update internal state
            self.after_panel._current_page = current_page
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
        if page_index >= len(self.before_panel._page_items):
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

        # Scroll đến trang hiện tại để giữ nó visible
        # scroll_to_page=True: scroll đến TOP của trang
        # scroll_to_page=False: scroll đến trang (giữ trang visible)
        self._scroll_to_page(page_index, align_top=scroll_to_page)

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
        if page_index >= len(self.before_panel._page_items):
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
    
    def get_processed_pages(self) -> List[np.ndarray]:
        """Lấy danh sách ảnh đã xử lý"""
        return self._processed_pages

    def set_text_protection(self, options):
        """Set text protection options"""
        from core.processor import TextProtectionOptions
        self._text_protection_enabled = options.enabled
        self._text_protection_margin = options.margin  # Store margin for overlay display

        # Clear cache khi settings thay đổi để detect lại với settings mới
        self._cached_regions.clear()

        # Loading overlay will be shown automatically in _start_background_detection
        self._processor.set_text_protection(options)
        self._schedule_process()

    def set_draw_mode(self, mode):
        """Enable/disable draw mode on before panel for drawing custom zones

        Args:
            mode: None (off), 'remove' (blue), or 'protect' (pink)
        """
        print(f"[DrawMode] ContinuousPreviewWidget.set_draw_mode: mode={mode}")
        self.before_panel.set_draw_mode(mode)

    def _on_rect_drawn(self, x: float, y: float, w: float, h: float, mode: str):
        """Forward rect_drawn signal from before_panel"""
        self.rect_drawn.emit(x, y, w, h, mode)
