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

from ui.continuous_preview import ContinuousPreviewWidget, LoadingOverlay
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

            # Get DPI for zone coordinate scaling
            export_dpi = self.settings.get('dpi', 300)
            preview_dpi = self.settings.get('preview_dpi', 120)

            # Deserialize and scale cached protected regions if provided
            scaled_regions_by_page = None
            preview_regions = self.settings.get('preview_cached_regions')
            if preview_regions:
                from core.parallel_processor import deserialize_and_scale_protected_regions
                scaled_regions_by_page = deserialize_and_scale_protected_regions(
                    preview_regions, preview_dpi, export_dpi
                )

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

                # Use scaled regions from preview if available (ensures consistency)
                page_regions = None
                if scaled_regions_by_page is not None:
                    page_regions = scaled_regions_by_page.get(page_num, [])

                return processor.process_image(
                    image, page_zones,
                    protected_regions=page_regions,
                    render_dpi=export_dpi
                )

            def progress_callback(current, total):
                self._total_pages = total
                if not self._cancelled:
                    self.progress.emit(current, total)

            success = PDFExporter.export(
                self.input_path,
                self.output_path,
                process_func,
                dpi=export_dpi,
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
    """Thread xử lý batch PDF với parallel processing (auto-scale theo CPU/RAM, max 80%)"""

    progress = pyqtSignal(int, int, str)  # current_file, total_files, current_filename
    file_progress = pyqtSignal(int, int)  # current_page, total_pages_in_file
    total_progress = pyqtSignal(int, int)  # pages_processed, total_pages_all_files
    finished = pyqtSignal(bool, dict)  # success, stats {total, success, failed, errors}
    worker_info = pyqtSignal(int)  # number of parallel workers being used

    def __init__(self, files: List[str], base_dir: str, output_dir: str,
                 zones: List[Zone], settings: dict, page_counts: dict = None,
                 per_file_zones: dict = None):
        super().__init__()
        self.files = files
        self.base_dir = base_dir
        self.output_dir = output_dir
        self.zones = zones  # Default zones (from current file with target_page set)
        self.settings = settings
        self.page_counts = page_counts or {}  # {file_path: page_count}
        self.per_file_zones = per_file_zones or {}  # {file_path: {page_idx: {zone_id: tuple}}}
        self._cancelled = False
        self._pages_processed = 0
        self._total_pages = sum(self.page_counts.get(f, 0) for f in files)

    def run(self):
        from concurrent.futures import ProcessPoolExecutor, as_completed
        from multiprocessing import Manager
        from core.resource_manager import ResourceManager
        from core.parallel_processor import process_single_pdf, serialize_zones, ProcessTask

        stats = {
            'total': len(self.files),
            'success': 0,
            'failed': 0,
            'errors': [],
            'input_size': 0,
            'output_size': 0
        }

        if not self.files:
            self.finished.emit(True, stats)
            return

        try:
            start_time = time.time()

            # Calculate optimal workers based on CPU/RAM (max 80%)
            config = ResourceManager.calculate_optimal_workers(
                cpu_limit=0.80,
                ram_limit=0.80,
                file_count=len(self.files)
            )
            max_workers = config.max_workers

            # Emit worker count
            self.worker_info.emit(max_workers)
            print(f"[Parallel] Sử dụng {max_workers} processes (CPU/RAM max 80%)")

            # Serialize default zones (from current file)
            default_zone_dicts = serialize_zones(self.zones)

            # Extract Zone Chung (corners, margins) from default zones - apply to all files
            zone_chung_dicts = [
                z for z in default_zone_dicts
                if z['id'].startswith('corner_') or z['id'].startswith('margin_')
            ]

            # Create tasks with file-specific zones
            tasks = []
            for i, input_path in enumerate(self.files):
                output_path = self._get_output_path(input_path)

                # Start with Zone Chung (global, applies to all files)
                file_zones = list(zone_chung_dicts)

                # Check if this file has Zone Riêng in per_file_zones
                if input_path in self.per_file_zones:
                    # Convert per_file_zones data to zone dicts with target_page set
                    file_zone_data = self.per_file_zones[input_path]
                    for page_idx, page_zones in file_zone_data.items():
                        for zone_id, zone_tuple in page_zones.items():
                            # Only add Zone Riêng (custom_*, protect_*)
                            if zone_id.startswith('custom_') or zone_id.startswith('protect_'):
                                zone_dict = {
                                    'id': zone_id,
                                    'name': zone_id,
                                    'x': zone_tuple[0],
                                    'y': zone_tuple[1],
                                    'width': zone_tuple[2],
                                    'height': zone_tuple[3],
                                    'threshold': 7,
                                    'enabled': True,
                                    'zone_type': 'protect' if zone_id.startswith('protect_') else 'remove',
                                    'page_filter': 'none',
                                    'target_page': page_idx,
                                    'size_mode': 'percent'
                                }
                                file_zones.append(zone_dict)
                # else: No Zone Riêng for this file - only Zone Chung applies

                task = ProcessTask(
                    input_path=input_path,
                    output_path=output_path,
                    zones=file_zones,
                    settings=self.settings,
                    file_index=i,
                    total_files=len(self.files)
                )
                tasks.append(task)

            # Process with parallel executor
            with Manager() as manager:
                progress_queue = manager.Queue()

                with ProcessPoolExecutor(max_workers=max_workers) as executor:
                    # Submit all tasks
                    futures = {
                        executor.submit(process_single_pdf, task, progress_queue): task
                        for task in tasks
                    }

                    # Track progress
                    files_completed = 0
                    pages_by_file = {}  # Track pages per file

                    while files_completed < len(futures):
                        if self._cancelled:
                            executor.shutdown(wait=False, cancel_futures=True)
                            break

                        # Process progress updates from queue
                        while not progress_queue.empty():
                            try:
                                msg = progress_queue.get_nowait()
                                if msg['type'] == 'page':
                                    file_idx = msg['file_index']
                                    page_num = msg['page_num']
                                    total_pages = msg['total_pages']
                                    filename = os.path.basename(msg['input_path'])

                                    # Update per-file progress
                                    pages_by_file[file_idx] = page_num

                                    # Emit signals
                                    self.progress.emit(file_idx + 1, len(self.files), filename)
                                    self.file_progress.emit(page_num, total_pages)

                                    # Calculate total pages processed
                                    total_done = sum(pages_by_file.values())
                                    self.total_progress.emit(total_done, self._total_pages)

                                    # Log (only non-skipped pages)
                                    if not msg.get('skipped'):
                                        print(f"{file_idx + 1}/{len(self.files)}: {msg['input_path']} >> Trang {page_num}")

                                elif msg['type'] == 'file_complete':
                                    files_completed += 1
                                    elapsed = msg['elapsed']
                                    h = int(elapsed // 3600)
                                    m = int((elapsed % 3600) // 60)
                                    s = int(elapsed % 60)
                                    status = "OK" if msg['success'] else f"FAILED: {msg.get('error', 'Unknown')}"
                                    print(f">> {os.path.basename(msg['input_path'])}: {status} ({h:02d}:{m:02d}:{s:02d})")

                            except Exception:
                                break

                        # Small delay to prevent busy-wait
                        time.sleep(0.05)

                    # Collect results from futures
                    for future in as_completed(futures):
                        try:
                            result = future.result()
                            stats['input_size'] += result.input_size
                            stats['output_size'] += result.output_size

                            if result.success:
                                stats['success'] += 1
                            else:
                                stats['failed'] += 1
                                if result.error:
                                    stats['errors'].append(f"{os.path.basename(result.input_path)}: {result.error}")
                        except Exception as e:
                            stats['failed'] += 1
                            task = futures[future]
                            stats['errors'].append(f"{os.path.basename(task.input_path)}: {str(e)}")

            # Log total time
            total_elapsed = int(time.time() - start_time)
            h, m, s = total_elapsed // 3600, (total_elapsed % 3600) // 60, total_elapsed % 60
            print(f"\n[Parallel] Tổng thời gian: {h:02d}:{m:02d}:{s:02d}")

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
        output_name = pattern.replace('{gốc}', name)
        return os.path.join(self.output_dir, output_name)

    def cancel(self):
        self._cancelled = True


class MainWindow(QMainWindow):
    """Cửa sổ chính"""

    MAX_PREVIEW_PAGES = 500
    INITIAL_LOAD_PAGES = 10  # Number of preview pages to load initially
    THUMBNAIL_DPI = 36  # Low DPI for fast thumbnail rendering
    PREVIEW_DPI = 120  # Full DPI for preview

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
        # Lazy loading state
        self._background_loading = False  # True when loading remaining pages in background
        self._stop_loading_flag = False  # Signal to stop background loading
        self._total_pages = 0  # Total pages in current PDF
        self._bg_load_index = 0  # Current page index for background preview loading
        self._thumb_load_index = 0  # Current page index for background thumbnail loading

        self.setWindowTitle("Xóa Ghim PDF (5S)")
        self.setMinimumSize(1200, 800)
        self.setAcceptDrops(True)

        self._setup_ui()
        self._update_ui_state()
        self._restore_window_state()

        # Loading overlay for PDF loading
        self._loading_overlay = LoadingOverlay(self)
        self._loading_overlay.hide()

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
        self.preview_splitter.setHandleWidth(1)  # Thin handle
        self.preview_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #D1D5DB;
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
        self.preview.page_load_requested.connect(self._on_page_load_requested)
        self.preview.zoom_changed.connect(self._on_zoom_changed_from_scroll)
        right_layout.addWidget(self.preview, stretch=1)

        # === BOTTOM BAR (inside right container) ===
        self._setup_bottom_bar(right_layout)

        self.preview_splitter.addWidget(right_container)
        self.preview_splitter.setCollapsible(1, False)  # Prevent right panel from collapsing
        self.preview_splitter.setStretchFactor(0, 0)    # Sidebar: fixed size when window resizes
        self.preview_splitter.setStretchFactor(1, 1)    # Right panel: stretch to fill
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

        # Keyboard shortcuts for draw mode (toggle on/off)
        # macOS: Cmd+A, Cmd+S | Windows: Alt+A, Alt+S
        import sys
        if sys.platform == 'darwin':
            # macOS: Ctrl maps to Cmd
            protect_key = "Ctrl+A"
            remove_key = "Ctrl+S"
        else:
            # Windows/Linux: Use Alt to avoid conflict with Ctrl+A/S
            protect_key = "Alt+A"
            remove_key = "Alt+S"

        self.draw_protect_a = QShortcut(QKeySequence(protect_key), self)
        self.draw_protect_a.setAutoRepeat(False)
        self.draw_protect_a.activated.connect(self._toggle_draw_protect)
        self.draw_protect_plus = QShortcut(QKeySequence("Shift+="), self)
        self.draw_protect_plus.setAutoRepeat(False)
        self.draw_protect_plus.activated.connect(self._toggle_draw_protect)
        # Also map = key (without shift) for convenience
        self.draw_protect_equal = QShortcut(QKeySequence("="), self)
        self.draw_protect_equal.setAutoRepeat(False)
        self.draw_protect_equal.activated.connect(self._toggle_draw_protect)

        self.draw_remove_s = QShortcut(QKeySequence(remove_key), self)
        self.draw_remove_s.setAutoRepeat(False)
        self.draw_remove_s.activated.connect(self._toggle_draw_remove)
        self.draw_remove_minus = QShortcut(QKeySequence("-"), self)
        self.draw_remove_minus.setAutoRepeat(False)
        self.draw_remove_minus.activated.connect(self._toggle_draw_remove)

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
                border: none;
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
        self.zone_count_label.setStyleSheet("color: #6B7280; font-size: 12px;")
        bar_layout.addWidget(self.zone_count_label)
        # Track previous zone counts for flash effect
        self._prev_zone_counts = (0, 0, 0)  # (zone_chung, zone_rieng_file, zone_rieng_total)
        self._zone_flash_timer = None

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
        # Free memory from previous session before loading new batch
        self._cleanup_memory()

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

        # Show batch sidebar FIRST, then load files
        self._batch_current_index = 0
        self._is_first_file_in_batch = True  # First file in new batch gets fit width
        self._background_loading = True  # Prevent eventFilter during loading
        self.batch_sidebar.setVisible(True)  # Show sidebar before loading
        QApplication.processEvents()  # Ensure sidebar is rendered
        self.batch_sidebar.set_files(pdf_files, folder_path)
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

        # Store pending zone info - will be loaded after set_pages() completes
        self._pending_zone_file = file_path
        self._pending_zone_index = original_idx

        self._load_pdf(file_path)

    def _load_zones_after_thumbnails(self):
        """Load zones after thumbnails have painted"""
        if not hasattr(self, '_pending_zone_file') or not self._pending_zone_file:
            return
        file_path = self._pending_zone_file
        original_idx = self._pending_zone_index
        self._pending_zone_file = None

        # Restore zones for this file
        self.settings_panel.load_per_file_custom_zones(file_path)
        self.preview.load_per_file_zones(file_path)
        self.preview.set_file_index(original_idx, len(self._batch_files))

        # Clear zone loading flag (may not be cleared if no zones existed)
        self.preview.before_panel._zones_loading = False

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

            # Store pending zone info - will be loaded after set_pages() completes
            self._pending_zone_file = file_path
            self._pending_zone_index = self._batch_current_index

            self._load_pdf(file_path)

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

            # Store pending zone info - will be loaded after set_pages() completes
            self._pending_zone_file = file_path
            self._pending_zone_index = self._batch_current_index

            self._load_pdf(file_path)

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
            # reset_paths=True to clear _batch_base_dir since we're closing batch mode
            self.preview.clear_per_file_zones(reset_paths=True)
            self.settings_panel.clear_per_file_custom_zones(reset_paths=True)
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

        # Clear preview and thumbnails
        self.preview.set_pages([])
        self.preview.clear_thumbnails()  # Also clear thumbnail panel
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
        # Free memory from previous file before loading new one
        self._cleanup_memory()

        try:
            # Set flag FIRST to prevent eventFilter crashes during processEvents
            self._background_loading = True
            self._stop_loading_flag = True  # Stop any ongoing background loading

            self.statusBar().showMessage("Đang tải PDF...")
            QApplication.processEvents()

            if self._pdf_handler:
                self._pdf_handler.close()

            self._pdf_handler = PDFHandler(file_path)
            self._current_file_path = file_path

            # Set current file path for per-file zone tracking
            self.preview.set_current_file_path(file_path)

            # Get page count
            self._total_pages = min(self._pdf_handler.page_count, self.MAX_PREVIEW_PAGES)
            num_pages = self._total_pages
            self._all_pages = []
            initial_pages = min(self.INITIAL_LOAD_PAGES, num_pages)

            # Set total pages for detection progress (before loading starts)
            self.preview.set_detection_total_pages(self._total_pages)

            # Update page navigation with total pages
            self.page_spin.setMaximum(self._pdf_handler.page_count)
            self.page_spin.setValue(1)
            self.total_pages_label.setText(str(self._pdf_handler.page_count))

            # Calculate paths first (lightweight)
            source_path = Path(file_path)
            if self._batch_mode:
                output_dir = self._batch_output_dir or str(source_path.parent)
                settings = self.settings_panel.get_settings()
                pattern = settings.get('filename_pattern', '{gốc}_clean.pdf')
                output_name = pattern.replace('{gốc}', source_path.stem)
                dest_path = Path(output_dir) / output_name
            else:
                file_folder = str(source_path.parent)
                file_path_str = str(source_path)  # Absolute path for single file
                self._batch_base_dir = file_path_str  # Use file path as source
                output_dir = file_folder
                self.settings_panel.set_output_path(output_dir)
                dest_path = source_path.parent / f"{source_path.stem}_clean{source_path.suffix}"
                # Set batch base dir for zone persistence (use file path for single file mode)
                self.preview.set_batch_base_dir(file_path_str)
                self.settings_panel.set_batch_base_dir(file_path_str)
                # Load persisted zones for this specific file
                self.preview.load_persisted_zones(file_path_str)
                self.settings_panel.load_persisted_custom_zones(file_path_str)
                # Set pending zone file for zone restoration after pages load
                self._pending_zone_file = str(file_path)
                self._pending_zone_index = 0

            # Store for deferred setup
            self._pending_file_path = str(file_path)
            self._pending_dest_path = str(dest_path)

            # Phase 1A: Load ONLY thumbnails first (fast at 36 DPI)
            self.preview.start_thumbnail_loading(num_pages)
            for i in range(initial_pages):
                thumb_img = self._pdf_handler.render_page(i, dpi=self.THUMBNAIL_DPI)
                if thumb_img is not None:
                    self.preview.add_thumbnail(i, thumb_img)

            # Force thumbnails to paint NOW before any preview work
            self._background_loading = False
            self.preview.repaint_thumbnails()
            QApplication.processEvents()

            # Always apply saved zoom when loading files
            self._fit_after_initial_load = True

            # Phase 1B: Load first N preview pages via QTimer (non-blocking)
            self._stop_loading_flag = False
            self._initial_preview_index = 0
            self._initial_preview_count = initial_pages
            self._thumb_load_index = initial_pages
            self._bg_load_index = initial_pages
            self._thumb_updates_paused = False  # Reset flag for new load

            # Start loading initial preview pages (deferred to allow thumbnails to show)
            QTimer.singleShot(10, self._load_initial_preview_pages)

            # Start loading remaining thumbnails in parallel
            # Use 500ms delay to ensure initial thumbnails are fully painted before pausing updates
            if num_pages > initial_pages:
                QTimer.singleShot(500, self._load_remaining_thumbnails)
            else:
                self.preview.finish_thumbnail_loading()

        except Exception as e:
            self._background_loading = False
            self._loading_overlay.hide()
            self.preview.hide_progress_bar()
            QMessageBox.critical(self, "Lỗi", f"Không thể mở file:\n{e}")

    def _load_initial_preview_pages(self):
        """Load initial preview pages one at a time via QTimer (non-blocking)"""
        if self._stop_loading_flag or not self._pdf_handler:
            return

        i = self._initial_preview_index
        if i >= self._initial_preview_count:
            # Done loading initial pages, now setup preview
            self._setup_preview_after_initial_load()
            return

        # Load one preview page
        preview_img = self._pdf_handler.render_page(i, dpi=self.PREVIEW_DPI)
        if preview_img is not None:
            self._all_pages.append(preview_img)

        self._initial_preview_index += 1

        # Schedule next page with small delay to yield to UI
        QTimer.singleShot(5, self._load_initial_preview_pages)

    def _setup_preview_after_initial_load(self):
        """Setup preview after initial pages are loaded"""
        if not hasattr(self, '_pending_file_path') or not self._pending_file_path:
            return

        # Set file paths on preview (lightweight)
        self.preview.set_file_paths(self._pending_file_path, self._pending_dest_path)

        # Set current file path on settings panel (for per-file zone tracking)
        self.settings_panel.set_current_file_path(self._pending_file_path)

        # Set initial pages - this rebuilds the graphics scene
        self.preview.set_pages(self._all_pages)

        # Re-apply Zone Chung after set_pages clears _per_page_zones
        self.settings_panel._emit_zones()

        # Apply text protection settings (triggers processing with zones)
        text_protection_opts = self.settings_panel.get_text_protection_options()
        self.preview.set_text_protection(text_protection_opts)

        # Load Zone Riêng (per-file zones) AFTER set_pages and Zone Chung
        # This must happen here, not via timer, to avoid race condition
        if hasattr(self, '_pending_zone_file') and self._pending_zone_file:
            file_path = self._pending_zone_file
            original_idx = getattr(self, '_pending_zone_index', 0)
            self._pending_zone_file = None

            # Restore zones for this file
            self.settings_panel.load_per_file_custom_zones(file_path)
            self.preview.load_per_file_zones(file_path)
            self.preview.set_file_index(original_idx, len(self._batch_files) if self._batch_files else 1)

            # Clear zone loading flag (may not be cleared if no zones existed)
            self.preview.before_panel._zones_loading = False

            # Update zone counts display
            self._update_zone_counts()

        # Force thumbnails to repaint AFTER preview setup (in case layout changed)
        QTimer.singleShot(10, self.preview.repaint_thumbnails)

        # Reset to first page
        self.preview.set_current_page(0)

        # Apply fit width if needed
        if hasattr(self, '_fit_after_initial_load') and self._fit_after_initial_load:
            QTimer.singleShot(50, self._fit_first_page_width)

        # Clear pending values
        self._pending_file_path = None
        self._pending_dest_path = None

        # Start background loading of remaining preview pages
        if self._bg_load_index < self._total_pages:
            QTimer.singleShot(20, self._load_remaining_pages_parallel)

        # Update UI state to enable Clean button now that PDF is loaded
        self._update_ui_state()

    def _fit_first_page_width(self):
        """Apply saved zoom or fit width for first page - called after layout update"""
        if self._all_pages:
            # Use saved zoom if available, otherwise fit to width
            if hasattr(self, '_saved_zoom_percent') and self._saved_zoom_percent > 0:
                zoom = self._saved_zoom_percent / 100.0
                self.preview.set_zoom(zoom)
                self._user_zoomed = True  # Preserve this zoom for subsequent files
                # Center page after setting zoom
                self.preview._scroll_to_page(0, align_top=False)
            else:
                # scroll_to_page=False để center trang đầu tiên
                self.preview.zoom_fit_width(0, scroll_to_page=False)
            self._update_zoom_combo()
            # Mark first file processed - subsequent files preserve zoom
            self._is_first_file_in_batch = False

    def _load_remaining_thumbnails(self):
        """Load remaining thumbnails in background using QTimer"""
        if self._stop_loading_flag or not self._pdf_handler:
            self.preview.finish_thumbnail_loading()
            return

        # Check if done with thumbnails
        if self._thumb_load_index >= self._total_pages:
            self.preview.finish_thumbnail_loading()
            return

        # NO pause_updates - let thumbnails be visible even with some flickering

        # Load one thumbnail
        i = self._thumb_load_index
        thumb_img = self._pdf_handler.render_page(i, dpi=self.THUMBNAIL_DPI)
        if thumb_img is not None:
            self.preview.add_thumbnail(i, thumb_img)

        self._thumb_load_index += 1

        # Schedule next thumbnail with small delay
        QTimer.singleShot(5, self._load_remaining_thumbnails)

    def _load_remaining_pages_parallel(self):
        """Start background loading of preview pages (runs in parallel with thumbnails)"""
        if self._stop_loading_flag or not self._pdf_handler:
            return

        self._background_loading = True

        # Show progress bar immediately
        self.preview.show_progress_bar()
        initial_progress = int(self._bg_load_index * 100 / self._total_pages)
        self.preview.set_progress(initial_progress)

        # Start loading chain
        QTimer.singleShot(15, self._load_next_background_page)

    def _load_next_background_page(self):
        """Load one page at a time with delay to keep UI responsive"""
        # Check if should stop
        if self._stop_loading_flag or not self._pdf_handler:
            self._finish_background_loading()
            return

        # Check if done
        if self._bg_load_index >= self._total_pages:
            self._finish_background_loading()
            return

        # Load current page
        i = self._bg_load_index
        preview_img = self._pdf_handler.render_page(i, dpi=self.PREVIEW_DPI)
        if preview_img is not None:
            self._all_pages.append(preview_img)
            self.preview.add_preview_page(preview_img)

        # Update progress
        progress = int((i + 1) * 100 / self._total_pages)
        self.preview.set_progress(progress)

        # Update status periodically
        if (i + 1) % 10 == 0:
            self.statusBar().showMessage(f"Đang tải trang {i+1}/{self._total_pages}...")

        # Move to next page
        self._bg_load_index += 1

        # Schedule next page with small delay (15ms) to yield to UI
        QTimer.singleShot(15, self._load_next_background_page)

    def _finish_background_loading(self):
        """Cleanup after background loading completes or stops"""
        self.preview.hide_progress_bar()
        self._background_loading = False

        # Rebuild preview scene with all loaded pages
        if not self._stop_loading_flag and self._total_pages > 0:
            self.preview.refresh_scene()
            self.statusBar().showMessage(f"Đã tải xong {self._total_pages} trang")

    def _on_page_load_requested(self, page_index: int):
        """Handle request to load a specific page (clicked on unloaded thumbnail)"""
        if not self._pdf_handler:
            return

        loaded_count = len(self._all_pages)
        if page_index < loaded_count:
            # Already loaded, just scroll preview (not thumbnail - user clicked it)
            self.preview.set_current_page(page_index, scroll_thumbnail=False)
            self.page_spin.blockSignals(True)
            self.page_spin.setValue(page_index + 1)
            self.page_spin.blockSignals(False)
            return

        # Show loading spinner
        preview_rect = self.preview.geometry()
        preview_pos = self.preview.mapTo(self, self.preview.rect().topLeft())
        self._loading_overlay.setGeometry(
            preview_pos.x(), preview_pos.y(),
            preview_rect.width(), preview_rect.height()
        )
        self._loading_overlay.set_text(f"Đang tải trang {page_index + 1}...")
        self._loading_overlay.show()
        self._loading_overlay.raise_()
        QApplication.processEvents()

        # Load pages from current loaded count up to requested page
        for i in range(loaded_count, page_index + 1):
            if self._stop_loading_flag:
                break

            preview_img = self._pdf_handler.render_page(i, dpi=self.PREVIEW_DPI)
            if preview_img is not None:
                self._all_pages.append(preview_img)
                self.preview.add_preview_page(preview_img)

            # Update progress
            self._loading_overlay.set_text(f"Đang tải trang {i + 1}/{page_index + 1}...")
            QApplication.processEvents()

        # Hide spinner
        self._loading_overlay.hide()

        # Scroll to requested page (not thumbnail - user clicked it)
        self.preview.set_current_page(page_index, scroll_thumbnail=False)
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(page_index + 1)
        self.page_spin.blockSignals(False)

        # Continue background loading for remaining pages if not already loading
        remaining_start = len(self._all_pages)
        if remaining_start < self._total_pages and not self._background_loading:
            self._stop_loading_flag = False
            QTimer.singleShot(50, lambda: self._load_remaining_pages(remaining_start))

    def _on_prev_page(self):
        if self.page_spin.value() > 1:
            self.page_spin.setValue(self.page_spin.value() - 1)

    def _on_next_page(self):
        if self.page_spin.value() < self._total_pages:
            self.page_spin.setValue(self.page_spin.value() + 1)
    
    def _on_page_changed(self, value):
        """Handle page number change"""
        if not self._pdf_handler:
            return

        max_loaded = len(self._all_pages)
        if max_loaded == 0:
            return

        # Clamp to valid total pages range
        total_pages = self._total_pages
        clamped_value = max(1, min(value, total_pages))
        if clamped_value != value:
            self.page_spin.blockSignals(True)
            self.page_spin.setValue(clamped_value)
            self.page_spin.blockSignals(False)
            value = clamped_value

        page_index = value - 1  # 0-based index

        # If page not loaded yet, trigger loading
        if page_index >= max_loaded:
            self._on_page_load_requested(page_index)
            return

        # Update preview - works for both continuous and single page mode
        self.preview.set_current_page(page_index)

        # Update prev/next button states
        self.prev_page_btn.setEnabled(value > 1)
        self.next_page_btn.setEnabled(value < total_pages)

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
        """Zoom in by 5%, snapping to nearest multiple of 5"""
        self._user_zoomed = True
        current = int(self.preview.before_panel.view._zoom * 100)
        # Ceil to nearest 5, then add 5
        import math
        next_level = math.ceil(current / 5) * 5 + 5
        # Clamp to max 400%
        next_level = min(next_level, 400)
        self.preview.set_zoom(next_level / 100.0)
        self._update_zoom_combo()

    def _on_zoom_out(self):
        """Zoom out by 5%, snapping to nearest multiple of 5"""
        self._user_zoomed = True
        current = int(self.preview.before_panel.view._zoom * 100)
        # Floor to nearest 5, then subtract 5
        prev_level = (current // 5) * 5 - 5
        # Clamp to min 25%
        prev_level = max(prev_level, 25)
        self.preview.set_zoom(prev_level / 100.0)
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

    def _on_zoom_changed_from_scroll(self, zoom: float):
        """Handle zoom change from scroll wheel - update combo and save to config"""
        try:
            self._user_zoomed = True
            self.zoom_combo.blockSignals(True)
            self.zoom_combo.setCurrentText(f"{int(zoom * 100)}%")
            self.zoom_combo.blockSignals(False)
            # Save to config
            self._saved_zoom_percent = int(zoom * 100)
            from core.config_manager import get_config_manager
            ui_config = get_config_manager().get_ui_config()
            ui_config['last_zoom_percent'] = self._saved_zoom_percent
            get_config_manager().save_ui_config(ui_config)
        except:
            pass

    def _on_zones_changed(self, zones: List[Zone]):
        self.preview.set_zones(zones)
        self._update_zone_counts()

        # Save per-file zones when Zone Riêng changes - ALWAYS save if has Zone Riêng
        # (regardless of _batch_mode since user might be in single file mode within folder)
        has_zone_rieng = any(z.page_filter == 'none' for z in zones)
        if has_zone_rieng:
            # Use QTimer to defer save until after set_zones completes
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(100, lambda: self.preview.save_per_file_zones())

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

        # Check which values changed
        new_counts = (zone_chung, zone_rieng_file, zone_rieng_total)
        old_chung, old_rieng_file, old_rieng_total = self._prev_zone_counts
        chung_changed = zone_chung != old_chung
        rieng_changed = (zone_rieng_file != old_rieng_file) or (zone_rieng_total != old_rieng_total)
        self._prev_zone_counts = new_counts

        # Flash effect: highlight only the changed value(s)
        if chung_changed or rieng_changed:
            self._start_zone_flash(zone_chung, zone_rieng_file, zone_rieng_total, chung_changed, rieng_changed)
        else:
            self.zone_count_label.setText(
                f"Zone chung: <b>{zone_chung}</b>; Zone riêng: <b>{zone_rieng_file}/{zone_rieng_total}</b>"
            )

    def _start_zone_flash(self, zone_chung: int, zone_rieng_file: int, zone_rieng_total: int,
                          chung_changed: bool, rieng_changed: bool):
        """Start flash animation with gradual fade for changed values"""
        # Cancel previous timer if running
        if self._zone_flash_timer:
            self._zone_flash_timer.stop()

        # Store flash state
        self._flash_chung = chung_changed
        self._flash_rieng = rieng_changed
        self._flash_step = 0
        # Fade steps: opacity from 1.0 to 0.0 (8 steps for smoother fade)
        self._flash_opacities = [1.0, 0.85, 0.7, 0.55, 0.4, 0.25, 0.1, 0.0]

        # Update label with initial flash
        self._update_zone_flash_label()

        # Start fade timer (2400ms total / 8 steps = 300ms per step)
        self._zone_flash_timer = QTimer()
        self._zone_flash_timer.timeout.connect(self._fade_zone_flash_step)
        self._zone_flash_timer.start(300)

    def _fade_zone_flash_step(self):
        """Handle one step of the fade animation"""
        self._flash_step += 1
        if self._flash_step >= len(self._flash_opacities):
            # Animation complete
            self._zone_flash_timer.stop()
            self._clear_zone_count_flash()
        else:
            self._update_zone_flash_label()

    def _update_zone_flash_label(self):
        """Update label with current flash style (like selected page thumbnail)"""
        zone_chung, zone_rieng_file, zone_rieng_total = self._prev_zone_counts
        opacity = self._flash_opacities[self._flash_step]

        # Style like selected page number: #3B82F6 background, white text
        bg_color = f"rgba(59,130,246,{opacity})"
        # Text color fades from white to normal gray
        text_color = f"rgba(255,255,255,{opacity})" if opacity > 0.3 else "#374151"

        # Build HTML with flash on changed values only
        if self._flash_chung:
            chung_html = f"<span style='background-color:{bg_color};color:{text_color};'><b> {zone_chung} </b></span>"
        else:
            chung_html = f"<b>{zone_chung}</b>"

        if self._flash_rieng:
            rieng_html = f"<span style='background-color:{bg_color};color:{text_color};'><b> {zone_rieng_file}/{zone_rieng_total} </b></span>"
        else:
            rieng_html = f"<b>{zone_rieng_file}/{zone_rieng_total}</b>"

        self.zone_count_label.setText(f"Zone chung: {chung_html}; Zone riêng: {rieng_html}")

    def _clear_zone_count_flash(self):
        """Remove flash background from zone count values"""
        zone_chung, zone_rieng_file, zone_rieng_total = self._prev_zone_counts
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

    def _toggle_draw_protect(self):
        """Toggle protection zone (+) draw mode.
        Keyboard shortcuts: Cmd+A (macOS), Alt+A (Windows), +, =
        """
        if self._current_draw_mode == 'protect':
            self._set_draw_mode_with_filter(None)
        else:
            self._set_draw_mode_with_filter('protect')

    def _toggle_draw_remove(self):
        """Toggle removal zone (-) draw mode.
        Keyboard shortcuts: Cmd+S (macOS), Alt+S (Windows), -
        """
        if self._current_draw_mode == 'remove':
            self._set_draw_mode_with_filter(None)
        else:
            self._set_draw_mode_with_filter('remove')

    def _set_draw_mode_with_filter(self, mode):
        """Set draw mode and update all UI components.

        Args:
            mode: 'remove', 'protect', or None
        """
        # Update filter to 'Từng trang' when entering draw mode
        if mode is not None:
            self.settings_panel.set_filter('none')
            self.compact_toolbar.set_filter_state('none')

        # Update internal state first
        self._current_draw_mode = mode

        # Update all UI components
        self.settings_panel.set_draw_mode(mode)
        self.settings_panel._current_draw_mode = mode
        self.compact_toolbar.set_draw_mode_state(mode)

        # Update preview
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
            else:
                # Clear Zone riêng for all files in folder
                self.preview.before_panel.clear_per_file_zones()
                self.preview.clear_zone_rieng()
        elif reset_type == 'chung':
            # Clear Zone chung for all pages (keep Zone riêng)
            self.preview.clear_zone_chung()
        elif scope == 'file':
            # Clear zones only for current file
            self.preview.clear_all_zones()
        else:
            # Clear all zones (folder scope)
            self.preview.clear_all_zones()

        # Persist zone changes to disk (works for both batch and single file mode)
        # _batch_base_dir is set to folder path (batch) or file path (single)
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
        # Save Zone riêng (Tự do zones) - works for both batch and single file mode
        # _batch_base_dir is set to folder path (batch) or file path (single)
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

        # Add cached protected regions from preview to settings (for consistency)
        if hasattr(self.preview, '_cached_regions') and self.preview._cached_regions:
            from core.parallel_processor import serialize_protected_regions
            settings['preview_cached_regions'] = serialize_protected_regions(
                self.preview._cached_regions
            )
            settings['preview_dpi'] = 120  # Preview DPI

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

        # Save current file's zones to per_file_zones before batch processing
        # This ensures the current file's Zone Riêng is included in per_file_zones
        current_file = self._pdf_handler.pdf_path if self._pdf_handler else None
        if current_file:
            self.preview.before_panel.save_per_file_zones(current_file, persist=False)

        # Get zones from preview - collect ALL zones from ALL pages with target_page set
        # This ensures Zone Riêng (per-page zones) work correctly in batch mode
        zones = self.preview.get_all_zones_for_batch_processing()

        # Get per-file zones for batch processing (Zone Riêng for each file)
        per_file_zones = self.preview.get_per_file_zones_for_batch()

        # Add cached protected regions from preview to settings (for consistency)
        if hasattr(self.preview, '_cached_regions') and self.preview._cached_regions:
            from core.parallel_processor import serialize_protected_regions
            settings['preview_cached_regions'] = serialize_protected_regions(
                self.preview._cached_regions
            )
            settings['preview_dpi'] = 120  # Preview DPI
            settings['preview_file_path'] = current_file  # File these regions belong to

        # Show batch progress dialog
        self._show_batch_progress_dialog(checked_files, output_dir, zones, settings, per_file_zones)
    
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

    def _cleanup_memory(self):
        """Free memory after processing completes"""
        import gc

        # Clear processed pages (keep original _pages for re-processing if needed)
        if hasattr(self, 'preview') and hasattr(self.preview, '_processed_pages'):
            self.preview._processed_pages.clear()

        # Clear after panel pages (result display)
        if hasattr(self, 'preview') and hasattr(self.preview, 'after_panel'):
            self.preview.after_panel._pages.clear()
            self.preview.after_panel._page_items.clear()
            self.preview.after_panel.scene.clear()

        # Clear PDF page cache
        if hasattr(self, '_pdf_handler') and self._pdf_handler:
            self._pdf_handler.clear_cache()

        # Clear cached detection regions
        if hasattr(self, 'preview') and hasattr(self.preview, '_cached_regions'):
            self.preview._cached_regions.clear()

        # Force garbage collection
        gc.collect()

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
                                    zones: List[Zone], settings: dict,
                                    per_file_zones: dict = None):
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

        # Worker info label
        self._batch_worker_label = QLabel("Processes: đang tính...")
        self._batch_worker_label.setStyleSheet("color: #6B7280; font-size: 12px;")
        layout.addWidget(self._batch_worker_label)

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
            files, self._batch_base_dir, output_dir, zones, settings, self._batch_page_counts,
            per_file_zones
        )
        self._batch_process_thread.progress.connect(self._on_batch_progress)
        self._batch_process_thread.file_progress.connect(self._on_batch_page_progress)
        self._batch_process_thread.total_progress.connect(self._on_batch_total_progress)
        self._batch_process_thread.finished.connect(self._on_batch_finished)
        self._batch_process_thread.worker_info.connect(self._on_batch_worker_info)

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

    def _on_batch_worker_info(self, num_workers: int):
        """Update worker count display"""
        self._batch_worker_label.setText(f"Đang dùng {num_workers} processes song song (CPU/RAM ≤80%)")
    
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
        # Save for both batch mode AND single file mode (when _batch_base_dir is set)
        if self._batch_base_dir:
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

        # Save window maximized state
        ui_config['window_maximized'] = self.isMaximized()

        # Save window size (only if not maximized)
        if not self.isMaximized():
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

        # Save toolbar visibility (hidden or shown)
        toolbar_visible = self.settings_panel.isVisible() or self.compact_toolbar.isVisible()
        ui_config['toolbar_visible'] = toolbar_visible

        # Save thumbnail panel collapsed state
        ui_config['thumbnail_collapsed'] = self.preview.is_thumbnail_collapsed()

        # Save text protection enabled state
        ui_config['text_protection_enabled'] = self.settings_panel.text_protection_cb.isChecked()

        get_config_manager().save_ui_config(ui_config)

    def _restore_window_state(self):
        """Restore window size, sidebar width, zoom level and panel state from config"""
        from core.config_manager import get_config_manager
        ui_config = get_config_manager().get_ui_config()

        # Restore window size first
        width = ui_config.get('window_width', 1200)
        height = ui_config.get('window_height', 800)
        self.resize(width, height)

        # Restore window maximized state
        if ui_config.get('window_maximized', False):
            self.showMaximized()

        # Restore sidebar width (will be applied when sidebar becomes visible)
        self._saved_sidebar_width = ui_config.get('sidebar_width', BatchSidebar.EXPANDED_WIDTH)

        # Restore zoom level (will be applied when file is loaded)
        self._saved_zoom_percent = ui_config.get('last_zoom_percent', 100)

        # Restore after panel (Đích) collapsed state
        if ui_config.get('after_panel_collapsed', False):
            self.preview._toggle_after_panel()  # Toggle to collapse

        # Restore toolbar visibility (hidden or shown)
        # Default is True (visible)
        if not ui_config.get('toolbar_visible', True):
            self._toggle_settings()  # Toggle to hide

        # Restore thumbnail panel collapsed state
        if ui_config.get('thumbnail_collapsed', False):
            if not self.preview.is_thumbnail_collapsed():
                self.preview.toggle_thumbnail_panel()  # Toggle to collapse

        # Restore text protection enabled state
        if ui_config.get('text_protection_enabled', False):
            self.settings_panel.text_protection_cb.setChecked(True)
            # Update options and apply to preview directly (signal might not fire correctly)
            self.settings_panel._text_protection_options.enabled = True
            self.preview.set_text_protection(self.settings_panel._text_protection_options)

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
        # Skip during loading to prevent crashes - check FIRST before any Qt operations
        if getattr(self, '_background_loading', False):
            return False  # Don't filter, just pass through

        try:
            from PyQt5.QtCore import QEvent

            if event.type() == QEvent.MouseButtonPress and self._current_draw_mode is not None:
                # Guard against accessing uninitialized widgets
                if not hasattr(self, 'settings_panel') or self.settings_panel is None:
                    return super().eventFilter(obj, event)
                if not hasattr(self.settings_panel, 'zone_selector') or self.settings_panel.zone_selector is None:
                    return super().eventFilter(obj, event)

                click_pos = event.globalPos()

                # Only cancel draw mode when clicking on corner or edge icons
                # (clicking on custom icon is handled by zone_selector toggle)
                corner_icon = self.settings_panel.zone_selector.corner_icon
                edge_icon = self.settings_panel.zone_selector.edge_icon

                if corner_icon is None or edge_icon is None:
                    return super().eventFilter(obj, event)

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
        except Exception:
            pass  # Ignore errors in eventFilter to prevent crashes

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

