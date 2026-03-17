"""Page Metadata Loader - Lazy loads A0-A7 size category and orientation per page"""
import fitz
from typing import List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt5.QtCore import QObject, pyqtSignal, QTimer

# (name, short_side, long_side) in PDF points with ±TOLERANCE
PAGE_SIZE_SPECS = [
    ("A0", 2384, 3370),
    ("A1", 1684, 2384),
    ("A2", 1190, 1684),
    ("A3", 841, 1190),
    ("A4", 595, 842),
    ("A5", 419, 595),
    ("A6", 297, 420),
    ("A7", 210, 297),
]
TOLERANCE = 15


def detect_page_size(w: float, h: float) -> str:
    """Detect A0-A7 category from page dimensions in pts. Returns 'other' if no match."""
    short, long = min(w, h), max(w, h)
    for name, s, l in PAGE_SIZE_SPECS:
        if abs(short - s) <= TOLERANCE and abs(long - l) <= TOLERANCE:
            return name
    return "other"


def load_file_metadata(file_path: str) -> List[Tuple[str, bool]]:
    """Load metadata for all pages: [(size_cat, is_landscape), ...]"""
    try:
        doc = fitz.open(file_path)
        result = []
        for page in doc:
            w, h = page.rect.width, page.rect.height
            size_cat = detect_page_size(w, h)
            is_landscape = w > h
            result.append((size_cat, is_landscape))
        doc.close()
        return result
    except Exception:
        return []


class PageMetadataLoader(QObject):
    """Lazy loader for page size+orientation metadata using ThreadPool"""

    metadata_loaded = pyqtSignal(str, list)  # (file_path, [(size_cat, is_landscape)])
    batch_complete = pyqtSignal()

    BATCH_SIZE = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending: List[str] = []
        self._index: int = 0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._load_next_batch)

    def load(self, file_paths: List[str]):
        """Start lazy loading metadata for a list of files"""
        self._timer.stop()
        self._pending = list(file_paths)
        self._index = 0
        self._timer.start(10)

    def cancel(self):
        """Cancel pending loads"""
        self._timer.stop()
        self._pending = []
        self._index = 0

    def _load_next_batch(self):
        if self._index >= len(self._pending):
            self.batch_complete.emit()
            return

        end = min(self._index + self.BATCH_SIZE, len(self._pending))
        batch = self._pending[self._index:end]

        with ThreadPoolExecutor(max_workers=min(10, len(batch))) as executor:
            futures = {executor.submit(load_file_metadata, fp): fp for fp in batch}
            for future in as_completed(futures):
                fp = futures[future]
                try:
                    meta = future.result()
                    self.metadata_loaded.emit(fp, meta)
                except Exception:
                    self.metadata_loaded.emit(fp, [])

        self._index = end
        if self._index < len(self._pending):
            self._timer.start(5)
        else:
            self.batch_complete.emit()
