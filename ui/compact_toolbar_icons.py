"""
Compact Toolbar Icons - QPainter-based icon buttons for collapsed settings toolbar
Larger icons with consistent single color, hover effect, and tooltips
"""

from PyQt5.QtWidgets import QPushButton
from PyQt5.QtCore import Qt, QRect, QRectF
from PyQt5.QtGui import QPainter, QPen, QColor, QBrush, QPainterPath


class CompactIconButton(QPushButton):
    """Reusable icon button with QPainter outline style - larger size for easy clicking"""

    # Colors - single consistent color scheme
    COLOR_NORMAL = QColor(107, 114, 128)      # #6B7280 gray
    COLOR_HOVER = QColor(59, 130, 246)        # #3B82F6 blue on hover
    COLOR_SELECTED = QColor(59, 130, 246)     # #3B82F6 blue when selected
    COLOR_SELECTED_BG = QColor(219, 234, 254) # #DBEAFE light blue background
    COLOR_PROTECT = QColor(236, 72, 153)      # #EC4899 pink for protect icon

    def __init__(self, icon_type: str, tooltip: str, parent=None):
        super().__init__(parent)
        self.icon_type = icon_type
        self._selected = False
        self._checkable = False
        self.setToolTip(tooltip)
        self.setFixedSize(38, 38)  # Icon size
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
            }
        """)

    def setCheckable(self, checkable: bool):
        """Make button toggleable"""
        self._checkable = checkable
        super().setCheckable(checkable)

    def setSelected(self, selected: bool):
        """Set selected state (for non-checkable buttons)"""
        self._selected = selected
        self.update()

    def isSelected(self) -> bool:
        return self._selected or self.isChecked()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        is_selected = self.isSelected()
        is_hovered = self.underMouse()

        # Draw background for selected state (blue for all)
        if is_selected:
            painter.setBrush(QBrush(self.COLOR_SELECTED_BG))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 4, 4)

        # Icon color - pink for protect when selected, blue for others
        if is_selected:
            if self.icon_type == 'draw_protect':
                pen_color = self.COLOR_PROTECT  # Pink for + icon
            else:
                pen_color = self.COLOR_SELECTED
        elif is_hovered:
            pen_color = self.COLOR_HOVER
        else:
            pen_color = self.COLOR_NORMAL

        painter.setPen(QPen(pen_color, 1.5))  # Line width for icons
        painter.setBrush(Qt.NoBrush)

        # Draw icon based on type
        self._draw_icon(painter, rect, pen_color)

    def _draw_icon(self, painter: QPainter, rect: QRect, color: QColor):
        """Draw the appropriate icon"""
        cx, cy = rect.center().x(), rect.center().y()

        # Corner icons
        if self.icon_type == 'corner_tl':
            self._draw_corner(painter, cx, cy, top=True, left=True)
        elif self.icon_type == 'corner_tr':
            self._draw_corner(painter, cx, cy, top=True, left=False)
        elif self.icon_type == 'corner_bl':
            self._draw_corner(painter, cx, cy, top=False, left=True)
        elif self.icon_type == 'corner_br':
            self._draw_corner(painter, cx, cy, top=False, left=False)

        # Edge icons
        elif self.icon_type == 'margin_top':
            self._draw_edge(painter, cx, cy, 'top')
        elif self.icon_type == 'margin_bottom':
            self._draw_edge(painter, cx, cy, 'bottom')
        elif self.icon_type == 'margin_left':
            self._draw_edge(painter, cx, cy, 'left')
        elif self.icon_type == 'margin_right':
            self._draw_edge(painter, cx, cy, 'right')

        # Custom draw icons
        elif self.icon_type == 'draw_remove':
            self._draw_minus(painter, cx, cy)
        elif self.icon_type == 'draw_protect':
            self._draw_plus(painter, cx, cy)

        # Filter icons
        elif self.icon_type == 'filter_all':
            self._draw_filter_all(painter, cx, cy)
        elif self.icon_type == 'filter_odd':
            self._draw_filter_page(painter, cx, cy, '1')
        elif self.icon_type == 'filter_even':
            self._draw_filter_page(painter, cx, cy, '2')
        elif self.icon_type == 'filter_free':
            self._draw_filter_page(painter, cx, cy, '*')

        # Action icons
        elif self.icon_type == 'clear':
            self._draw_trash(painter, cx, cy)
        elif self.icon_type == 'ai_detect':
            self._draw_ai(painter, cx, cy)
        elif self.icon_type == 'collapse':
            self._draw_chevron(painter, cx, cy, up=True)
        elif self.icon_type == 'expand':
            self._draw_chevron(painter, cx, cy, up=False)

    def _draw_corner(self, painter: QPainter, cx: int, cy: int, top: bool, left: bool):
        """Draw rectangle with filled corner"""
        w, h = 14, 18  # Rectangle size
        rect_x = cx - w // 2
        rect_y = cy - h // 2
        corner_size = 5  # Filled corner size

        # Save current pen color before modifying
        fill_color = painter.pen().color()

        # Draw rectangle outline (no rounded corners)
        painter.save()
        pen = painter.pen()
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect_x, rect_y, w, h)
        painter.restore()

        # Fill the corner
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(fill_color))

        if top and left:  # Top-left corner
            painter.drawRect(rect_x + 1, rect_y + 1, corner_size, corner_size)
        elif top and not left:  # Top-right corner
            painter.drawRect(rect_x + w - corner_size - 1, rect_y + 1, corner_size, corner_size)
        elif not top and left:  # Bottom-left corner
            painter.drawRect(rect_x + 1, rect_y + h - corner_size - 1, corner_size, corner_size)
        else:  # Bottom-right corner
            painter.drawRect(rect_x + w - corner_size - 1, rect_y + h - corner_size - 1, corner_size, corner_size)

        painter.restore()

    def _draw_edge(self, painter: QPainter, cx: int, cy: int, position: str):
        """Draw edge/margin icon - rectangle with filled edge inside"""
        w, h = 14, 18  # Rectangle size
        rect_x = cx - w // 2
        rect_y = cy - h // 2
        edge_thickness = 4  # Filled edge thickness

        # Save current pen color
        fill_color = painter.pen().color()

        # Draw rectangle outline (no rounded corners)
        painter.save()
        pen = painter.pen()
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect_x, rect_y, w, h)
        painter.restore()

        # Fill the edge inside the rectangle
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(fill_color))

        if position == 'top':
            painter.drawRect(rect_x + 1, rect_y + 1, w - 2, edge_thickness)
        elif position == 'bottom':
            painter.drawRect(rect_x + 1, rect_y + h - edge_thickness - 1, w - 2, edge_thickness)
        elif position == 'left':
            painter.drawRect(rect_x + 1, rect_y + 1, edge_thickness, h - 2)
        elif position == 'right':
            painter.drawRect(rect_x + w - edge_thickness - 1, rect_y + 1, edge_thickness, h - 2)

        painter.restore()

    def _draw_minus(self, painter: QPainter, cx: int, cy: int):
        """Draw minus (-) icon for remove zone"""
        # Horizontal line (minus)
        painter.save()
        pen = painter.pen()
        pen.setWidthF(1.5)
        painter.setPen(pen)
        painter.drawLine(cx - 6, cy, cx + 6, cy)
        painter.restore()

    def _draw_plus(self, painter: QPainter, cx: int, cy: int):
        """Draw plus (+) icon for protect zone"""
        # Horizontal and vertical lines (plus)
        painter.save()
        pen = painter.pen()
        pen.setWidthF(1.5)
        painter.setPen(pen)
        painter.drawLine(cx - 6, cy, cx + 6, cy)  # Horizontal
        painter.drawLine(cx, cy - 6, cx, cy + 6)  # Vertical
        painter.restore()

    def _draw_filter_all(self, painter: QPainter, cx: int, cy: int):
        """Draw 2 stacked pages icon for 'all pages' filter"""
        painter.save()
        pen = painter.pen()
        pen.setWidthF(1.0)
        painter.setPen(pen)
        w, h = 12, 16  # Rectangle size
        offset = 3  # Offset between rectangles (closer)
        # Back page (top-right)
        painter.drawRect(cx - w // 2 + offset, cy - h // 2 - offset, w, h)
        # Front page (bottom-left)
        painter.drawRect(cx - w // 2 - offset, cy - h // 2 + offset, w, h)
        painter.restore()

    def _draw_filter_page(self, painter: QPainter, cx: int, cy: int, label: str):
        """Draw single page with label"""
        w, h = 14, 20
        rect_x = cx - w // 2
        rect_y = cy - h // 2

        # Page outline with thin border
        painter.save()
        pen = painter.pen()
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawRect(rect_x, rect_y, w, h)
        painter.restore()

        # Label text - centered in the rectangle
        painter.save()
        font = painter.font()
        font.setPixelSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRect(rect_x, rect_y, w, h), Qt.AlignCenter, label)
        painter.restore()

    def _draw_trash(self, painter: QPainter, cx: int, cy: int):
        """Draw trash/delete icon - larger"""
        # Lid
        painter.drawLine(cx - 7, cy - 7, cx + 7, cy - 7)
        painter.drawLine(cx - 3, cy - 10, cx + 3, cy - 10)
        painter.drawLine(cx - 3, cy - 10, cx - 3, cy - 7)
        painter.drawLine(cx + 3, cy - 10, cx + 3, cy - 7)

        # Body
        path = QPainterPath()
        path.moveTo(cx - 6, cy - 6)
        path.lineTo(cx - 5, cy + 9)
        path.lineTo(cx + 5, cy + 9)
        path.lineTo(cx + 6, cy - 6)
        painter.drawPath(path)

        # Lines inside
        painter.drawLine(cx - 2, cy - 4, cx - 2, cy + 7)
        painter.drawLine(cx + 2, cy - 4, cx + 2, cy + 7)

    def _draw_ai(self, painter: QPainter, cx: int, cy: int):
        """Draw AI text icon for auto-detect protect zones"""
        painter.save()
        font = painter.font()
        font.setPixelSize(14)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(QRect(cx - 12, cy - 10, 24, 20), Qt.AlignCenter, "AI")
        painter.restore()

    def _draw_chevron(self, painter: QPainter, cx: int, cy: int, up: bool):
        """Draw chevron for collapse/expand - larger"""
        path = QPainterPath()
        if up:  # ^
            path.moveTo(cx - 8, cy + 4)
            path.lineTo(cx, cy - 4)
            path.lineTo(cx + 8, cy + 4)
        else:  # v
            path.moveTo(cx - 8, cy - 4)
            path.lineTo(cx, cy + 4)
            path.lineTo(cx + 8, cy - 4)

        painter.drawPath(path)

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)


class CompactIconSeparator(QPushButton):
    """Vertical separator between icon groups"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(8, 38)  # Match icon height
        self.setEnabled(False)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(209, 213, 219), 1))  # #D1D5DB
        cx = self.width() // 2
        painter.drawLine(cx, 6, cx, self.height() - 6)
