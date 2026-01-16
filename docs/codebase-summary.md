# XoaGhim PDF - Codebase Summary

## Overview

**Application Name:** Xóa Vết Ghim PDF (Remove Staple Marks PDF)
**Version:** 1.1.18
**Organization:** HUCE
**Purpose:** Desktop application for removing staple marks from scanned PDF documents
**Framework:** PyQt5 (Python 3.8+)
**Total Codebase:** ~14,500+ lines across 25+ Python files

## Core Features

### File Processing
- Single file processing via file dialog
- Batch processing from directories
- Drag & drop support (Windows + macOS)
- Page filtering: all/odd/even/current page
- File metadata display: name, page count, size

### Zone Selection
- **8 Preset Zones:** 4 corners + 4 edges
- **Custom Draw Mode:** Draw zones directly on preview
- **Multi-page Support:** Apply zones to multiple pages at once
- **Config Persistence:** Auto-save zones to JSON
- **2-click Reset:** Deselect then select = reset to default size
- **Reset Popup:** 3 options (manual/auto/all)

### Content Protection
- **Red/Blue Pixel Protection:** Preserves signatures and marks
- **AI Layout Detection:**
  - YOLO DocLayNet (ONNX Runtime)
  - 11 categories: text, title, list, table, figure, caption, header, footer, page-number, footnote, section-header
  - Auto-exclude protected regions from processing

### Preview & Export
- Side-by-side preview: Original | Processed (synchronized)
- Sync zoom/scroll between panels
- Continuous (multi-page) or single-page view
- PDF export: DPI 72-300, JPEG/TIFF compression
- Real-time preview updates

## Project Structure

```
xoaghim/
├── main.py                              # Entry point, UI theme setup
├── requirements.txt                     # Dependencies
├── README.md                            # Project readme
├── XoaGhim-1.1.18.spec                 # PyInstaller spec (Windows)
│
├── core/                                # Business logic (6 files, ~2,930 lines)
│   ├── processor.py         (670L)      # Staple removal engine
│   ├── pdf_handler.py       (645L)      # PDF I/O, caching, compression
│   ├── layout_detector.py   (1,602L)    # AI layout detection (6 backends)
│   ├── zone_optimizer.py    (315L)      # Shapely-based safe zones
│   ├── config_manager.py    (124L)      # Config persistence (JSON)
│   └── __init__.py
│
├── ui/                                  # User interface (12 files, ~10,313 lines)
│   ├── main_window.py       (2,828L)    # Main orchestrator, menus, batch
│   ├── continuous_preview.py (1,200L)   # Multi-page preview, zones overlay
│   ├── settings_panel.py    (500+L)     # Zone config, sliders
│   ├── zone_selector.py     (502L)      # Visual zone selector
│   ├── zone_item.py         (292L)      # Draggable zones
│   ├── compact_toolbar_icons.py (326L)  # QPainter icon buttons
│   ├── compact_settings_toolbar.py (243L) # Icon-only toolbar
│   ├── batch_sidebar.py     (300+L)     # Batch file list
│   ├── batch_preview.py     (100+L)     # Batch file widget
│   ├── preview_widget.py    (200+L)     # Dual preview panels
│   ├── text_protection_dialog.py (200L) # AI settings dialog
│   └── __init__.py
│
├── utils/                               # Utilities (1 file, 360 lines)
│   ├── geometry.py          (360L)      # Rectangle ops, format conversions
│   └── __init__.py
│
├── scripts/                             # Utility scripts (1 file)
│   ├── verify_gpu_environment.py (433L) # GPU environment checker
│   └── __init__.py
│
├── tests/                               # Tests (6 files, ~1,195 lines)
│   ├── test_processor.py                # Processor tests
│   ├── test_layout_detector.py          # Layout detection tests
│   ├── test_zone_optimizer.py           # Zone optimization tests
│   ├── test_geometry.py                 # Geometry utility tests
│   ├── test_compact_toolbar.py (31 tests) # Compact toolbar tests
│   └── __init__.py
│
├── resources/                           # Application resources
│   └── models/
│       └── yolov12s-doclaynet.onnx     # AI model (100MB+)
│
├── docs/                                # Documentation
│   ├── project-overview-pdr.md          # Project overview & PDR
│   ├── codebase-summary.md              # This file
│   ├── code-standards.md                # Code standards & structure
│   ├── system-architecture.md           # Architecture diagrams
│   └── project-roadmap.md               # Feature roadmap
│
└── .github/
    └── workflows/
        └── build-windows.yml            # GitHub Actions build
```

## Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Language | Python | 3.8+ |
| GUI Framework | PyQt5 | ≥5.15.0 |
| PDF Processing | PyMuPDF (fitz) | ≥1.20.0 |
| Image Processing | OpenCV | ≥4.5.0 |
| AI Inference | ONNX Runtime | ≥1.22.0 |
| Geometry | Shapely | ≥2.0.0 |
| Arrays | NumPy | ≥1.20.0 |
| Testing | unittest/pytest | - |

### Optional Dependencies
- ultralytics (YOLO training)
- torch (PyTorch backend for layout detection)
- PaddleOCR (alternative layout detection)
- detectron2 (Detectron2 layout detection backend)
- huggingface_hub (model downloads)

## Module Details

### Core Layer (6 files, ~2,930 lines)

#### `core/processor.py` (670 lines)
**Staple Removal Engine**
- **Zone (dataclass):** Coordinates (%), width/height percentages, threshold, enabled flag
- **StapleRemover:** Main processing class
  - `get_background_color()` - Detect safe zone background color
  - `is_red_or_blue()` - Detect red/blue pixels (signatures)
  - `process_zone()` - Process individual zone
  - `process_image()` - Process image with multiple zones
  - `apply_protection()` - Apply AI-detected protected regions
- **PRESET_ZONES:** 8 zones (4 corners, 4 edges) with default coordinates

**Algorithm Flow:**
1. Sample background color from safe zone
2. Convert zone to grayscale
3. Find pixels darker than background by threshold
4. Exclude dark text (gray < 80)
5. Exclude red/blue pixels (signature protection)
6. Apply morphological operations (erosion/dilation)
7. Fill artifacts with background color

#### `core/pdf_handler.py` (645 lines)
**PDF I/O and Rendering**
- **PDFHandler:**
  - Page rendering with caching (10 pages max)
  - Zoom support
  - Page iteration
  - Metadata extraction (title, author, page count)
- **PDFExporter:**
  - Format selection: JPEG for color, TIFF for B/W
  - DPI configuration (72-300)
  - Compression optimization
  - Batch export support

#### `core/layout_detector.py` (1,602 lines)
**AI-Powered Layout Detection**
- **LayoutDetector:** Main interface for layout detection
  - 6 backend support: YOLO (primary), PyTorch, PaddleOCR, legacy, Detectron2, GPU server
  - YOLO DocLayNet model (opset 22, ONNX Runtime ≥1.22.0)
  - Lazy model loading for memory efficiency
  - Support for 11 categories: text, title, list, table, figure, caption, header, footer, page-number, footnote, section-header
- **ProtectedRegion (dataclass):** Category, bounding box (x, y, w, h)
- **YOLODocLayNetONNXDetector:** Primary Windows-friendly detector
  - Automatic model download from HuggingFace
  - CPU inference (<5 sec/page)
  - Confidence filtering

#### `core/zone_optimizer.py` (315 lines)
**Geometry & Safe Zone Calculation**
- **ZoneOptimizer:** Shapely-based polygon operations
  - Safe zone buffer calculation
  - Intersection detection
  - Polygon simplification
  - Coordinate validation
  - Text protection integration

#### `core/config_manager.py` (124 lines)
**Configuration Persistence**
- **ConfigManager:** JSON-based configuration storage
  - Platform-specific paths:
    - macOS: `~/Library/Application Support/XoaGhim/config.json`
    - Windows: `%APPDATA%/XoaGhim/config.json`
    - Linux: `~/.config/XoaGhim/config.json`
  - Zone persistence: enabled zones, coordinates, thresholds
  - Settings persistence: DPI, filter mode, window size
  - Auto-load on startup, auto-save on change

### UI Layer (12 files, ~10,313 lines)

#### `ui/main_window.py` (2,828 lines)
**Main Application Window**
- **MainWindow:** Central orchestrator
  - Menu bar: File, Edit, View, Help
  - Menu items: Open, Batch, Settings, About
  - Bottom status bar: page info, zoom controls
  - Drag & drop support (Windows + macOS)
  - Window size/position persistence
  - Signal coordination
- **ProcessThread:** Single-file processing in background
  - Emits progress signals
  - Error handling
  - Output validation
- **BatchProcessThread:** Multi-file batch processing
  - Parallel execution (configurable)
  - Progress tracking
  - Error recovery

#### `ui/continuous_preview.py` (1,200+ lines)
**Multi-Page Preview with Zones**
- **ContinuousPreviewWidget:** Main preview container
  - Dual panel: original | processed
  - Synchronized zoom & scroll
  - Real-time update on settings change
- **ContinuousPreviewPanel:** Individual preview panel
  - Page caching for performance
  - Zone overlay rendering
  - Custom zone drawing mode
  - Page navigation
- **ContinuousGraphicsView:** QGraphicsView with sync
  - Scroll/zoom synchronization
  - Performance optimization
  - Custom zone drawing interaction

#### `ui/settings_panel.py` (500+ lines)
**Zone Configuration Panel**
- **SettingsPanel:** 3-column layout
  - Column 1: ZoneSelectorWidget (8 preset zones + custom)
  - Column 2: Parameters (width %, height %, threshold slider)
  - Column 3: Output (DPI dropdown, folder, filename pattern)
- Features:
  - Detail/Compact mode toggle (V button on menu bar)
  - "Clear All" popup with 3 options: manual/auto/all
  - Text protection checkbox
  - Real-time preview sync
- Compact mode: CollapseButton hides panel, shows CompactSettingsToolbar

#### `ui/zone_selector.py` (502 lines)
**Visual Zone Selection Widget**
- **PaperIcon:** Visual representation of page with zones
  - 8 zones displayed as colored rectangles
  - DPI-aware rendering
  - Cosmetic pen for consistency
- **ZoneSelectorWidget:** Combined zone control
  - Toggle buttons for each zone
  - Visual feedback on selection
  - Multi-page support

#### `ui/zone_item.py` (292 lines)
**Draggable Zone Graphics Item**
- **ZoneItem:** QGraphicsRectItem with interaction
  - 8 resize handles (corners + edges)
  - Drag support
  - Boundary constraints
  - Multi-page selection
  - Visual highlighting

#### `ui/compact_toolbar_icons.py` (326 lines)
**Icon Button Component for Compact Toolbar**
- **CompactIconButton:** Reusable QPainter-based button
  - 20+ icon types: corners, edges, draw modes, filters, actions
  - Checkable & selectable state management
  - Color states: normal (gray #6B7280), hover (blue #3B82F6), selected (light blue #DBEAFE), protect (pink #EC4899)
  - Fixed 38x38px size
  - Optional rounded background
  - Tooltip support
  - Cursor feedback
  - Icons: top-left, top-right, bottom-left, bottom-right, top, bottom, left, right, add, remove, all-pages, odd-pages, even-pages, current-page, clear, ai-detect, etc.
- **CompactIconSeparator:** Vertical divider
  - Fixed 8x38px
  - Light gray color (#D1D5DB)

#### `ui/compact_settings_toolbar.py` (243 lines)
**Collapsed Settings Toolbar**
- **CompactSettingsToolbar:** Icon-only toolbar widget
  - Use when settings panel is collapsed
  - Organized button groups with separators
  - Zone buttons: 8 total (4 corners + 4 edges)
  - Draw mode: Remove (-) and Protect (+) exclusive group
  - Filter: All, Odd, Even, Current Page exclusive group
  - Action buttons: Clear zones, AI detect
- Signals: zone_toggled, filter_changed, draw_mode_changed, clear_zones, ai_detect_toggled
- State sync methods: set_zone_state(), set_filter_state(), set_draw_mode_state(), set_ai_detect_state()
- Full sync: sync_from_settings(enabled_zones, filter_mode, draw_mode, ai_detect)
- Visual: White background, 42px fixed height

#### `ui/batch_sidebar.py` (300+ lines)
**Batch File Management Panel**
- **BatchSidebar:** File list with metadata
  - File name, page count, file size
  - Selection state
  - Progress indicator
  - Drag & drop support

#### `ui/batch_preview.py` (100+ lines)
**Batch File List Widget**
- **BatchPreviewWidget:** Visual file list
  - Thumbnail preview (optional)
  - File metadata display
  - Multi-selection support

#### `ui/preview_widget.py` (200+ lines)
**Basic Preview Component**
- **PreviewWidget:** Single image display
  - Zoom controls
  - Scroll support
  - Image caching

#### `ui/text_protection_dialog.py` (200+ lines)
**AI Settings Dialog**
- **TextProtectionDialog:** Configuration dialog
  - Backend selection (YOLO, PyTorch, PaddleOCR, Detectron2, GPU server)
  - Model download/cache management
  - Confidence threshold slider
  - Category filtering
  - Test mode with preview

### Utils Layer (1 file, 360 lines)

#### `utils/geometry.py` (360 lines)
**Geometry Utilities**
- **Rectangle operations:**
  - Intersection detection
  - Union calculation
  - Bounds validation
- **Format conversions:**
  - Shapely ↔ OpenCV
  - Percent ↔ Pixel coordinates
  - Polygon simplification
- **Coordinate validation:**
  - Bounds checking
  - DPI adjustment
  - Safe zone buffering

### Scripts (1 file, 433 lines)

#### `scripts/verify_gpu_environment.py` (433 lines)
**GPU Environment Verification**
- Environment checker for Rocky Linux + Tesla V100 GPU
- Validates CUDA, cuDNN, ONNX Runtime setup
- Performance benchmarking
- Used for GPU server deployment validation

### Tests (6 files, ~1,195 lines)

#### Test Coverage (124+ test cases)
- `test_processor.py` - StapleRemover algorithm tests
- `test_layout_detector.py` - Layout detection backend tests
- `test_zone_optimizer.py` - Geometry and zone calculation tests
- `test_geometry.py` - Utility geometry function tests
- `test_compact_toolbar.py` - 31+ tests for toolbar widgets
  - Icon button state management
  - Toolbar initialization
  - Signal emission
  - State synchronization
  - Draw mode exclusivity
  - Filter group exclusivity

## Keyboard Shortcuts

| Shortcut | Function | Location |
|----------|----------|----------|
| Ctrl+O | Open file | File menu |
| Ctrl+Enter | Process (Clean button) | Main window |
| Ctrl+Plus | Zoom in preview | Bottom bar |
| Ctrl+Minus | Zoom out preview | Bottom bar |
| V (click button) | Toggle settings panel detail/compact | Menu bar |

## Default Settings

| Setting | Default Value | Range |
|---------|---------------|-------|
| Export DPI | 250 | 72-300 |
| Default Zone | Top-left corner | 12% x 12% |
| Threshold | 5 | 1-20 |
| File pattern | `{original}_clean.pdf` | Custom |
| Red/Blue protection | Enabled | Boolean |
| Max preview pages | 10 (cached) | 1-20 |
| Page cache size | 10 pages | 1-50 |
| UI theme | Light | Light/Dark |

## Build & Deployment

### Windows Build Process
```bash
# Tag release to trigger GitHub Actions
git tag v1.1.18
git push origin v1.1.18
```

**GitHub Actions Workflow** (`.github/workflows/build-windows.yml`):
1. Build executable with PyInstaller (onedir mode)
2. Bundle ONNX Runtime DLLs
3. Bundle VC++ Runtime DLLs
4. Hide console window
5. Create ZIP archive
6. Upload artifact
7. Create GitHub release

**Output:**
- `XoaGhim-1.1.18-Windows.zip`
- Contents: exe, all DLLs, resources/, models/
- Size: ~150-200 MB (includes model)

### Installation Methods
1. **Source:** Clone + `pip install -r requirements.txt` + `python main.py`
2. **Windows:** Download ZIP, extract, run `XoaGhim-1.1.18.exe`
3. **Future:** Conda package, NSIS installer

## Version History

### v1.1.18 (Current - 2026-01-17)
**Compact Settings Toolbar**
- Icon-only toolbar when settings panel is collapsed
- 8 zone toggle buttons (4 corners + 4 edges)
- Draw mode buttons: Remove (-) and Protect (+) exclusive
- Filter buttons: All, Odd, Even, Current Page exclusive
- Action buttons: Clear zones, AI detect
- QPainter-based 20+ icon types
- Color scheme: gray base, blue hover, pink protect, light blue selected
- 38x38px buttons, 42px fixed height toolbar
- Full state synchronization with settings panel

### v1.1.17
**Zone Configuration Persistence**
- Save zones to JSON across app sessions
- Platform-specific config paths (macOS/Windows/Linux)
- 2-click zone reset mechanism

### v1.1.16
**AI Layout Detection & Custom Zones**
- AI layout detection with YOLO DocLayNet (ONNX)
- Custom zone draw mode
- Multi-page zone selection
- 3-option reset popup

## Code Metrics

**Total Codebase: ~14,500+ lines**
- Core modules: ~2,930 lines
- UI modules: ~10,313 lines
- Tests: ~1,195 lines (124+ test cases)
- Utilities: ~360 lines
- Scripts: ~433 lines

**Complexity Highlights:**
- Layout detector: 1,602 lines (6 backend support)
- Main window: 2,828 lines (orchestrator)
- Continuous preview: 1,200+ lines (UI interaction)

## Performance Characteristics

**Page Processing:** 2-5 sec/page (CPU)
**AI Detection:** 3-5 sec/page (YOLO ONNX)
**Memory:** 50-100 MB/page (cached, 10 pages)
**Model Size:** ~100 MB

---

*Last Updated: 2026-01-17*
