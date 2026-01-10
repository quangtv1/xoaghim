"""
Zone Selector - Widget chọn vùng xử lý bằng icon trang giấy
"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame
from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath

from typing import Set


class PaperIcon(QWidget):
    """
    Icon trang giấy xếp chồng với các vùng có thể click
    """
    
    zone_toggled = pyqtSignal(str, bool)  # zone_id, enabled
    
    def __init__(self, mode: str = 'corner', parent=None):
        """
        mode: 'corner' | 'edge' | 'custom'
        """
        super().__init__(parent)
        
        self.mode = mode
        self._selected_zones: Set[str] = set()
        self._hover_zone = None
        
        # Size and white background
        self.setFixedSize(100, 120)
        self.setMouseTracking(True)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(255, 255, 255))
        self.setPalette(palette)
        
        # Zone definitions (relative to paper rect)
        self._init_zones()
    
    def _init_zones(self):
        """Định nghĩa các vùng có thể click"""
        if self.mode == 'corner':
            # 4 góc
            self.zones = {
                'corner_tl': {'name': 'Góc TL', 'pos': 'tl'},
                'corner_tr': {'name': 'Góc TR', 'pos': 'tr'},
                'corner_bl': {'name': 'Góc DL', 'pos': 'bl'},
                'corner_br': {'name': 'Góc DR', 'pos': 'br'},
            }
        elif self.mode == 'edge':
            # 4 cạnh
            self.zones = {
                'margin_left': {'name': 'Trái', 'pos': 'left'},
                'margin_right': {'name': 'Phải', 'pos': 'right'},
                'margin_top': {'name': 'Trên', 'pos': 'top'},
                'margin_bottom': {'name': 'Dưới', 'pos': 'bottom'},
            }
        else:
            # Custom - không có preset
            self.zones = {}
    
    def _get_paper_rect(self) -> QRectF:
        """Lấy rect của trang giấy chính"""
        w, h = self.width(), self.height()
        margin = 10
        paper_w = w - margin * 2 - 6  # 6 for stacked effect
        paper_h = h - margin * 2 - 6
        return QRectF(margin + 6, margin, paper_w, paper_h)
    
    def _get_zone_rect(self, zone_id: str) -> QRectF:
        """Lấy rect của một zone"""
        paper = self._get_paper_rect()
        zone = self.zones.get(zone_id, {})
        pos = zone.get('pos', '')
        
        size = 18  # Zone size
        edge_width = 10  # Edge width
        
        if pos == 'tl':
            return QRectF(paper.left(), paper.top(), size, size)
        elif pos == 'tr':
            return QRectF(paper.right() - size, paper.top(), size, size)
        elif pos == 'bl':
            return QRectF(paper.left(), paper.bottom() - size, size, size)
        elif pos == 'br':
            return QRectF(paper.right() - size, paper.bottom() - size, size, size)
        elif pos == 'left':
            return QRectF(paper.left(), paper.top() + size, edge_width, paper.height() - size * 2)
        elif pos == 'right':
            return QRectF(paper.right() - edge_width, paper.top() + size, edge_width, paper.height() - size * 2)
        elif pos == 'top':
            return QRectF(paper.left() + size, paper.top(), paper.width() - size * 2, edge_width)
        elif pos == 'bottom':
            return QRectF(paper.left() + size, paper.bottom() - edge_width, paper.width() - size * 2, edge_width)
        
        return QRectF()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Fill background with white
        painter.fillRect(self.rect(), QColor(255, 255, 255))
        
        paper = self._get_paper_rect()
        
        # Vẽ trang giấy xếp chồng (shadow papers)
        for i in range(2, 0, -1):
            offset = i * 3
            shadow_rect = QRectF(
                paper.left() - offset,
                paper.top() + offset,
                paper.width(),
                paper.height()
            )
            painter.setPen(QPen(QColor(180, 180, 180), 1))
            painter.setBrush(QBrush(QColor(240, 240, 240)))
            painter.drawRect(shadow_rect)
        
        # Vẽ trang giấy chính
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawRect(paper)
        
        # Vẽ các đường kẻ giả lập text
        painter.setPen(QPen(QColor(220, 220, 220), 1))
        line_y = paper.top() + 25
        while line_y < paper.bottom() - 15:
            painter.drawLine(
                int(paper.left() + 20), int(line_y),
                int(paper.right() - 10), int(line_y)
            )
            line_y += 8
        
        # Vẽ các zones
        for zone_id in self.zones:
            zone_rect = self._get_zone_rect(zone_id)
            
            is_selected = zone_id in self._selected_zones
            is_hover = zone_id == self._hover_zone
            
            # Màu sắc - Blue theme
            if is_selected:
                fill_color = QColor(0, 104, 255, 150)  # Blue khi chọn
                border_color = QColor(0, 82, 204)
            elif is_hover:
                fill_color = QColor(0, 104, 255, 80)  # Blue nhạt khi hover
                border_color = QColor(0, 104, 255)
            else:
                fill_color = QColor(209, 213, 219, 100)  # Xám nhạt
                border_color = QColor(156, 163, 175)
            
            painter.setPen(QPen(border_color, 1))
            painter.setBrush(QBrush(fill_color))
            painter.drawRect(zone_rect)
        
        # Vẽ dấu + cho custom mode
        if self.mode == 'custom':
            # Dashed border around paper
            pen = QPen(QColor(156, 163, 175), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(paper.adjusted(2, 2, -2, -2))
            
            # Draw + sign
            center_x = paper.center().x()
            center_y = paper.center().y()
            plus_size = 20
            
            painter.setPen(QPen(QColor(107, 114, 128), 3))
            painter.drawLine(int(center_x - plus_size/2), int(center_y),
                           int(center_x + plus_size/2), int(center_y))
            painter.drawLine(int(center_x), int(center_y - plus_size/2),
                           int(center_x), int(center_y + plus_size/2))
            
            self.setCursor(Qt.PointingHandCursor)
    
    def mouseMoveEvent(self, event):
        """Track hover"""
        pos = event.pos()
        new_hover = None
        
        for zone_id in self.zones:
            zone_rect = self._get_zone_rect(zone_id)
            if zone_rect.contains(QPointF(pos)):
                new_hover = zone_id
                break
        
        if new_hover != self._hover_zone:
            self._hover_zone = new_hover
            self.setCursor(Qt.PointingHandCursor if new_hover else Qt.ArrowCursor)
            self.update()
    
    def mousePressEvent(self, event):
        """Toggle zone khi click"""
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            
            for zone_id in self.zones:
                zone_rect = self._get_zone_rect(zone_id)
                if zone_rect.contains(QPointF(pos)):
                    # Toggle
                    if zone_id in self._selected_zones:
                        self._selected_zones.remove(zone_id)
                        self.zone_toggled.emit(zone_id, False)
                    else:
                        self._selected_zones.add(zone_id)
                        self.zone_toggled.emit(zone_id, True)
                    
                    self.update()
                    break
    
    def leaveEvent(self, event):
        self._hover_zone = None
        self.update()
    
    def set_zone_selected(self, zone_id: str, selected: bool):
        """Set trạng thái zone từ bên ngoài"""
        if selected:
            self._selected_zones.add(zone_id)
        else:
            self._selected_zones.discard(zone_id)
        self.update()
    
    def get_selected_zones(self) -> Set[str]:
        """Lấy danh sách zones đang chọn"""
        return self._selected_zones.copy()
    
    def clear_selection(self):
        """Bỏ chọn tất cả"""
        self._selected_zones.clear()
        self.update()


class ZoneSelectorWidget(QFrame):
    """
    Widget tổng hợp cho việc chọn zones
    Gồm: Icon Góc | Icon Cạnh | Icon Tùy biến
    """
    
    zones_changed = pyqtSignal(set)  # Set of zone_ids
    zone_clicked = pyqtSignal(str, bool)  # zone_id, enabled - last clicked zone
    add_custom_zone = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setFrameStyle(QFrame.NoFrame)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(255, 255, 255))
        self.setPalette(palette)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # Corner selector (no label - label is in settings_panel)
        self.corner_icon = PaperIcon(mode='corner')
        self.corner_icon.zone_toggled.connect(self._on_zone_toggled)
        self.corner_icon.set_zone_selected('corner_tl', True)
        layout.addWidget(self.corner_icon)
        
        # Edge selector (no label)
        self.edge_icon = PaperIcon(mode='edge')
        self.edge_icon.zone_toggled.connect(self._on_zone_toggled)
        layout.addWidget(self.edge_icon)
        
        # Custom button (no label)
        self.custom_icon = PaperIcon(mode='custom')
        self.custom_icon.setToolTip("Thêm vùng tùy biến")
        layout.addWidget(self.custom_icon)
        
        # Connect custom icon click
        self.custom_icon.mousePressEvent = self._on_custom_click
    
    def _on_zone_toggled(self, zone_id: str, enabled: bool):
        """Khi toggle zone"""
        all_zones = self.get_all_selected_zones()
        self.zones_changed.emit(all_zones)
        # Emit last clicked zone
        self.zone_clicked.emit(zone_id, enabled)
    
    def _on_custom_click(self, event):
        """Khi click vào custom icon"""
        self.add_custom_zone.emit()
    
    def get_all_selected_zones(self) -> set:
        """Lấy tất cả zones đang chọn"""
        zones = set()
        zones.update(self.corner_icon.get_selected_zones())
        zones.update(self.edge_icon.get_selected_zones())
        return zones
    
    def set_zone_selected(self, zone_id: str, selected: bool):
        """Set trạng thái zone"""
        if zone_id.startswith('corner'):
            self.corner_icon.set_zone_selected(zone_id, selected)
        elif zone_id.startswith('margin'):
            self.edge_icon.set_zone_selected(zone_id, selected)
        # Emit signal to notify listeners
        self.zones_changed.emit(self.get_all_selected_zones())
