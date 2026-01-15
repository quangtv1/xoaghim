"""
Zone Selector - Widget chọn vùng xử lý bằng icon trang giấy
"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame
from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath

from typing import Set, Optional


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

        # For custom mode - track which draw mode is active
        self._draw_mode_remove = False  # "-" mode (blue)
        self._draw_mode_protect = False  # "+" mode (pink)
        self._hover_area: Optional[str] = None  # 'remove' or 'protect' or None

        # Size and white background
        self.setFixedSize(80, 100)
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

        size = 18  # Zone size (corners)
        edge_thickness = 10  # Thickness for all edges (width for left/right, height for top/bottom)
        edge_inset = 10  # Offset from corners for top/bottom edges (smaller = wider)

        if pos == 'tl':
            return QRectF(paper.left(), paper.top(), size, size)
        elif pos == 'tr':
            return QRectF(paper.right() - size, paper.top(), size, size)
        elif pos == 'bl':
            return QRectF(paper.left(), paper.bottom() - size, size, size)
        elif pos == 'br':
            return QRectF(paper.right() - size, paper.bottom() - size, size, size)
        elif pos == 'left':
            return QRectF(paper.left(), paper.top() + size, edge_thickness, paper.height() - size * 2)
        elif pos == 'right':
            return QRectF(paper.right() - edge_thickness, paper.top() + size, edge_thickness, paper.height() - size * 2)
        elif pos == 'top':
            return QRectF(paper.left() + edge_inset, paper.top(), paper.width() - edge_inset * 2, edge_thickness)
        elif pos == 'bottom':
            return QRectF(paper.left() + edge_inset, paper.bottom() - edge_thickness, paper.width() - edge_inset * 2, edge_thickness)

        return QRectF()

    def _get_custom_areas(self) -> tuple:
        """Get clickable areas for custom mode (top: remove, bottom: protect)"""
        paper = self._get_paper_rect()
        half_height = paper.height() / 2

        # Top half for "-" (remove)
        remove_rect = QRectF(paper.left(), paper.top(), paper.width(), half_height)
        # Bottom half for "+" (protect)
        protect_rect = QRectF(paper.left(), paper.top() + half_height, paper.width(), half_height)

        return remove_rect, protect_rect

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

        if self.mode == 'custom':
            # Custom mode: split into 2 areas (top: -, bottom: +)
            self._paint_custom_mode(painter, paper)
        else:
            # Normal mode: draw text lines and zones
            self._paint_normal_mode(painter, paper)

        self.setCursor(Qt.PointingHandCursor)

    def _paint_normal_mode(self, painter: QPainter, paper: QRectF):
        """Paint normal mode (corner/edge zones)"""
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

    def _paint_custom_mode(self, painter: QPainter, paper: QRectF):
        """Paint custom mode with split areas (- top, + bottom)"""
        remove_rect, protect_rect = self._get_custom_areas()

        # Colors
        blue_light = QColor(59, 130, 246, 50)  # Light blue
        blue_border = QColor(59, 130, 246)
        pink_light = QColor(244, 114, 182, 50)  # Light pink
        pink_border = QColor(244, 114, 182)
        gray_border = QColor(156, 163, 175)
        gray_line = QColor(107, 114, 128)

        # Draw horizontal divider line
        divider_y = paper.top() + paper.height() / 2
        painter.setPen(QPen(QColor(200, 200, 200), 1, Qt.DashLine))
        painter.drawLine(int(paper.left() + 5), int(divider_y),
                        int(paper.right() - 5), int(divider_y))

        # === TOP AREA: "-" (remove mode) ===
        top_rect = QRectF(paper.left() + 2, paper.top() + 2,
                         paper.width() - 4, paper.height() / 2 - 4)

        if self._draw_mode_remove:
            # Active - blue background
            painter.fillRect(top_rect, blue_light)
            border_color = blue_border
            line_color = blue_border
        elif self._hover_area == 'remove':
            # Hover - light blue
            painter.fillRect(top_rect, QColor(59, 130, 246, 30))
            border_color = blue_border
            line_color = blue_border
        else:
            border_color = gray_border
            line_color = gray_line

        # Draw "-" sign (smaller, at top)
        minus_size = 16
        center_x = paper.center().x()
        center_y = paper.top() + paper.height() / 4

        painter.setPen(QPen(line_color, 2))
        painter.drawLine(int(center_x - minus_size/2), int(center_y),
                        int(center_x + minus_size/2), int(center_y))

        # === BOTTOM AREA: "+" (protect mode) ===
        bottom_rect = QRectF(paper.left() + 2, paper.top() + paper.height() / 2 + 2,
                            paper.width() - 4, paper.height() / 2 - 4)

        if self._draw_mode_protect:
            # Active - pink background
            painter.fillRect(bottom_rect, pink_light)
            border_color = pink_border
            line_color = pink_border
        elif self._hover_area == 'protect':
            # Hover - light pink
            painter.fillRect(bottom_rect, QColor(244, 114, 182, 30))
            border_color = pink_border
            line_color = pink_border
        else:
            border_color = gray_border
            line_color = gray_line

        # Draw "+" sign (at bottom)
        plus_size = 18
        center_y = paper.top() + paper.height() * 3 / 4

        painter.setPen(QPen(line_color, 2))
        # Horizontal line
        painter.drawLine(int(center_x - plus_size/2), int(center_y),
                        int(center_x + plus_size/2), int(center_y))
        # Vertical line
        painter.drawLine(int(center_x), int(center_y - plus_size/2),
                        int(center_x), int(center_y + plus_size/2))

        # Draw dashed border around paper if any mode is active
        if self._draw_mode_remove or self._draw_mode_protect:
            if self._draw_mode_remove:
                pen_color = blue_border
            else:
                pen_color = pink_border
            pen = QPen(pen_color, 2, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(paper.adjusted(1, 1, -1, -1))

    def mouseMoveEvent(self, event):
        """Track hover"""
        pos = event.pos()

        if self.mode == 'custom':
            # Custom mode: check which area is hovered
            remove_rect, protect_rect = self._get_custom_areas()
            old_hover = self._hover_area

            if remove_rect.contains(QPointF(pos)):
                self._hover_area = 'remove'
            elif protect_rect.contains(QPointF(pos)):
                self._hover_area = 'protect'
            else:
                self._hover_area = None

            if old_hover != self._hover_area:
                self.update()
        else:
            # Normal mode
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

            if self.mode == 'custom':
                # Custom mode: handled by ZoneSelectorWidget
                # Just pass through to parent's handler
                pass
            else:
                # Normal mode
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
        self._hover_area = None
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

    def set_draw_mode(self, mode: Optional[str]):
        """Set draw mode: 'remove', 'protect', or None"""
        self._draw_mode_remove = (mode == 'remove')
        self._draw_mode_protect = (mode == 'protect')
        self.update()

    def get_draw_mode(self) -> Optional[str]:
        """Get current draw mode"""
        if self._draw_mode_remove:
            return 'remove'
        elif self._draw_mode_protect:
            return 'protect'
        return None


class ZoneSelectorWidget(QFrame):
    """
    Widget tổng hợp cho việc chọn zones
    Gồm: Icon Góc | Icon Cạnh | Icon Tùy biến
    """

    zones_changed = pyqtSignal(set)  # Set of zone_ids
    zone_clicked = pyqtSignal(str, bool)  # zone_id, enabled - last clicked zone
    add_custom_zone = pyqtSignal()
    # Draw mode signal: None = off, 'remove' = draw removal zone, 'protect' = draw protection zone
    draw_mode_changed = pyqtSignal(object)  # str or None

    def __init__(self, parent=None):
        super().__init__(parent)

        self._draw_mode: Optional[str] = None  # 'remove', 'protect', or None
        self.setFrameStyle(QFrame.NoFrame)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(255, 255, 255))
        self.setPalette(palette)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignTop)

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
        self.custom_icon.setToolTip("Vẽ vùng xóa ghim (-) hoặc bảo vệ (+)")
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
        """Khi click vào custom icon - detect which area clicked"""
        if event.button() != Qt.LeftButton:
            return

        pos = event.pos()
        remove_rect, protect_rect = self.custom_icon._get_custom_areas()

        if remove_rect.contains(QPointF(pos)):
            # Clicked on "-" (remove) area
            if self._draw_mode == 'remove':
                # Toggle off
                self._set_draw_mode(None)
            else:
                # Turn on remove mode (turn off protect if on)
                self._set_draw_mode('remove')
        elif protect_rect.contains(QPointF(pos)):
            # Clicked on "+" (protect) area
            if self._draw_mode == 'protect':
                # Toggle off
                self._set_draw_mode(None)
            else:
                # Turn on protect mode (turn off remove if on)
                self._set_draw_mode('protect')

    def _set_draw_mode(self, mode: Optional[str]):
        """Internal: set draw mode and emit signal"""
        self._draw_mode = mode
        self.custom_icon.set_draw_mode(mode)
        self.draw_mode_changed.emit(mode)

    def set_draw_mode(self, mode: Optional[str]):
        """Set draw mode state from outside"""
        self._draw_mode = mode
        self.custom_icon.set_draw_mode(mode)

    def get_draw_mode(self) -> Optional[str]:
        """Get current draw mode: 'remove', 'protect', or None"""
        return self._draw_mode

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

    def reset_all(self):
        """Reset all zones - deselect all corners and edges"""
        self.corner_icon.clear_selection()
        self.edge_icon.clear_selection()
        self.custom_icon.set_draw_mode(None)
        self._draw_mode = None
        self.zones_changed.emit(set())

    def reset_preset(self):
        """Reset only preset zones (corners and edges)"""
        self.corner_icon.clear_selection()
        self.edge_icon.clear_selection()
        self.zones_changed.emit(set())

    def reset_custom(self):
        """Reset only custom draw mode"""
        self.custom_icon.set_draw_mode(None)
        self._draw_mode = None
