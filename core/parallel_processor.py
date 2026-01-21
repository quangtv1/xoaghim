"""
Parallel PDF Processor - Process multiple PDFs concurrently
Uses ProcessPoolExecutor with in-memory buffer to reduce I/O
"""

import io
import os
import time
import fitz
import cv2
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import Manager
from typing import List, Dict, Callable, Optional, Any
from dataclasses import dataclass

try:
    from PIL import Image
except ImportError:
    Image = None

from core.processor import StapleRemover, Zone


@dataclass
class ProcessTask:
    """Task for processing a single PDF"""
    input_path: str
    output_path: str
    zones: List[Dict]  # Serialized zones (dicts for pickling)
    settings: Dict
    file_index: int
    total_files: int


@dataclass
class ProcessResult:
    """Result of processing a single PDF"""
    input_path: str
    output_path: str
    success: bool
    error: Optional[str]
    input_size: int
    output_size: int
    page_count: int
    elapsed_time: float


def _is_grayscale_image(img: np.ndarray) -> bool:
    """Check if image is grayscale"""
    if len(img.shape) == 2:
        return True
    if img.shape[2] == 1:
        return True
    b, g, r = cv2.split(img)
    return np.allclose(b, g, atol=5) and np.allclose(g, r, atol=5)


def _is_bw_image(img: np.ndarray, threshold: float = 0.85) -> bool:
    """Check if image is mostly black/white"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
    near_black = np.sum(gray < 50)
    near_white = np.sum(gray > 205)
    total = gray.size
    bw_ratio = (near_black + near_white) / total
    return bw_ratio >= threshold


def _deserialize_zones(zone_dicts: List[Dict]) -> List[Zone]:
    """Convert serialized zone dicts back to Zone objects"""
    zones = []
    for d in zone_dicts:
        zone = Zone(
            id=d['id'],
            name=d['name'],
            x=d['x'],
            y=d['y'],
            width=d['width'],
            height=d['height'],
            threshold=d.get('threshold', 5),
            enabled=d.get('enabled', True),
            zone_type=d.get('zone_type', 'remove'),
            page_filter=d.get('page_filter', 'all'),
            target_page=d.get('target_page', -1),
            width_px=d.get('width_px', 0),
            height_px=d.get('height_px', 0),
            size_mode=d.get('size_mode', 'percent')
        )
        zones.append(zone)
    return zones


def _get_applicable_zones(zones: List[Zone], page_num: int, total_pages: int) -> List[Zone]:
    """Filter zones that apply to specific page"""
    applicable = []
    for zone in zones:
        if not zone.enabled:
            continue

        page_filter = getattr(zone, 'page_filter', 'all')
        target_page = getattr(zone, 'target_page', -1)

        if target_page >= 0:
            if page_num == target_page:
                applicable.append(zone)
        elif page_filter == 'all':
            applicable.append(zone)
        elif page_filter == 'odd':
            if (page_num + 1) % 2 == 1:
                applicable.append(zone)
        elif page_filter == 'even':
            if (page_num + 1) % 2 == 0:
                applicable.append(zone)

    return applicable


def process_single_pdf(task: ProcessTask, progress_queue=None) -> ProcessResult:
    """
    Process a single PDF file with in-memory buffer (worker function)

    This runs in a separate process - no PyQt, no closures with non-picklable objects
    """
    start_time = time.time()
    input_size = 0
    output_size = 0
    page_count = 0

    try:
        input_size = os.path.getsize(task.input_path)

        # Create processor
        processor = StapleRemover(protect_red=False)

        # Apply text protection if provided
        text_protection = task.settings.get('text_protection')
        if text_protection:
            processor.set_text_protection(text_protection)

        # Get settings
        export_dpi = task.settings.get('dpi', 300)
        jpeg_quality = task.settings.get('jpeg_quality', 90)
        optimize_size = task.settings.get('optimize_size', False)

        # Deserialize zones
        zones = _deserialize_zones(task.zones)

        # Open documents
        doc = fitz.open(task.input_path)
        out_doc = fitz.open()
        page_count = len(doc)

        for page_num in range(page_count):
            page = doc[page_num]

            # Check if any zones apply to this page
            applicable_zones = _get_applicable_zones(zones, page_num, page_count)

            if not applicable_zones:
                # Direct copy - skip processing
                out_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

                if progress_queue:
                    progress_queue.put({
                        'type': 'page',
                        'file_index': task.file_index,
                        'page_num': page_num + 1,
                        'total_pages': page_count,
                        'input_path': task.input_path,
                        'skipped': True
                    })
                continue

            # Render page to image
            mat = fitz.Matrix(export_dpi / 72, export_dpi / 72)
            pix = page.get_pixmap(matrix=mat)

            # Convert to numpy BGR
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            if pix.n == 4:
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
            elif pix.n == 3:
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            # Process with applicable zones
            processed = processor.process_image(img, applicable_zones, render_dpi=export_dpi)

            # === IN-MEMORY BUFFER (no disk I/O) ===
            if optimize_size and _is_bw_image(processed):
                gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
                _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
                if Image is not None:
                    # TIFF Group4 in memory
                    pil_img = Image.fromarray(binary).convert('1')
                    buffer = io.BytesIO()
                    pil_img.save(buffer, 'TIFF', compression='group4')
                    img_bytes = buffer.getvalue()
                else:
                    # PNG fallback
                    success, buffer = cv2.imencode('.png', binary, [cv2.IMWRITE_PNG_COMPRESSION, 9])
                    img_bytes = buffer.tobytes()
            elif optimize_size and _is_grayscale_image(processed):
                gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
                effective_quality = min(jpeg_quality, 90)
                success, buffer = cv2.imencode('.jpg', gray, [cv2.IMWRITE_JPEG_QUALITY, effective_quality])
                img_bytes = buffer.tobytes()
            else:
                # Standard JPEG
                success, buffer = cv2.imencode('.jpg', processed, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
                img_bytes = buffer.tobytes()

            # Insert from memory stream (no disk I/O)
            new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, stream=img_bytes)

            # Report progress
            if progress_queue:
                progress_queue.put({
                    'type': 'page',
                    'file_index': task.file_index,
                    'page_num': page_num + 1,
                    'total_pages': page_count,
                    'input_path': task.input_path
                })

        # Ensure output directory exists
        output_dir = os.path.dirname(task.output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        # Save
        out_doc.save(task.output_path, garbage=4, deflate=True)
        out_doc.close()
        doc.close()

        if os.path.exists(task.output_path):
            output_size = os.path.getsize(task.output_path)

        elapsed = time.time() - start_time

        # Report completion
        if progress_queue:
            progress_queue.put({
                'type': 'file_complete',
                'file_index': task.file_index,
                'input_path': task.input_path,
                'success': True,
                'elapsed': elapsed
            })

        return ProcessResult(
            input_path=task.input_path,
            output_path=task.output_path,
            success=True,
            error=None,
            input_size=input_size,
            output_size=output_size,
            page_count=page_count,
            elapsed_time=elapsed
        )

    except Exception as e:
        elapsed = time.time() - start_time

        if progress_queue:
            progress_queue.put({
                'type': 'file_complete',
                'file_index': task.file_index,
                'input_path': task.input_path,
                'success': False,
                'error': str(e),
                'elapsed': elapsed
            })

        return ProcessResult(
            input_path=task.input_path,
            output_path=task.output_path,
            success=False,
            error=str(e),
            input_size=input_size,
            output_size=output_size,
            page_count=page_count,
            elapsed_time=elapsed
        )


def serialize_zones(zones: List[Zone]) -> List[Dict]:
    """Convert Zone objects to serializable dicts for multiprocessing"""
    zone_dicts = []
    for z in zones:
        d = {
            'id': z.id,
            'name': z.name,
            'x': z.x,
            'y': z.y,
            'width': z.width,
            'height': z.height,
            'threshold': z.threshold,
            'enabled': z.enabled,
            'zone_type': z.zone_type,
            'page_filter': z.page_filter,
            'target_page': z.target_page,
            'width_px': z.width_px,
            'height_px': z.height_px,
            'size_mode': z.size_mode
        }
        zone_dicts.append(d)
    return zone_dicts
