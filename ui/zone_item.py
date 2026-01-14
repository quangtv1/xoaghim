"""
Zone Item - Vùng chọn có thể kéo thả trên preview
"""

from PyQt5.QtWidgets import QGraphicsRectItem, QGraphicsItem, QGraphicsEllipseItem, QMenu, QAction
from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal, QObject
from PyQt5.QtGui import QPen, QBrush, QColor, QCursor


class ZoneSignals(QObject):
    """Signals cho ZoneItem"""
    zone_changed = pyqtSignal(str)  # zone_id
    zone_selected = pyqtSignal(str)  # zone_id
    zone_delete = pyqtSignal(str)  # zone_id - request to delete zone


class HandleItem(QGraphicsEllipseItem):
    """Handle để resize zone"""
    
    def __init__(self, position: str, parent=None):
        super().__init__(-5, -5, 10, 10, parent)
        self.position = position  # 'tl', 'tr', 'bl', 'br', 't', 'b', 'l', 'r'
        
        self.setBrush(QBrush(QColor(255, 255, 255)))
        self.setPen(QPen(QColor(0, 0, 0), 1))
        self.setZValue(100)
        self.setVisible(False)
        
        # Set cursor based on position
        cursors = {
            'tl': Qt.SizeFDiagCursor,
            'br': Qt.SizeFDiagCursor,
            'tr': Qt.SizeBDiagCursor,
            'bl': Qt.SizeBDiagCursor,
            't': Qt.SizeVerCursor,
            'b': Qt.SizeVerCursor,
            'l': Qt.SizeHorCursor,
            'r': Qt.SizeHorCursor,
        }
        self.setCursor(cursors.get(position, Qt.ArrowCursor))


class ZoneItem(QGraphicsRectItem):
    """
    Vùng chọn có thể kéo thả
    """

    def __init__(self, zone_id: str, rect: QRectF, zone_type: str = 'remove', parent=None):
        super().__init__(rect, parent)

        self.zone_id = zone_id
        self.zone_type = zone_type  # 'remove' (blue) or 'protect' (pink)
        self.signals = ZoneSignals()

        # Appearance
        self._selected = False

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        self.setCursor(Qt.SizeAllCursor)

        # Create handles
        self.handles = {}
        for pos in ['tl', 'tr', 'bl', 'br', 't', 'b', 'l', 'r']:
            handle = HandleItem(pos, self)
            self.handles[pos] = handle

        # Dragging state
        self._drag_handle = None
        self._drag_start_rect = None
        self._drag_start_pos = None

        # Bounds (image size)
        self._bounds = None

        # Z-value for layering (base value, increased when selected)
        self._base_z_value = 10
        self.setZValue(self._base_z_value)

        self._update_appearance()
        self._update_handles()
    
    def set_bounds(self, bounds: QRectF):
        """Set giới hạn di chuyển (kích thước ảnh)"""
        self._bounds = bounds
    
    def set_selected(self, selected: bool):
        """Set trạng thái chọn"""
        self._selected = selected
        # Manage z-order: selected zone goes to front
        if selected:
            self.setZValue(50)
        else:
            self.setZValue(self._base_z_value)
        self._update_appearance()
        self._update_handles()
    
    def _update_appearance(self):
        """Cập nhật màu sắc dựa trên zone_type"""
        # Colors based on zone_type
        if self.zone_type == 'protect':
            # Pink for protection zones
            color_normal = QColor(244, 114, 182)      # #F472B6
            color_selected = QColor(219, 39, 119)     # #DB2777 (darker pink)
        else:
            # Blue for removal zones (default)
            color_normal = QColor(59, 130, 246)       # #3B82F6
            color_selected = QColor(29, 78, 216)      # #1D4ED8 (darker blue)

        if self._selected:
            self.setPen(QPen(color_selected, 3))
            self.setBrush(QBrush(QColor(color_normal.red(), color_normal.green(), color_normal.blue(), 100)))
        else:
            self.setPen(QPen(color_normal, 2))
            self.setBrush(QBrush(QColor(color_normal.red(), color_normal.green(), color_normal.blue(), 40)))
    
    def _update_handles(self):
        """Cập nhật vị trí handles"""
        rect = self.rect()
        
        positions = {
            'tl': rect.topLeft(),
            'tr': rect.topRight(),
            'bl': rect.bottomLeft(),
            'br': rect.bottomRight(),
            't': QPointF(rect.center().x(), rect.top()),
            'b': QPointF(rect.center().x(), rect.bottom()),
            'l': QPointF(rect.left(), rect.center().y()),
            'r': QPointF(rect.right(), rect.center().y()),
        }
        
        for pos, point in positions.items():
            self.handles[pos].setPos(point)
            self.handles[pos].setVisible(self._selected)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Emit zone_selected signal first - this triggers set_selected() which handles z-order
            self.signals.zone_selected.emit(self.zone_id)

            # Check if clicking on a handle
            pos = event.pos()
            for handle_pos, handle in self.handles.items():
                if handle.contains(pos - handle.pos()):
                    self._drag_handle = handle_pos
                    self._drag_start_rect = self.rect()
                    self._drag_start_pos = event.scenePos()
                    event.accept()
                    return

            # Otherwise, start moving
            self._drag_handle = None
            self._drag_start_rect = self.rect()
            self._drag_start_pos = event.scenePos()

        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self._drag_start_pos is None:
            super().mouseMoveEvent(event)
            return
        
        delta = event.scenePos() - self._drag_start_pos
        rect = QRectF(self._drag_start_rect)
        
        if self._drag_handle:
            # Resize
            if 'l' in self._drag_handle:
                rect.setLeft(rect.left() + delta.x())
            if 'r' in self._drag_handle:
                rect.setRight(rect.right() + delta.x())
            if 't' in self._drag_handle:
                rect.setTop(rect.top() + delta.y())
            if 'b' in self._drag_handle:
                rect.setBottom(rect.bottom() + delta.y())
            
            # Ensure minimum size
            if rect.width() < 20:
                if 'l' in self._drag_handle:
                    rect.setLeft(rect.right() - 20)
                else:
                    rect.setRight(rect.left() + 20)
            if rect.height() < 20:
                if 't' in self._drag_handle:
                    rect.setTop(rect.bottom() - 20)
                else:
                    rect.setBottom(rect.top() + 20)
            
            self.setRect(rect)
        else:
            # Move
            new_rect = rect.translated(delta)
            
            # Constrain to bounds
            if self._bounds:
                if new_rect.left() < self._bounds.left():
                    new_rect.moveLeft(self._bounds.left())
                if new_rect.right() > self._bounds.right():
                    new_rect.moveRight(self._bounds.right())
                if new_rect.top() < self._bounds.top():
                    new_rect.moveTop(self._bounds.top())
                if new_rect.bottom() > self._bounds.bottom():
                    new_rect.moveBottom(self._bounds.bottom())
            
            self.setRect(new_rect)
        
        self._update_handles()
        self.signals.zone_changed.emit(self.zone_id)
    
    def mouseReleaseEvent(self, event):
        self._drag_handle = None
        self._drag_start_rect = None
        self._drag_start_pos = None
        # Don't restore z-value here - let set_selected handle it
        self.signals.zone_changed.emit(self.zone_id)
        super().mouseReleaseEvent(event)
    
    def contextMenuEvent(self, event):
        """Right-click context menu - show delete option for all zones"""
        menu = QMenu()
        
        # Determine zone type for menu text
        base_id = self.zone_id.rsplit('_', 1)[0]  # e.g., "custom_1", "corner_tl", "margin_top"
        
        # Get display name for zone type
        zone_names = {
            'corner_tl': 'góc trên trái',
            'corner_tr': 'góc trên phải', 
            'corner_bl': 'góc dưới trái',
            'corner_br': 'góc dưới phải',
            'margin_top': 'cạnh trên',
            'margin_bottom': 'cạnh dưới',
            'margin_left': 'cạnh trái',
            'margin_right': 'cạnh phải',
        }
        
        if base_id.startswith('protect'):
            delete_text = "Xóa vùng bảo vệ"
        elif base_id.startswith('custom'):
            delete_text = "Xóa vùng tùy biến"
        elif base_id in zone_names:
            delete_text = f"Xóa vùng {zone_names[base_id]}"
        else:
            delete_text = "Xóa vùng này"
        
        delete_action = QAction(delete_text, menu)
        
        # Capture zone_id in closure
        zone_id_to_delete = self.zone_id
        
        # Get scene and view to find parent panel
        scene = self.scene()
        
        def do_delete():
            """Request deletion through scene views"""
            if scene:
                for view in scene.views():
                    parent = view.parent()
                    # Walk up to find ContinuousPreviewPanel
                    while parent:
                        if hasattr(parent, 'request_zone_delete'):
                            parent.request_zone_delete(zone_id_to_delete)
                            return
                        parent = parent.parent() if hasattr(parent, 'parent') else None
        
        delete_action.triggered.connect(do_delete)
        menu.addAction(delete_action)
        
        # Show menu at cursor position
        # screenPos() returns QPointF on some platforms, QPoint on others
        screen_pos = event.screenPos()
        if hasattr(screen_pos, 'toPoint'):
            screen_pos = screen_pos.toPoint()
        menu.exec_(screen_pos)
        event.accept()
    
    def mouseDoubleClickEvent(self, event):
        """Double click để mở dialog chỉnh sửa (implement later)"""
        super().mouseDoubleClickEvent(event)
    
    def get_normalized_rect(self, image_width: int, image_height: int) -> tuple:
        """Lấy rect dưới dạng % (x, y, w, h)"""
        rect = self.rect()
        return (
            rect.x() / image_width,
            rect.y() / image_height,
            rect.width() / image_width,
            rect.height() / image_height
        )
