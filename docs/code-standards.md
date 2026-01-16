# XoaGhim PDF - Code Standards & Structure

**Last Updated:** 2026-01-17
**Version:** 1.1.18

---

## Table of Contents

1. [Project Organization](#project-organization)
2. [Code Style Guidelines](#code-style-guidelines)
3. [Architecture Patterns](#architecture-patterns)
4. [Module Organization](#module-organization)
5. [Testing Standards](#testing-standards)
6. [Documentation Requirements](#documentation-requirements)
7. [Performance Guidelines](#performance-guidelines)
8. [Security Standards](#security-standards)

---

## Project Organization

### Directory Structure

```
xoaghim/
├── core/              # Business logic layer (processor, pdf_handler, detectors)
├── ui/                # PyQt5 presentation layer (widgets, dialogs, windows)
├── utils/             # Shared utility functions (geometry, helpers)
├── tests/             # Unit and integration tests
├── scripts/           # Utility scripts (GPU verification, build helpers)
├── resources/         # Static assets (models, icons, configs)
├── docs/              # Project documentation
└── .github/           # GitHub Actions and templates
```

### Naming Conventions

**Modules & Files:**
- Use snake_case for filenames: `pdf_handler.py`, `layout_detector.py`
- One primary class per file (optional, smaller utilities can share)
- Grouping: Feature-based organization within directories

**Classes:**
- Use PascalCase: `StapleRemover`, `PDFHandler`, `MainWindow`
- Suffix UI classes with their widget type: `ZoneSelector`, `SettingsPanel`
- Use dataclasses for simple data containers: `Zone`, `ProtectedRegion`

**Functions & Methods:**
- Use snake_case: `get_background_color()`, `process_zone()`
- Prefix private methods with underscore: `_validate_bounds()`
- Use descriptive names: `calculate_safe_zone()` not `calc_sz()`

**Constants:**
- Use UPPER_SNAKE_CASE: `PRESET_ZONES`, `DEFAULT_DPI`
- Magic numbers should be named constants: `MAX_CACHE_PAGES = 10`

**Variables:**
- Use snake_case: `zone_width`, `page_count`
- Boolean variables start with `is_`, `has_`, `can_`: `is_red_or_blue`, `has_protection`
- Abbreviations only in standard contexts: `dpi`, `pdf`, `yolo`, `onnx`

---

## Code Style Guidelines

### Python Style (PEP 8 + Project Extensions)

**Indentation & Formatting:**
- 4 spaces for indentation (no tabs)
- Line length: 100 characters (soft limit, hard limit at 120)
- Use double quotes for strings (consistency)
- Blank lines: 2 between top-level items, 1 between methods

**Imports:**
- Group: stdlib → third-party → local
- Use absolute imports: `from core.processor import StapleRemover`
- Avoid wildcard imports: `from core import *`
- Type hints for public APIs (Python 3.8+ compatible)

```python
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import numpy as np
import cv2
from PyQt5.QtCore import Qt, pyqtSignal

from core.processor import StapleRemover, Zone
```

**Docstrings:**
- Use Google-style docstrings (not NumPy style)
- Include Args, Returns, Raises sections
- Example:

```python
def process_zone(self, image: np.ndarray, zone: Zone) -> np.ndarray:
    """Process a single zone in the image.

    Args:
        image: Input image as numpy array (BGR format).
        zone: Zone configuration with coordinates and threshold.

    Returns:
        Processed image with artifacts removed.

    Raises:
        ValueError: If zone coordinates are outside image bounds.
    """
```

**Type Hints:**
- Use for all public methods
- Optional types: use `Optional[T]` not `T | None` (Python 3.8 compat)
- Complex returns: use `Tuple`, `Dict`, `List` from typing

```python
def get_background_color(
    self,
    image: np.ndarray,
    safe_zone: Zone
) -> Tuple[int, int, int]:
    """Return RGB background color."""
```

### Error Handling

**Exception Strategy:**
- Use specific exceptions: `ValueError`, `FileNotFoundError`, `RuntimeError`
- Custom exceptions for domain errors:

```python
class InvalidZoneError(ValueError):
    """Raised when zone coordinates are invalid."""

class PDFProcessingError(RuntimeError):
    """Raised when PDF processing fails."""
```

**Logging:**
- Use Python logging module (not print)
- Levels: DEBUG (detail) → INFO (progress) → WARNING (issues) → ERROR (failures)

```python
import logging

logger = logging.getLogger(__name__)

logger.debug(f"Processing zone: {zone}")
logger.info(f"PDF processed: {page_count} pages")
logger.warning(f"Low confidence detection: {confidence:.2f}")
logger.error(f"Failed to load model: {error}")
```

### Comments & Clarity

**Comment Guidelines:**
- Write code that is self-explanatory (good names > comments)
- Comments explain "why", code explains "what"
- Block comments for complex algorithms
- Inline comments sparingly

```python
# GOOD: Clear method names, minimal comments
background_color = self.get_background_color(image, safe_zone)
darker_pixels = np.where(grayscale < background_color - threshold)

# BAD: Vague code, overly commented
bc = self.gbg(img, sz)  # get background color
dp = np.where(gs < bc - t)  # find darker pixels
```

---

## Architecture Patterns

### Layered Architecture

**Separation of Concerns:**
```
┌─────────────────────────────────┐
│ UI Layer (PyQt5)                │
│ main_window, dialogs, widgets   │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│ Application Layer               │
│ Orchestration, threading        │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│ Business Logic Layer (core/)    │
│ Processing, detection, I/O      │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│ Data Layer                      │
│ Config, files, models           │
└─────────────────────────────────┘
```

**Design Patterns Used:**

1. **Factory Pattern:** Layout detector backends (YOLO, PyTorch, etc.)
   ```python
   detector = LayoutDetector.create(backend="yolo")
   ```

2. **Strategy Pattern:** Different compression strategies (JPEG/TIFF)
   ```python
   exporter.compress_strategy = JPEGCompressionStrategy()
   ```

3. **Observer Pattern:** PyQt5 signals for UI updates
   ```python
   self.processing_finished.connect(self.on_processing_done)
   ```

4. **Caching Pattern:** Page rendering cache
   ```python
   self._page_cache = OrderedDict(maxlen=10)
   ```

### Threading Model

**Background Processing:**
- UI thread (PyQt5 main): No blocking operations
- Worker threads: PDF processing, AI detection
- Thread-safe communication via signals/slots

```python
class ProcessThread(QThread):
    progress_updated = pyqtSignal(int)
    finished = pyqtSignal(str)

    def run(self):
        try:
            result = self._process()
            self.finished.emit(result)
        except Exception as e:
            logger.error(f"Processing failed: {e}")
```

**No:** Busy waiting or blocking calls in UI thread
**Yes:** QThread with signals for async operations

---

## Module Organization

### Core Module Structure

#### processor.py
```python
# 1. Imports
# 2. Module-level constants
PRESET_ZONES = {...}
DEFAULT_THRESHOLD = 5

# 3. Dataclasses
@dataclass
class Zone:
    x: float
    y: float
    width: float
    height: float
    threshold: int = 5
    enabled: bool = True

# 4. Main class
class StapleRemover:
    """Staple mark removal algorithm."""

    def __init__(self, ...):
        pass

    def process_image(self, image: np.ndarray, zones: List[Zone]) -> np.ndarray:
        """Process image with multiple zones."""
```

#### pdf_handler.py
```python
class PDFHandler:
    """Handle PDF reading and page rendering."""

    def __init__(self, file_path: Path):
        self._document = fitz.open(file_path)
        self._cache = OrderedDict(maxlen=10)

    def get_page_image(self, page_num: int) -> np.ndarray:
        """Get rendered page with caching."""

class PDFExporter:
    """Export processed images to PDF."""

    def export(self, images: List[np.ndarray], dpi: int) -> bytes:
        """Export images as PDF."""
```

#### layout_detector.py
```python
class LayoutDetector:
    """Base class for layout detection."""

    @staticmethod
    def create(backend: str) -> "LayoutDetector":
        """Factory method for detector creation."""

    def detect(self, image: np.ndarray) -> List[ProtectedRegion]:
        """Detect layout regions in image."""

class YOLODocLayNetONNXDetector(LayoutDetector):
    """YOLO DocLayNet detector using ONNX Runtime."""
```

### UI Module Structure

**Pattern:** Each major UI component in separate file

```python
# ui/main_window.py
class MainWindow(QMainWindow):
    """Central application window."""

    def __init__(self):
        self.preview_widget = ContinuousPreviewWidget()
        self.settings_panel = SettingsPanel()

    def setup_ui(self):
        """Initialize UI components."""

    def setup_connections(self):
        """Connect signals to slots."""

# ui/settings_panel.py
class SettingsPanel(QWidget):
    """Zone configuration panel."""

    zone_changed = pyqtSignal(Zone)

    def __init__(self):
        self.zone_selector = ZoneSelectorWidget()

# ui/continuous_preview.py
class ContinuousPreviewWidget(QWidget):
    """Dual preview with synchronized scrolling."""
```

---

## Testing Standards

### Test Organization

**File Structure:**
```
tests/
├── test_processor.py          # StapleRemover tests
├── test_layout_detector.py    # LayoutDetector tests
├── test_zone_optimizer.py     # Zone calculation tests
├── test_geometry.py           # Geometry utility tests
├── test_compact_toolbar.py    # UI widget tests
└── __init__.py
```

### Test Coverage Requirements

**Targets:**
- Core modules: ≥80% coverage
- UI modules: ≥50% coverage (hard to test GUI)
- Critical paths: 100% coverage
- Algorithm functions: 100% coverage

### Testing Patterns

**Unit Tests:**
```python
import unittest
from core.processor import StapleRemover, Zone

class TestStapleRemover(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures."""
        self.remover = StapleRemover()
        self.test_image = np.zeros((100, 100, 3), dtype=np.uint8)

    def test_process_zone_with_valid_zone(self):
        """Test processing valid zone."""
        zone = Zone(x=10, y=10, width=20, height=20, threshold=5)
        result = self.remover.process_zone(self.test_image, zone)
        self.assertIsNotNone(result)
        self.assertEqual(result.shape, self.test_image.shape)

    def test_process_zone_with_invalid_zone(self):
        """Test processing with zone outside bounds."""
        zone = Zone(x=150, y=150, width=50, height=50)
        with self.assertRaises(ValueError):
            self.remover.process_zone(self.test_image, zone)
```

**Integration Tests:**
```python
def test_full_processing_pipeline(self):
    """Test complete PDF processing pipeline."""
    pdf_path = Path("test_data/sample.pdf")
    handler = PDFHandler(pdf_path)

    image = handler.get_page_image(0)
    remover = StapleRemover()
    zones = [Zone(x=0, y=0, width=12, height=12)]

    result = remover.process_image(image, zones)
    self.assertIsNotNone(result)
```

### Test Execution

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=core --cov=ui --cov-report=term-missing

# Run single test file
python -m pytest tests/test_processor.py

# Run specific test
python -m pytest tests/test_processor.py::TestStapleRemover::test_process_zone
```

---

## Documentation Requirements

### Code Comments

**When to Comment:**
- Complex algorithms (explain logic flow)
- Non-obvious design decisions
- Workarounds or hacks
- Limitations or known issues

**Example:**
```python
def get_background_color(self, image: np.ndarray, safe_zone: Zone) -> Tuple[int, int, int]:
    """Get background color from safe zone.

    We use the safe zone (typically top-right corner) because it's
    unlikely to contain document content. The median is more robust
    than mean against outliers.

    Args:
        image: Input BGR image
        safe_zone: Zone guaranteed to be background

    Returns:
        RGB tuple of background color
    """
```

### Docstring Locations

**Public APIs:** Always include docstrings
```python
def process_image(self, image: np.ndarray) -> np.ndarray:
    """Process image and remove staple marks."""
```

**Private Methods:** Docstring optional if code is clear
```python
def _validate_bounds(self, zone: Zone) -> bool:
    return 0 <= zone.x < 100 and 0 <= zone.y < 100
```

**Module-level:** Include module docstring
```python
"""PDF handling for staple removal.

This module provides PDF reading, page rendering, and export functionality.
Features:
- Lazy page rendering with caching
- Multiple compression formats (JPEG/TIFF)
- Batch export support
"""
```

---

## Performance Guidelines

### Optimization Priorities

1. **Correctness** (must-have)
2. **Maintainability** (important)
3. **Performance** (optimize where it matters)

### Performance Targets

| Operation | Target | Measured |
|-----------|--------|----------|
| Single page processing | <5 sec | 2-5 sec (CPU) |
| AI detection per page | <5 sec | 3-5 sec (ONNX CPU) |
| Page caching hits | >80% | Depends on workflow |
| UI responsiveness | <200ms | Monitor with profiling |
| Memory per page | <100 MB | 50-100 MB (cached) |

### Optimization Strategies

**PDF Processing:**
```python
# Use caching for frequently accessed pages
class PDFHandler:
    def __init__(self):
        self._cache = OrderedDict(maxlen=10)  # Keep 10 pages

    def get_page_image(self, page_num: int) -> np.ndarray:
        if page_num in self._cache:
            return self._cache[page_num]
        image = self._render_page(page_num)
        self._cache[page_num] = image
        return image
```

**Image Processing:**
```python
# Use vectorized numpy operations, not loops
# BAD: Loop over pixels
for i in range(image.shape[0]):
    for j in range(image.shape[1]):
        darker = image[i, j] < threshold

# GOOD: Vectorized
darker = image < threshold
```

**AI Detection:**
```python
# Lazy load expensive models
class LayoutDetector:
    def __init__(self):
        self._model = None

    def detect(self, image):
        if self._model is None:
            self._load_model()  # Expensive operation
        return self._model.infer(image)
```

### Profiling & Monitoring

```python
# Use timers for profiling
import time

start = time.time()
result = self.process_zone(image, zone)
elapsed = time.time() - start
logger.debug(f"Zone processing took {elapsed:.2f}s")

# Monitor memory usage
import tracemalloc
tracemalloc.start()
# ... code to profile ...
current, peak = tracemalloc.get_traced_memory()
logger.info(f"Memory: {current/1e6:.1f} MB, Peak: {peak/1e6:.1f} MB")
```

---

## Security Standards

### Data Protection

**Input Validation:**
```python
def set_zone(self, zone: Zone) -> None:
    """Set processing zone with validation."""
    if not (0 <= zone.x <= 100):
        raise ValueError("Zone X must be 0-100%")
    if not (0 <= zone.width <= (100 - zone.x)):
        raise ValueError("Zone width exceeds bounds")
    self._zone = zone
```

**File Handling:**
```python
# Always validate file paths
from pathlib import Path

def open_pdf(self, file_path: str) -> None:
    path = Path(file_path).resolve()

    # Validate file exists and is readable
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")

    # Safe to open
    self._document = fitz.open(path)
```

### No Network Operations

**Requirement:** All processing is local, no remote calls
- AI models downloaded once to local cache
- No telemetry or phone-home behavior
- Exception: Optional GPU server (explicitly configured)

### Logging Safety

**Don't log:**
- File paths with sensitive information
- Configuration with passwords
- Personal data

**Do log:**
- Processing progress
- Error messages (without sensitive details)
- Performance metrics

```python
# BAD: Logs full path
logger.info(f"Processing file: {file_path}")

# GOOD: Logs only filename
logger.info(f"Processing file: {Path(file_path).name}")
```

---

## Style Checklist for Code Reviews

Before committing code, verify:

- [ ] Function/variable names are descriptive (snake_case)
- [ ] Class names use PascalCase
- [ ] Type hints for public APIs
- [ ] Docstrings for public methods
- [ ] Error handling with specific exceptions
- [ ] No blocking operations in UI thread
- [ ] No hardcoded values (use constants)
- [ ] No print() statements (use logging)
- [ ] Unit tests for core logic
- [ ] Comments explain "why", not "what"
- [ ] Line length <100 characters
- [ ] 4-space indentation
- [ ] Imports organized by group
- [ ] No unused imports
- [ ] F-strings for string formatting
- [ ] No wildcard imports

---

## References

- PEP 8: Python Style Guide - https://www.python.org/dev/peps/pep-0008/
- Google Python Style Guide - https://google.github.io/styleguide/pyguide.html
- PyQt5 Best Practices - https://www.riverbankcomputing.com/static/Docs/PyQt5/
- Type Hints - https://docs.python.org/3/library/typing.html

