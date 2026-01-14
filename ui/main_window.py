"""
Main Window - Cửa sổ chính với UI theo mẫu Foxit
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QAction, QLabel, QPushButton, QToolButton,
    QFileDialog, QMessageBox, QProgressBar,
    QFrame, QApplication, QSpinBox, QComboBox, QSizePolicy,
    QMenu, QDialog, QRadioButton, QStackedWidget,
    QGroupBox, QDialogButtonBox, QSplitter
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QEvent, QObject, QRect, QTimer
from PyQt5.QtGui import QKeySequence, QDragEnterEvent, QDropEvent, QPixmap, QPainter, QPen, QIcon, QColor

import os
import time
from pathlib import Path
from typing import Optional, List
import numpy as np

from ui.continuous_preview import ContinuousPreviewWidget
from ui.batch_preview import BatchFileListWidget
from ui.settings_panel import SettingsPanel
from core.processor import Zone, StapleRemover
from core.pdf_handler import PDFHandler, PDFExporter


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

    def __init__(self, input_path: str, output_path: str, zones: List[Zone], settings: dict):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.zones = zones
        self.settings = settings
        self._cancelled = False
        self._total_pages = 0

    def run(self):
        try:
            start_time = time.time()
            processor = StapleRemover(protect_red=self.settings.get('protect_red', True))

            def process_func(image, page_num):
                if self._cancelled:
                    return image
                # Log format: Trang X/Y: full_path
                print(f"Trang {page_num}/{self._total_pages}: {self.input_path}")
                return processor.process_image(image, self.zones)

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
    file_progress = pyqtSignal(int, int)  # current_page, total_pages
    finished = pyqtSignal(bool, dict)  # success, stats {total, success, failed, errors}
    
    def __init__(self, files: List[str], base_dir: str, output_dir: str, 
                 zones: List[Zone], settings: dict):
        super().__init__()
        self.files = files
        self.base_dir = base_dir
        self.output_dir = output_dir
        self.zones = zones
        self.settings = settings
        self._cancelled = False
    
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
            processor = StapleRemover(protect_red=self.settings.get('protect_red', True))

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

                    def page_progress(current, total):
                        if not self._cancelled:
                            self.file_progress.emit(current, total)

                    success = PDFExporter.export(
                        input_path,
                        output_path,
                        process_func,
                        dpi=self.settings.get('dpi', 200),
                        jpeg_quality=self.settings.get('jpeg_quality', 90),
                        optimize_size=self.settings.get('optimize_size', False),
                        progress_callback=page_progress
                    )

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
        self._last_dir = ""  # Remember last opened folder
        self._user_zoomed = False  # Track if user has manually zoomed
        self._current_draw_mode = None  # Track current draw mode for cancel logic

        self.setWindowTitle("Xóa Vết Ghim PDF")
        self.setMinimumSize(1200, 800)
        self.setAcceptDrops(True)

        self._setup_ui()
        self._update_ui_state()

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
        
        # === SETTINGS PANEL (Cấu hình) - White background, visible by default ===
        self.settings_panel = SettingsPanel()
        self.settings_panel.zones_changed.connect(self._on_zones_changed)
        self.settings_panel.settings_changed.connect(self._on_settings_changed)
        self.settings_panel.page_filter_changed.connect(self._on_page_filter_changed)
        self.settings_panel.output_settings_changed.connect(self._on_output_settings_changed)
        self.settings_panel.text_protection_changed.connect(self._on_text_protection_changed)
        self.settings_panel.draw_mode_changed.connect(self._on_draw_mode_changed)
        self.settings_panel.setVisible(True)  # Visible by default
        layout.addWidget(self.settings_panel)
        
        # === PREVIEW AREA - Gray background ===
        preview_container = QWidget()
        preview_container.setStyleSheet("background-color: #E5E7EB;")
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)
        
        # Vertical splitter for batch file list and preview
        self.preview_splitter = QSplitter(Qt.Vertical)
        self.preview_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #D1D5DB;
                height: 4px;
            }
            QSplitter::handle:hover {
                background-color: #9CA3AF;
            }
        """)
        
        # Batch file list (hidden by default)
        self.batch_file_list = BatchFileListWidget()
        self.batch_file_list.file_selected.connect(self._on_batch_file_selected)
        self.batch_file_list.close_requested.connect(self._on_close_file)
        self.batch_file_list.setVisible(False)
        self.batch_file_list.setMinimumHeight(100)
        self.preview_splitter.addWidget(self.batch_file_list)
        
        # Preview widget (same for single and batch modes)
        self.preview = ContinuousPreviewWidget()
        self.preview.zone_changed.connect(self._on_zone_changed_from_preview)
        self.preview.zone_selected.connect(self._on_zone_selected_from_preview)
        self.preview.zone_delete.connect(self._on_zone_delete_from_preview)
        self.preview.open_file_requested.connect(self._on_open)
        self.preview.open_folder_requested.connect(self._on_open_folder_batch)
        self.preview.file_dropped.connect(self._on_file_dropped)
        self.preview.close_requested.connect(self._on_close_file)
        self.preview.page_changed.connect(self._on_page_changed_from_scroll)
        self.preview.rect_drawn.connect(self._on_rect_drawn_from_preview)
        self.preview_splitter.addWidget(self.preview)
        
        # Set initial splitter sizes (file list: 200, preview: stretch)
        self.preview_splitter.setSizes([200, 600])
        
        preview_layout.addWidget(self.preview_splitter)
        
        layout.addWidget(preview_container, stretch=1)
        
        # === BOTTOM BAR ===
        self._setup_bottom_bar(layout)
        
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
            # Box with horizontal arrows inside (like the reference image)
            # No margin - border fills entire icon
            m = 0
            iw = size - 1
            ih = size - 1
            
            # Draw rounded rectangle border (fills entire area)
            painter.drawRoundedRect(m, m, iw, ih, 3, 3)
            
            # Center y position
            cy = ih // 2
            
            # Left arrow ← (pointing to left edge)
            arrow_len = iw // 3
            painter.drawLine(5, cy, 5 + arrow_len, cy)  # Arrow shaft
            painter.drawLine(5, cy, 8, cy - 3)  # Arrow head top
            painter.drawLine(5, cy, 8, cy + 3)  # Arrow head bottom
            
            # Right arrow → (pointing to right edge)
            painter.drawLine(iw - 5 - arrow_len, cy, iw - 5, cy)  # Arrow shaft
            painter.drawLine(iw - 5, cy, iw - 8, cy - 3)  # Arrow head top
            painter.drawLine(iw - 5, cy, iw - 8, cy + 3)  # Arrow head bottom

        elif icon_type == "fit_height":
            # Box with vertical arrows inside
            m = 0
            iw = size - 1
            ih = size - 1

            # Draw rounded rectangle border
            painter.drawRoundedRect(m, m, iw, ih, 3, 3)

            # Center x position
            cx = iw // 2

            # Top arrow ↑ (pointing to top edge)
            arrow_len = ih // 3
            painter.drawLine(cx, 5, cx, 5 + arrow_len)  # Arrow shaft
            painter.drawLine(cx, 5, cx - 3, 8)  # Arrow head left
            painter.drawLine(cx, 5, cx + 3, 8)  # Arrow head right

            # Bottom arrow ↓ (pointing to bottom edge)
            painter.drawLine(cx, ih - 5 - arrow_len, cx, ih - 5)  # Arrow shaft
            painter.drawLine(cx, ih - 5, cx - 3, ih - 8)  # Arrow head left
            painter.drawLine(cx, ih - 5, cx + 3, ih - 8)  # Arrow head right

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
                background-color: #D1D5DB;
            }
            QPushButton:checked:hover {
                background-color: #D1D5DB;
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
                font-size: 14px;
            }}
            QToolButton {{
                background-color: transparent;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px 10px;
                color: #374151;
                font-size: 14px;
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
                font-size: 14px;
            }}
            QComboBox {{
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px 6px;
                padding-right: 24px;
                background-color: white;
                font-size: 14px;
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
        slash_label.setStyleSheet("color: #6B7280;")
        bar_layout.addWidget(slash_label)
        
        self.total_pages_label = QLabel("1")
        bar_layout.addWidget(self.total_pages_label)
        
        # Separator
        sep1 = QLabel("|")
        sep1.setStyleSheet("color: #D1D5DB; padding: 0 6px;")
        bar_layout.addWidget(sep1)
        
        # View mode - wider with dropdown arrow
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems(["Cuộn liên tục", "Xem một trang"])
        self.view_mode_combo.setCurrentIndex(0)
        self.view_mode_combo.setFixedSize(155, btn_height)
        self.view_mode_combo.currentIndexChanged.connect(self._on_view_mode_changed)
        bar_layout.addWidget(self.view_mode_combo)
        
        # Fit width - icon button using uploaded image
        self.zoom_fit_btn = QToolButton()
        # Load fit_width icon from resources or use generated icon
        fit_width_path = os.path.join(os.path.dirname(__file__), "..", "resources", "fit_width.png")
        if os.path.exists(fit_width_path):
            self.zoom_fit_btn.setIcon(QIcon(fit_width_path))
        else:
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

        # Fit height - icon button
        self.zoom_fit_height_btn = QToolButton()
        fit_height_path = os.path.join(os.path.dirname(__file__), "..", "resources", "fit_height.png")
        if os.path.exists(fit_height_path):
            self.zoom_fit_height_btn.setIcon(QIcon(fit_height_path))
        else:
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
        sep2.setStyleSheet("color: #D1D5DB; padding: 0 6px;")
        bar_layout.addWidget(sep2)
        
        # Zoom dropdown - wider
        self.zoom_combo = QComboBox()
        zoom_levels = [f"{z}%" for z in range(25, 425, 25)]
        self.zoom_combo.addItems(zoom_levels)
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.setFixedSize(100, btn_height)
        self.zoom_combo.setEditable(True)
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
        """Toggle settings panel visibility"""
        visible = not self.settings_panel.isVisible()
        self.settings_panel.setVisible(visible)
        
        # Sync menu button state
        if hasattr(self, 'config_menu_btn'):
            self.config_menu_btn.setChecked(visible)
    
    def _set_bottom_bar_visible(self, visible: bool):
        """Show/hide bottom bar controls"""
        if hasattr(self, 'bottom_bar'):
            self.bottom_bar.setVisible(visible)
    
    def _update_ui_state(self):
        """Cập nhật trạng thái UI"""
        has_file = self._pdf_handler is not None
        
        if self._batch_mode:
            # Batch mode - enable run if there are checked files
            has_checked = bool(self.batch_file_list.get_checked_files())
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
            self._last_dir = str(Path(file_path).parent)
            self._load_pdf(file_path)
    
    def _on_file_dropped(self, file_path: str):
        """Handle file dropped from preview area"""
        if file_path and file_path.lower().endswith('.pdf'):
            self._load_pdf(file_path)
    
    def _on_open_folder_batch(self):
        """Mở thư mục để xử lý batch"""
        folder_path = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục chứa file PDF", self._last_dir
        )
        if folder_path:
            self._last_dir = folder_path
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
        
        # Switch to batch mode
        self._batch_mode = True
        self._batch_base_dir = folder_path
        self._batch_files = pdf_files
        
        # Always default output to source folder when opening new batch
        output_dir = folder_path
        self._batch_output_dir = output_dir

        # Update settings panel output path to source folder
        self.settings_panel.set_output_path(output_dir)

        # Get filename pattern from settings
        settings = self.settings_panel.get_settings()
        filename_pattern = settings.get('filename_pattern', '{gốc}_clean.pdf')

        # Show batch file list with filename pattern
        self.batch_file_list.set_folder(folder_path, output_dir, pdf_files, filename_pattern)
        self.batch_file_list.setVisible(True)
        
        # Update UI
        self.setWindowTitle(f"Xóa Vết Ghim PDF - {folder_path} ({len(pdf_files)} files)")
        
        # Load first file (will be triggered by file_selected signal)
        self._update_ui_state()
    
    def _on_batch_file_selected(self, file_path: str):
        """When file selected in batch mode file list"""
        # Load the selected file using the same method as single mode
        self._load_pdf(file_path)
    
    def _on_close_file(self):
        """Close currently opened file or folder"""
        if self._batch_mode:
            # Close batch mode
            self._batch_mode = False
            self._batch_base_dir = ""
            self._batch_output_dir = ""
            self._batch_files = []
            
            # Hide batch file list
            self.batch_file_list.setVisible(False)
            
            self.setWindowTitle("Xóa Vết Ghim PDF")
        
        # Close current file (applies to both modes)
        if self._pdf_handler:
            self._pdf_handler.close()
            self._pdf_handler = None
        
        self._current_file_path = None
        self._all_pages = []
        
        # Clear preview
        self.preview.set_pages([])
        self.preview.clear_file_paths()
        
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
                # Single file mode: set output path to file's parent
                output_dir = str(source_path.parent)
                self.settings_panel.set_output_path(output_dir)
                dest_path = source_path.parent / f"{source_path.stem}_clean{source_path.suffix}"

            # Update preview panel titles with file paths
            self.preview.set_file_paths(str(file_path), str(dest_path))
            
            # Set pages
            self.preview.set_pages(self._all_pages)
            zones = self.settings_panel.get_zones()
            self.preview.set_zones(zones)

            # Apply text protection options (để vẽ bounding boxes ngay khi mở file)
            text_protection_opts = self.settings_panel.get_text_protection_options()
            self.preview.set_text_protection(text_protection_opts)

            self._update_ui_state()
            self.statusBar().showMessage(f"Đã mở: {file_path}")

            # Reset to first page
            self._user_zoomed = False
            self.preview.set_current_page(0)  # Scroll về trang đầu

            # Defer fit width đến sau khi layout hoàn tất
            # Dùng 100ms delay để đảm bảo viewport đã có kích thước đúng
            QTimer.singleShot(100, self._fit_first_page_width)
            
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể mở file:\n{e}")
    
    def _fit_first_page_width(self):
        """Fit chiều rộng trang đầu và scroll đến trang đầu - được gọi sau khi layout cập nhật"""
        if self._all_pages:
            # scroll_to_page=True để scroll đến trang đầu tiên
            self.preview.zoom_fit_width(0, scroll_to_page=True)
            self._update_zoom_combo()

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
        except:
            pass
    
    def _update_zoom_combo(self):
        try:
            zoom = self.preview.before_panel.view._zoom
            self.zoom_combo.blockSignals(True)
            self.zoom_combo.setCurrentText(f"{int(zoom * 100)}%")
            self.zoom_combo.blockSignals(False)
        except:
            pass
    
    def _on_zones_changed(self, zones: List[Zone]):
        self.preview.set_zones(zones)
    
    def _on_settings_changed(self, settings: dict):
        pass

    def _on_text_protection_changed(self, options):
        """Handle text protection settings change"""
        self.preview.set_text_protection(options)

    def _on_draw_mode_changed(self, mode):
        """Handle draw mode toggle from settings panel (mode: 'remove', 'protect', or None)"""
        print(f"[DrawMode] MainWindow._on_draw_mode_changed: mode={mode}")
        self._current_draw_mode = mode
        self.preview.set_draw_mode(mode)

    def _on_rect_drawn_from_preview(self, x: float, y: float, w: float, h: float, mode: str):
        """Handle rectangle drawn on preview - create custom zone"""
        self.settings_panel.add_custom_zone_from_rect(x, y, w, h, mode)

    def _on_output_settings_changed(self, output_dir: str, filename_pattern: str):
        """Handle output settings change - update batch file list"""
        if self._batch_mode:
            self._batch_output_dir = output_dir if output_dir else self._batch_base_dir
            self.batch_file_list.update_output_settings(output_dir, filename_pattern)

    def _on_page_filter_changed(self, filter_mode: str):
        """Handle page filter change from settings"""
        self.preview.set_page_filter(filter_mode)
    
    def _on_zone_changed_from_preview(self, zone_id: str, x: float, y: float, w: float, h: float):
        self.settings_panel.update_zone_from_preview(zone_id, x, y, w, h)
    
    def _on_zone_selected_from_preview(self, zone_id: str):
        pass
    
    def _on_zone_delete_from_preview(self, zone_id: str):
        """Handle zone delete request from preview"""
        self.settings_panel.delete_custom_zone(zone_id)
        # Refresh preview with updated zones
        zones = self.settings_panel.get_zones()
        self.preview.set_zones(zones)
    
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

        if os.path.exists(output_path):
            if not self._show_overwrite_dialog(output_path):
                return

        zones = self.settings_panel.get_zones()

        # Show progress dialog like batch mode
        self._show_single_progress_dialog(
            self._pdf_handler.pdf_path, output_path, zones, settings
        )
    
    def _on_process_batch(self):
        """Xử lý batch files"""
        checked_files = self.batch_file_list.get_checked_files()
        if not checked_files:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng chọn ít nhất một file để xử lý!")
            return
        
        settings = self.settings_panel.get_settings()
        
        output_dir = settings.get('output_path', '')
        if not output_dir:
            output_dir = self._batch_base_dir
        
        # Check for existing files - use same logic as batch_preview
        existing_files = []
        pattern = settings.get('filename_pattern', '{gốc}_clean.pdf')
        for f in checked_files:
            rel_path = os.path.relpath(f, self._batch_base_dir)
            name, _ = os.path.splitext(rel_path)
            output_name = pattern.replace('{gốc}', name)
            output_path = os.path.join(output_dir, output_name)
            if os.path.exists(output_path):
                existing_files.append(output_path)
        
        if existing_files:
            if not self._show_batch_overwrite_dialog(len(existing_files)):
                return
        
        zones = self.settings_panel.get_zones()
        
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
                                     zones: List[Zone], settings: dict):
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

        # Start processing
        self._process_thread = ProcessThread(input_path, output_path, zones, settings)
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
            QDialog {
                background-color: white;
            }
            QLabel {
                font-size: 13px;
                font-weight: normal;
            }
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                min-width: 80px;
                background-color: #E5E7EB;
                color: #374151;
                border: 1px solid #D1D5DB;
            }
            QPushButton:hover {
                background-color: #D1D5DB;
            }
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
            QDialog {
                background-color: white;
            }
            QLabel {
                font-size: 13px;
                font-weight: normal;
            }
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                min-width: 80px;
                background-color: #E5E7EB;
                color: #374151;
                border: 1px solid #D1D5DB;
            }
            QPushButton:hover {
                background-color: #D1D5DB;
            }
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
            QPushButton:hover { background-color: #D1D5DB; }
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
            QPushButton:hover { background-color: #D1D5DB; }
        """)

        layout = QVBoxLayout(self._batch_dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # Current file label
        self._batch_file_label = QLabel("Đang chuẩn bị...")
        layout.addWidget(self._batch_file_label)

        # Progress bar
        self._batch_progress = QProgressBar()
        self._batch_progress.setMaximum(len(files))
        self._batch_progress.setValue(0)
        layout.addWidget(self._batch_progress)

        # Stats label
        self._batch_stats_label = QLabel(f"0/{len(files)} files")
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
            files, self._batch_base_dir, output_dir, zones, settings
        )
        self._batch_process_thread.progress.connect(self._on_batch_progress)
        self._batch_process_thread.finished.connect(self._on_batch_finished)

        self._batch_process_thread.start()
        self._batch_dialog.exec_()

    def _update_batch_timer(self):
        """Update batch elapsed time display"""
        elapsed = int(time.time() - self._batch_start_time)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        self._batch_time_label.setText(f"Thời gian: {h:02d}:{m:02d}:{s:02d}")
    
    def _on_batch_progress(self, current: int, total: int, filename: str):
        """Update batch progress"""
        self._batch_file_label.setText(f"File hiện tại: {filename}")
        self._batch_progress.setValue(current)
        self._batch_stats_label.setText(f"Đã xử lý: {current}/{total} files")
    
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
            QPushButton:hover { background-color: #D1D5DB; }
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
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(url.toLocalFile().lower().endswith('.pdf') for url in urls):
                event.acceptProposedAction()
    
    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        for url in urls:
            file_path = url.toLocalFile()
            if file_path.lower().endswith('.pdf'):
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

        if self._pdf_handler:
            self._pdf_handler.close()

        event.accept()

    def eventFilter(self, obj, event):
        """Cancel draw mode when clicking outside the preview before_panel"""
        from PyQt5.QtCore import QEvent

        if event.type() == QEvent.MouseButtonPress and self._current_draw_mode is not None:
            # Check if click is inside the before_panel of preview
            click_pos = event.globalPos()
            before_panel = self.preview.before_panel

            # Get before_panel's global geometry
            panel_rect = before_panel.rect()
            panel_global_pos = before_panel.mapToGlobal(panel_rect.topLeft())
            panel_global_rect = panel_rect.translated(panel_global_pos)

            if not panel_global_rect.contains(click_pos):
                # Click is outside before_panel - cancel draw mode
                # But don't cancel if clicking on the custom icon itself
                custom_icon = self.settings_panel.zone_selector.custom_icon
                icon_rect = custom_icon.rect()
                icon_global_pos = custom_icon.mapToGlobal(icon_rect.topLeft())
                icon_global_rect = icon_rect.translated(icon_global_pos)

                if not icon_global_rect.contains(click_pos):
                    # Cancel draw mode
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
        <h3>Hướng dẫn sử dụng Xóa Vết Ghim PDF</h3>
        
        <p><b>1. Mở file PDF:</b> Nhấn nút "Mở file" hoặc kéo thả file PDF vào vùng preview.</p>
        
        <p><b>2. Chọn vùng xử lý:</b> Mở "Chỉnh sửa" và chọn các góc/cạnh cần xử lý.</p>
        
        <p><b>3. Điều chỉnh thông số:</b> Điều chỉnh kích thước vùng và độ nhạy.</p>
        
        <p><b>4. Xử lý:</b> Nhấn nút "Xử lý" để bắt đầu xóa vết ghim.</p>
        
        <p><b>Phím tắt:</b></p>
        <ul>
            <li>Ctrl+O: Mở file</li>
            <li>Ctrl++: Phóng to</li>
            <li>Ctrl+-: Thu nhỏ</li>
        </ul>
        """
        QMessageBox.information(self, "Hướng dẫn", help_text)
    
    def _on_fit_width(self):
        """Fit chiều rộng trang hiện tại (menu action)"""
        self._user_zoomed = False  # Cho phép auto-fit khi resize
        self.preview.zoom_fit_width()  # Fit trang hiện tại
        self._update_zoom_combo()
    
    def _on_single_page(self):
        """Switch to single page view mode"""
        # TODO: Implement single page mode
        QMessageBox.information(self, "Thông báo", "Chế độ xem 1 trang sẽ được cập nhật trong phiên bản sau.")
    
    def _on_continuous_scroll(self):
        """Switch to continuous scroll mode"""
        # Already in continuous mode by default
        QMessageBox.information(self, "Thông báo", "Đang ở chế độ cuộn liên tục.")
    
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

