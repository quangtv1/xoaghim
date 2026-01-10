"""
PDF Handler - Đọc/ghi file PDF
"""

import cv2
import numpy as np
import tempfile
import os
from typing import Optional, Callable
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


class PDFHandler:
    """Xử lý đọc/ghi PDF"""
    
    def __init__(self, pdf_path: str):
        if fitz is None:
            raise ImportError("Cần cài PyMuPDF: pip install PyMuPDF")
        
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        self._page_cache = {}
    
    @property
    def page_count(self) -> int:
        return len(self.doc)
    
    def get_page_size(self, page_num: int) -> tuple:
        """Lấy kích thước trang (width, height)"""
        page = self.doc[page_num]
        return (page.rect.width, page.rect.height)
    
    def render_page(self, page_num: int, dpi: int = 150) -> np.ndarray:
        """Render trang thành numpy array (BGR)"""
        if page_num < 0 or page_num >= self.page_count:
            return None
        
        # Check cache
        cache_key = (page_num, dpi)
        if cache_key in self._page_cache:
            return self._page_cache[cache_key].copy()
        
        page = self.doc[page_num]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to numpy
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        
        # Convert to BGR
        if pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        elif pix.n == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        elif pix.n == 1:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        
        # Cache (limit cache size)
        if len(self._page_cache) > 10:
            self._page_cache.pop(next(iter(self._page_cache)))
        self._page_cache[cache_key] = img.copy()
        
        return img
    
    def clear_cache(self):
        """Xóa cache"""
        self._page_cache.clear()
    
    def close(self):
        """Đóng file"""
        self.doc.close()
        self._page_cache.clear()
    
    def __del__(self):
        try:
            self.close()
        except:
            pass


class PDFExporter:
    """Xuất file PDF"""
    
    @staticmethod
    def export(
        input_path: str,
        output_path: str,
        process_func: Callable[[np.ndarray, int], np.ndarray],
        dpi: int = 200,
        jpeg_quality: int = 85,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bool:
        """
        Xuất PDF đã xử lý
        
        Args:
            input_path: File PDF input
            output_path: File PDF output
            process_func: Hàm xử lý (image, page_num) -> processed_image
            dpi: DPI render
            jpeg_quality: Chất lượng JPEG
            progress_callback: Callback (current, total)
        """
        try:
            doc = fitz.open(input_path)
            out_doc = fitz.open()
            
            total_pages = len(doc)
            
            for page_num in range(total_pages):
                page = doc[page_num]
                
                # Render
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                
                # Convert to numpy BGR
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                if pix.n == 4:
                    img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
                elif pix.n == 3:
                    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                
                # Process
                processed = process_func(img, page_num)
                
                # Save temp JPEG
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                    tmp_path = tmp.name
                
                cv2.imwrite(tmp_path, processed, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
                
                # Insert to new PDF
                new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
                new_page.insert_image(new_page.rect, filename=tmp_path)
                
                os.unlink(tmp_path)
                
                # Progress callback
                if progress_callback:
                    progress_callback(page_num + 1, total_pages)
            
            # Save with compression
            out_doc.save(output_path, garbage=4, deflate=True)
            out_doc.close()
            doc.close()
            
            return True
            
        except Exception as e:
            print(f"Export error: {e}")
            return False
