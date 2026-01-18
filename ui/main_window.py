"""
Main Window - Cửa sổ chính với UI theo mẫu Foxit
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QAction, QLabel, QPushButton, QToolButton,
    QFileDialog, QMessageBox, QProgressBar,
    QFrame, QApplication, QSpinBox, QComboBox, QSizePolicy,
    QMenu, QDialog, QRadioButton, QStackedWidget,
    QGroupBox, QDialogButtonBox, QSplitter, QStyledItemDelegate, QShortcut
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QEvent, QObject, QRect, QTimer
from PyQt5.QtGui import QKeySequence, QDragEnterEvent, QDropEvent, QPixmap, QPainter, QPen, QIcon, QColor

import os
import time
from pathlib import Path
from typing import Optional, List
import numpy as np

from ui.continuous_preview import ContinuousPreviewWidget
from ui.batch_sidebar import BatchSidebar
from ui.settings_panel import SettingsPanel
from core.processor import Zone, StapleRemover
from core.pdf_handler import PDFHandler, PDFExporter


class ComboItemDelegate(QStyledItemDelegate):
    """Custom delegate for larger combobox items"""
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(24)  # Set item height to 24px
        return size


class MenuHoverManager(QObject):
    """Manages hover behavior for menu buttons at application level"""
    
    _instance = None
    
    def __init__(self):
        super().__init__()
        self._buttons = []
        self._active_menu = None
        self._installed = False
    
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = MenuHoverManager()
        return cls._instance
    
    def register_button(self, btn):
        self._buttons.append(btn)
        if not self._installed:
            QApplication.instance().installEventFilter(self)
            self._installed = True
    
    def set_active_menu(self, menu):
        self._active_menu = menu
    
    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseMove and self._active_menu and self._active_menu.isVisible():
            global_pos = event.globalPos()
            for btn in self._buttons:
                if btn._menu and btn._menu != self._active_menu:
                    btn_top_left = btn.mapToGlobal(btn.rect().topLeft())
                    btn_global_rect = QRect(btn_top_left, btn.size())
                    if btn_global_rect.contains(global_pos):
                        # Mouse is over another button, switch menu
                        self._active_menu.hide()
                        btn._menu.popup(btn.mapToGlobal(btn.rect().bottomLeft()))
                        self._active_menu = btn._menu
                        return False
        return False


class HoverMenuButton(QPushButton):
    """Button that shows menu on hover, closes other menus in group"""
    
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self._menu = None
        MenuHoverManager.instance().register_button(self)
        self.setMouseTracking(True)
    
    def setMenu(self, menu: QMenu):
        self._menu = menu
        menu.aboutToShow.connect(lambda: MenuHoverManager.instance().set_active_menu(menu))
        menu.aboutToHide.connect(lambda: MenuHoverManager.instance().set_active_menu(None))
        super().setMenu(menu)
    
    def enterEvent(self, event):
        """Show menu when mouse enters if another menu is open"""
        if self._menu:
            manager = MenuHoverManager.instance()
            if manager._active_menu and manager._active_menu.isVisible() and manager._active_menu != self._menu:
                manager._active_menu.hide()
                self._menu.popup(self.mapToGlobal(self.rect().bottomLeft()))
        super().enterEvent(event)
    
    def mousePressEvent(self, event):
        """Toggle menu on click"""
        if self._menu:
            if self._menu.isVisible():
                self._menu.hide()
            else:
                self._menu.popup(self.mapToGlobal(self.rect().bottomLeft()))


class ProcessThread(QThread):
    """Thread xử lý PDF"""

    progress = pyqtSignal(int, int)  # current_page, total_pages
    finished = pyqtSignal(bool, str)

    def __init__(self, input_path: str, output_path: str, zones: List[Zone], settings: dict,
                 zone_getter=None):
        """Initialize ProcessThread.

        Args:
            input_path: Input PDF path
            output_path: Output PDF path
            zones: Default zones (used when zone_getter is None)
            settings: Processing settings
            zone_getter: Optional callable(page_idx) -> List[Zone] for per-page zones
        """
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.zones = zones
        self.settings = settings
        self.zone_getter = zone_getter  # For per-page zone support
        self._cancelled = False
        self._total_pages = 0

    def run(self):
        try:
            start_time = time.time()
            processor = StapleRemover(protect_red=False)

            # Apply text protection settings if provided
            text_protection = self.settings.get('text_protection')
            if text_protection:
                processor.set_text_protection(text_protection)

            def process_func(image, page_num):
                if self._cancelled:
                    return image
                # Log format: Trang X/Y: full_path
                print(f"Trang {page_num}/{self._total_pages}: {self.input_path}")

                # Get zones for this page (per-page or global)
                if self.zone_getter:
                    page_zones = self.zone_getter(page_num)  # page_num is 0-based from exporter
                else:
                    page_zones = self.zones

                if not page_zones:
                    return image  # No zones for this page

                return processor.process_image(image, page_zones)

            def progress_callback(current, total):
                self._total_pages = total
                if not self._cancelled:
                    self.progress.emit(current, total)

            success = PDFExporter.export(
                self.input_path,
                self.output_path,
                process_func,
                dpi=self.settings.get('dpi', 200),
                jpeg_quality=self.settings.get('jpeg_quality', 90),
                optimize_size=self.settings.get('optimize_size', False),
                progress_callback=progress_callback
            )

            # Log elapsed time after file completes
            elapsed = int(time.time() - start_time)
            h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
            print(f">> Thời gian: {h:02d}:{m:02d}:{s:02d}")

            if self._cancelled:
                self.finished.emit(False, "Đã hủy")
            elif success:
                self.finished.emit(True, self.output_path)
            else:
                self.finished.emit(False, "Lỗi khi xử lý")

        except Exception as e:
            self.finished.emit(False, str(e))

    def cancel(self):
        self._cancelled = True


class BatchProcessThread(QThread):
    """Thread xử lý batch PDF"""

    progress = pyqtSignal(int, int, str)  # current_file, total_files, current_filename
    file_progress = pyqtSignal(int, int)  # current_page, total_pages_in_file
    total_progress = pyqtSignal(int, int)  # pages_processed, total_pages_all_files
    finished = pyqtSignal(bool, dict)  # success, stats {total, success, failed, errors}

    def __init__(self, files: List[str], base_dir: str, output_dir: str,
                 zones: List[Zone], settings: dict, page_counts: dict = None):
        super().__init__()
        self.files = files
        self.base_dir = base_dir
        self.output_dir = output_dir
        self.zones = zones
        self.settings = settings
        self.page_counts = page_counts or {}  # {file_path: page_count}
        self._cancelled = False
        self._pages_processed = 0
        self._total_pages = sum(self.page_counts.get(f, 0) for f in files)
    
    def run(self):
        stats = {
            'total': len(self.files),
            'success': 0,
            'failed': 0,
            'errors': [],
            'input_size': 0,
            'output_size': 0
        }

        try:
            start_time = time.time()
            processor = StapleRemover(protect_red=False)

            # Apply text protection settings if provided
            text_protection = self.settings.get('text_protection')
            if text_protection:
                processor.set_text_protection(text_protection)

            for i, input_path in enumerate(self.files):
                if self._cancelled:
                    break

                filename = os.path.basename(input_path)
                self.progress.emit(i + 1, len(self.files), filename)

                try:
                    # Generate output path
                    output_path = self._get_output_path(input_path)

                    # Create output directory if needed
                    output_dir = os.path.dirname(output_path)
                    if output_dir:
                        os.makedirs(output_dir, exist_ok=True)

                    # Get file sizes
                    stats['input_size'] += os.path.getsize(input_path)

                    # Closure để capture file index và full path cho logging
                    file_idx = i + 1
                    total_files = len(self.files)
                    pdf_path = input_path
                    zones_list = self.zones

                    # Blank line giữa các file (trừ file đầu)
                    if i > 0:
                        print()

                    def process_func(image, page_num):
                        if self._cancelled:
                            return image
                        # Log format: STT/Tổng: full_path >> Trang X
                        print(f"{file_idx}/{total_files}: {pdf_path} >> Trang {page_num}")
                        return processor.process_image(image, zones_list)

                    # Track pages for total progress
                    file_pages_before = self._pages_processed

                    def page_progress(current, total):
                        if not self._cancelled:
                            self.file_progress.emit(current, total)
                            # Emit total progress (pages across all files)
                            pages_done = file_pages_before + current
                            self.total_progress.emit(pages_done, self._total_pages)

                    success = PDFExporter.export(
                        input_path,
                        output_path,
                        process_func,
                        dpi=self.settings.get('dpi', 200),
                        jpeg_quality=self.settings.get('jpeg_quality', 90),
                        optimize_size=self.settings.get('optimize_size', False),
                        progress_callback=page_progress
                    )

                    # Update pages processed for next file
                    self._pages_processed += self.page_counts.get(input_path, 0)

                    # Log elapsed time after each file
                    elapsed = int(time.time() - start_time)
                    h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
                    print(f">> Thời gian: {h:02d}:{m:02d}:{s:02d}")

                    if success and os.path.exists(output_path):
                        stats['success'] += 1
                        stats['output_size'] += os.path.getsize(output_path)
                    else:
                        stats['failed'] += 1
                        stats['errors'].append(f"{filename}: Lỗi xuất file")

                except Exception as e:
                    stats['failed'] += 1
                    stats['errors'].append(f"{filename}: {str(e)}")
            
            if self._cancelled:
                self.finished.emit(False, stats)
            else:
                self.finished.emit(True, stats)
                
        except Exception as e:
            stats['errors'].append(str(e))
            self.finished.emit(False, stats)
    
    def _get_output_path(self, input_path: str) -> str:
        """Generate output path for input file - matches batch_preview logic"""
        rel_path = os.path.relpath(input_path, self.base_dir)
        name, _ = os.path.splitext(rel_path)
        pattern = self.settings.get('filename_pattern', '{gốc}_clean.pdf')
        # Always apply filename pattern
        output_name = pattern.replace('{gốc}', name)
        return os.path.join(self.output_dir, output_name)
    
    def cancel(self):
        self._cancelled = True


class MainWindow(QMainWindow):
    """Cửa sổ chính"""
    
    MAX_PREVIEW_PAGES = 20
    
    def __init__(self):
        super().__init__()

        self._pdf_handler: Optional[PDFHandler] = None
        self._all_pages: List[np.ndarray] = []
        self._process_thread: Optional[ProcessThread] = None
        self._batch_process_thread: Optional[BatchProcessThread] = None
        self._current_file_path = ""
        self._batch_mode = False  # True when processing folder
        self._batch_base_dir = ""
        self._batch_output_dir = ""
        self._batch_files: List[str] = []
        self._last_dir = self._get_default_folder_dir()  # Remember last opened folder
        self._user_zoomed = False  # Track if user has manually zoomed
        self._current_draw_mode = None  # Track current draw mode for cancel logic

        self.setWindowTitle("Xóa Ghim PDF (5S)")
        self.setMinimumSize(1200, 800)
        self.setAcceptDrops(True)

        self._setup_ui()
        self._update_ui_state()
        self._restore_window_state()

        # Install event filter to cancel draw mode on click outside preview
        QApplication.instance().installEventFilter(self)
    
    def _setup_ui(self):
        """Thiết lập giao diện"""
        central = QWidget()
        central.setStyleSheet("background-color: white;")  # White background for everything below menu
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # === MENU BAR (Ribbon tabs) ===
        self._setup_menu_bar()

        # === SETTINGS PANEL (creates compact_toolbar, will be moved to right container) ===
        self.settings_panel = SettingsPanel()
        self.settings_panel.zones_changed.connect(self._on_zones_changed)
        self.settings_panel.settings_changed.connect(self._on_settings_changed)
        self.settings_panel.page_filter_changed.connect(self._on_page_filter_changed)
        self.settings_panel.output_settings_changed.connect(self._on_output_settings_changed)
        self.settings_panel.text_protection_changed.connect(self._on_text_protection_changed)
        self.settings_panel.draw_mode_changed.connect(self._on_draw_mode_changed)
        self.settings_panel.zones_reset.connect(self._on_zones_reset)
        self.settings_panel.zone_preset_toggled.connect(self._on_preset_zone_toggled)

        # === COMPACT TOOLBAR (above splitter) ===
        # Move compact_toolbar from settings_panel to main layout
        self.compact_toolbar = self.settings_panel.compact_toolbar
        self.compact_toolbar.setParent(None)  # Remove from settings_panel
        layout.addWidget(self.compact_toolbar)

        # Set initial visibility based on collapsed state (mutually exclusive)
        # Compact mode: show compact_toolbar, hide settings_panel
        # Detail mode: show settings_panel, hide compact_toolbar
        if self.settings_panel._collapsed:
            self.compact_toolbar.setVisible(True)
            self.settings_panel.setVisible(False)
        else:
            self.compact_toolbar.setVisible(False)
            self.settings_panel.setVisible(True)

        # Sync collapse button state with settings panel
        self._settings_collapsed = self.settings_panel._collapsed
        self._update_collapse_button_icon()

        # === MAIN CONTENT AREA (Sidebar + Right Panel) ===
        # Horizontal splitter: Sidebar | Right content
        self.preview_splitter = QSplitter(Qt.Horizontal)
        self.preview_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #D1D5DB;
                width: 4px;
            }
            QSplitter::handle:hover {
                background-color: #9CA3AF;
            }
        """)

        # Batch sidebar (left, hidden by default)
        self.batch_sidebar = BatchSidebar()
        self.batch_sidebar.file_selected.connect(self._on_sidebar_file_selected)
        self.batch_sidebar.selection_changed.connect(self._on_sidebar_selection_changed)
        self.batch_sidebar.close_requested.connect(self._on_close_file)
        self.batch_sidebar.collapsed_changed.connect(self._on_sidebar_collapsed_changed)
        self.batch_sidebar.setVisible(False)
        self.preview_splitter.addWidget(self.batch_sidebar)
        self.preview_splitter.setCollapsible(0, False)
        self.preview_splitter.splitterMoved.connect(self._on_splitter_moved)

        # Batch state variables
        self._batch_files: List[str] = []
        self._batch_current_index: int = 0
        self._is_first_file_in_batch: bool = True  # Track first file to fit width

        # Right container (Settings expanded + Preview + Bottom bar)
        right_container = QWidget()
        right_container.setStyleSheet("background-color: #E5E7EB;")
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Add settings panel (visibility already set based on collapsed state)
        right_layout.addWidget(self.settings_panel)

        # Connect compact toolbar signals
        self.compact_toolbar.search_changed.connect(
            self.batch_sidebar.set_search_filter
        )
        # Initially hide search box (sidebar is hidden by default)
        self.compact_toolbar.set_search_visible(False)

        # === PREVIEW WIDGET ===
        self.preview = ContinuousPreviewWidget()
        self.preview.zone_changed.connect(self._on_zone_changed_from_preview)
        self.preview.zone_selected.connect(self._on_zone_selected_from_preview)
        self.preview.zone_delete.connect(self._on_zone_delete_from_preview)
        self.preview.zone_drag_save_requested.connect(self._on_zone_drag_save_requested)
        self.preview.undo_zone_removed.connect(self._on_undo_zone_removed)
        self.preview.undo_zone_restored.connect(self._on_undo_zone_restored)
        self.preview.undo_preset_zone_toggled.connect(self._on_undo_preset_zone_toggled)
        self.preview.open_file_requested.connect(self._on_open)
        self.preview.open_folder_requested.connect(self._on_open_folder_batch)
        self.preview.file_dropped.connect(self._on_file_dropped)
        self.preview.folder_dropped.connect(self._on_folder_dropped)
        self.preview.files_dropped.connect(self._on_files_dropped)
        self.preview.close_requested.connect(self._on_close_file)
        self.preview.page_changed.connect(self._on_page_changed_from_scroll)
        self.preview.rect_drawn.connect(self._on_rect_drawn_from_preview)
        self.preview.prev_file_requested.connect(self._on_prev_file)
        self.preview.next_file_requested.connect(self._on_next_file)
        right_layout.addWidget(self.preview, stretch=1)

        # === BOTTOM BAR (inside right container) ===
        self._setup_bottom_bar(right_layout)

        self.preview_splitter.addWidget(right_container)
        self.preview_splitter.setSizes([200, 800])

        layout.addWidget(self.preview_splitter, stretch=1)
        
        # Hide status bar
        self.statusBar().hide()
    
    def _create_line_icon(self, icon_type: str, size: int = 16) -> QIcon:
        """Create line vector icon using QPainter"""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        pen = QPen(QColor(80, 80, 80))  # Dark gray
        pen.setWidth(1)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        
        margin = 2
        w = size - margin * 2
        h = size - margin * 2
        
        if icon_type == "open_file":
            # Folder with arrow - open file
            painter.drawRect(margin + 1, margin + 4, w - 2, h - 5)
            painter.drawLine(margin + 1, margin + 4, margin + 4, margin + 1)
            painter.drawLine(margin + 4, margin + 1, margin + 8, margin + 1)
            painter.drawLine(margin + 8, margin + 1, margin + 10, margin + 4)
            
        elif icon_type == "folder":
            # Simple folder
            painter.drawRect(margin + 1, margin + 4, w - 2, h - 5)
            painter.drawLine(margin + 1, margin + 4, margin + 4, margin + 1)
            painter.drawLine(margin + 4, margin + 1, margin + 7, margin + 1)
            painter.drawLine(margin + 7, margin + 1, margin + 9, margin + 4)
            
        elif icon_type == "help":
            # Question mark circle
            painter.drawEllipse(margin + 1, margin + 1, w - 2, h - 2)
            painter.drawArc(margin + 5, margin + 4, 6, 5, 0, 180 * 16)
            painter.drawLine(margin + 8, margin + 7, margin + 8, margin + 10)
            painter.drawPoint(margin + 8, margin + 12)
            
        elif icon_type == "zoom_in":
            # Magnifier with plus
            painter.drawEllipse(margin, margin, 10, 10)
            painter.drawLine(margin + 9, margin + 9, margin + 13, margin + 13)
            painter.drawLine(margin + 3, margin + 5, margin + 7, margin + 5)
            painter.drawLine(margin + 5, margin + 3, margin + 5, margin + 7)
            
        elif icon_type == "zoom_out":
            # Magnifier with minus
            painter.drawEllipse(margin, margin, 10, 10)
            painter.drawLine(margin + 9, margin + 9, margin + 13, margin + 13)
            painter.drawLine(margin + 3, margin + 5, margin + 7, margin + 5)
            
        elif icon_type == "fit_width":
            # Double-headed horizontal arrow with end bars |←→|
            cy = size // 2
            margin_x = 4
            bar_half = 6

            # Left vertical bar |
            painter.drawLine(margin_x, cy - bar_half, margin_x, cy + bar_half)
            # Right vertical bar |
            painter.drawLine(size - margin_x - 1, cy - bar_half, size - margin_x - 1, cy + bar_half)

            # Horizontal line connecting
            painter.drawLine(margin_x, cy, size - margin_x - 1, cy)

            # Left arrow head <
            painter.drawLine(margin_x, cy, margin_x + 4, cy - 3)
            painter.drawLine(margin_x, cy, margin_x + 4, cy + 3)

            # Right arrow head >
            painter.drawLine(size - margin_x - 1, cy, size - margin_x - 5, cy - 3)
            painter.drawLine(size - margin_x - 1, cy, size - margin_x - 5, cy + 3)

        elif icon_type == "fit_height":
            # Double-headed vertical arrow with end bars (rotated version of fit_width)
            cx = size // 2
            margin_y = 4
            bar_half = 6

            # Top horizontal bar —
            painter.drawLine(cx - bar_half, margin_y, cx + bar_half, margin_y)
            # Bottom horizontal bar —
            painter.drawLine(cx - bar_half, size - margin_y - 1, cx + bar_half, size - margin_y - 1)

            # Vertical line connecting
            painter.drawLine(cx, margin_y, cx, size - margin_y - 1)

            # Top arrow head ^
            painter.drawLine(cx, margin_y, cx - 3, margin_y + 4)
            painter.drawLine(cx, margin_y, cx + 3, margin_y + 4)

            # Bottom arrow head v
            painter.drawLine(cx, size - margin_y - 1, cx - 3, size - margin_y - 5)
            painter.drawLine(cx, size - margin_y - 1, cx + 3, size - margin_y - 5)

        elif icon_type == "single_page":
            # Single document
            painter.drawRect(margin + 2, margin, w - 4, h)
            painter.drawLine(margin + 4, margin + 4, margin + w - 4, margin + 4)
            painter.drawLine(margin + 4, margin + 7, margin + w - 4, margin + 7)
            painter.drawLine(margin + 4, margin + 10, margin + 8, margin + 10)
            
        elif icon_type == "continuous":
            # Multiple lines (scroll)
            for i in range(4):
                y = margin + 2 + i * 3
                painter.drawLine(margin + 2, y, margin + w - 2, y)
        
        elif icon_type == "dropdown":
            # Dropdown arrow triangle ▼
            cx = size // 2
            cy = size // 2
            # Draw filled triangle pointing down
            from PyQt5.QtGui import QPolygon
            from PyQt5.QtCore import QPoint
            painter.setBrush(QColor(100, 100, 100))
            points = [
                QPoint(cx - 4, cy - 2),
                QPoint(cx + 4, cy - 2),
                QPoint(cx, cy + 3)
            ]
            painter.drawPolygon(QPolygon(points))
        
        painter.end()
        return QIcon(pixmap)
    
    def _setup_menu_bar(self):
        """Setup Ribbon-style menu bar: File | View | Cấu hình | Cài đặt | [Run]"""
        # Create custom menu bar widget
        menu_widget = QWidget()
        menu_widget.setFixedHeight(36)
        menu_widget.setStyleSheet("""
            QWidget {
                background-color: #F3F4F6;
                border-bottom: 1px solid #D1D5DB;
            }
        """)
        
        menu_layout = QHBoxLayout(menu_widget)
        menu_layout.setContentsMargins(8, 0, 8, 0)
        menu_layout.setSpacing(0)
        
        # Style for dropdown menu buttons (Tệp tin, Xem, Cài đặt) - NO background ever
        dropdown_btn_style = """
            QPushButton {
                background-color: transparent;
                border: none;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: normal;
                color: #374151;
            }
            QPushButton:hover {
                background-color: transparent;
            }
            QPushButton:pressed {
                background-color: transparent;
            }
            QPushButton::menu-indicator {
                image: none;
                width: 0px;
            }
        """
        
        # Style for toggle button (Chỉnh sửa) - ONLY checked state has background
        toggle_btn_style = """
            QPushButton {
                background-color: transparent;
                border: none;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: normal;
                color: #374151;
            }
            QPushButton:hover {
                background-color: transparent;
            }
            QPushButton:checked {
                background-color: #FFFFFF;
            }
            QPushButton:checked:hover {
                background-color: #FFFFFF;
            }
        """
        
        # Menu style with icon support
        menu_style = """
            QMenu {
                background-color: white;
                border: 1px solid #D1D5DB;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 20px 8px 8px;
            }
            QMenu::item:selected {
                background-color: #E5E7EB;
            }
            QMenu::icon {
                padding-left: 4px;
            }
        """
        
        # === Menu Tệp tin ===
        self.file_menu_btn = HoverMenuButton("Tệp tin")
        self.file_menu_btn.setStyleSheet(dropdown_btn_style)
        file_menu = QMenu(self)
        file_menu.setStyleSheet(menu_style)
        
        # Mở file
        open_action = QAction(self._create_line_icon("open_file"), "Mở file", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)
        
        # Mở thư mục (batch processing)
        open_folder_action = QAction(self._create_line_icon("folder"), "Mở thư mục", self)
        open_folder_action.triggered.connect(self._on_open_folder_batch)
        file_menu.addAction(open_folder_action)
        
        file_menu.addSeparator()
        
        # Hướng dẫn
        help_action = QAction(self._create_line_icon("help"), "Hướng dẫn", self)
        help_action.triggered.connect(self._show_help)
        file_menu.addAction(help_action)
        
        self.file_menu_btn.setMenu(file_menu)
        menu_layout.addWidget(self.file_menu_btn)
        
        # === Menu Xem ===
        self.view_menu_btn = HoverMenuButton("Xem")
        self.view_menu_btn.setStyleSheet(dropdown_btn_style)
        view_menu = QMenu(self)
        view_menu.setStyleSheet(menu_style)
        
        # Zoom in
        zoom_in_action = QAction(self._create_line_icon("zoom_in"), "Zoom in", self)
        zoom_in_action.setShortcut(QKeySequence.ZoomIn)
        zoom_in_action.triggered.connect(self._on_zoom_in)
        view_menu.addAction(zoom_in_action)
        
        # Zoom out
        zoom_out_action = QAction(self._create_line_icon("zoom_out"), "Zoom out", self)
        zoom_out_action.setShortcut(QKeySequence.ZoomOut)
        zoom_out_action.triggered.connect(self._on_zoom_out)
        view_menu.addAction(zoom_out_action)
        
        view_menu.addSeparator()
        
        # Vừa chiều ngang
        fit_width_action = QAction(self._create_line_icon("fit_width"), "Vừa chiều ngang", self)
        fit_width_action.triggered.connect(self._on_fit_width)
        view_menu.addAction(fit_width_action)

        # Vừa chiều cao
        fit_height_action = QAction(self._create_line_icon("fit_height"), "Vừa chiều cao", self)
        fit_height_action.triggered.connect(self._on_fit_height)
        view_menu.addAction(fit_height_action)

        view_menu.addSeparator()

        # Xem 1 trang
        single_page_action = QAction(self._create_line_icon("single_page"), "Xem 1 trang", self)
        single_page_action.triggered.connect(self._on_single_page)
        view_menu.addAction(single_page_action)
        
        # Cuộn liên tục
        continuous_action = QAction(self._create_line_icon("continuous"), "Cuộn liên tục", self)
        continuous_action.triggered.connect(self._on_continuous_scroll)
        view_menu.addAction(continuous_action)
        
        self.view_menu_btn.setMenu(view_menu)
        menu_layout.addWidget(self.view_menu_btn)
        
        # === Menu Chỉnh sửa (Toggle button) ===
        self.config_menu_btn = QPushButton("Chỉnh sửa")
        self.config_menu_btn.setStyleSheet(toggle_btn_style)
        self.config_menu_btn.setCheckable(True)
        self.config_menu_btn.setChecked(True)  # Checked by default
        self.config_menu_btn.clicked.connect(self._toggle_settings)
        menu_layout.addWidget(self.config_menu_btn)
        
        # === Menu Cài đặt ===
        self.settings_menu_btn = QPushButton("Cài đặt")
        self.settings_menu_btn.setStyleSheet(dropdown_btn_style)
        self.settings_menu_btn.clicked.connect(self._show_settings_dialog)
        menu_layout.addWidget(self.settings_menu_btn)

        # Spacer
        menu_layout.addStretch()

        # === Collapse Settings Toolbar Button (before Clean button) ===
        self.collapse_settings_btn = QPushButton()
        self.collapse_settings_btn.setFixedSize(20, 20)
        self.collapse_settings_btn.setToolTip("Thu gọn thanh công cụ")
        self.collapse_settings_btn.setCursor(Qt.PointingHandCursor)
        self._settings_collapsed = False  # Track collapsed state
        self._update_collapse_button_icon()
        self.collapse_settings_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.05);
                border-radius: 4px;
            }
        """)
        self.collapse_settings_btn.clicked.connect(self._on_collapse_settings_clicked)
        menu_layout.addWidget(self.collapse_settings_btn)
        menu_layout.addSpacing(12)  # Spacing before Clean button

        # === Run Button (right side) ===
        self.run_btn = QPushButton("▶ Clean")
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #0043a5;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 20px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1790ff;
            }
            QPushButton:disabled {
                background-color: #D1D5DB;
                color: #9CA3AF;
            }
        """)
        self.run_btn.clicked.connect(self._on_process)
        self.run_btn.setEnabled(False)
        menu_layout.addWidget(self.run_btn)

        # Keyboard shortcut Ctrl+Enter for Clean button
        self.clean_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.clean_shortcut.activated.connect(self._on_clean_shortcut)

        # Note: Ctrl+O is already set on open_action in menu bar

        # Keyboard shortcut Ctrl+Shift+O for Open folder
        self.open_folder_shortcut = QShortcut(QKeySequence("Ctrl+Shift+O"), self)
        self.open_folder_shortcut.activated.connect(self._on_open_folder_batch)

        # Keyboard shortcut Ctrl+Z for Undo zone operations
        self.undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.undo_shortcut.activated.connect(self._on_undo)

        # Cancel button (hidden by default)
        self.cancel_btn = QPushButton("Dừng")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #DC2626;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #B91C1C;
            }
        """)
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.cancel_btn.setVisible(False)
        menu_layout.addWidget(self.cancel_btn)
        
        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(120)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 4px;
                background-color: #D1D5DB;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #0068FF;
                border-radius: 4px;
            }
        """)
        menu_layout.addWidget(self.progress_bar)
        
        # Add to main window (above central widget)
        self.setMenuWidget(menu_widget)

        # Sync collapse state from settings panel
        self._sync_collapse_state_from_settings()

    def _setup_bottom_bar(self, parent_layout):
        """Bottom bar - centered controls"""
        # Create dropdown arrow image
        import tempfile
        import os
        
        arrow_pixmap = QPixmap(12, 12)
        arrow_pixmap.fill(Qt.transparent)
        painter = QPainter(arrow_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(100, 107, 128))
        # Draw triangle pointing down
        from PyQt5.QtGui import QPolygon
        from PyQt5.QtCore import QPoint
        points = [QPoint(2, 3), QPoint(10, 3), QPoint(6, 8)]
        painter.drawPolygon(QPolygon(points))
        painter.end()
        
        # Save to temp file - use forward slashes for CSS url()
        self._arrow_file = os.path.join(tempfile.gettempdir(), "dropdown_arrow.png")
        arrow_pixmap.save(self._arrow_file)
        arrow_url = self._arrow_file.replace("\\", "/")
        
        bottom_bar = QFrame()
        bottom_bar.setFixedHeight(44)
        bottom_bar.setStyleSheet(f"""
            QFrame {{
                background-color: #F3F4F6;
                border-top: 1px solid #D1D5DB;
            }}
            QLabel {{
                color: #374151;
                font-size: 12px;
            }}
            QToolButton {{
                background-color: transparent;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px 10px;
                color: #374151;
                font-size: 12px;
            }}
            QToolButton:hover {{
                background-color: #E5E7EB;
            }}
            QToolButton:disabled {{
                color: #9CA3AF;
            }}
            QSpinBox {{
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px 6px;
                background-color: white;
                font-size: 12px;
            }}
            QComboBox {{
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px 6px;
                padding-right: 24px;
                background-color: white;
                color: #374151;
                font-size: 12px;
            }}
            QComboBox QAbstractItemView {{
                background-color: white;
                color: #374151;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                background-color: white;
                color: #374151;
                padding: 10px 8px 10px 18px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: #93C5FD;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: #93C5FD;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px;
                border: none;
                background: transparent;
            }}
            QComboBox::down-arrow {{
                image: url({arrow_url});
                width: 10px;
                height: 10px;
            }}
        """)
        
        bar_layout = QHBoxLayout(bottom_bar)
        bar_layout.setContentsMargins(12, 0, 12, 0)
        bar_layout.setSpacing(6)

        # Zone count status (left side)
        self.zone_count_label = QLabel("Zone chung: <b>0</b>; Zone riêng: <b>0/0</b>")
        self.zone_count_label.setStyleSheet("""
            QLabel {
                color: #6B7280;
                font-size: 12px;
            }
        """)
        bar_layout.addWidget(self.zone_count_label)

        # Left stretch for centering
        bar_layout.addStretch(1)
        
        # Center controls - bigger buttons
        btn_width = 36
        btn_height = 30
        
        # Previous page
        self.prev_page_btn = QToolButton()
        self.prev_page_btn.setText("◀")
        self.prev_page_btn.setToolTip("Trang trước")
        self.prev_page_btn.setFixedSize(btn_width, btn_height)
        self.prev_page_btn.clicked.connect(self._on_prev_page)
        self.prev_page_btn.setEnabled(False)
        bar_layout.addWidget(self.prev_page_btn)
        
        # Next page
        self.next_page_btn = QToolButton()
        self.next_page_btn.setText("▶")
        self.next_page_btn.setToolTip("Trang sau")
        self.next_page_btn.setFixedSize(btn_width, btn_height)
        self.next_page_btn.clicked.connect(self._on_next_page)
        self.next_page_btn.setEnabled(False)
        bar_layout.addWidget(self.next_page_btn)
        
        bar_layout.addSpacing(6)
        
        # Page number - wider
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.setFixedSize(55, btn_height)
        self.page_spin.setAlignment(Qt.AlignCenter)
        self.page_spin.valueChanged.connect(self._on_page_changed)
        self.page_spin.setEnabled(False)
        self.page_spin.setButtonSymbols(QSpinBox.NoButtons)
        bar_layout.addWidget(self.page_spin)
        
        slash_label = QLabel("/")
        slash_label.setStyleSheet("color: #6B7280; background: transparent; border: none;")
        bar_layout.addWidget(slash_label)

        self.total_pages_label = QLabel("1")
        self.total_pages_label.setStyleSheet("background: transparent; border: none;")
        bar_layout.addWidget(self.total_pages_label)

        # Separator
        sep1 = QLabel("|")
        sep1.setStyleSheet("color: #D1D5DB; padding: 0 6px; background: transparent; border: none;")
        bar_layout.addWidget(sep1)
        
        # View mode - with dropdown arrow (editable for custom popup styling on macOS)
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems(["Liên tiếp", "Một trang"])
        self.view_mode_combo.setCurrentIndex(0)
        self.view_mode_combo.setFixedSize(120, btn_height)
        self.view_mode_combo.setEditable(True)
        self.view_mode_combo.lineEdit().setReadOnly(True)  # Prevent typing
        self.view_mode_combo.lineEdit().setTextMargins(0, 0, 0, 0)
        # Use custom delegate for larger item height
        self.view_mode_combo.setItemDelegate(ComboItemDelegate(self.view_mode_combo))
        # Apply view stylesheet directly for dropdown items
        self.view_mode_combo.view().setStyleSheet("""
            QListView::item {
                padding: 8px 8px 8px 8px;
            }
            QListView::item:hover {
                background-color: #93C5FD;
            }
            QListView::item:selected {
                background-color: #93C5FD;
            }
        """)
        self.view_mode_combo.currentIndexChanged.connect(self._on_view_mode_changed)
        bar_layout.addWidget(self.view_mode_combo)
        
        # Fit width - icon button (generated icon for consistency)
        self.zoom_fit_btn = QToolButton()
        self.zoom_fit_btn.setIcon(self._create_line_icon("fit_width", 30))
        self.zoom_fit_btn.setIconSize(QSize(30, 27))  # Icon fits button
        self.zoom_fit_btn.setToolTip("Vừa chiều rộng trang")
        # Height reduced by 10% (30 -> 27), width kept same (30)
        self.zoom_fit_btn.setFixedSize(30, 27)
        # Gray background with no padding
        self.zoom_fit_btn.setStyleSheet("""
            QToolButton {
                padding: 0px;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                background-color: #E5E7EB;
            }
            QToolButton:hover {
                background-color: #D1D5DB;
            }
        """)
        self.zoom_fit_btn.clicked.connect(self._on_zoom_fit_width)
        bar_layout.addWidget(self.zoom_fit_btn)

        # Fit height - icon button (generated icon for consistency)
        self.zoom_fit_height_btn = QToolButton()
        self.zoom_fit_height_btn.setIcon(self._create_line_icon("fit_height", 30))
        self.zoom_fit_height_btn.setIconSize(QSize(30, 27))
        self.zoom_fit_height_btn.setToolTip("Vừa chiều cao trang")
        self.zoom_fit_height_btn.setFixedSize(30, 27)
        self.zoom_fit_height_btn.setStyleSheet("""
            QToolButton {
                padding: 0px;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                background-color: #E5E7EB;
            }
            QToolButton:hover {
                background-color: #D1D5DB;
            }
        """)
        self.zoom_fit_height_btn.clicked.connect(self._on_zoom_fit_height)
        bar_layout.addWidget(self.zoom_fit_height_btn)

        # Separator
        sep2 = QLabel("|")
        sep2.setStyleSheet("color: #D1D5DB; padding: 0 6px; background: transparent; border: none;")
        bar_layout.addWidget(sep2)
        
        # Zoom dropdown - wider
        self.zoom_combo = QComboBox()
        zoom_levels = [f"{z}%" for z in range(25, 425, 25)]
        self.zoom_combo.addItems(zoom_levels)
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.setFixedSize(100, btn_height)
        self.zoom_combo.setEditable(True)
        self.zoom_combo.lineEdit().setTextMargins(0, 0, 0, 0)
        # Use custom delegate for larger item height
        self.zoom_combo.setItemDelegate(ComboItemDelegate(self.zoom_combo))
        # Apply view stylesheet directly for dropdown items
        self.zoom_combo.view().setStyleSheet("""
            QListView::item {
                padding: 8px 8px 8px 8px;
            }
            QListView::item:hover {
                background-color: #93C5FD;
            }
            QListView::item:selected {
                background-color: #93C5FD;
            }
        """)
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_combo_changed)
        bar_layout.addWidget(self.zoom_combo)
        
        # Zoom out - wider
        self.zoom_out_btn = QToolButton()
        self.zoom_out_btn.setText("-")
        self.zoom_out_btn.setToolTip("Thu nhỏ")
        self.zoom_out_btn.setFixedSize(38, btn_height)
        self.zoom_out_btn.clicked.connect(self._on_zoom_out)
        bar_layout.addWidget(self.zoom_out_btn)
        
        # Zoom in - wider
        self.zoom_in_btn = QToolButton()
        self.zoom_in_btn.setText("+")
        self.zoom_in_btn.setToolTip("Phóng to")
        self.zoom_in_btn.setFixedSize(38, btn_height)
        self.zoom_in_btn.clicked.connect(self._on_zoom_in)
        bar_layout.addWidget(self.zoom_in_btn)

        # Right stretch for centering
        bar_layout.addStretch(1)

        self.bottom_bar = bottom_bar
        parent_layout.addWidget(self.bottom_bar)
    
    def _on_view_mode_changed(self, index):
        """Change view mode"""
        if index == 0:  # Cuộn liên tục
            self.preview.set_view_mode('continuous')
        else:  # Một trang
            self.preview.set_view_mode('single')
            # Set to current page
            current_page = self.page_spin.value() - 1  # 0-based
            self.preview.set_current_page(current_page)
    
    def _toggle_settings(self):
        """Toggle settings toolbar visibility (show/hide both compact and detail)"""
        # Check if any toolbar is visible
        any_visible = self.settings_panel.isVisible() or self.compact_toolbar.isVisible()

        if any_visible:
            # Hide both toolbars
            self.settings_panel.setVisible(False)
            self.compact_toolbar.setVisible(False)
            if hasattr(self, 'config_menu_btn'):
                self.config_menu_btn.setChecked(False)
            if hasattr(self, 'collapse_settings_btn'):
                self.collapse_settings_btn.setVisible(False)
        else:
            # Show based on collapsed state
            if self._settings_collapsed:
                self.compact_toolbar.setVisible(True)
                self.settings_panel.setVisible(False)
            else:
                self.settings_panel.setVisible(True)
                self.compact_toolbar.setVisible(False)
            if hasattr(self, 'config_menu_btn'):
                self.config_menu_btn.setChecked(True)
            if hasattr(self, 'collapse_settings_btn'):
                self.collapse_settings_btn.setVisible(True)

    def _on_collapse_settings_clicked(self):
        """Toggle between compact toolbar and detail settings panel"""
        self._settings_collapsed = not self._settings_collapsed
        self._update_collapse_button_icon()

        # Toggle between compact and detail modes (mutually exclusive)
        if self._settings_collapsed:
            # Switch to Compact mode: show compact_toolbar, hide settings_panel
            self.settings_panel._collapsed = True
            self.settings_panel._sync_to_compact_toolbar()
            self.settings_panel.main_content.setVisible(False)
            self.settings_panel.setMaximumHeight(0)
            self.settings_panel.setVisible(False)
            self.settings_panel._save_collapsed_state()
            self.compact_toolbar.setVisible(True)
        else:
            # Switch to Detail mode: show settings_panel, hide compact_toolbar
            self.settings_panel._collapsed = False
            self.settings_panel.main_content.setVisible(True)
            self.settings_panel.setMaximumHeight(16777215)
            self.settings_panel.setVisible(True)
            self.settings_panel._save_collapsed_state()
            self.compact_toolbar.setVisible(False)

    def _update_collapse_button_icon(self):
        """Update collapse button icon based on state - simple chevron"""
        from PyQt5.QtGui import QIcon, QPixmap, QPainter, QPen, QPainterPath
        from PyQt5.QtCore import Qt

        size = 20
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        color = QColor(107, 114, 128)  # Gray
        cx, cy = size // 2, size // 2

        # Simple chevron icon (smaller)
        painter.setPen(QPen(color, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        path = QPainterPath()

        if self._settings_collapsed:
            # Down chevron (expand)
            path.moveTo(cx - 4, cy - 2)
            path.lineTo(cx, cy + 2)
            path.lineTo(cx + 4, cy - 2)
            self.collapse_settings_btn.setToolTip("Mở rộng thanh công cụ")
        else:
            # Up chevron (collapse)
            path.moveTo(cx - 4, cy + 2)
            path.lineTo(cx, cy - 2)
            path.lineTo(cx + 4, cy + 2)
            self.collapse_settings_btn.setToolTip("Thu gọn thanh công cụ")

        painter.drawPath(path)
        painter.end()

        self.collapse_settings_btn.setIcon(QIcon(pixmap))
        self.collapse_settings_btn.setIconSize(QSize(size, size))

    def _sync_collapse_state_from_settings(self):
        """Sync collapse state from settings panel"""
        if hasattr(self, 'settings_panel'):
            self._settings_collapsed = self.settings_panel._collapsed
            self._update_collapse_button_icon()

    def _set_bottom_bar_visible(self, visible: bool):
        """Show/hide bottom bar controls"""
        if hasattr(self, 'bottom_bar'):
            self.bottom_bar.setVisible(visible)
    
    def _update_ui_state(self):
        """Cập nhật trạng thái UI"""
        has_file = self._pdf_handler is not None
        
        if self._batch_mode:
            # Batch mode - enable run if there are checked files
            has_checked = bool(self.batch_sidebar.get_checked_files())
            self.run_btn.setEnabled(has_checked)
        else:
            # Single file mode
            self.run_btn.setEnabled(has_file)
        
        # Page navigation works the same in both modes
        self.page_spin.setEnabled(has_file)
        
        if has_file:
            current = self.page_spin.value()
            max_loaded = len(self._all_pages)
            self.prev_page_btn.setEnabled(current > 1)
            self.next_page_btn.setEnabled(current < max_loaded)
        else:
            self.prev_page_btn.setEnabled(False)
            self.next_page_btn.setEnabled(False)
    
    def _on_open(self):
        """Mở file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Mở file PDF", self._last_dir,
            "PDF Files (*.pdf);;All Files (*)"
        )
        if file_path:
            # Save file's directory for next time
            file_dir = str(Path(file_path).parent)
            self._last_dir = file_dir
            self._save_last_folder_dir(file_dir)
            self._load_pdf(file_path)
    
    def _on_file_dropped(self, file_path: str):
        """Handle file dropped from preview area"""
        if file_path and file_path.lower().endswith('.pdf'):
            self._load_pdf(file_path)

    def _on_folder_dropped(self, folder_path: str):
        """Handle folder dropped from preview area"""
        if folder_path and os.path.isdir(folder_path):
            self._load_folder(folder_path)

    def _on_files_dropped(self, file_paths: list):
        """Handle multiple PDF files dropped - switch to batch mode"""
        if not file_paths:
            return
        # Filter valid PDF files
        pdf_files = [f for f in file_paths if f.lower().endswith('.pdf') and os.path.isfile(f)]
        if not pdf_files:
            return
        # Sort files
        pdf_files.sort()
        # Find common parent directory
        common_dir = os.path.commonpath(pdf_files)
        if os.path.isfile(common_dir):
            common_dir = os.path.dirname(common_dir)
        self._load_files_batch(pdf_files, common_dir)

    def _load_files_batch(self, pdf_files: list, base_dir: str):
        """Load multiple PDF files for batch processing"""
        # Check if this is a NEW folder (different from current)
        is_new_folder = self._batch_base_dir != base_dir and self._batch_base_dir != ""

        # If opening a DIFFERENT folder, clear the old batch zones file
        if is_new_folder:
            from core.config_manager import get_config_manager
            get_config_manager().clear_batch_zones()

        # Switch to batch mode
        self._batch_mode = True
        self._batch_base_dir = base_dir
        self._batch_files = pdf_files

        # Set batch base dir for crash recovery persistence
        self.preview.set_batch_base_dir(base_dir)
        self.settings_panel.set_batch_base_dir(base_dir)

        # Load persisted zones for this batch (crash recovery)
        self.preview.load_persisted_zones(base_dir)
        self.settings_panel.load_persisted_custom_zones(base_dir)

        # Zones persist across folders (saved in config)
        # No longer reset zones when opening new folder

        # Always default output to source folder when opening new batch
        output_dir = base_dir
        self._batch_output_dir = output_dir

        # Update settings panel output path to source folder
        self.settings_panel.set_output_path(output_dir)

        # Get filename pattern from settings
        settings = self.settings_panel.get_settings()
        filename_pattern = settings.get('filename_pattern', '{gốc}_clean.pdf')

        # Show batch sidebar with file list
        self._batch_current_index = 0
        self._is_first_file_in_batch = True  # First file in new batch gets fit width
        self.batch_sidebar.set_files(pdf_files, base_dir)
        self.batch_sidebar.setVisible(True)
        # Apply saved sidebar width
        self._apply_saved_sidebar_width()
        # Show search box in compact toolbar and sync width (if sidebar not collapsed)
        if not self.batch_sidebar.is_collapsed():
            self.compact_toolbar.set_search_visible(True)
            # Delay width sync until after layout is complete
            QTimer.singleShot(0, self._sync_search_width)


        # Enable batch mode in preview
        self.preview.set_batch_mode(True, 0, len(pdf_files))

        # Update UI
        self.setWindowTitle(f"Xóa Ghim PDF (5S) - {len(pdf_files)} files")

        # Load first file (will be triggered by file_selected signal)
        self._update_ui_state()

    def _on_open_folder_batch(self):
        """Mở thư mục để xử lý batch"""
        folder_path = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục chứa file PDF", self._last_dir
        )
        if folder_path:
            # Save parent directory for next time
            parent_dir = os.path.dirname(folder_path)
            self._last_dir = parent_dir
            self._save_last_folder_dir(parent_dir)
            self._load_folder(folder_path)
    
    def _load_folder(self, folder_path: str):
        """Load thư mục cho batch processing"""
        # Scan for PDF files recursively
        pdf_files = []
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith('.pdf'):
                    pdf_files.append(os.path.join(root, file))

        if not pdf_files:
            QMessageBox.warning(self, "Không tìm thấy file",
                              "Không tìm thấy file PDF trong thư mục đã chọn.")
            return

        # Sort files
        pdf_files.sort()

        # Check if this is a NEW folder (different from current)
        is_new_folder = self._batch_base_dir != folder_path and self._batch_base_dir != ""

        # If opening a DIFFERENT folder, clear the old batch zones file
        if is_new_folder:
            from core.config_manager import get_config_manager
            get_config_manager().clear_batch_zones()

        # Switch to batch mode
        self._batch_mode = True
        self._batch_base_dir = folder_path
        self._batch_files = pdf_files

        # Set batch base dir for crash recovery persistence
        self.preview.set_batch_base_dir(folder_path)
        self.settings_panel.set_batch_base_dir(folder_path)

        # Load persisted zones for this batch (crash recovery)
        self.preview.load_persisted_zones(folder_path)
        self.settings_panel.load_persisted_custom_zones(folder_path)

        # Zones persist across folders (saved in config)
        # No longer reset zones when opening new folder

        # Always default output to source folder when opening new batch
        output_dir = folder_path
        self._batch_output_dir = output_dir

        # Update settings panel output path to source folder
        self.settings_panel.set_output_path(output_dir)

        # Get filename pattern from settings
        settings = self.settings_panel.get_settings()
        filename_pattern = settings.get('filename_pattern', '{gốc}_clean.pdf')

        # Show batch sidebar with file list
        self._batch_current_index = 0
        self._is_first_file_in_batch = True  # First file in new batch gets fit width
        self.batch_sidebar.set_files(pdf_files, folder_path)
        self.batch_sidebar.setVisible(True)
        # Apply saved sidebar width
        self._apply_saved_sidebar_width()
        # Show search box in compact toolbar and sync width (if sidebar not collapsed)
        if not self.batch_sidebar.is_collapsed():
            self.compact_toolbar.set_search_visible(True)
            # Delay width sync until after layout is complete
            QTimer.singleShot(0, self._sync_search_width)

        # Enable batch mode in preview
        self.preview.set_batch_mode(True, 0, len(pdf_files))

        # Update UI
        self.setWindowTitle(f"Xóa Ghim PDF (5S) - {folder_path} ({len(pdf_files)} files)")

        # Load first file (will be triggered by file_selected signal)
        self._update_ui_state()
    
    def _on_batch_file_selected(self, file_path: str):
        """When file selected in batch mode file list"""
        # Load the selected file using the same method as single mode
        self._load_pdf(file_path)

    def _on_sidebar_file_selected(self, file_path: str, original_idx: int):
        """Handle file selection from sidebar"""
        # Save zones from current file before switching
        self.preview.save_per_file_zones()
        self.settings_panel.save_per_file_custom_zones()

        self._batch_current_index = original_idx
        # Clear custom zones with 'none' filter (Tự do) - will be restored from per-file storage
        self.settings_panel.clear_custom_zones_with_free_filter()
        self._load_pdf(file_path)

        # Restore zones for this file
        self.settings_panel.load_per_file_custom_zones(file_path)
        self.preview.load_per_file_zones(file_path)
        self.preview.set_file_index(original_idx, len(self._batch_files))

        # Update zone counts display
        self._update_zone_counts()

    def _on_sidebar_selection_changed(self, checked_files: List[str]):
        """Handle checkbox selection change in sidebar"""
        self._update_ui_state()

    def _on_sidebar_collapsed_changed(self, collapsed: bool):
        """Handle sidebar collapse/expand"""
        if collapsed:
            # Set splitter to collapsed width (40px)
            self.preview_splitter.setSizes([40, self.preview_splitter.width() - 40])
            # Hide search box in compact toolbar
            self.compact_toolbar.set_search_visible(False)
        else:
            # Restore to default expanded width
            self.preview_splitter.setSizes([200, self.preview_splitter.width() - 200])
            # Show search box in compact toolbar and sync width
            self.compact_toolbar.set_search_visible(True)
            QTimer.singleShot(0, self._sync_search_width)

    def _sync_search_width(self):
        """Sync search box width with actual sidebar width"""
        if self.batch_sidebar.isVisible() and not self.batch_sidebar.is_collapsed():
            sidebar_width = self.preview_splitter.sizes()[0]
            if sidebar_width > 0:
                self.compact_toolbar.set_search_width(sidebar_width)

    def _on_splitter_moved(self, pos: int, index: int):
        """Handle splitter drag - enforce minimum sidebar width and sync search width"""
        if not self.batch_sidebar.isVisible():
            return
        sizes = self.preview_splitter.sizes()
        sidebar_width = sizes[0]
        min_width = BatchSidebar.COLLAPSED_WIDTH if self.batch_sidebar.is_collapsed() else BatchSidebar.MIN_WIDTH
        if sidebar_width < min_width:
            # Force minimum width
            self.preview_splitter.setSizes([min_width, self.preview_splitter.width() - min_width])
            sidebar_width = min_width
        # Sync search box width with sidebar
        if not self.batch_sidebar.is_collapsed():
            self.compact_toolbar.set_search_width(sidebar_width)
            # Update saved sidebar width for persistence
            self._saved_sidebar_width = sidebar_width
            # Save to config immediately
            from core.config_manager import get_config_manager
            ui_config = get_config_manager().get_ui_config()
            ui_config['sidebar_width'] = sidebar_width
            get_config_manager().save_ui_config(ui_config)

    def _on_prev_file(self):
        """Navigate to previous file in batch mode"""
        if self._batch_current_index > 0:
            # Save zones from current file before switching
            self.preview.save_per_file_zones()
            self.settings_panel.save_per_file_custom_zones()

            self._batch_current_index -= 1
            file_path = self._batch_files[self._batch_current_index]
            self.batch_sidebar.select_by_original_index(self._batch_current_index)
            # Clear custom zones with 'none' filter (Tự do) - will be restored from per-file storage
            self.settings_panel.clear_custom_zones_with_free_filter()
            self._load_pdf(file_path)

            # Restore zones for this file
            self.settings_panel.load_per_file_custom_zones(file_path)
            self.preview.load_per_file_zones(file_path)
            self.preview.set_file_index(self._batch_current_index, len(self._batch_files))

            # Update zone counts display
            self._update_zone_counts()

    def _on_next_file(self):
        """Navigate to next file in batch mode"""
        if self._batch_current_index < len(self._batch_files) - 1:
            # Save zones from current file before switching
            self.preview.save_per_file_zones()
            self.settings_panel.save_per_file_custom_zones()

            self._batch_current_index += 1
            file_path = self._batch_files[self._batch_current_index]
            self.batch_sidebar.select_by_original_index(self._batch_current_index)
            # Clear custom zones with 'none' filter (Tự do) - will be restored from per-file storage
            self.settings_panel.clear_custom_zones_with_free_filter()
            self._load_pdf(file_path)

            # Restore zones for this file
            self.settings_panel.load_per_file_custom_zones(file_path)
            self.preview.load_per_file_zones(file_path)
            self.preview.set_file_index(self._batch_current_index, len(self._batch_files))

            # Update zone counts display
            self._update_zone_counts()

    def _on_close_file(self):
        """Close currently opened file or folder"""
        if self._batch_mode:
            # Close batch mode
            self._batch_mode = False
            self._batch_base_dir = ""
            self._batch_output_dir = ""
            self._batch_files = []
            self._batch_current_index = 0
            self._is_first_file_in_batch = True  # Reset for next batch

            # Clear per-file zone storage in MEMORY only
            # DON'T clear disk file - zones will be restored when reopening same folder
            self.preview.clear_per_file_zones()
            self.settings_panel.clear_per_file_custom_zones()
            # NOTE: Removed clear_batch_zones() call - zones persist on disk
            # They will be overwritten when opening a different folder

            # Hide sidebar and disable batch mode in preview
            self.batch_sidebar.setVisible(False)
            self.compact_toolbar.set_search_visible(False)
            self.compact_toolbar.clear_search()
            self.preview.set_batch_mode(False)

            self.setWindowTitle("Xóa Ghim PDF (5S)")
        
        # Close current file (applies to both modes)
        if self._pdf_handler:
            self._pdf_handler.close()
            self._pdf_handler = None
        
        self._current_file_path = None
        self._all_pages = []
        
        # Clear draw mode (remove override cursor)
        self.preview.set_draw_mode(None)
        self.settings_panel.set_draw_mode(None)

        # Clear preview
        self.preview.set_pages([])
        self.preview.clear_file_paths()

        # Reset zoom to 100% for placeholder icons
        self.zoom_combo.blockSignals(True)
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.blockSignals(False)

        # Reset page navigation
        self.page_spin.setMaximum(1)
        self.page_spin.setValue(1)
        self.total_pages_label.setText("0")
        
        self._update_ui_state()
    
    def _load_pdf(self, file_path: str):
        """Load file PDF"""
        try:
            self.statusBar().showMessage("Đang tải PDF...")
            QApplication.processEvents()

            if self._pdf_handler:
                self._pdf_handler.close()

            self._pdf_handler = PDFHandler(file_path)
            self._current_file_path = file_path

            # Load pages
            num_pages = min(self._pdf_handler.page_count, self.MAX_PREVIEW_PAGES)
            self._all_pages = []

            for i in range(num_pages):
                self.statusBar().showMessage(f"Đang tải trang {i+1}/{num_pages}...")
                QApplication.processEvents()

                img = self._pdf_handler.render_page(i, dpi=120)
                if img is not None:
                    self._all_pages.append(img)

            # Update page navigation
            self.page_spin.setMaximum(self._pdf_handler.page_count)
            self.page_spin.setValue(1)
            self.total_pages_label.setText(str(self._pdf_handler.page_count))

            # Set output path and calculate dest_path
            source_path = Path(file_path)
            if self._batch_mode:
                # In batch mode: use batch output dir, don't reset settings
                output_dir = self._batch_output_dir or str(source_path.parent)
                settings = self.settings_panel.get_settings()
                pattern = settings.get('filename_pattern', '{gốc}_clean.pdf')
                output_name = pattern.replace('{gốc}', source_path.stem)
                dest_path = Path(output_dir) / output_name
            else:
                # Single file mode: check if folder changed
                file_folder = str(source_path.parent)
                # Zones persist across folders (saved in config)
                # No longer reset zones when opening file from different folder
                # Update current folder
                self._batch_base_dir = file_folder
                # Set output path to file's parent
                output_dir = file_folder
                self.settings_panel.set_output_path(output_dir)
                dest_path = source_path.parent / f"{source_path.stem}_clean{source_path.suffix}"

            # Update preview panel titles with file paths
            self.preview.set_file_paths(str(file_path), str(dest_path))
            
            # Set pages and track current file for per-file zone storage
            self.preview.set_pages(self._all_pages)
            self.preview.set_current_file_path(str(file_path))
            self.settings_panel.set_current_file_path(str(file_path))
            zones = self.settings_panel.get_zones()
            self.preview.set_zones(zones)

            # Apply text protection options (để vẽ bounding boxes ngay khi mở file)
            text_protection_opts = self.settings_panel.get_text_protection_options()
            self.preview.set_text_protection(text_protection_opts)

            self._update_ui_state()
            self.statusBar().showMessage(f"Đã mở: {file_path}")

            # Reset to first page
            self.preview.set_current_page(0)  # Scroll về trang đầu

            # Only fit width for first file in batch, otherwise preserve zoom
            if self._is_first_file_in_batch:
                self._user_zoomed = False
                # Defer fit width đến sau khi layout hoàn tất
                # Dùng 100ms delay để đảm bảo viewport đã có kích thước đúng
                QTimer.singleShot(100, self._fit_first_page_width)
            
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể mở file:\n{e}")
    
    def _fit_first_page_width(self):
        """Apply saved zoom or fit width for first page - called after layout update"""
        if self._all_pages:
            # Use saved zoom if available, otherwise fit to width
            if hasattr(self, '_saved_zoom_percent') and self._saved_zoom_percent > 0:
                zoom = self._saved_zoom_percent / 100.0
                self.preview.set_zoom(zoom)
                self._user_zoomed = True  # Preserve this zoom for subsequent files
            else:
                # scroll_to_page=True để scroll đến trang đầu tiên
                self.preview.zoom_fit_width(0, scroll_to_page=True)
            self._update_zoom_combo()
            # Mark first file processed - subsequent files preserve zoom
            self._is_first_file_in_batch = False

    def _on_prev_page(self):
        if self.page_spin.value() > 1:
            self.page_spin.setValue(self.page_spin.value() - 1)

    def _on_next_page(self):
        max_loaded = len(self._all_pages)
        if self.page_spin.value() < max_loaded:
            self.page_spin.setValue(self.page_spin.value() + 1)
    
    def _on_page_changed(self, value):
        """Handle page number change"""
        if not self._pdf_handler:
            return

        # Validate: giới hạn trong phạm vi trang đã load
        max_loaded = len(self._all_pages)
        if max_loaded == 0:
            return

        # Clamp value to valid range
        clamped_value = max(1, min(value, max_loaded))
        if clamped_value != value:
            # Block signals to avoid recursion, then update spinbox
            self.page_spin.blockSignals(True)
            self.page_spin.setValue(clamped_value)
            self.page_spin.blockSignals(False)
            value = clamped_value

        # Update preview - works for both continuous and single page mode
        self.preview.set_current_page(value - 1)  # 0-based index

        # Update prev/next button states
        self.prev_page_btn.setEnabled(value > 1)
        self.next_page_btn.setEnabled(value < max_loaded)

    def _on_page_changed_from_scroll(self, page_index: int):
        """Handle page change from scroll - update spinbox without triggering scroll"""
        if not self._pdf_handler:
            return

        max_loaded = len(self._all_pages)
        if max_loaded == 0:
            return

        # Convert 0-based index to 1-based page number
        page_num = page_index + 1
        page_num = max(1, min(page_num, max_loaded))

        # Update spinbox without triggering _on_page_changed
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(page_num)
        self.page_spin.blockSignals(False)

        # Update prev/next button states
        self.prev_page_btn.setEnabled(page_num > 1)
        self.next_page_btn.setEnabled(page_num < max_loaded)

    def _on_zoom_in(self):
        """Zoom in to next preset level"""
        self._user_zoomed = True  # Track manual zoom
        zoom_levels = list(range(25, 425, 25))  # 25, 50, 75, ... 400
        current = int(self.preview.before_panel.view._zoom * 100)

        # Find next level
        for level in zoom_levels:
            if level > current:
                self.preview.set_zoom(level / 100.0)
                self._update_zoom_combo()
                return

        # Already at max
        self.preview.set_zoom(4.0)
        self._update_zoom_combo()
    
    def _on_zoom_out(self):
        """Zoom out to previous preset level"""
        self._user_zoomed = True  # Track manual zoom
        zoom_levels = list(range(25, 425, 25))  # 25, 50, 75, ... 400
        current = int(self.preview.before_panel.view._zoom * 100)

        # Find previous level
        for level in reversed(zoom_levels):
            if level < current:
                self.preview.set_zoom(level / 100.0)
                self._update_zoom_combo()
                return

        # Already at min
        self.preview.set_zoom(0.25)
        self._update_zoom_combo()
    
    def _on_zoom_fit_width(self):
        """Fit chiều rộng trang hiện tại"""
        self._user_zoomed = False  # Cho phép auto-fit khi resize
        self.preview.zoom_fit_width()  # Fit trang hiện tại (không truyền param)
        self._update_zoom_combo()

    def _on_zoom_fit_height(self):
        """Fit chiều cao trang hiện tại"""
        self._user_zoomed = True  # Không auto-fit khi resize
        self.preview.zoom_fit_height()  # Fit theo chiều cao
        self._update_zoom_combo()

    def _on_zoom_combo_changed(self, text):
        try:
            zoom = int(text.replace('%', '')) / 100.0
            if 0.1 <= zoom <= 5.0:
                self._user_zoomed = True  # Track manual zoom
                self.preview.set_zoom(zoom)
                self._saved_zoom_percent = int(zoom * 100)
                # Save to config immediately
                from core.config_manager import get_config_manager
                ui_config = get_config_manager().get_ui_config()
                ui_config['last_zoom_percent'] = self._saved_zoom_percent
                get_config_manager().save_ui_config(ui_config)
        except:
            pass
    
    def _update_zoom_combo(self):
        try:
            zoom = self.preview.before_panel.view._zoom
            self.zoom_combo.blockSignals(True)
            self.zoom_combo.setCurrentText(f"{int(zoom * 100)}%")
            self.zoom_combo.blockSignals(False)
            # Update saved zoom for persistence when opening new files
            self._saved_zoom_percent = int(zoom * 100)
            # Save to config immediately
            from core.config_manager import get_config_manager
            ui_config = get_config_manager().get_ui_config()
            ui_config['last_zoom_percent'] = self._saved_zoom_percent
            get_config_manager().save_ui_config(ui_config)
        except:
            pass
    
    def _on_zones_changed(self, zones: List[Zone]):
        self.preview.set_zones(zones)
        self._update_zone_counts()

    def _update_zone_counts(self):
        """Update zone count display in bottom bar

        Zone chung: x (preset zones + custom zones with page_filter != 'none')
        Zone riêng: y/z (y = current file, z = total all files)
        """
        # Count Zone chung (global, counted once)
        zone_chung = 0
        # Preset zones (corners, edges)
        for zone in self.settings_panel._zones.values():
            if zone.enabled:
                zone_chung += 1
        # Custom zones with page_filter != 'none'
        for zone in self.settings_panel._custom_zones.values():
            if zone.enabled and getattr(zone, 'page_filter', 'all') != 'none':
                zone_chung += 1

        # Count Zone riêng for current file (unique custom zone IDs, not corner_*/margin_*)
        zone_rieng_file = 0
        per_page_zones = getattr(self.preview.before_panel, '_per_page_zones', {})
        unique_zone_ids = set()
        for page_zones in per_page_zones.values():
            for zone_id in page_zones.keys():
                if not zone_id.startswith('corner_') and not zone_id.startswith('margin_'):
                    unique_zone_ids.add(zone_id)
        zone_rieng_file = len(unique_zone_ids)

        # Count total Zone riêng across all files
        zone_rieng_total = zone_rieng_file  # Start with current file
        per_file_zones = getattr(self.preview.before_panel, '_per_file_zones', {})
        current_file = getattr(self, '_current_file_path', '')
        for file_path, file_zones in per_file_zones.items():
            if file_path == current_file:
                continue  # Already counted above
            file_unique_ids = set()
            for page_zones in file_zones.values():
                for zone_id in page_zones.keys():
                    if not zone_id.startswith('corner_') and not zone_id.startswith('margin_'):
                        file_unique_ids.add(zone_id)
            zone_rieng_total += len(file_unique_ids)

        # Update bottom bar label (bold numbers)
        self.zone_count_label.setText(
            f"Zone chung: <b>{zone_chung}</b>; Zone riêng: <b>{zone_rieng_file}/{zone_rieng_total}</b>"
        )

    def _on_settings_changed(self, settings: dict):
        pass

    def _on_text_protection_changed(self, options):
        """Handle text protection settings change"""
        self.preview.set_text_protection(options)

    def _on_draw_mode_changed(self, mode):
        """Handle draw mode toggle from settings panel (mode: 'remove', 'protect', or None)"""
        self._current_draw_mode = mode
        self.preview.set_draw_mode(mode)

    def _on_rect_drawn_from_preview(self, x: float, y: float, w: float, h: float, mode: str, page_idx: int):
        """Handle rectangle drawn on preview - create custom zone on specific page"""
        self.settings_panel.add_custom_zone_from_rect(x, y, w, h, mode, page_idx)
        # Record undo action for the newly added zone
        # Get the last added zone id from settings panel
        zones = self.settings_panel.get_zones()
        if zones:
            last_zone = zones[-1]  # Most recently added
            zone_data = (last_zone.x, last_zone.y, last_zone.width, last_zone.height)
            zone_type = getattr(last_zone, 'zone_type', 'remove')
            self.preview.record_zone_add(last_zone.id, page_idx, zone_data, zone_type)
        # Immediate persist
        self._persist_all_zones()

    def _on_output_settings_changed(self, output_dir: str, filename_pattern: str):
        """Handle output settings change"""
        if self._batch_mode:
            self._batch_output_dir = output_dir if output_dir else self._batch_base_dir
            # Output settings stored for use during processing (sidebar shows source files only)

    def _on_page_filter_changed(self, filter_mode: str):
        """Handle page filter change from settings"""
        self.preview.set_page_filter(filter_mode)

    def _on_zones_reset(self, scope: str = 'folder', reset_type: str = 'manual'):
        """Handle zones reset from settings - clear zones based on scope

        Args:
            scope: 'file' for current file only, 'folder' for entire folder
            reset_type: 'manual', 'rieng', 'chung', or 'all'
        """
        if reset_type == 'rieng':
            if scope == 'file':
                # Clear Zone riêng for current file only (keep Zone chung)
                self.preview.clear_zone_rieng()
                # Save immediately
                if hasattr(self, '_batch_mode') and self._batch_mode:
                    self.preview.save_per_file_zones()
            else:
                # Clear Zone riêng for all files in folder
                self.preview.before_panel.clear_per_file_zones()
                self.preview.clear_zone_rieng()
                # Save immediately (empty)
                if hasattr(self, '_batch_mode') and self._batch_mode:
                    self.preview.save_per_file_zones()
        elif reset_type == 'chung':
            # Clear Zone chung for all pages (keep Zone riêng)
            self.preview.clear_zone_chung()
        elif scope == 'file':
            # Clear zones only for current file
            self.preview.clear_all_zones()
        else:
            # Clear all zones (folder scope)
            self.preview.clear_all_zones()

        # Persist zone removal to batch_zones.json
        if hasattr(self, '_batch_mode') and self._batch_mode:
            self.preview.save_per_file_zones()
            self.settings_panel.save_per_file_custom_zones()

        # Update zone counts display
        self._update_zone_counts()

    def _on_zone_changed_from_preview(self, zone_id: str, x: float, y: float, w: float, h: float,
                                       w_px: int = 0, h_px: int = 0):
        self.settings_panel.update_zone_from_preview(zone_id, x, y, w, h, w_px, h_px)
        # Immediate persist
        self._persist_all_zones()

    def _on_zone_drag_save_requested(self):
        """Trigger immediate save after zone drag ends (crash recovery)"""
        self._persist_all_zones()

    def _persist_all_zones(self):
        """Persist all zones immediately to memory and disk (crash recovery)"""
        # Save Zone chung (preset + custom with filter != 'none') to config.json
        self.settings_panel._save_zone_config()
        # Save Zone riêng (Tự do zones) to batch_zones.json (if in batch mode)
        if hasattr(self, '_batch_mode') and self._batch_mode:
            self.preview.save_per_file_zones()
            self.settings_panel.save_per_file_custom_zones()

    def _on_zone_selected_from_preview(self, zone_id: str):
        """Khi click vào zone trong preview → chuyển filter theo zone"""
        # Tìm zone và lấy page_filter của nó
        zone = self.settings_panel.get_zone_by_id(zone_id)
        if zone and hasattr(zone, 'page_filter'):
            self.settings_panel.set_filter(zone.page_filter)
    
    def _on_zone_delete_from_preview(self, zone_id: str):
        """Handle zone delete request from preview"""
        # Record undo action before deletion
        per_page_zones = self.preview.before_panel._per_page_zones
        # Get zone data from first page that has it
        zone_data = None
        zone_type = 'remove'
        for page_idx in per_page_zones:
            if zone_id in per_page_zones[page_idx]:
                zone_data = per_page_zones[page_idx][zone_id]
                # Get zone type from _zones
                for z in self.preview._zones:
                    if z.id == zone_id:
                        zone_type = getattr(z, 'zone_type', 'remove')
                        break
                break
        if zone_data:
            self.preview.record_zone_delete(zone_id, -1, zone_data, zone_type)

        # Remove zone from _per_page_zones directly (for immediate visual update)
        for page_idx in list(per_page_zones.keys()):
            if zone_id in per_page_zones[page_idx]:
                del per_page_zones[page_idx][zone_id]

        # Force visual update
        self.preview.before_panel.scene.update()

        self.settings_panel.delete_custom_zone(zone_id)
        # Refresh preview with updated zones
        zones = self.settings_panel.get_zones()
        self.preview.set_zones(zones)
        # Persist zone removal to batch_zones.json (Tự do zones)
        if hasattr(self, '_batch_mode') and self._batch_mode:
            self.preview.save_per_file_zones()
        # Update zone counts
        self._update_zone_counts()

    def _on_clean_shortcut(self):
        """Handle Ctrl+Enter shortcut - only trigger if button is enabled"""
        if self.run_btn.isEnabled() and self.run_btn.isVisible():
            self._on_process()

    def _on_undo(self):
        """Handle Ctrl+Z shortcut - undo zone operations"""
        if self.preview.undo():
            self.statusBar().showMessage("Đã hoàn tác", 2000)

    def _on_undo_zone_removed(self, zone_id: str):
        """Handle undo zone removed - sync with settings_panel"""
        self.settings_panel.delete_custom_zone(zone_id)
        # Immediate persist
        self._persist_all_zones()

    def _on_undo_zone_restored(self, zone_id: str, x: float, y: float, w: float, h: float, zone_type: str):
        """Handle undo zone restored - sync with settings_panel"""
        self.settings_panel.restore_custom_zone(zone_id, x, y, w, h, zone_type)
        # Immediate persist
        self._persist_all_zones()

    def _on_preset_zone_toggled(self, zone_id: str, enabled: bool, zone_data: tuple):
        """Handle preset zone (corner/edge) toggle - record undo"""
        if enabled:
            # Zone was added (enabled) -> record add action
            self.preview.record_zone_add(zone_id, -1, zone_data, 'remove')
        else:
            # Zone was removed (disabled) -> record delete action
            self.preview.record_zone_delete(zone_id, -1, zone_data, 'remove')
        # Immediate persist
        self._persist_all_zones()

    def _on_undo_preset_zone_toggled(self, zone_id: str, enabled: bool):
        """Handle undo for preset zone toggle - toggle zone in settings_panel"""
        self.settings_panel.toggle_preset_zone(zone_id, enabled)
        # Immediate persist
        self._persist_all_zones()

    def _on_process(self):
        """Bắt đầu xử lý"""
        if self._batch_mode:
            self._on_process_batch()
        else:
            self._on_process_single()
    
    def _on_process_single(self):
        """Xử lý single file"""
        if not self._pdf_handler:
            return

        settings = self.settings_panel.get_settings()

        output_dir = settings.get('output_path', '')
        if not output_dir:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng chọn thư mục đầu ra!")
            return

        input_name = Path(self._pdf_handler.pdf_path).stem
        pattern = settings.get('filename_pattern', '{gốc}_clean.pdf')
        output_name = pattern.replace('{gốc}', input_name)
        output_path = os.path.join(output_dir, output_name)

        # Check if destination is same as source (prevent overwriting original)
        source_path = os.path.normpath(os.path.abspath(self._pdf_handler.pdf_path))
        dest_path = os.path.normpath(os.path.abspath(output_path))
        if source_path == dest_path:
            QMessageBox.warning(
                self, "Không thể ghi đè file gốc",
                "File đích trùng với file gốc.\n\n"
                "Vui lòng chọn thư mục đầu ra khác hoặc đổi tên file đầu ra."
            )
            return

        if os.path.exists(output_path):
            if not self._show_overwrite_dialog(output_path):
                return

        # Get zones from preview (with user-modified coordinates)
        zones = self.preview.get_zones_for_processing()

        # Create zone_getter for per-page zone support
        zone_getter = self.preview.get_zones_for_page_processing

        # Show progress dialog like batch mode
        self._show_single_progress_dialog(
            self._pdf_handler.pdf_path, output_path, zones, settings, zone_getter
        )
    
    def _on_process_batch(self):
        """Xử lý batch files"""
        checked_files = self.batch_sidebar.get_checked_files()
        if not checked_files:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng chọn ít nhất một file để xử lý!")
            return
        
        settings = self.settings_panel.get_settings()
        
        output_dir = settings.get('output_path', '')
        if not output_dir:
            output_dir = self._batch_base_dir
        
        # Check for existing files and same-as-source files
        existing_files = []
        same_as_source = []
        pattern = settings.get('filename_pattern', '{gốc}_clean.pdf')
        for f in checked_files:
            rel_path = os.path.relpath(f, self._batch_base_dir)
            name, _ = os.path.splitext(rel_path)
            output_name = pattern.replace('{gốc}', name)
            output_path = os.path.join(output_dir, output_name)
            # Check if destination == source
            source_abs = os.path.normpath(os.path.abspath(f))
            dest_abs = os.path.normpath(os.path.abspath(output_path))
            if source_abs == dest_abs:
                same_as_source.append(os.path.basename(f))
            elif os.path.exists(output_path):
                existing_files.append(output_path)

        # Prevent overwriting source files
        if same_as_source:
            file_list = "\n".join(same_as_source[:5])
            if len(same_as_source) > 5:
                file_list += f"\n... và {len(same_as_source) - 5} file khác"
            QMessageBox.warning(
                self, "Không thể ghi đè file gốc",
                f"Có {len(same_as_source)} file đích trùng với file gốc:\n\n"
                f"{file_list}\n\n"
                "Vui lòng chọn thư mục đầu ra khác hoặc đổi tên file đầu ra."
            )
            return

        if existing_files:
            if not self._show_batch_overwrite_dialog(len(existing_files)):
                return

        # Show confirmation dialog with file counts
        checked_count, total_count = self.batch_sidebar.get_file_count()
        if not self._show_batch_confirm_dialog(checked_count, total_count):
            return

        # Get zones from preview (with user-modified coordinates)
        zones = self.preview.get_zones_for_processing()

        # Show batch progress dialog
        self._show_batch_progress_dialog(checked_files, output_dir, zones, settings)
    
    def _on_cancel(self):
        if self._process_thread:
            self._process_thread.cancel()
    
    def _on_process_progress(self, current: int, total: int):
        percent = int(current * 100 / total)
        self.progress_bar.setValue(percent)
        self.progress_bar.setFormat(f"{current}/{total}")
    
    def _on_process_finished(self, success: bool, message: str):
        self.run_btn.setVisible(True)
        self.cancel_btn.setVisible(False)
        self.progress_bar.setVisible(False)
        
        if success:
            self._result_path = message
            
            input_size = os.path.getsize(self._pdf_handler.pdf_path) / (1024 * 1024)
            output_size = os.path.getsize(message) / (1024 * 1024)
            
            self.statusBar().showMessage(
                f"✅ Hoàn thành! {input_size:.1f}MB → {output_size:.1f}MB"
            )
            
            # Show custom completion dialog
            self._show_completion_dialog(message, input_size, output_size)
        else:
            self.statusBar().showMessage(f"❌ {message}")
            if message != "Đã hủy":
                QMessageBox.critical(self, "Lỗi", f"Lỗi khi xử lý:\n{message}")
        
        self._process_thread = None

    def _show_single_progress_dialog(self, input_path: str, output_path: str,
                                     zones: List[Zone], settings: dict, zone_getter=None):
        """Show progress dialog for single file processing"""
        self._single_dialog = QDialog(self)
        self._single_dialog.setWindowTitle("Đang xử lý...")
        self._single_dialog.setMinimumSize(500, 200)
        self._single_dialog.setModal(True)
        self._single_dialog.setStyleSheet("""
            QDialog { background-color: white; }
            QLabel { font-size: 13px; font-weight: normal; }
            QProgressBar {
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                text-align: center;
                height: 24px;
            }
            QProgressBar::chunk {
                background-color: #3B82F6;
                border-radius: 3px;
            }
            QPushButton {
                padding: 8px 16px; border-radius: 4px; font-size: 13px;
                min-width: 80px; background-color: #E5E7EB;
                color: #374151; border: 1px solid #D1D5DB;
            }
            QPushButton:hover { background-color: #D1D5DB; }
        """)

        layout = QVBoxLayout(self._single_dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # File label
        filename = os.path.basename(input_path)
        self._single_file_label = QLabel(f"File: {filename}")
        layout.addWidget(self._single_file_label)

        # Progress bar
        self._single_progress = QProgressBar()
        self._single_progress.setMaximum(100)
        self._single_progress.setValue(0)
        layout.addWidget(self._single_progress)

        # Page label
        self._single_page_label = QLabel("Đang chuẩn bị...")
        layout.addWidget(self._single_page_label)

        # Timer label
        self._single_time_label = QLabel("Thời gian: 00:00:00")
        layout.addWidget(self._single_time_label)

        layout.addStretch()

        # Cancel button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Hủy")
        cancel_btn.clicked.connect(self._on_single_cancel)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        # Timer for elapsed time
        self._single_start_time = time.time()
        self._single_timer = QTimer()
        self._single_timer.timeout.connect(self._update_single_timer)
        self._single_timer.start(1000)

        # Start processing (with per-page zone support)
        self._process_thread = ProcessThread(input_path, output_path, zones, settings, zone_getter)
        self._process_thread.progress.connect(self._on_single_progress)
        self._process_thread.finished.connect(self._on_single_finished)

        self._single_output_path = output_path
        self._process_thread.start()
        self._single_dialog.exec_()

    def _update_single_timer(self):
        """Update elapsed time display"""
        elapsed = int(time.time() - self._single_start_time)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        self._single_time_label.setText(f"Thời gian: {h:02d}:{m:02d}:{s:02d}")

    def _on_single_progress(self, current: int, total: int):
        """Update single file progress"""
        percent = int(current * 100 / total) if total > 0 else 0
        self._single_progress.setValue(percent)
        self._single_page_label.setText(f"Trang: {current}/{total}")

    def _on_single_cancel(self):
        """Cancel single file processing"""
        if hasattr(self, '_single_timer'):
            self._single_timer.stop()
        if self._process_thread:
            self._process_thread.cancel()
        if hasattr(self, '_single_dialog'):
            self._single_dialog.close()

    def _on_single_finished(self, success: bool, message: str):
        """Single file processing finished"""
        # Stop timer and get elapsed time
        if hasattr(self, '_single_timer'):
            self._single_timer.stop()
        elapsed = int(time.time() - self._single_start_time) if hasattr(self, '_single_start_time') else 0

        if hasattr(self, '_single_dialog'):
            self._single_dialog.close()

        if success:
            self._result_path = message
            input_size = os.path.getsize(self._pdf_handler.pdf_path) / (1024 * 1024)
            output_size = os.path.getsize(message) / (1024 * 1024)
            self.statusBar().showMessage(
                f"✅ Hoàn thành! {input_size:.1f}MB → {output_size:.1f}MB"
            )
            self._show_completion_dialog(message, input_size, output_size, elapsed)
        else:
            self.statusBar().showMessage(f"❌ {message}")
            if message != "Đã hủy":
                QMessageBox.critical(self, "Lỗi", f"Lỗi khi xử lý:\n{message}")

        self._process_thread = None

    def _on_open_folder(self):
        if hasattr(self, '_result_path') and self._result_path:
            folder = os.path.dirname(self._result_path)
            if os.name == 'nt':
                os.startfile(folder)
            else:
                os.system(f'open "{folder}"' if os.uname().sysname == 'Darwin' else f'xdg-open "{folder}"')
    
    def _on_open_result_file(self):
        if hasattr(self, '_result_path') and self._result_path:
            if os.name == 'nt':
                os.startfile(self._result_path)
            else:
                os.system(f'open "{self._result_path}"' if os.uname().sysname == 'Darwin' else f'xdg-open "{self._result_path}"')
    
    def _show_completion_dialog(self, output_path: str, input_size: float, output_size: float,
                                elapsed: int = 0):
        """Show custom completion dialog"""
        # Format elapsed time
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        time_str = f"{h:02d}:{m:02d}:{s:02d}"

        dialog = QDialog(self)
        dialog.setWindowTitle("Hoàn thành")
        dialog.setMinimumSize(450, 200)
        dialog.setStyleSheet("""
            QDialog { background-color: white; }
            QLabel { font-size: 13px; font-weight: normal; }
            QPushButton {
                padding: 8px 16px; border-radius: 4px; font-size: 13px;
                min-width: 80px; background-color: #E5E7EB;
                color: #374151; border: 1px solid #D1D5DB;
            }
            QPushButton:hover { background-color: #3B82F6; color: white; border: none; }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Message (Regular font, not bold)
        msg_label = QLabel(
            f"Đã xử lý xong!\n\n"
            f"File đầu ra: {output_path}\n"
            f"Dung lượng: {input_size:.1f}MB → {output_size:.1f}MB\n"
            f"Thời gian: {time_str}"
        )
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label)
        
        layout.addStretch()
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()
        
        open_btn = QPushButton("Mở file")
        open_btn.setObjectName("open_btn")
        open_btn.clicked.connect(lambda: self._open_result_and_close(dialog))
        btn_layout.addWidget(open_btn)
        
        close_btn = QPushButton("Đóng")
        close_btn.setObjectName("close_btn")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.exec_()
    
    def _open_result_and_close(self, dialog):
        """Open result file and close dialog"""
        self._on_open_result_file()
        dialog.accept()
    
    def _show_overwrite_dialog(self, file_path: str) -> bool:
        """Show custom overwrite confirmation dialog with Regular font"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Xác nhận")
        dialog.setMinimumSize(450, 180)
        dialog.setStyleSheet("""
            QDialog { background-color: white; }
            QLabel { font-size: 13px; font-weight: normal; }
            QPushButton {
                padding: 8px 16px; border-radius: 4px; font-size: 13px;
                min-width: 80px; background-color: #E5E7EB;
                color: #374151; border: 1px solid #D1D5DB;
            }
            QPushButton:hover { background-color: #3B82F6; color: white; border: none; }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # Message
        msg_label = QLabel(f"File đã tồn tại:\n{file_path}\n\nGhi đè?")
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label)
        
        layout.addStretch()
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()
        
        no_btn = QPushButton("Không")
        no_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(no_btn)
        
        yes_btn = QPushButton("Có")
        yes_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(yes_btn)
        
        layout.addLayout(btn_layout)
        
        return dialog.exec_() == QDialog.Accepted
    
    def _show_batch_overwrite_dialog(self, count: int) -> bool:
        """Show batch overwrite confirmation dialog"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Xác nhận")
        dialog.setMinimumSize(400, 150)
        dialog.setStyleSheet("""
            QDialog { background-color: white; }
            QLabel { font-size: 13px; font-weight: normal; }
            QPushButton {
                padding: 8px 16px; border-radius: 4px; font-size: 13px;
                min-width: 80px; background-color: #E5E7EB;
                color: #374151; border: 1px solid #D1D5DB;
            }
            QPushButton:hover { background-color: #3B82F6; color: white; border: none; }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        msg_label = QLabel(f"Có {count} file đích đã tồn tại.\n\nGhi đè tất cả?")
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label)
        
        layout.addStretch()
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()
        
        no_btn = QPushButton("Không")
        no_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(no_btn)
        
        yes_btn = QPushButton("Ghi đè tất cả")
        yes_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(yes_btn)
        
        layout.addLayout(btn_layout)

        return dialog.exec_() == QDialog.Accepted

    def _show_batch_confirm_dialog(self, checked_count: int, total_count: int) -> bool:
        """Show batch confirmation dialog with file counts"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Xác nhận")
        dialog.setMinimumSize(400, 150)
        dialog.setStyleSheet("""
            QDialog { background-color: white; }
            QLabel { font-size: 13px; font-weight: normal; }
            QPushButton {
                padding: 8px 16px; border-radius: 4px; font-size: 13px;
                min-width: 80px; background-color: #E5E7EB;
                color: #374151; border: 1px solid #D1D5DB;
            }
            QPushButton:hover { background-color: #D1D5DB; }
            QPushButton#confirm_btn { background-color: #3B82F6; color: white; border: none; }
            QPushButton#confirm_btn:hover { background-color: #2563EB; }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        msg_label = QLabel(f"Xử lý {checked_count} / {total_count} file?\n\nBạn có muốn tiếp tục?")
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        cancel_btn = QPushButton("Hủy")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        confirm_btn = QPushButton("Xác nhận")
        confirm_btn.setObjectName("confirm_btn")
        confirm_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(confirm_btn)

        layout.addLayout(btn_layout)

        return dialog.exec_() == QDialog.Accepted

    def _show_batch_progress_dialog(self, files: List[str], output_dir: str,
                                    zones: List[Zone], settings: dict):
        """Show batch processing progress dialog"""
        self._batch_dialog = QDialog(self)
        self._batch_dialog.setWindowTitle("Đang xử lý...")
        self._batch_dialog.setMinimumSize(500, 220)
        self._batch_dialog.setModal(True)
        self._batch_dialog.setStyleSheet("""
            QDialog { background-color: white; }
            QLabel { font-size: 13px; font-weight: normal; }
            QProgressBar {
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                text-align: center;
                height: 24px;
            }
            QProgressBar::chunk {
                background-color: #3B82F6;
                border-radius: 3px;
            }
            QPushButton {
                padding: 8px 16px; border-radius: 4px; font-size: 13px;
                min-width: 80px; background-color: #E5E7EB;
                color: #374151; border: 1px solid #D1D5DB;
            }
            QPushButton:hover { background-color: #EF4444; color: white; border: none; }
        """)

        # Get page counts for accurate progress
        self._batch_page_counts = self.batch_sidebar.get_page_counts()
        self._batch_total_pages = sum(self._batch_page_counts.get(f, 0) for f in files)
        self._batch_total_files = len(files)

        layout = QVBoxLayout(self._batch_dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # Current file label
        self._batch_file_label = QLabel("Đang chuẩn bị...")
        layout.addWidget(self._batch_file_label)

        # Page progress label
        self._batch_page_label = QLabel("")
        self._batch_page_label.setStyleSheet("color: #6B7280; font-size: 12px;")
        layout.addWidget(self._batch_page_label)

        # Progress bar (based on total pages)
        self._batch_progress = QProgressBar()
        self._batch_progress.setMaximum(self._batch_total_pages if self._batch_total_pages > 0 else 100)
        self._batch_progress.setValue(0)
        layout.addWidget(self._batch_progress)

        # Stats label
        self._batch_stats_label = QLabel(f"0/{self._batch_total_files} files (0/{self._batch_total_pages} trang)")
        layout.addWidget(self._batch_stats_label)

        # Timer label
        self._batch_time_label = QLabel("Thời gian: 00:00:00")
        layout.addWidget(self._batch_time_label)

        layout.addStretch()

        # Cancel button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Hủy")
        cancel_btn.clicked.connect(self._on_batch_cancel)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        # Timer for elapsed time
        self._batch_start_time = time.time()
        self._batch_timer = QTimer()
        self._batch_timer.timeout.connect(self._update_batch_timer)
        self._batch_timer.start(1000)

        # Start batch processing
        self._batch_process_thread = BatchProcessThread(
            files, self._batch_base_dir, output_dir, zones, settings, self._batch_page_counts
        )
        self._batch_process_thread.progress.connect(self._on_batch_progress)
        self._batch_process_thread.file_progress.connect(self._on_batch_page_progress)
        self._batch_process_thread.total_progress.connect(self._on_batch_total_progress)
        self._batch_process_thread.finished.connect(self._on_batch_finished)

        self._batch_process_thread.start()
        self._batch_dialog.exec_()

    def _update_batch_timer(self):
        """Update batch elapsed time display"""
        elapsed = int(time.time() - self._batch_start_time)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        self._batch_time_label.setText(f"Thời gian: {h:02d}:{m:02d}:{s:02d}")
    
    def _on_batch_progress(self, current: int, total: int, filename: str):
        """Update batch file progress (file info only, progress bar updated by total_progress)"""
        self._batch_file_label.setText(f"File {current}/{total}: {filename}")
        self._batch_current_file = current
        # Reset page label when starting new file
        self._batch_page_label.setText("")

    def _on_batch_page_progress(self, current_page: int, total_pages: int):
        """Update page progress within current file"""
        self._batch_page_label.setText(f"Trang {current_page}/{total_pages}")

    def _on_batch_total_progress(self, pages_done: int, total_pages: int):
        """Update total progress bar based on pages processed"""
        self._batch_progress.setValue(pages_done)
        file_info = f"{getattr(self, '_batch_current_file', 0)}/{self._batch_total_files} files"
        page_info = f"{pages_done}/{total_pages} trang"
        self._batch_stats_label.setText(f"Đã xử lý: {file_info} ({page_info})")
    
    def _on_batch_cancel(self):
        """Cancel batch processing"""
        if hasattr(self, '_batch_timer'):
            self._batch_timer.stop()
        if self._batch_process_thread:
            self._batch_process_thread.cancel()
        if hasattr(self, '_batch_dialog'):
            self._batch_dialog.close()

    def _on_batch_finished(self, success: bool, stats: dict):
        """Batch processing finished"""
        # Stop timer and get elapsed time
        if hasattr(self, '_batch_timer'):
            self._batch_timer.stop()
        elapsed = int(time.time() - self._batch_start_time) if hasattr(self, '_batch_start_time') else 0

        if hasattr(self, '_batch_dialog'):
            self._batch_dialog.close()

        # Show completion dialog
        self._show_batch_completion_dialog(stats, elapsed)

        self._batch_process_thread = None

    def _show_batch_completion_dialog(self, stats: dict, elapsed: int = 0):
        """Show batch completion dialog"""
        # Format elapsed time
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        time_str = f"{h:02d}:{m:02d}:{s:02d}"

        dialog = QDialog(self)
        dialog.setWindowTitle("Hoàn thành")
        dialog.setMinimumSize(450, 280)
        dialog.setStyleSheet("""
            QDialog { background-color: white; }
            QLabel { font-size: 13px; font-weight: normal; }
            QPushButton {
                padding: 8px 16px; border-radius: 4px; font-size: 13px;
                min-width: 80px; background-color: #E5E7EB;
                color: #374151; border: 1px solid #D1D5DB;
            }
            QPushButton:hover { background-color: #3B82F6; color: white; border: none; }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Stats
        input_mb = stats['input_size'] / (1024 * 1024)
        output_mb = stats['output_size'] / (1024 * 1024)

        msg = f"""Đã xử lý xong!

Tổng số file: {stats['total']}
Thành công: {stats['success']}
Lỗi: {stats['failed']}

Thư mục đầu ra: {self._batch_output_dir}
Dung lượng: {input_mb:.1f}MB → {output_mb:.1f}MB
Thời gian: {time_str}"""
        
        msg_label = QLabel(msg)
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label)
        
        # Show errors if any
        if stats['errors']:
            error_text = "\n".join(stats['errors'][:5])
            if len(stats['errors']) > 5:
                error_text += f"\n... và {len(stats['errors']) - 5} lỗi khác"
            error_label = QLabel(f"Lỗi:\n{error_text}")
            error_label.setStyleSheet("color: #DC2626;")
            error_label.setWordWrap(True)
            layout.addWidget(error_label)
        
        layout.addStretch()
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()
        
        open_folder_btn = QPushButton("Mở thư mục")
        open_folder_btn.clicked.connect(lambda: self._open_output_folder(self._batch_output_dir))
        btn_layout.addWidget(open_folder_btn)
        
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.exec_()
    
    def _open_output_folder(self, folder_path: str):
        """Open output folder"""
        if os.path.exists(folder_path):
            if os.name == 'nt':
                os.startfile(folder_path)
            else:
                os.system(f'open "{folder_path}"' if os.uname().sysname == 'Darwin' else f'xdg-open "{folder_path}"')
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Accept drag if it contains URLs (files or folders)"""
        if event.mimeData().hasUrls():
            # Accept any URL - we'll check content in dropEvent
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        """Handle dropped files or folders"""
        urls = event.mimeData().urls()
        for url in urls:
            file_path = url.toLocalFile()
            # Handle Windows path format
            if not file_path and url.toString().startswith('file:///'):
                # Windows file:///C:/path format
                file_path = url.toString()[8:]  # Remove 'file:///'

            if not file_path:
                continue

            # Normalize path for cross-platform compatibility
            file_path = os.path.normpath(file_path)

            if os.path.isdir(file_path):
                # Dropped a folder - load it
                self._load_folder(file_path)
                break
            elif file_path.lower().endswith('.pdf'):
                # Dropped a PDF file
                self._load_pdf(file_path)
                break
    
    def closeEvent(self, event):
        if self._process_thread and self._process_thread.isRunning():
            reply = QMessageBox.question(
                self, "Xác nhận",
                "Đang xử lý, bạn có muốn dừng và thoát?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._process_thread.cancel()
                self._process_thread.wait()
            else:
                event.ignore()
                return

        # Save per-file zones before closing (crash recovery)
        if self._batch_mode:
            # First save current file zones to memory
            self.preview.save_per_file_zones(persist=False)
            self.settings_panel.save_per_file_custom_zones(persist=False)
            # Then force persist ALL per-file zones to disk
            self.preview._persist_zones_to_disk()
            self.settings_panel._persist_custom_zones_to_disk()

        # Save window size and sidebar width
        self._save_window_state()

        if self._pdf_handler:
            self._pdf_handler.close()

        event.accept()

    def _save_window_state(self):
        """Save window size, sidebar width, zoom level and panel state to config"""
        from core.config_manager import get_config_manager
        ui_config = get_config_manager().get_ui_config()

        # Save window size
        ui_config['window_width'] = self.width()
        ui_config['window_height'] = self.height()

        # Save sidebar width (if visible and not collapsed)
        if self.batch_sidebar.isVisible() and not self.batch_sidebar.is_collapsed():
            sidebar_width = self.preview_splitter.sizes()[0]
            ui_config['sidebar_width'] = sidebar_width

        # Save zoom level (as percentage)
        zoom = self.preview.before_panel.view._zoom
        ui_config['last_zoom_percent'] = int(zoom * 100)

        # Save after panel (Đích) collapsed state
        ui_config['after_panel_collapsed'] = self.preview._after_panel_collapsed

        get_config_manager().save_ui_config(ui_config)

    def _restore_window_state(self):
        """Restore window size, sidebar width, zoom level and panel state from config"""
        from core.config_manager import get_config_manager
        ui_config = get_config_manager().get_ui_config()

        # Restore window size
        width = ui_config.get('window_width', 1200)
        height = ui_config.get('window_height', 800)
        self.resize(width, height)

        # Restore sidebar width (will be applied when sidebar becomes visible)
        self._saved_sidebar_width = ui_config.get('sidebar_width', BatchSidebar.EXPANDED_WIDTH)

        # Restore zoom level (will be applied when file is loaded)
        self._saved_zoom_percent = ui_config.get('last_zoom_percent', 100)

        # Restore after panel (Đích) collapsed state
        if ui_config.get('after_panel_collapsed', False):
            self.preview._toggle_after_panel()  # Toggle to collapse

    def _get_default_folder_dir(self) -> str:
        """Get default folder directory from config, fallback to Desktop"""
        from core.config_manager import get_config_manager
        ui_config = get_config_manager().get_ui_config()
        saved_dir = ui_config.get('last_folder_parent', '')

        # Check if saved directory exists
        if saved_dir and os.path.isdir(saved_dir):
            return saved_dir

        # Fallback to Desktop
        desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
        if os.path.isdir(desktop):
            return desktop

        # Fallback to home directory
        return os.path.expanduser('~')

    def _save_last_folder_dir(self, folder_dir: str):
        """Save last folder parent directory to config"""
        from core.config_manager import get_config_manager
        ui_config = get_config_manager().get_ui_config()
        ui_config['last_folder_parent'] = folder_dir
        get_config_manager().save_ui_config(ui_config)

    def _apply_saved_sidebar_width(self):
        """Apply saved sidebar width to splitter"""
        if hasattr(self, '_saved_sidebar_width') and self._saved_sidebar_width > 0:
            total_width = self.preview_splitter.width()
            remaining = total_width - self._saved_sidebar_width
            self.preview_splitter.setSizes([self._saved_sidebar_width, remaining])

    def eventFilter(self, obj, event):
        """Cancel draw mode when clicking on corner/edge icons only"""
        from PyQt5.QtCore import QEvent

        if event.type() == QEvent.MouseButtonPress and self._current_draw_mode is not None:
            click_pos = event.globalPos()

            # Only cancel draw mode when clicking on corner or edge icons
            # (clicking on custom icon is handled by zone_selector toggle)
            corner_icon = self.settings_panel.zone_selector.corner_icon
            edge_icon = self.settings_panel.zone_selector.edge_icon

            corner_rect = corner_icon.rect()
            corner_global_pos = corner_icon.mapToGlobal(corner_rect.topLeft())
            corner_global_rect = corner_rect.translated(corner_global_pos)

            edge_rect = edge_icon.rect()
            edge_global_pos = edge_icon.mapToGlobal(edge_rect.topLeft())
            edge_global_rect = edge_rect.translated(edge_global_pos)

            if corner_global_rect.contains(click_pos) or edge_global_rect.contains(click_pos):
                # Cancel draw mode when clicking on corners or edges
                self._current_draw_mode = None
                self.preview.set_draw_mode(None)
                self.settings_panel.set_draw_mode(None)

        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        """Auto fit preview to page width on window resize (unless user manually zoomed)"""
        super().resizeEvent(event)
        if self._pdf_handler and not self._user_zoomed:
            self.preview.zoom_fit_width()
            self._update_zoom_combo()
    
    def _on_open_output_folder(self):
        """Open output folder in file explorer"""
        output_path = self.settings_panel.get_settings().get('output_path', '')
        if output_path and os.path.isdir(output_path):
            os.startfile(output_path) if os.name == 'nt' else os.system(f'xdg-open "{output_path}"')
        else:
            QMessageBox.information(self, "Thông báo", "Chưa có thư mục đầu ra được chọn.")
    
    def _show_help(self):
        """Show help dialog"""
        help_text = """
        <h3>Hướng dẫn sử dụng Xóa Ghim PDF (5S)</h3>
        
        <p><b>1. Mở file PDF:</b> Nhấn nút "Mở file" hoặc kéo thả file PDF vào vùng preview.</p>
        
        <p><b>2. Chọn vùng xử lý:</b> Mở "Chỉnh sửa" và chọn các góc/cạnh cần xử lý.</p>
        
        <p><b>3. Điều chỉnh thông số:</b> Điều chỉnh kích thước vùng và độ nhạy.</p>
        
        <p><b>4. Xử lý:</b> Nhấn nút "Xử lý" để bắt đầu xóa vết ghim.</p>
        
        <p><b>Phím tắt:</b></p>
        <ul>
            <li>Ctrl+O: Mở file</li>
            <li>Ctrl++: Phóng to</li>
            <li>Ctrl+-: Thu nhỏ</li>
            <li>Ctrl+Z: Hoàn tác thao tác vùng chọn</li>
            <li>Delete: Xóa vùng đang chọn</li>
        </ul>
        """
        QMessageBox.information(self, "Hướng dẫn", help_text)
    
    def _on_fit_width(self):
        """Fit chiều rộng trang hiện tại (menu action)"""
        self._user_zoomed = False  # Cho phép auto-fit khi resize
        self.preview.zoom_fit_width()  # Fit trang hiện tại
        self._update_zoom_combo()

    def _on_fit_height(self):
        """Fit chiều cao trang hiện tại (menu action)"""
        self._user_zoomed = False  # Cho phép auto-fit khi resize
        self.preview.zoom_fit_height()  # Fit trang hiện tại
        self._update_zoom_combo()

    def _on_single_page(self):
        """Switch to single page view mode"""
        self.view_mode_combo.setCurrentIndex(1)  # Sync combo box
        self.preview.set_view_mode('single')
        current_page = self.page_spin.value() - 1  # 0-based
        self.preview.set_current_page(current_page)

    def _on_continuous_scroll(self):
        """Switch to continuous scroll mode"""
        self.view_mode_combo.setCurrentIndex(0)  # Sync combo box
        self.preview.set_view_mode('continuous')
    
    def _get_device_info(self):
        """
        Detect GPU/CPU và trả về thông tin thiết bị YOLO sẽ sử dụng.

        Returns:
            dict: {
                'device': 'cuda' | 'mps' | 'cpu',
                'name': tên thiết bị,
                'memory': dung lượng memory (nếu có),
                'has_gpu': True/False,
                'cpu_name': tên CPU,
                'cpu_cores': số cores
            }
        """
        import platform
        import os

        # Get CPU info
        cpu_name = platform.processor() or 'CPU'
        if len(cpu_name) > 30:
            cpu_name = cpu_name[:27] + '...'
        cpu_cores = os.cpu_count() or 1

        info = {
            'device': 'cpu',
            'name': 'CPU',
            'memory': '',
            'has_gpu': False,
            'cpu_name': cpu_name,
            'cpu_cores': cpu_cores
        }

        try:
            import torch

            # Check CUDA (NVIDIA GPU)
            if torch.cuda.is_available():
                info['device'] = 'cuda'
                info['has_gpu'] = True
                info['name'] = torch.cuda.get_device_name(0)
                # Get memory info
                total_mem = torch.cuda.get_device_properties(0).total_memory
                info['memory'] = f"{total_mem / (1024**3):.1f} GB"
            # Check MPS (Apple Silicon)
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                info['device'] = 'mps'
                info['has_gpu'] = True
                info['name'] = 'Apple Silicon GPU'
                info['memory'] = 'Shared'
            else:
                info['name'] = cpu_name
        except ImportError:
            info['name'] = cpu_name
        except Exception:
            info['name'] = cpu_name

        return info

    def _show_settings_dialog(self):
        """Show settings dialog for algorithm selection"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Cài đặt thuật toán")
        dialog.setMinimumSize(500, 380)
        dialog.setStyleSheet("""
            QDialog {
                background-color: white;
            }
            QLabel.section-title {
                font-weight: bold;
                font-size: 14px;
                color: #374151;
                padding: 4px 0;
            }
            QRadioButton {
                padding: 6px 0;
                font-size: 13px;
                spacing: 8px;
                margin-left: 16px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(8)
        layout.setContentsMargins(24, 24, 24, 24)

        # Algorithm section title
        algo_title = QLabel("Thuật toán xử lý")
        algo_title.setProperty("class", "section-title")
        algo_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #374151; padding: 4px 0;")
        layout.addWidget(algo_title)

        algo_opencv = QRadioButton("OpenCV (CPU) - Nhanh, phù hợp hầu hết trường hợp")
        algo_opencv.setChecked(True)
        layout.addWidget(algo_opencv)

        algo_gpu = QRadioButton("Model GPU - Chất lượng cao, yêu cầu GPU")
        layout.addWidget(algo_gpu)

        # Spacer between sections
        layout.addSpacing(16)

        # === Device Info Section ===
        device_info = self._get_device_info()

        # Title
        gpu_title = QLabel("Tùy chọn GPU")
        gpu_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #374151; padding: 4px 0;")
        layout.addWidget(gpu_title)

        # Two-column layout: radio buttons (left) + device info (right)
        gpu_row = QHBoxLayout()
        gpu_row.setSpacing(16)

        # Left column: Radio buttons (in button group for mutual exclusion)
        from PyQt5.QtWidgets import QButtonGroup
        radio_column = QVBoxLayout()
        radio_column.setSpacing(4)

        gpu_button_group = QButtonGroup(dialog)

        gpu_auto = QRadioButton("Tự động phát hiện")
        gpu_auto.setChecked(True)
        gpu_button_group.addButton(gpu_auto, 0)
        radio_column.addWidget(gpu_auto)

        gpu_cuda = QRadioButton("CUDA (NVIDIA)")
        gpu_button_group.addButton(gpu_cuda, 1)
        radio_column.addWidget(gpu_cuda)

        gpu_cpu = QRadioButton("CPU fallback")
        gpu_button_group.addButton(gpu_cpu, 2)
        radio_column.addWidget(gpu_cpu)

        radio_column.addStretch()
        gpu_row.addLayout(radio_column)

        # Right column: Device info panel (no border)
        info_panel = QFrame()
        info_panel.setStyleSheet("""
            QFrame {
                background-color: #F3F4F6;
                border-radius: 6px;
            }
        """)
        info_panel.setMinimumWidth(220)
        info_layout = QVBoxLayout(info_panel)
        info_layout.setContentsMargins(12, 10, 12, 10)
        info_layout.setSpacing(2)

        # Device info label (code-style, small font)
        self._device_info_label = QLabel()
        self._device_info_label.setStyleSheet("""
            QLabel {
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 11px;
                color: #374151;
            }
        """)
        self._device_info_label.setWordWrap(True)
        info_layout.addWidget(self._device_info_label)

        gpu_row.addWidget(info_panel)
        layout.addLayout(gpu_row)

        # Store device info for updates
        self._cached_device_info = device_info
        cpu_name = device_info['cpu_name']
        cpu_cores = device_info['cpu_cores']

        # Function to update info panel based on selection
        def update_device_info():
            if gpu_auto.isChecked():
                # Auto detect - show what YOLO will actually use
                if device_info['has_gpu']:
                    text = f"<b>GPU (Auto)</b><br>"
                    text += f"• {device_info['name']}<br>"
                    if device_info['memory']:
                        text += f"• Memory: {device_info['memory']}<br>"
                    text += f"• CPU: {cpu_name} ({cpu_cores} cores)"
                else:
                    text = f"<b>CPU (Auto)</b><br>"
                    text += f"• {cpu_name}<br>"
                    text += f"• Cores: {cpu_cores}<br>"
                    text += "• GPU: <i>Không tìm thấy</i>"

            elif gpu_cuda.isChecked():
                # CUDA mode - show NVIDIA info if available
                if device_info['device'] == 'cuda':
                    text = f"<b>CUDA</b><br>"
                    text += f"• {device_info['name']}<br>"
                    if device_info['memory']:
                        text += f"• Memory: {device_info['memory']}<br>"
                    text += f"• CPU: {cpu_name} ({cpu_cores} cores)"
                else:
                    text = "<b>CUDA</b><br>"
                    text += "• <span style='color:#DC2626'>Không có NVIDIA GPU</span><br>"
                    text += f"• Fallback: {cpu_name}<br>"
                    text += f"• Cores: {cpu_cores}"

            else:  # CPU fallback
                text = f"<b>CPU</b><br>"
                text += f"• {cpu_name}<br>"
                text += f"• Cores: {cpu_cores}<br>"
                text += "• GPU: <i>Bỏ qua</i>"

            self._device_info_label.setText(text)

        # Connect radio buttons to update function
        gpu_auto.toggled.connect(update_device_info)
        gpu_cuda.toggled.connect(update_device_info)
        gpu_cpu.toggled.connect(update_device_info)

        # Initial update
        update_device_info()

        layout.addStretch()
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Hủy")
        cancel_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                border-radius: 4px;
                font-size: 13px;
                min-width: 70px;
                background-color: #E5E7EB;
                color: #374151;
                border: 1px solid #D1D5DB;
            }
            QPushButton:hover {
                background-color: #D1D5DB;
            }
        """)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Lưu")
        save_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                border-radius: 4px;
                font-size: 13px;
                min-width: 70px;
                background-color: #E5E7EB;
                color: #374151;
                border: 1px solid #D1D5DB;
            }
            QPushButton:hover {
                background-color: #D1D5DB;
            }
        """)
        save_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.exec_()

