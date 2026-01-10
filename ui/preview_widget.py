"""
Preview Widget - Hiển thị preview side-by-side TRƯỚC | SAU
"""

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, 
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QFrame, QSplitter, QScrollBar
)
from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QTimer
from PyQt5.QtGui import QPixmap, QImage, QPainter, QWheelEvent, QColor, QBrush

import numpy as np
import cv2
from typing import List, Optional

from ui.zone_item import ZoneItem
from core.processor import Zone, StapleRemover


class SyncGraphicsView(QGraphicsView):
    """GraphicsView với synchronized zoom/pan"""
    
    zoom_changed = pyqtSignal(float)
    scroll_changed = pyqtSignal(int, int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Nền xám
        self.setBackgroundBrush(QBrush(QColor(229, 231, 235)))
        
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self._zoom = 1.0
        self._syncing = False
    
    def wheelEvent(self, event: QWheelEvent):
        """Zoom với scroll wheel"""
        if event.modifiers() == Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1/1.15
            self._zoom *= factor
            self._zoom = max(0.1, min(10.0, self._zoom))
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


class PreviewPanel(QFrame):
    """Panel preview với title"""
    
    zone_changed = pyqtSignal(str)  # zone_id
    zone_selected = pyqtSignal(str)  # zone_id
    
    def __init__(self, title: str, show_overlay: bool = False, parent=None):
        super().__init__(parent)
        
        self.show_overlay = show_overlay
        self._image = None
        self._zones: List[ZoneItem] = []
        self._image_width = 0
        self._image_height = 0
        
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("QFrame { border-radius: 0; }")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Title - gray bg like preview area, darker bottom line
        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("""
            QLabel {
                font-weight: 600;
                font-size: 12px;
                padding: 8px;
                background-color: #E5E7EB;
                color: #0047AB;
                border: none;
                border-bottom: 1px solid #9CA3AF;
            }
        """)
        layout.addWidget(self.title_label)
        
        # Graphics view
        self.scene = QGraphicsScene()
        self.view = SyncGraphicsView()
        self.view.setScene(self.scene)
        layout.addWidget(self.view)
        
        # Image item
        self.image_item = QGraphicsPixmapItem()
        self.scene.addItem(self.image_item)
    
    def set_image(self, image: np.ndarray):
        """Set ảnh hiển thị (numpy BGR)"""
        if image is None:
            return
        
        self._image = image
        self._image_height, self._image_width = image.shape[:2]
        
        # Convert to QPixmap
        if len(image.shape) == 3:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        else:
            h, w = image.shape
            qimg = QImage(image.data, w, h, w, QImage.Format_Grayscale8)
        
        pixmap = QPixmap.fromImage(qimg)
        self.image_item.setPixmap(pixmap)
        
        # Update scene rect
        self.scene.setSceneRect(0, 0, w, h)
        
        # Update zone bounds
        for zone in self._zones:
            zone.set_bounds(QRectF(0, 0, w, h))
    
    def add_zone(self, zone_id: str, x: float, y: float, w: float, h: float):
        """Thêm vùng chọn (tọa độ %)"""
        if not self.show_overlay:
            return
        
        # Convert % to pixels
        px = x * self._image_width
        py = y * self._image_height
        pw = w * self._image_width
        ph = h * self._image_height
        
        rect = QRectF(px, py, pw, ph)
        zone_item = ZoneItem(zone_id, rect)
        zone_item.set_bounds(QRectF(0, 0, self._image_width, self._image_height))
        
        zone_item.signals.zone_changed.connect(self._on_zone_changed)
        zone_item.signals.zone_selected.connect(self._on_zone_selected)
        
        self.scene.addItem(zone_item)
        self._zones.append(zone_item)
    
    def clear_zones(self):
        """Xóa tất cả zones"""
        for zone in self._zones:
            self.scene.removeItem(zone)
        self._zones.clear()
    
    def update_zone(self, zone_id: str, x: float, y: float, w: float, h: float):
        """Cập nhật vùng chọn"""
        for zone in self._zones:
            if zone.zone_id == zone_id:
                px = x * self._image_width
                py = y * self._image_height
                pw = w * self._image_width
                ph = h * self._image_height
                zone.setRect(QRectF(px, py, pw, ph))
                break
    
    def select_zone(self, zone_id: str):
        """Chọn zone"""
        for zone in self._zones:
            zone.set_selected(zone.zone_id == zone_id)
    
    def get_zone_rect(self, zone_id: str) -> Optional[tuple]:
        """Lấy rect của zone (%)"""
        for zone in self._zones:
            if zone.zone_id == zone_id:
                return zone.get_normalized_rect(self._image_width, self._image_height)
        return None
    
    def _on_zone_changed(self, zone_id: str):
        self.zone_changed.emit(zone_id)
    
    def _on_zone_selected(self, zone_id: str):
        self.select_zone(zone_id)
        self.zone_selected.emit(zone_id)


class PreviewWidget(QWidget):
    """
    Widget preview side-by-side: TRƯỚC | SAU
    """
    
    zone_changed = pyqtSignal(str, float, float, float, float)  # zone_id, x, y, w, h
    zone_selected = pyqtSignal(str)  # zone_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._original_image = None
        self._processed_image = None
        self._zones: List[Zone] = []
        self._processor = StapleRemover(protect_red=True)
        
        # Debounce timer for processing
        self._process_timer = QTimer()
        self._process_timer.setSingleShot(True)
        self._process_timer.timeout.connect(self._do_process)
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Splitter để resize 2 panel
        splitter = QSplitter(Qt.Horizontal)
        
        # Panel TRƯỚC (có overlay)
        self.before_panel = PreviewPanel("TRƯỚC (Gốc)", show_overlay=True)
        self.before_panel.zone_changed.connect(self._on_zone_changed)
        self.before_panel.zone_selected.connect(self._on_zone_selected)
        splitter.addWidget(self.before_panel)
        
        # Panel SAU (chỉ kết quả)
        self.after_panel = PreviewPanel("SAU (Kết quả)", show_overlay=False)
        splitter.addWidget(self.after_panel)
        
        # Sync zoom/scroll
        self.before_panel.view.zoom_changed.connect(self._sync_zoom)
        self.after_panel.view.zoom_changed.connect(self._sync_zoom)
        self.before_panel.view.scroll_changed.connect(self._sync_scroll_from_before)
        self.after_panel.view.scroll_changed.connect(self._sync_scroll_from_after)
        
        # Equal sizes
        splitter.setSizes([1, 1])
        
        layout.addWidget(splitter)
    
    def set_image(self, image: np.ndarray):
        """Set ảnh gốc"""
        self._original_image = image.copy()
        self.before_panel.set_image(image)
        
        # Process and show result
        self._schedule_process()
    
    def set_zones(self, zones: List[Zone]):
        """Set danh sách zones"""
        self._zones = zones
        
        # Clear and recreate zone overlays
        self.before_panel.clear_zones()
        
        for zone in zones:
            if zone.enabled:
                self.before_panel.add_zone(
                    zone.id,
                    zone.x, zone.y,
                    zone.width, zone.height
                )
        
        self._schedule_process()
    
    def update_zone(self, zone: Zone):
        """Cập nhật một zone"""
        # Update in list
        for i, z in enumerate(self._zones):
            if z.id == zone.id:
                self._zones[i] = zone
                break
        
        # Update overlay
        if zone.enabled:
            self.before_panel.update_zone(
                zone.id,
                zone.x, zone.y,
                zone.width, zone.height
            )
        
        self._schedule_process()
    
    def select_zone(self, zone_id: str):
        """Chọn zone"""
        self.before_panel.select_zone(zone_id)
    
    def _on_zone_changed(self, zone_id: str):
        """Khi zone bị thay đổi (kéo/resize)"""
        rect = self.before_panel.get_zone_rect(zone_id)
        if rect:
            x, y, w, h = rect
            self.zone_changed.emit(zone_id, x, y, w, h)
            
            # Update internal zone
            for zone in self._zones:
                if zone.id == zone_id:
                    zone.x = x
                    zone.y = y
                    zone.width = w
                    zone.height = h
                    break
            
            self._schedule_process()
    
    def _on_zone_selected(self, zone_id: str):
        """Khi zone được chọn"""
        self.zone_selected.emit(zone_id)
    
    def _schedule_process(self):
        """Schedule processing với debounce"""
        self._process_timer.start(200)  # 200ms debounce
    
    def _do_process(self):
        """Thực hiện xử lý ảnh"""
        if self._original_image is None:
            return
        
        # Process
        self._processed_image = self._processor.process_image(
            self._original_image, self._zones
        )
        
        # Show result
        self.after_panel.set_image(self._processed_image)
    
    def _sync_zoom(self, zoom: float):
        """Sync zoom giữa 2 panel"""
        self.before_panel.view.set_zoom(zoom)
        self.after_panel.view.set_zoom(zoom)
    
    def _sync_scroll_from_before(self, h: int, v: int):
        self.after_panel.view.sync_scroll(h, v)
    
    def _sync_scroll_from_after(self, h: int, v: int):
        self.before_panel.view.sync_scroll(h, v)
    
    def zoom_in(self):
        """Zoom in"""
        zoom = self.before_panel.view._zoom * 1.2
        self._sync_zoom(zoom)
    
    def zoom_out(self):
        """Zoom out"""
        zoom = self.before_panel.view._zoom / 1.2
        self._sync_zoom(zoom)
    
    def zoom_fit(self):
        """Fit to view"""
        self.before_panel.view.fitInView(
            self.before_panel.scene.sceneRect(),
            Qt.KeepAspectRatio
        )
        self.after_panel.view.fitInView(
            self.after_panel.scene.sceneRect(),
            Qt.KeepAspectRatio
        )
    
    def get_processed_image(self) -> Optional[np.ndarray]:
        """Lấy ảnh đã xử lý"""
        return self._processed_image
