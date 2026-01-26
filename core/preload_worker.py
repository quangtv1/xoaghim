"""
Background worker for preloading next PDF file.
Runs in separate QThread to not block UI during zone drawing.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

from core.pdf_handler import PDFHandler


@dataclass
class FileCache:
    """Cached data for a preloaded PDF file"""
    pages: List[np.ndarray]
    thumbnails: List[np.ndarray]
    page_count: int
    detected_regions: Dict[int, list] = field(default_factory=dict)  # page_idx -> regions


class PreloadWorker(QThread):
    """Background worker that preloads next file while user works on current.

    Usage:
        worker = PreloadWorker(file_path, detect_regions=True)
        worker.finished.connect(on_preload_done)
        worker.start()

        # To cancel:
        worker.cancel()
        worker.wait(200)
    """

    finished = pyqtSignal(str, object)  # (file_path, FileCache)
    error = pyqtSignal(str, str)        # (file_path, error_message)

    PREVIEW_DPI = 150
    THUMBNAIL_DPI = 36

    def __init__(self, file_path: str, detect_regions: bool = False,
                 text_protection_options: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._file_path = file_path
        self._detect_regions = detect_regions
        self._text_protection_options = text_protection_options or {}
        self._cancel = False

    def cancel(self):
        """Request cancellation (checked between pages)"""
        self._cancel = True

    def is_cancelled(self) -> bool:
        """Check if cancellation was requested"""
        return self._cancel

    def run(self):
        """Execute in background thread - renders all pages and optionally detects regions"""
        try:
            # Each thread uses its own PDFHandler (thread-safe)
            handler = PDFHandler(self._file_path)
            pages = []
            thumbnails = []
            detected_regions = {}

            # Create processor for detection if needed
            processor = None
            if self._detect_regions:
                try:
                    from core.processor import StapleRemover, TextProtectionSettings
                    processor = StapleRemover(protect_red=False)
                    # Configure text protection
                    if self._text_protection_options:
                        processor.set_text_protection(TextProtectionSettings(
                            enabled=self._text_protection_options.get('enabled', True),
                            protected_labels=self._text_protection_options.get('protected_labels', ['text', 'title'])
                        ))
                except Exception as e:
                    print(f"[PreloadWorker] Failed to init processor: {e}")
                    processor = None

            for i in range(handler.page_count):
                # Check cancel flag between pages
                if self._cancel:
                    handler.close()
                    return

                # Render preview page
                page_img = handler.render_page(i, dpi=self.PREVIEW_DPI)
                pages.append(page_img)

                # Render thumbnail
                thumb_img = handler.render_page(i, dpi=self.THUMBNAIL_DPI)
                thumbnails.append(thumb_img)

                # Detect regions if enabled
                if processor and self._detect_regions:
                    try:
                        regions = processor.detect_protected_regions(page_img)
                        detected_regions[i] = regions
                    except Exception as e:
                        print(f"[PreloadWorker] Detection failed for page {i}: {e}")
                        detected_regions[i] = []

            handler.close()

            # Only emit if not cancelled
            if not self._cancel:
                cache = FileCache(
                    pages=pages,
                    thumbnails=thumbnails,
                    page_count=len(pages),
                    detected_regions=detected_regions
                )
                self.finished.emit(self._file_path, cache)

        except Exception as e:
            if not self._cancel:
                self.error.emit(self._file_path, str(e))
