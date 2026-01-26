# XoaGhim PDF - System Architecture

**Last Updated:** 2026-01-26
**Version:** 1.1.22

---

## Architecture Overview

XoaGhim follows a **layered architecture pattern** with clear separation of concerns between user interface, application logic, and data processing.

```
┌────────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER (PyQt5)                  │
│  main_window.py | continuous_preview.py | settings_panel.py  │
│  compact_settings_toolbar.py | zone_selector.py | ...          │
└─────────────────────────────┬──────────────────────────────────┘
                              │ QThread signals/slots
                              │
┌─────────────────────────────▼──────────────────────────────────┐
│              APPLICATION/ORCHESTRATION LAYER                    │
│  ProcessThread | BatchProcessThread | Signal handlers           │
│  State management | Event coordination                          │
└─────────────────────────────┬──────────────────────────────────┘
                              │
┌─────────────────────────────▼──────────────────────────────────┐
│            BUSINESS LOGIC LAYER (core/)                         │
│  processor.py (StapleRemover)                                   │
│  layout_detector.py (AI detection)                              │
│  zone_optimizer.py (geometry)                                   │
│  pdf_handler.py (PDF I/O)                                       │
│  config_manager.py (persistence)                                │
└─────────────────────────────┬──────────────────────────────────┘
                              │
┌─────────────────────────────▼──────────────────────────────────┐
│              DATA/RESOURCE LAYER                                │
│  File I/O | Config files | AI models | Image caching           │
└────────────────────────────────────────────────────────────────┘
```

---

## Detailed Component Architecture

### 1. Presentation Layer (UI)

**Main Components:**

```
┌──────────────────────────────────────────────┐
│         MainWindow (2,828 lines)             │
│  - Menu bar (File, Edit, View, Help)         │
│  - Toolbar (Clean button, settings toggle)   │
│  - Central widgets container                 │
│  - Status bar (page info, zoom)              │
│  - Signal coordination center                │
└────────┬──────────┬─────────────┬────────────┘
         │          │             │
    ┌────▼─┐  ┌─────▼──┐  ┌──────▼─────┐
    │Preview│  │Settings│  │  Batch     │
    │(1200L)│  │Panel   │  │  Sidebar   │
    │       │  │(500L)  │  │  (300L)    │
    └────┬─┘  └────┬────┘  └──────┬─────┘
         │         │              │
         └──────┬──┘              │
         ┌──────▼──────────────────┘
         │
    ┌────▼──────────────────────────┐
    │  Settings Panel Detail/Compact │
    │  - Detail: 3 columns          │
    │    - Zone selector (502L)     │
    │    - Parameters               │
    │    - Output settings          │
    │  - Compact: Icon toolbar      │
    │    - CompactIconButton        │
    │    - CompactSettingsToolbar   │
    └───────────────────────────────┘
```

**Preview System:**
- **ContinuousPreviewWidget:** Dual panel (original | processed)
- **ContinuousPreviewPanel:** Individual panel with zone overlay
- **ContinuousGraphicsView:** QGraphicsView with sync scroll/zoom
- **ZoneItem:** Draggable zone graphics item

**Zone Selection:**
- **ZoneSelectorWidget:** 8 preset zones + custom
- **PaperIcon:** Visual page representation
- **CompactIconButton:** 20+ icon types (QPainter-based)
- **CompactSettingsToolbar:** Collapsed toolbar

### 2. Application/Orchestration Layer

**Threading Model:**

```
┌─────────────────────────────────────┐
│      Main Thread (PyQt5 Event Loop)  │
│      - UI updates                    │
│      - Signal handling               │
│      - User interactions             │
└────────────┬────────────────────────┘
             │
    ┌────────┴──────────┐
    │                   │
┌───▼──────────────┐  ┌─▼───────────────┐
│  ProcessThread   │  │ BatchProcess    │
│  (single file)   │  │ Thread (multiple)│
│  - PDF loading   │  │ - Parallel exec │
│  - Processing    │  │ - File iteration│
│  - Exporting     │  │ - Progress track│
│  - Signals:      │  │ - Error recovery│
│    progress,     │  │                 │
│    finished      │  │                 │
└──────────────────┘  └─────────────────┘
```

**State Management:**
- Application state held in MainWindow
- Shared via signals/slots
- Config persistence via ConfigManager
- Per-document state in handler objects

### 3. Business Logic Layer (core/)

**Processor Module:**
```
┌────────────────────────────────────┐
│   StapleRemover (500+ lines)        │
├────────────────────────────────────┤
│ Input: image + Zone[]               │
│ Process: 7-step algorithm           │
│ Output: processed image             │
├────────────────────────────────────┤
│ Key Methods:                        │
│ - process_image(img, zones)         │
│ - process_zone(img, zone)           │
│ - get_background_color()            │
│ - remove_staples()                  │
│ - protect_signatures()              │
│ - apply_protected_regions()         │
└────────────────────────────────────┘

Step 1: Sample background color from safe zone
  ↓
Step 2: Convert to grayscale
  ↓
Step 3: Find darker pixels (threshold-based)
  ↓
Step 4: Exclude dark text (gray < 80)
  ↓
Step 5: Exclude red/blue signature colors
  ↓
Step 6: Apply morphological operations
  ↓
Step 7: Fill removed areas with background color
```

**PDF Handler Module:**
```
┌──────────────────────────────────────┐
│   PDFHandler (645 lines)              │
├──────────────────────────────────────┤
│ - Page caching (10 pages max)         │
│ - Lazy rendering                      │
│ - Zoom support                        │
│ - Metadata extraction                 │
│                                       │
│   PDFExporter                         │
├──────────────────────────────────────┤
│ - JPEG compression (color)            │
│ - TIFF compression (B/W)              │
│ - DPI configuration (72-300)          │
│ - Batch export support                │
└──────────────────────────────────────┘
```

**Layout Detector Module:**
```
┌──────────────────────────────────────┐
│   LayoutDetector (500+ lines)         │
│   Abstract base class + factory       │
├──────────────────────────────────────┤
│ create(backend: str) → Detector       │
│ detect(image) → ProtectedRegion[]     │
├──────────────────────────────────────┤
│ Implementations (6 backends):         │
│ 1. YOLODocLayNetONNXDetector (primary)│
│    - ONNX Runtime inference           │
│    - CPU-friendly, auto-download      │
│                                       │
│ 2. YOLODocLayNetDetector (PyTorch)    │
│    - PyTorch + GPU support            │
│                                       │
│ 3. PPDocLayoutDetector (PaddleOCR)    │
│    - PaddleOCR backend                │
│                                       │
│ 4. DocLayoutYOLO (legacy)             │
│    - Fallback implementation          │
│                                       │
│ 5. LayoutParserDetector (Detectron2)  │
│    - Facebook research model          │
│                                       │
│ 6. RemoteLayoutDetector (GPU server)  │
│    - Server-based processing          │
└──────────────────────────────────────┘

Detection Categories (11):
- text, title, list, table, figure
- caption, header, footer
- page-number, footnote, section-header
```

**Zone Optimizer Module:**
```
┌──────────────────────────────────────┐
│   HybridPolygonOptimizer (315 lines)  │
│   Shapely-based geometry              │
├──────────────────────────────────────┤
│ - Safe zone calculation               │
│ - Protected region subtraction        │
│ - Polygon simplification              │
│ - DPI-aware scaling                   │
│ - Intersection detection              │
│ - Coordinate validation               │
└──────────────────────────────────────┘
```

**Config Manager Module:**
```
┌──────────────────────────────────────┐
│   ConfigManager (271 lines)           │
│   JSON persistence + auto-recovery    │
├──────────────────────────────────────┤
│ Platform-specific paths:              │
│ - macOS: ~/Library/Application       │
│   Support/XoaGhim/config.json         │
│ - Windows: %APPDATA%/XoaGhim/         │
│ - Linux: ~/.config/XoaGhim/           │
├──────────────────────────────────────┤
│ Persisted Config:                     │
│ - Enabled zones (global/per-file)     │
│ - Zone coordinates/sizes              │
│ - Threshold values                    │
│ - DPI and compression settings        │
│ - Window size/position                │
│ - Filter mode (all/odd/even/current)  │
│ - Last opened file/folder             │
│ - Text protection settings            │
└──────────────────────────────────────┘
```

### 4. Data & Resource Layer

**File Structure:**
```
File System                    Application Memory
├── PDF files                  ├── PDFHandler._cache
├── Config (JSON)              │   (10 pages max)
├── ONNX models                │
│   (100MB+)                   ├── UI state
└── Cache directory            │   (current zones,
                               │    settings, etc)
                               │
                               └── Log files
```

**Caching Strategy:**
```
Page Cache (LRU):
  Page N-2 ← Page N-1 ← Page N (current) → Page N+1 → Page N+2
  [Keep max 10 pages in memory]

AI Model Cache:
  - Downloaded to: ~/.cache/XoaGhim/ or %APPDATA%/XoaGhim/models/
  - Lazy loaded on first use
  - Reused for subsequent detections
```

---

## Data Flow

### Single File Processing Flow

```
User clicks "Open PDF"
    ↓
MainWindow.on_file_selected(path)
    ↓
PDFHandler.open(path)
    ├─ Load PDF document
    └─ Cache first page
    ↓
ContinuousPreviewWidget.display_page(0)
    ├─ Render original
    └─ Display zones overlay
    ↓
User adjusts zones, threshold, etc.
    ↓
Preview updates in real-time
    ├─ StapleRemover.process_image()
    └─ Display processed version
    ↓
User clicks "Clean"
    ↓
ProcessThread.run()
    ├─ For each page:
    │  ├─ Load page
    │  ├─ Get layout (optional)
    │  ├─ Apply zones + protection
    │  ├─ Process all zones
    │  └─ Emit progress_updated
    ├─ Collect processed images
    └─ PDFExporter.export()
    ↓
PDFExporter saves file
    ↓
Signal finished
    ↓
MainWindow shows completion message
```

### Batch Processing Flow

```
User selects folder
    ↓
BatchProcessThread.run()
    ├─ For each file in folder:
    │  ├─ ProcessThread for single file (or parallel)
    │  ├─ Emit file_progress
    │  └─ Continue with next
    ├─ Track success/failures
    └─ Emit batch_finished
    ↓
BatchSidebar updates with results
    ↓
User reviews results
```

### AI Detection Flow

```
User clicks "AI Detect"
    ↓
LayoutDetector.create(backend)
    ├─ If YOLO: YOLODocLayNetONNXDetector
    │   ├─ Check cache for model
    │   └─ Auto-download if missing
    └─ Load other backends as needed
    ↓
LayoutDetector.detect(current_page)
    ├─ Preprocess image
    ├─ Run inference
    └─ Return ProtectedRegion[]
    ↓
StapleRemover.apply_protection(zones, protected)
    ├─ Exclude protected regions
    └─ Update effective zones
    ↓
Preview updates with protected regions shown
```

---

## Key Design Decisions

### 1. Layered Architecture
**Why:** Clear separation of concerns allows independent testing and maintenance
**Impact:** UI can be replaced without touching core logic

### 2. Factory Pattern for Layout Detectors
**Why:** Support multiple backends (YOLO, PyTorch, PaddleOCR, etc.)
**Impact:** Easy to add new detection methods

### 3. Caching with LRU (Least Recently Used)
**Why:** PDF pages can be large; caching improves responsiveness
**Impact:** Memory-bounded; old pages automatically discarded

### 4. QThread for Background Processing
**Why:** Keep UI responsive during long operations
**Impact:** Signals/slots for thread-safe communication

### 5. Dataclasses for Simple Data
**Why:** Cleaner than traditional classes for simple containers
**Impact:** Reduced boilerplate; type safety

### 6. JSON Configuration
**Why:** Human-readable; platform-independent
**Impact:** Users can edit config manually if needed

### 7. Lazy Model Loading
**Why:** First use requires download (~100MB); avoid blocking UI
**Impact:** Smooth initial experience for default (no AI) workflows

---

## Signal Flow Diagram

```
MainWindow
├─ zone_changed → SettingsPanel
├─ preview_updated → ContinuousPreviewWidget
├─ processing_started → ProcessThread
├─ processing_finished → Display result
├─ batch_progress → BatchSidebar
└─ config_saved → ConfigManager

CompactSettingsToolbar
├─ zone_toggled → MainWindow
├─ filter_changed → MainWindow
├─ draw_mode_changed → MainWindow
├─ clear_zones → SettingsPanel
└─ ai_detect_toggled → MainWindow

ProcessThread
├─ progress_updated → MainWindow
└─ finished → MainWindow

ContinuousPreviewWidget
├─ page_changed → PDFHandler
├─ zoom_changed → sync to other panel
└─ scroll_changed → sync to other panel
```

---

## Performance Characteristics

### Scalability

**Document Size:**
- Tested: 1-1000+ pages
- Limiting factor: User patience (not crash)
- Mitigation: Page caching, progress reporting

**Batch Size:**
- Tested: 100+ files
- Thread pool: Configurable parallelism
- Mitigation: Background threading, error recovery

**Memory:**
- Per-page cache: 50-100 MB
- Max cached pages: 10
- Total baseline: 200-300 MB + cache

### Performance Profile

```
Operation          CPU Time    Wall Time   Memory
──────────────────────────────────────────────
PDF load           0.5s        0.5s        ~20MB
Single page render 0.5s        0.5s        ~50-100MB
Process 1 zone     0.2s        0.2s        minimal
AI detection       2-3s        3-5s        ~150MB
Export PDF         1-2s        2-3s        <10MB
──────────────────────────────────────────────
Total pipeline:    3-7s        5-15s       variable
```

---

## Extension Points

### Adding New Layout Detector

```python
# 1. Extend LayoutDetector
class MyCustomDetector(LayoutDetector):
    def detect(self, image: np.ndarray) -> List[ProtectedRegion]:
        # Implement detection logic
        pass

# 2. Register in factory
def create(backend: str) -> LayoutDetector:
    if backend == "custom":
        return MyCustomDetector()
    # ... other backends
```

### Adding New Export Format

```python
# 1. Extend PDFExporter
class PNGExporter(Exporter):
    def export(self, images: List[np.ndarray]) -> bytes:
        # Save as PNG sequence

# 2. Use in export workflow
exporter = PNGExporter()
exporter.export(images)
```

### Custom Zone Algorithm

```python
# 1. Modify StapleRemover algorithm
def process_zone(self, image, zone):
    # Custom algorithm step
    # Replace morphological ops with custom logic
```

---

## Dependencies

### External Libraries Dependency Graph

```
XoaGhim
├─ PyQt5 (GUI framework)
│  └─ Qt (C++ runtime)
├─ PyMuPDF/fitz (PDF I/O)
│  └─ MuPDF (C library)
├─ OpenCV (image processing)
│  └─ C++ optimized operations
├─ ONNX Runtime (AI inference)
│  └─ CPU/GPU hardware support
├─ Shapely (polygon geometry)
│  └─ GEOS (geometry engine)
├─ NumPy (array operations)
│  └─ BLAS/LAPACK
├─ psutil (resource monitoring)
└─ Optional:
   ├─ PyTorch (alternative AI backend)
   ├─ PaddleOCR (alternative AI)
   ├─ detectron2 (Detectron2 backend)
   └─ requests (remote API)
```

**Version Lock:**
- Core: requirements.txt pins exact versions
- Optional: Flexible for user choice
- CI/CD: Tests against minimum/maximum versions

---

## Deployment Architecture

### Single Executable (Windows)

```
XoaGhim-1.1.18-Windows.zip
├── XoaGhim-1.1.18.exe (PyInstaller onedir)
├── DLLs/
│   ├── onnxruntime.dll
│   ├── opencv_core.dll
│   └── [other libraries]
├── resources/
│   └── models/
│       └── yolov12s-doclaynet.onnx
└── config.json (created on first run)
```

### Multi-Platform (Source)

```
Git repository
├── core/ (platform-agnostic)
├── ui/ (PyQt5, cross-platform)
├── resources/ (platform-agnostic)
├── requirements.txt (pinned versions)
└── .github/workflows/
    └── build-windows.yml (CI/CD)
```

---

## Future Architecture Considerations

**GPU Acceleration:**
- Option 1: Local GPU (CUDA/cuDNN)
- Option 2: Server-based (RemoteLayoutDetector)
- Decision point: User hardware capability

**Web Interface:**
- Separate backend API
- Frontend: React/Vue
- Communication: REST or WebSocket

**Plugin System:**
- Extend with custom zones algorithms
- Add export formats
- Integrate external services

