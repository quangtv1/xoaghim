# Codebase Summary - Xóa Vết Ghim PDF v1.1.23

## Overview

**Total Lines of Code:** ~17,800+ LOC (excluding tests)
**Total Files:** 29 Python modules + main.py
**Test Coverage:** 6 test files, 1,546 test LOC, 108 test cases (98%+ pass rate)
**Architecture:** PyQt5 MVC with signal/slot pattern
**Last Updated:** 2026-01-27

## Directory Structure

```
xoaghim/
├── main.py                    (270 lines)     - Application entry point
├── core/                      (3,146 LOC)     - Processing engine
├── ui/                        (12,620 LOC)    - User interface
├── tests/                     (1,546 LOC)     - Unit tests
├── utils/                     (360 LOC)       - Helper utilities
└── docs/                      (documentation)
```

## Core Module (2,146 LOC)

Low-level processing engine with AI-powered detection and staple removal.

### Files

| File | Lines | Purpose |
|------|-------|---------|
| `processor.py` | 500+ | Core staple removal with 7-step algorithm + content protection |
| `layout_detector.py` | 500+ | Multi-model AI detection (ONNX/PyTorch/PaddleOCR/Detectron2) |
| `zone_optimizer.py` | 315 | Hybrid Polygon Algorithm using Shapely for safe zone calculation |
| `pdf_handler.py` | 223 | PDF I/O with PyMuPDF, rendering + LRU cache |
| `config_manager.py` | 271 | JSON persistence for zones, UI state, auto-recovery |
| `resource_manager.py` | 118 | CPU/RAM monitoring via psutil, optimal worker calculation |
| `parallel_processor.py` | 300+ | ProcessPoolExecutor for batch processing, DPI scaling |
| `__init__.py` | 1 | Module initialization |
| **Total** | **2,146** | |

### Key Classes

#### processor.py (500+ LOC)
- **Zone** - Dataclass defining removal/protection zones with hybrid sizing
  - `to_pixels()` - Convert percentage/hybrid zones to pixel coordinates
  - `is_applicable()` - Check if zone applies to given page
- **StapleRemover** - Core removal engine with 7-step algorithm
  - `process_image()` - Main pipeline for multiple zones
  - `process_zone()` - Process single zone with scaling
  - `remove_staples()` - Artifact detection and removal
  - `protect_signatures()` - Red/blue color preservation
  - `apply_protected_regions()` - AI-based region exclusion
  - `get_background_color()` - Background sampling from safe zone

#### layout_detector.py (500+ LOC)
- **LayoutDetector (base)** - Abstract interface for layout detection
  - `create(backend)` - Factory method for detector creation
  - Implementations: ONNX, PyTorch, PaddleOCR, Detectron2, RemoteServer
- **YOLODocLayNetONNXDetector** - Primary ONNX-based detector
  - `detect()` - Run YOLO DocLayNet inference
  - Auto model download, CPU-friendly inference
  - Results: text, title, list, table, figure, caption, header, footer, etc.

#### zone_optimizer.py (315 LOC)
- **SafeZone** - Dataclass for safe zone representation
- **HybridPolygonOptimizer** - Shapely-based geometry calculations
  - `optimize()` - Calculate safe zones
  - `subtract()` - Subtract protected regions using Shapely
  - Polygon simplification and validation
  - DPI-aware coordinate scaling

#### config_manager.py (234 LOC)
- **ConfigManager** - Persistent settings
  - `load_config()`, `save_config()` - JSON I/O
  - Cross-platform paths (Windows/macOS/Linux)
  - Crash recovery for files, folders, zones
  - Settings: output_dir, dpi, filter_mode, etc.

#### pdf_handler.py (222 LOC)
- **PDFHandler** - PDF reading with caching
  - `render_page()` - Convert PDF page to image
  - Page caching to reduce re-renders
- **PDFExporter** - PDF writing
  - `export_pdf()` - Write processed pages to PDF
  - DPI adjustment, JPEG compression

## UI Module (13,620 LOC)

PyQt5-based GUI with advanced widgets and real-time preview.

### Files

| File | Lines | Purpose |
|------|-------|---------|
| `continuous_preview.py` | 3,400+ | Multi-page preview with zone overlay, LoadingOverlay |
| `main_window.py` | 3,316+ | Main application orchestrator, menu/toolbar/status bar |
| `settings_panel.py` | 1,985+ | Zone config UI, mode switching (Global/File/Page) |
| `batch_sidebar.py` | 800+ | File list with name/page filtering, sorting |
| `batch_preview.py` | 615+ | Batch processing container and results display |
| `zone_selector.py` | 523+ | Visual zone picker with PaperIcon |
| `text_protection_dialog.py` | 487+ | AI protection settings and configuration dialog |
| `preview_widget.py` | 454+ | Before/after synchronized preview panels |
| `compact_toolbar_icons.py` | 357+ | Custom QPainter icon rendering (20+ icon types) |
| `zone_item.py` | 331+ | Draggable/resizable zone rectangles with handles |
| `compact_settings_toolbar.py` | 294+ | Collapsed toolbar UI with zone toggles |
| `page_thumbnail_sidebar.py` | TBD | Page thumbnail navigation |
| `undo_manager.py` | 57 | Action stack management (79 max actions) |
| `__init__.py` | 1 | Module initialization |
| **Total** | **13,620** | |

### Key Classes

#### main_window.py (3,316 LOC)
- **MainWindow** - QMainWindow orchestrator
  - Layout: MenuBar → MainToolbar → Splitter(Sidebar, Preview, SettingsPanel)
  - File drag & drop handling
  - Menu actions: File, Edit, View, Tools, Help
  - Progress bar for batch operations
  - Undo/Redo shortcuts (Ctrl+Z, Ctrl+Shift+Z)
  - Zone counter display on status bar
- **HoverMenuButton** - Menu button with hover behavior
- **MenuHoverManager** - Global hover menu coordination

#### continuous_preview.py (3,400 LOC)
- **ContinuousPreviewWidget** - Multi-page preview
  - Split view: original | processed
  - QGraphicsView for interactive zone display
  - `render_page()` - Generate preview image
  - `set_zones()` - Update zone overlays
  - Synchronized scroll/zoom
  - Zoom preservation across file switches
- **LoadingOverlay** - Spinner for large PDFs (>20 pages)

#### settings_panel.py (1,985 LOC)
- **SettingsPanel** - Zone configuration UI
  - Zone preset buttons (8 zones)
  - Custom draw mode toggle
  - Hybrid sizing controls (% and pixels)
  - Threshold/sensitivity sliders
  - Mode tabs: Global | Per-File | Per-Page
  - Delete zone controls (global/per-file/per-page)

#### batch_sidebar.py (800 LOC)
- **BatchSidebar** - File list with UI
  - File filter by name (search box)
  - File filter by page count
  - Sort by name/modification time
  - File selection with keyboard nav
  - Double-click to select file
  - Visual feedback for current selection

#### zone_selector.py (523 LOC)
- **ZoneSelector** - Visual zone picker
  - Preset zone buttons arranged in 2x4 grid
  - Custom draw mode activation
  - Zone name/description display
  - Zone configuration preview

#### preview_widget.py (454 LOC)
- **PreviewWidget** - Synchronized before/after
  - Left panel: original PDF
  - Right panel: processed result
  - Synchronized scrolling
  - Synchronized zoom
  - QScrollArea with QLabel for image display

#### zone_item.py (331 LOC)
- **ZoneItem** - Draggable/resizable rectangle
  - Inherits QGraphicsItem
  - Mouse press/move/release handlers
  - Resize handles at corners and edges
  - Selection state visualization
  - Delete key handling

#### undo_manager.py (57 LOC)
- **UndoManager** - Action history stack
  - Action stack (max 79 items)
  - Undo/Redo functionality
  - Signal emission for state changes

## Utilities Module (359 LOC)

### Files

| File | Lines | Purpose |
|------|-------|---------|
| `geometry.py` | 359 | Polygon/geometry helper functions |
| `__init__.py` | 1 | Module initialization |
| **Total** | **360** | |

### Key Functions in geometry.py

- `point_in_polygon()` - Ray casting algorithm
- `polygon_area()` - Shoelace formula
- `line_intersection()` - 2D line segment intersection
- `polygon_union()` - Merge overlapping polygons
- `polygon_difference()` - Subtract zones
- 16+ geometry utility functions

## Tests Module (1,546 LOC)

Comprehensive unit test suite with 108 test cases (98%+ pass rate).

### Files

| File | Tests | Lines | Coverage |
|------|-------|-------|----------|
| `test_processor.py` | 20+ | 299 | Core removal logic |
| `test_zone_undo.py` | 15+ | 351 | Undo/Redo functionality |
| `test_compact_toolbar.py` | 25+ | 409 | UI toolbar |
| `test_geometry.py` | 20+ | 257 | Polygon operations |
| `test_layout_detector.py` | 10+ | 85 | AI detection |
| `test_zone_optimizer.py` | 9+ | 145 | Zone calculations |
| `__init__.py` | - | 0 | - |
| **Total** | **108** | **1,546** | 98%+ passing |

## Architecture Patterns

### Signal/Slot Communication
- **PyQt5 signals** for decoupled component communication
- Prevents circular imports and tight coupling
- Examples:
  - `MainWindow` → `ContinuousPreview` (zone changes)
  - `SettingsPanel` → `MainWindow` (mode switches)
  - `BatchSidebar` → `PreviewWidget` (file selection)

### Model-View-Controller (MVC)
- **Model:** Core module (processor, layout_detector, zone_optimizer)
- **View:** UI module (windows, panels, widgets)
- **Controller:** Main window coordinates interactions

### Threading
- **Main thread:** UI operations via Qt event loop
- **Background thread:** PDF processing via QThread
  - Heavy operations: PDF rendering, AI inference
  - Non-blocking UI during batch processing

### Caching Strategy
- **PDF page cache:** Store rendered pages to avoid re-renders
- **Image cache:** Smart purging for large PDFs (>100 pages)
- **Configuration cache:** Lazy load on demand

### State Management
- **QSettings:** Persistent application configuration
- **File-based JSON:** Zone configurations
- **Memory-based:** Current session state (selected file, zoom level)

## Data Flow

### Single File Processing
```
User Input (zone selection)
    ↓
SettingsPanel (zone configuration)
    ↓
ContinuousPreviewWidget (real-time preview)
    ↓
StapleRemover.remove() (core processing)
    ├── DocumentLayoutDetector.detect() (AI inference)
    ├── protect_signatures() (red/blue preservation)
    ├── remove_staples() (artifact removal)
    └── apply_protected_regions() (safety layer)
    ↓
PreviewWidget (before/after display)
    ↓
PDFExporter.export_pdf() (file output)
```

### Batch Processing
```
File Selection (drag & drop | folder select)
    ↓
BatchSidebar.load_files() (populate file list)
    ↓
User iterates: select file → configure zones
    ↓
MainWindow.run_batch() (background thread)
    ├── For each file:
    │   ├── PDFHandler.render_page()
    │   ├── StapleRemover.remove()
    │   └── PDFExporter.export_pdf()
    ├── Progress bar updates
    └── Auto-recovery saves state
    ↓
Completion notification
```

## Key Features Implementation

### v1.1.21 Features

#### 1. Sidebar File Filters
- **File:** `batch_sidebar.py` (800 LOC)
- **Implementation:**
  - Search box filters by filename (case-insensitive)
  - Slider filters by page count range
  - Real-time filtering as user types
  - Highlights matching files in list

#### 2. Loading Overlay for Large PDFs
- **File:** `continuous_preview.py` (3,400 LOC)
- **Trigger:** PDF >20 pages
- **Implementation:**
  - QWidget overlay with spinning animation
  - Displays during `render_page()` calls
  - Auto-dismiss when rendering completes

#### 3. Zone Counter
- **File:** `main_window.py` (3,316 LOC)
- **Location:** Status bar (bottom right)
- **Display:** "Global: N | Per-File: M | Per-Page: K"
- **Update:** Real-time as zones are added/removed

#### 4. Delete Zones
- **Files:** `settings_panel.py`, `zone_item.py`
- **Methods:**
  - Delete key on selected zone
  - UI buttons for global/per-file/per-page deletion
  - Confirmation dialog before deletion

#### 5. Auto-Recovery
- **File:** `config_manager.py` (234 LOC)
- **Saved State:**
  - Last opened file/folder
  - Active zone configuration
  - Settings (DPI, compression, etc.)
- **Recovery:** On app startup, restore previous state

#### 6. Undo (Ctrl+Z)
- **Files:** `undo_manager.py` (57 LOC), `main_window.py`
- **Stack Size:** 79 actions max
- **Actions:** Zone add, modify, delete
- **Keyboard:** Ctrl+Z to undo, Ctrl+Shift+Z to redo

#### 7. Hybrid Zone Sizing
- **File:** `processor.py` (774 LOC)
- **Modes:**
  - `percent`: width/height as % of page
  - `fixed`: fixed pixel size (corners)
  - `hybrid`: one dimension %, other fixed (edges)
- **Implementation:** `Zone.to_pixels()` method

#### 8. Batch Zoom Preservation
- **File:** `continuous_preview.py` (3,400 LOC)
- **Implementation:**
  - Store zoom level per file
  - Restore when switching between files
  - Prevents jarring zoom changes

## Dependencies

### Required Libraries
- `PyQt5>=5.15` - UI framework
- `OpenCV (cv2)>=4.5` - Image processing
- `Pillow>=8.0` - Image format handling
- `numpy` - Array operations
- `onnxruntime>=1.11` - ML inference
- `pymupdf` or `pypdf` - PDF I/O

### Optional Libraries
- `torch>=1.9` - PyTorch-based ML models
- `paddleocr` - PaddleOCR text detection

## Performance Characteristics

### Memory Usage
- Single page (A4 300 DPI): ~30-50 MB
- Page cache (10 pages): ~300-500 MB
- Layout detector model: ~100-200 MB
- Typical 100-page PDF: <500 MB total

### Processing Speed
- Single page removal: 0.5-1.0 second
- Batch processing: 2-3 pages/second
- Layout detection: 0.3-0.5 second per page
- Preview rendering: <200ms

### File Size Impact
- Original PDF (100 pages, 300 DPI): ~50 MB
- Processed PDF (DPI 150, JPEG): ~15-20 MB
- Compression ratio: 60-70%

## Code Quality Metrics

### Test Coverage
- Core module: ~85% line coverage
- UI module: ~60% coverage (interactive components harder to test)
- Overall: ~75% coverage

### Code Organization
- Average file size: 600 LOC (manageable)
- Longest file: `continuous_preview.py` (3,400 LOC, can be split)
- Clear module boundaries and responsibilities

### Naming Conventions
- Classes: PascalCase (`StapleRemover`, `ZoneItem`)
- Functions: snake_case (`remove_staples()`, `to_pixels()`)
- Constants: UPPER_SNAKE_CASE (`THRESHOLD_DEFAULT = 5`)
- Private: Leading underscore (`_load_onnx_model()`)

## Potential Improvements

### Code Refactoring
1. Split `continuous_preview.py` into smaller components
2. Extract common style definitions to CSS-like module
3. Consolidate zone sizing logic into dedicated class

### Performance
1. Implement multi-threaded batch processing
2. Add GPU acceleration for layout detection
3. Lazy-load preview images for large PDFs

### Testing
1. Add integration tests for UI workflows
2. Performance benchmarking suite
3. Model accuracy validation tests

## Key Features by Version

### v1.1.23 (Current - 2026-01-27)
#### Sliding Window Preview (Memory Optimization)
- Only keeps 10 pages in RAM (current page ±5)
- Reduces memory footprint for large PDFs
- Auto-purges pages outside window
- Seamless scrolling experience
- **File:** `continuous_preview.py` (~3,500+ LOC)

#### AI Detection Preload
- Auto-loads YOLO DocLayNet model when text protection enabled
- Improves UX by avoiding model load delay during processing
- Non-blocking preload in background
- **File:** `text_protection_dialog.py`, `main_window.py`

#### Background File Preload
- Pre-renders next file while processing current file
- Batch mode optimization for sequential processing
- **File:** `main_window.py`, `batch_sidebar.py`

#### Lazy Page Count Loading
- Load page counts in batches (ThreadPoolExecutor)
- Batch sidebar remains responsive
- **File:** `batch_sidebar.py`

#### Keyboard Navigation
- **[** - Previous file in batch mode
- **]** - Next file in batch mode
- Tooltips show shortcuts
- **File:** `batch_sidebar.py`, `main_window.py`

#### Bug Fixes & Stability
- Fixed TextProtectionOptions dataclass attribute access
- Fixed _load_from_cache invalid method call
- Fixed panel centering when pages have different sizes
- Improved error handling in file loading

### v1.1.22 (Previous - 2026-01-26)
- Fixed "Xóa tất cả" (Clear All) not persisting to JSON in single/batch mode
- Improved protected region caching from preview with DPI scaling
- Fixed kernel size scaling in zone processing operations
- Fixed text protection consistency across operations
- Enhanced memory cleanup when loading new files/folders

### v1.1.21
- Sidebar file filters (name + page count)
- Loading overlay for large PDFs (>20 pages)
- Zone counter on status bar (global + per-file + per-page)
- Delete zones (global/per-file/per-page)
- Auto-recovery on crash
- Undo (Ctrl+Z) up to 79 actions
- Hybrid zone sizing (pixels + percentage)
- Batch mode zoom preservation

## Document Control

- **Last Updated:** 2026-01-27
- **Version:** 1.3
- **Status:** Current (v1.1.23)
- **Generated by:** Documentation manager - codebase analysis
