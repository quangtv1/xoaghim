"""
Continuous Preview - Preview liên tục nhiều trang với nền đen
"""

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsRectItem, QFrame, QSplitter, QScrollArea, QPushButton
)
from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QTimer, QPointF
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QBrush, QPen, QCursor, QPainterPath

import numpy as np
import cv2
from typing import List, Optional, Dict, TYPE_CHECKING

from ui.zone_item import ZoneItem
from core.processor import Zone, StapleRemover


class ContinuousGraphicsView(QGraphicsView):
    """GraphicsView với nền xám và synchronized scroll"""
    
    zoom_changed = pyqtSignal(float)
    scroll_changed = pyqtSignal(int, int)
    
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
        
        self._zoom = 1.0
        self._syncing = False
    
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
    close_requested = pyqtSignal()  # When close button is clicked
    
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
        title_bar.setStyleSheet("background-color: #D1D5DB;")
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
                    background-color: #C9CDD4;
                    border: none;
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: bold;
                    color: #4B5563;
                    padding: 0;
                    margin: 0;
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
        """Set current page index for single page mode"""
        if 0 <= index < len(self._pages):
            self._current_page = index
            if self._view_mode == 'single':
                self._rebuild_scene()
    
    def get_current_page(self) -> int:
        """Get current page index"""
        return self._current_page
    
    def set_page_filter(self, filter_mode: str):
        """Set page filter: 'all', 'odd', 'even', 'none'"""
        if filter_mode not in ('all', 'odd', 'even', 'none'):
            return
        if self._page_filter != filter_mode:
            old_filter = self._page_filter
            self._page_filter = filter_mode
            
            # When switching from 'none' to sync mode, reset per-page zones
            if old_filter == 'none' and filter_mode != 'none':
                self._per_page_zones.clear()
            
            # When switching to 'none', initialize per-page zones from current definitions
            if filter_mode == 'none' and old_filter != 'none':
                self._init_per_page_zones()
            
            # Recreate zone overlays with new filter
            if self.show_overlay:
                if self._view_mode == 'single':
                    self._recreate_zone_overlays_single()
                else:
                    self._recreate_zone_overlays()
    
    def _init_per_page_zones(self):
        """Initialize per-page zones from zone definitions"""
        self._per_page_zones.clear()
        for page_idx in range(len(self._pages)):
            self._per_page_zones[page_idx] = {}
            for zdef in self._zone_definitions:
                self._per_page_zones[page_idx][zdef.id] = (zdef.x, zdef.y, zdef.width, zdef.height)
    
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
        
        # Hover background for "Mở file" - add first so it's behind icon
        file_hover_rect = QRectF(
            file_icon_x - 15, icon_y - 8,
            icon_width + 30, icon_height + 35
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
        
        # Store click area for "Mở file"
        self._placeholder_file_rect = QRectF(
            file_icon_x - 20, icon_y - 10,
            icon_width + 40, icon_height + file_hint_rect.height() + 30
        )
        
        # === RIGHT ICON: Folder (Mở thư mục) - rounded corners, thin line ===
        folder_icon_x = placeholder_width / 2 + icon_spacing - 12
        folder_width = 28
        folder_height = 20
        folder_y = icon_y + 5
        tab_width = 10
        tab_height = 5
        corner_r = 2  # Small corner radius
        
        # Hover background for "Mở thư mục" - add first so it's behind icon
        folder_hover_rect = QRectF(
            folder_icon_x - 10, icon_y - 8,
            folder_width + 20, icon_height + 35
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
        
        # Store click area for "Mở thư mục"
        self._placeholder_folder_rect = QRectF(
            folder_icon_x - 20, icon_y - 10,
            folder_width + 40, icon_height + folder_hint_rect.height() + 30
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
            QGraphicsView.mouseMoveEvent(self.view, event)
    
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
            # Call parent implementation
            QGraphicsView.mousePressEvent(self.view, event)
    
    def dragEnterEvent(self, event):
        """Handle drag enter for file drop"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                if url.toLocalFile().lower().endswith('.pdf'):
                    event.acceptProposedAction()
                    return
        event.ignore()
    
    def dragOverEvent(self, event):
        """Handle drag over"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        """Handle file drop"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                file_path = url.toLocalFile()
                if file_path.lower().endswith('.pdf'):
                    self.file_dropped.emit(file_path)
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
        """Set zone definitions (áp dụng cho tất cả trang)"""
        self._zone_definitions = zones
        if self.show_overlay:
            if self._view_mode == 'single':
                self._recreate_zone_overlays_single()
            else:
                self._recreate_zone_overlays()
    
    def _recreate_zone_overlays(self):
        """Tạo lại overlay zones cho tất cả trang"""
        # Remove existing zones
        for zone in self._zones:
            self.scene.removeItem(zone)
        self._zones.clear()
        
        if not self._pages or not self._zone_definitions:
            return
        
        # Create zones for each page (respecting page filter)
        for page_idx, page_item in enumerate(self._page_items):
            # In 'none' mode, all pages get zones (but independent)
            # In other modes, check filter
            if self._page_filter != 'none' and not self._should_apply_to_page(page_idx):
                continue
                
            page_rect = page_item.boundingRect()
            page_pos = page_item.pos()
            
            for zone_def in self._zone_definitions:
                if not zone_def.enabled:
                    continue
                
                # Get zone coordinates - from per-page storage or shared definition
                if self._page_filter == 'none' and page_idx in self._per_page_zones:
                    zone_coords = self._per_page_zones[page_idx].get(zone_def.id)
                    if zone_coords:
                        zx = zone_coords[0] * page_rect.width()
                        zy = zone_coords[1] * page_rect.height()
                        zw = zone_coords[2] * page_rect.width()
                        zh = zone_coords[3] * page_rect.height()
                    else:
                        # Fallback to zone_def
                        zx = zone_def.x * page_rect.width()
                        zy = zone_def.y * page_rect.height()
                        zw = zone_def.width * page_rect.width()
                        zh = zone_def.height * page_rect.height()
                else:
                    # Sync mode - use shared definition
                    zx = zone_def.x * page_rect.width()
                    zy = zone_def.y * page_rect.height()
                    zw = zone_def.width * page_rect.width()
                    zh = zone_def.height * page_rect.height()
                
                # Create zone item
                rect = QRectF(zx, zy, zw, zh)
                zone_item = ZoneItem(f"{zone_def.id}_{page_idx}", rect)
                zone_item.setPos(page_pos)
                zone_item.set_bounds(page_rect)
                
                zone_item.signals.zone_changed.connect(self._on_zone_changed)
                zone_item.signals.zone_selected.connect(self._on_zone_selected)
                zone_item.signals.zone_delete.connect(self._on_zone_delete)
                
                self.scene.addItem(zone_item)
                self._zones.append(zone_item)
    
    def _recreate_zone_overlays_single(self):
        """Tạo lại overlay zones cho trang hiện tại (single page mode)"""
        # Remove existing zones
        for zone in self._zones:
            self.scene.removeItem(zone)
        self._zones.clear()
        
        if not self._pages or not self._zone_definitions or not self._page_items:
            return
        
        # In 'none' mode, all pages have zones; otherwise check filter
        if self._page_filter != 'none' and not self._should_apply_to_page(self._current_page):
            return
        
        # Create zones for current page only
        page_item = self._page_items[0]  # Only one item in single mode
        page_rect = page_item.boundingRect()
        page_pos = page_item.pos()
        page_idx = self._current_page
        
        for zone_def in self._zone_definitions:
            if not zone_def.enabled:
                continue
            
            # Get zone coordinates - from per-page storage or shared definition
            if self._page_filter == 'none' and page_idx in self._per_page_zones:
                zone_coords = self._per_page_zones[page_idx].get(zone_def.id)
                if zone_coords:
                    zx = zone_coords[0] * page_rect.width()
                    zy = zone_coords[1] * page_rect.height()
                    zw = zone_coords[2] * page_rect.width()
                    zh = zone_coords[3] * page_rect.height()
                else:
                    zx = zone_def.x * page_rect.width()
                    zy = zone_def.y * page_rect.height()
                    zw = zone_def.width * page_rect.width()
                    zh = zone_def.height * page_rect.height()
            else:
                zx = zone_def.x * page_rect.width()
                zy = zone_def.y * page_rect.height()
                zw = zone_def.width * page_rect.width()
                zh = zone_def.height * page_rect.height()
            
            # Create zone item (use current page index)
            rect = QRectF(zx, zy, zw, zh)
            zone_item = ZoneItem(f"{zone_def.id}_{page_idx}", rect)
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
        # Highlight zone
        for zone in self._zones:
            zone.set_selected(zone.zone_id == zone_id)
        self.zone_selected.emit(zone_id)
    
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
        pen.setWidth(2)
        pen.setCosmetic(True)  # Pen width is in screen pixels
        brush = QBrush(QColor(220, 38, 38, 60))  # ~24% opacity

        page_item = self._page_items[page_idx]
        page_pos = page_item.pos()
        page_rect = page_item.boundingRect()

        print(f"[DEBUG ContinuousPanel] Drawing {len(regions)} protected regions for page {page_idx} (margin={margin})")

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
            print(f"[DEBUG ContinuousPanel] Region bbox=({x1}, {y1}, {x2}, {y2}) + margin={margin} -> ({x1_expanded}, {y1_expanded}, {x2_expanded}, {y2_expanded})")

            rect_item = QGraphicsRectItem(rect)
            rect_item.setPen(pen)
            rect_item.setBrush(brush)
            rect_item.setZValue(100)  # High z-value to be on top
            self.scene.addItem(rect_item)
            self._protected_region_items[page_idx].append(rect_item)
            print(f"[DEBUG ContinuousPanel] Added rect_item, scene now has {len(self.scene.items())} items")

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
    close_requested = pyqtSignal()  # When close button is clicked
    
    def __init__(self, parent=None):
        super().__init__(parent)

        self._pages: List[np.ndarray] = []  # Original pages
        self._processed_pages: List[np.ndarray] = []  # Processed pages
        self._zones: List[Zone] = []
        self._processor = StapleRemover(protect_red=True)
        self._text_protection_enabled = False
        self._text_protection_margin = 10  # Default margin for protected regions overlay
        self._cached_regions: Dict[int, list] = {}  # Cache protected regions per page

        # Debounce timer
        self._process_timer = QTimer()
        self._process_timer.setSingleShot(True)
        self._process_timer.timeout.connect(self._do_process_all)

        self._setup_ui()
    
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
        self.before_panel.close_requested.connect(self._on_close_requested)
        splitter.addWidget(self.before_panel)
        
        # Panel SAU (chỉ kết quả)
        self.after_panel = ContinuousPreviewPanel("Đích:", show_overlay=False)
        self.after_panel.placeholder_clicked.connect(self._on_placeholder_clicked)
        self.after_panel.folder_placeholder_clicked.connect(self._on_folder_placeholder_clicked)
        self.after_panel.file_dropped.connect(self._on_file_dropped)
        splitter.addWidget(self.after_panel)
        
        # Sync zoom/scroll
        self.before_panel.view.zoom_changed.connect(self._sync_zoom)
        self.after_panel.view.zoom_changed.connect(self._sync_zoom)
        self.before_panel.view.scroll_changed.connect(self._sync_scroll_from_before)
        self.after_panel.view.scroll_changed.connect(self._sync_scroll_from_after)
        
        splitter.setSizes([1, 1])
        layout.addWidget(splitter)
    
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
        """Set current page index for single page mode"""
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

        print(f"[DEBUG ContinuousPreview] _do_process_all: text_protection_enabled={self._text_protection_enabled}")

        # Clear protected regions display before processing
        self.before_panel.clear_protected_regions()

        # Get page filter from before_panel
        page_filter = self.before_panel._page_filter

        for i, page in enumerate(self._pages):
            # Check if this page should be processed based on filter
            page_num = i + 1  # 1-based page number

            if page_filter == 'none':
                # Per-page mode: use page-specific zones
                page_zones = self._get_zones_for_page(i)
                if page_zones:
                    if self._text_protection_enabled:
                        # Sử dụng cached regions hoặc detect mới
                        regions = self._get_cached_regions(i, page)
                        # Process với regions đã cache
                        processed = self._processor.process_image(page, page_zones, protected_regions=regions)
                        self._processed_pages[i] = processed
                        # Draw protected regions on before panel
                        self.before_panel.set_protected_regions(i, regions, margin=self._text_protection_margin)
                        print(f"[DEBUG ContinuousPreview] Page {i}: using {len(regions)} cached regions")
                    else:
                        processed = self._processor.process_image(page, page_zones)
                        self._processed_pages[i] = processed
                else:
                    self._processed_pages[i] = page.copy()
            else:
                # Sync mode: check filter and use shared zones
                should_process = (
                    page_filter == 'all' or
                    (page_filter == 'odd' and page_num % 2 == 1) or
                    (page_filter == 'even' and page_num % 2 == 0)
                )

                if should_process:
                    if self._text_protection_enabled:
                        # Sử dụng cached regions hoặc detect mới
                        regions = self._get_cached_regions(i, page)
                        # Process với regions đã cache
                        processed = self._processor.process_image(page, self._zones, protected_regions=regions)
                        self._processed_pages[i] = processed
                        # Draw protected regions on before panel
                        self.before_panel.set_protected_regions(i, regions, margin=self._text_protection_margin)
                        print(f"[DEBUG ContinuousPreview] Page {i}: using {len(regions)} cached regions")
                    else:
                        processed = self._processor.process_image(page, self._zones)
                        self._processed_pages[i] = processed
                else:
                    # Keep original page if not processed
                    self._processed_pages[i] = page.copy()

        self.after_panel.set_pages(self._processed_pages)

    def _get_cached_regions(self, page_idx: int, page: 'np.ndarray') -> list:
        """Lấy cached regions hoặc detect mới nếu chưa có"""
        if page_idx not in self._cached_regions:
            regions = self._processor.detect_protected_regions(page)
            self._cached_regions[page_idx] = regions
            print(f"[DEBUG ContinuousPreview] Page {page_idx}: detected and cached {len(regions)} regions")
        return self._cached_regions[page_idx]

    def clear_cached_regions(self):
        """Xóa cache khi cần detect lại (thay đổi settings, load PDF mới)"""
        self._cached_regions.clear()
        print("[DEBUG ContinuousPreview] Cleared cached regions")
    
    def _get_zones_for_page(self, page_idx: int) -> List[Zone]:
        """Get zones with page-specific coordinates for 'none' mode"""
        from core.processor import Zone
        
        page_zones = []
        per_page_zones = self.before_panel._per_page_zones
        
        if page_idx in per_page_zones:
            for zone in self._zones:
                zone_coords = per_page_zones[page_idx].get(zone.id)
                if zone_coords:
                    # Create zone with page-specific coordinates
                    page_zone = Zone(
                        id=zone.id,
                        name=zone.name,
                        x=zone_coords[0],
                        y=zone_coords[1],
                        width=zone_coords[2],
                        height=zone_coords[3],
                        threshold=zone.threshold,
                        enabled=zone.enabled
                    )
                    page_zones.append(page_zone)
                else:
                    page_zones.append(zone)
        else:
            # Fallback to shared zones
            page_zones = self._zones
        
        return page_zones
    
    def _sync_zoom(self, zoom: float):
        """Sync zoom"""
        self.before_panel.view.set_zoom(zoom)
        self.after_panel.view.set_zoom(zoom)
    
    def _sync_scroll_from_before(self, h: int, v: int):
        self.after_panel.view.sync_scroll(h, v)
    
    def _sync_scroll_from_after(self, h: int, v: int):
        self.before_panel.view.sync_scroll(h, v)
    
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
    
    def zoom_fit_width(self):
        """Fit vừa chiều rộng trang (từng trang)"""
        if not self._pages:
            return
        
        # Lấy chiều rộng trang đầu tiên
        first_page = self._pages[0]
        page_width = first_page.shape[1]  # width
        
        # Tính zoom để fit vừa chiều rộng view
        view_width = self.before_panel.view.viewport().width() - 40  # padding
        
        if page_width > 0 and view_width > 0:
            zoom = view_width / page_width
            
            # Reset transform và set zoom mới
            self.before_panel.view.resetTransform()
            self.before_panel.view.scale(zoom, zoom)
            self.before_panel.view._zoom = zoom
            
            self.after_panel.view.resetTransform()
            self.after_panel.view.scale(zoom, zoom)
            self.after_panel.view._zoom = zoom
    
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

        self._processor.set_text_protection(options)
        self._schedule_process()
