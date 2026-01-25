"""
Core processor - Xử lý xóa vết ghim

Tính năng:
- Xóa vết ghim dựa trên phát hiện artifact
- Bảo vệ chữ đen, dấu đỏ/xanh
- Text Protection AI (YOLO DocLayNet) - tùy chọn
"""

import cv2
import numpy as np
from typing import List, Tuple, Optional, Set
from dataclasses import dataclass, field



@dataclass
class Zone:
    """Vùng xử lý với hybrid sizing support.

    Size modes:
    - 'percent': width/height as % of page (default, backward compatible)
    - 'fixed': width_px/height_px as fixed pixels (corners)
    - 'hybrid': one dimension as %, other as fixed pixels (edges)
    """
    id: str
    name: str
    x: float  # % từ trái (0.0 - 1.0)
    y: float  # % từ trên (0.0 - 1.0)
    width: float  # % chiều rộng (0.0 - 1.0)
    height: float  # % chiều cao (0.0 - 1.0)
    threshold: int = 5
    enabled: bool = True
    zone_type: str = 'remove'  # 'remove' (xóa) or 'protect' (bảo vệ)
    page_filter: str = 'all'  # 'all', 'odd', 'even', 'none' - filter khi tạo zone
    target_page: int = -1  # Target page index when page_filter='none' (-1 means all)
    # Hybrid sizing fields
    width_px: int = 0   # Fixed pixel width (for corners, edge depth)
    height_px: int = 0  # Fixed pixel height (for corners, edge depth)
    size_mode: str = 'percent'  # 'percent', 'fixed', 'hybrid'

    def to_pixels(self, img_width: int, img_height: int, render_dpi: int = 120) -> Tuple[int, int, int, int]:
        """Chuyển đổi sang pixels dựa trên size_mode.

        - percent: width/height as % of page dimensions
        - fixed: width_px/height_px as fixed pixels (corners - position adjusted)
        - hybrid: one dimension %, other fixed pixels (edges)

        Args:
            img_width: Image width in pixels
            img_height: Image height in pixels
            render_dpi: DPI used to render the image (default 120 for preview)
                        Pixel values are scaled proportionally for different DPIs

        Returns: (x, y, w, h) in pixels
        """
        zone_id = self.id.lower()
        # Scale pixel values based on DPI (base DPI = 120 for preview)
        dpi_scale = render_dpi / 120.0

        if self.size_mode == 'fixed':
            # Fixed pixel size (corners) - position based on corner type
            # Scale pixel values by DPI ratio
            w = int(self.width_px * dpi_scale) if self.width_px > 0 else int(self.width * img_width)
            h = int(self.height_px * dpi_scale) if self.height_px > 0 else int(self.height * img_height)

            # Calculate exact corner positions
            if zone_id == 'corner_tl':
                x, y = 0, 0
            elif zone_id == 'corner_tr':
                x, y = img_width - w, 0
            elif zone_id == 'corner_bl':
                x, y = 0, img_height - h
            elif zone_id == 'corner_br':
                x, y = img_width - w, img_height - h
            else:
                # Non-corner fixed zones: use percentage position
                x = int(self.x * img_width)
                y = int(self.y * img_height)

        elif self.size_mode == 'hybrid':
            # Hybrid: one dimension %, other fixed (edges)
            # Edges: 100% along edge, fixed depth into page
            # Scale pixel values by DPI ratio
            if zone_id == 'margin_top':
                # Top edge: width=100%, height=fixed
                w = int(self.width * img_width)
                h = int(self.height_px * dpi_scale) if self.height_px > 0 else int(self.height * img_height)
                x = 0
                y = 0
            elif zone_id == 'margin_bottom':
                # Bottom edge: width=100%, height=fixed
                w = int(self.width * img_width)
                h = int(self.height_px * dpi_scale) if self.height_px > 0 else int(self.height * img_height)
                x = 0
                y = img_height - h
            elif zone_id == 'margin_left':
                # Left edge: width=fixed, height=100%
                w = int(self.width_px * dpi_scale) if self.width_px > 0 else int(self.width * img_width)
                h = int(self.height * img_height)
                x = 0
                y = 0
            elif zone_id == 'margin_right':
                # Right edge: width=fixed, height=100%
                w = int(self.width_px * dpi_scale) if self.width_px > 0 else int(self.width * img_width)
                h = int(self.height * img_height)
                x = img_width - w
                y = 0
            else:
                # Custom zones in hybrid mode
                x = int(self.x * img_width)
                y = int(self.y * img_height)
                w = int(self.width_px * dpi_scale) if self.width_px > 0 else int(self.width * img_width)
                h = int(self.height_px * dpi_scale) if self.height_px > 0 else int(self.height * img_height)
        else:
            # Default: percent mode (backward compatible)
            x = int(self.x * img_width)
            y = int(self.y * img_height)
            w = int(self.width * img_width)
            h = int(self.height * img_height)

        # Clip to image bounds
        x = max(0, min(x, img_width - 1))
        y = max(0, min(y, img_height - 1))
        w = min(w, img_width - x)
        h = min(h, img_height - y)

        return (x, y, w, h)

    def to_bbox(self, img_width: int, img_height: int, render_dpi: int = 120) -> Tuple[int, int, int, int]:
        """Chuyển đổi sang bbox format: (x1, y1, x2, y2)"""
        x, y, w, h = self.to_pixels(img_width, img_height, render_dpi)
        return (x, y, x + w, y + h)

    def to_bbox_with_edge_padding(self, img_width: int, img_height: int, padding: int = 10, render_dpi: int = 120) -> Tuple[int, int, int, int]:
        """Chuyển đổi sang bbox với padding mở rộng ra ngoài đường viền trang.

        - Góc (corner_*): mở rộng padding ở 2 cạnh giao nhau
        - Cạnh (margin_*): mở rộng padding ở 1 cạnh

        Args:
            img_width: Chiều rộng ảnh
            img_height: Chiều cao ảnh
            padding: Số pixel mở rộng ra ngoài viền (default 10px)
            render_dpi: DPI used to render the image (default 120 for preview)

        Returns:
            (x1, y1, x2, y2) đã được mở rộng và clip vào bounds
        """
        x1, y1, x2, y2 = self.to_bbox(img_width, img_height, render_dpi)

        # Xác định hướng mở rộng dựa trên zone ID
        zone_id = self.id.lower()

        if zone_id == 'corner_tl':
            # Góc trên trái: mở rộng lên trên và sang trái
            x1 = max(0, x1 - padding)
            y1 = max(0, y1 - padding)
        elif zone_id == 'corner_tr':
            # Góc trên phải: mở rộng lên trên và sang phải
            x2 = min(img_width, x2 + padding)
            y1 = max(0, y1 - padding)
        elif zone_id == 'corner_bl':
            # Góc dưới trái: mở rộng xuống dưới và sang trái
            x1 = max(0, x1 - padding)
            y2 = min(img_height, y2 + padding)
        elif zone_id == 'corner_br':
            # Góc dưới phải: mở rộng xuống dưới và sang phải
            x2 = min(img_width, x2 + padding)
            y2 = min(img_height, y2 + padding)
        elif zone_id == 'margin_left':
            # Cạnh trái: mở rộng sang trái
            x1 = max(0, x1 - padding)
        elif zone_id == 'margin_right':
            # Cạnh phải: mở rộng sang phải
            x2 = min(img_width, x2 + padding)
        elif zone_id == 'margin_top':
            # Cạnh trên: mở rộng lên trên
            y1 = max(0, y1 - padding)
        elif zone_id == 'margin_bottom':
            # Cạnh dưới: mở rộng xuống dưới
            y2 = min(img_height, y2 + padding)
        # Zone tùy chỉnh (custom_*): không mở rộng

        return (x1, y1, x2, y2)

    def to_pixels_with_edge_padding(self, img_width: int, img_height: int, padding: int = 10, render_dpi: int = 120) -> Tuple[int, int, int, int]:
        """Chuyển đổi sang pixels với padding mở rộng ra ngoài đường viền trang.

        - Góc (corner_*): mở rộng padding ở 2 cạnh giao nhau
        - Cạnh (margin_*): mở rộng padding ở 1 cạnh

        Args:
            img_width: Image width in pixels
            img_height: Image height in pixels
            padding: Pixel padding for edge extension
            render_dpi: DPI used to render the image (default 120 for preview)

        Returns:
            (x, y, w, h) đã được mở rộng và clip vào bounds
        """
        x1, y1, x2, y2 = self.to_bbox_with_edge_padding(img_width, img_height, padding, render_dpi)
        return (x1, y1, x2 - x1, y2 - y1)


@dataclass
class TextProtectionOptions:
    """Tùy chọn bảo vệ text bằng AI"""
    enabled: bool = True  # Mặc định bật
    protected_labels: Set[str] = field(default_factory=lambda: {
        'title', 'plain_text', 'table',
        'table_footnote', 'figure_caption', 'isolate_formula'
    })  # YOLO DocLayNet labels
    margin: int = 5  # Lề an toàn xung quanh text (pixels)
    confidence: float = 0.1  # Ngưỡng confidence 10%
    use_remote: bool = False  # Mặc định dùng local (YOLO DocLayNet)
    remote_url: str = "http://10.20.0.36:8765"  # URL của remote GPU server


class StapleRemover:
    """Xử lý xóa vết ghim"""

    def __init__(self, protect_red: bool = True):
        self.protect_red = protect_red
        self._layout_detector = None
        self._remote_detector = None
        self._zone_optimizer = None
        self._text_protection = TextProtectionOptions()

    @property
    def layout_detector(self):
        """
        Lazy load layout detector.
        Sử dụng RemoteLayoutDetector nếu use_remote=True, ngược lại dùng YOLODocLayNetDetector local.
        """
        # Sử dụng remote detector nếu được cấu hình
        if self._text_protection.use_remote:
            if self._remote_detector is None:
                try:
                    from .layout_detector import RemoteLayoutDetector
                    self._remote_detector = RemoteLayoutDetector(
                        api_url=self._text_protection.remote_url,
                        confidence_threshold=self._text_protection.confidence,
                        protected_labels=self._text_protection.protected_labels
                    )
                except ImportError:
                    print("[Processor] Remote layout detector not available")
                    return None
            return self._remote_detector

        # Sử dụng local detector (ONNX - fastest, TensorRT/CUDA optimized)
        if self._layout_detector is None:
            try:
                # Prefer ONNX detector (TensorRT > CUDA > CPU)
                from .layout_detector import YOLODocLayNetONNXDetector
                self._layout_detector = YOLODocLayNetONNXDetector(
                    confidence_threshold=self._text_protection.confidence
                )
            except (ImportError, FileNotFoundError):
                # Fallback to PyTorch detector
                try:
                    from .layout_detector import YOLODocLayNetDetector
                    self._layout_detector = YOLODocLayNetDetector(
                        confidence_threshold=self._text_protection.confidence
                    )
                except ImportError:
                    print("[Processor] Layout detector not available")
                    return None
        return self._layout_detector

    @property
    def zone_optimizer(self):
        """Lazy load zone optimizer"""
        if self._zone_optimizer is None:
            try:
                from .zone_optimizer import HybridPolygonOptimizer
                self._zone_optimizer = HybridPolygonOptimizer(
                    margin=self._text_protection.margin
                )
            except Exception as e:
                print(f"[Processor] Zone optimizer not available: {e}")
                return None
        return self._zone_optimizer

    def set_text_protection(self, options: TextProtectionOptions):
        """Cập nhật tùy chọn bảo vệ text"""
        old_use_remote = self._text_protection.use_remote
        old_remote_url = self._text_protection.remote_url
        self._text_protection = options

        # Reset remote detector nếu URL thay đổi hoặc chuyển mode
        if (options.use_remote != old_use_remote or
                options.remote_url != old_remote_url):
            self._remote_detector = None

        # Update local detector nếu đã load
        if self._layout_detector is not None:
            self._layout_detector.set_confidence_threshold(options.confidence)
            self._layout_detector.set_protected_labels(options.protected_labels)

        # Update remote detector nếu đã load
        if self._remote_detector is not None:
            self._remote_detector.set_confidence_threshold(options.confidence)
            self._remote_detector.set_protected_labels(options.protected_labels)

        # Update zone optimizer nếu đã load
        if self._zone_optimizer is not None:
            self._zone_optimizer.set_margin(options.margin)

    def is_text_protection_available(self) -> bool:
        """Kiểm tra text protection có sẵn không"""
        try:
            # Check ONNX detector first (preferred)
            try:
                from .layout_detector import YOLODocLayNetONNXDetector
            except ImportError:
                from .layout_detector import YOLODocLayNetDetector
            from .zone_optimizer import is_shapely_available
            return is_shapely_available()
        except ImportError:
            return False

    def detect_protected_regions(self, image: np.ndarray):
        """
        Detect vùng text cần bảo vệ trong ảnh.

        Returns:
            List[ProtectedRegion] hoặc [] nếu không khả dụng
        """
        if not self._text_protection.enabled:
            print("[Processor] Text protection disabled")
            return []

        detector = self.layout_detector
        if detector is None:
            print("[Processor] Detector is None")
            return []

        if not detector.is_available():
            error = getattr(detector, 'get_load_error', lambda: None)()
            print(f"[Processor] Detector not available: {error}")
            return []

        regions = detector.detect(
            image,
            protected_labels=self._text_protection.protected_labels
        )
        return regions
    
    def get_background_color(self, image: np.ndarray) -> Tuple[int, int, int]:
        """Lấy màu nền từ vùng giữa-phải của trang"""
        h, w = image.shape[:2]
        
        # Sample từ vùng giữa-phải (không có vết ghim)
        y1, y2 = h // 3, 2 * h // 3
        x1, x2 = w // 2, 3 * w // 4
        
        bg_region = image[y1:y2, x1:x2]
        
        if len(image.shape) == 3:
            b = int(np.median(bg_region[:, :, 0]))
            g = int(np.median(bg_region[:, :, 1]))
            r = int(np.median(bg_region[:, :, 2]))
            return (b, g, r)
        else:
            val = int(np.median(bg_region))
            return (val, val, val)
    
    def is_red_or_blue(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Phát hiện pixel màu đỏ hoặc xanh (dấu, chữ ký) để bảo vệ"""
        if len(image.shape) != 3:
            return np.zeros_like(mask, dtype=bool)
        
        # Chuyển sang HSV
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        
        # Màu đỏ: H = 0-10 hoặc 170-180, S > 50, V > 50
        red_mask = ((h < 10) | (h > 170)) & (s > 50) & (v > 50)
        
        # Màu xanh dương: H = 100-130, S > 50, V > 50
        blue_mask = (h > 100) & (h < 130) & (s > 50) & (v > 50)
        
        return red_mask | blue_mask
    
    def process_zone(self, image: np.ndarray, zone: Zone, render_dpi: int = 120) -> np.ndarray:
        """Xử lý một vùng cụ thể

        Args:
            image: Image to process
            zone: Zone to process
            render_dpi: DPI used to render the image (default 120 for preview)
        """
        if not zone.enabled:
            return image

        result = image.copy()
        h, w = image.shape[:2]
        is_color = len(image.shape) == 3

        # Lấy tọa độ vùng (với edge padding cho góc/cạnh)
        zx, zy, zw, zh = zone.to_pixels_with_edge_padding(w, h, padding=10, render_dpi=render_dpi)

        # Đảm bảo không vượt quá biên
        zx = max(0, min(zx, w - 1))
        zy = max(0, min(zy, h - 1))
        zw = min(zw, w - zx)
        zh = min(zh, h - zy)

        if zw <= 0 or zh <= 0:
            return result
        
        # Lấy màu nền
        bg_color = self.get_background_color(image)
        
        # Vùng cần xử lý
        region = image[zy:zy+zh, zx:zx+zw]
        
        # Chuyển sang grayscale để phân tích
        if is_color:
            gray_region = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
            bg_gray = int(0.114 * bg_color[0] + 0.587 * bg_color[1] + 0.299 * bg_color[2])
        else:
            gray_region = region.copy()
            bg_gray = bg_color[0]
        
        # Tìm pixel tối hơn nền
        diff = bg_gray - gray_region.astype(np.int16)
        artifact_mask = diff > zone.threshold
        artifact_count_initial = artifact_mask.sum()

        # Bảo vệ chữ đen - chỉ khi text protection được bật
        text_protected = 0
        if self._text_protection.enabled:
            zone_id_lower = zone.id.lower()
            is_edge_or_corner = zone_id_lower.startswith('margin_') or zone_id_lower.startswith('corner_')
            text_threshold = 50 if is_edge_or_corner else 80  # Giảm cho cạnh/góc
            text_mask = gray_region < text_threshold
            text_protected = (artifact_mask & text_mask).sum()
            artifact_mask = artifact_mask & ~text_mask

        
        # Bảo vệ màu đỏ/xanh nếu được bật
        if self.protect_red and is_color:
            color_mask = self.is_red_or_blue(region, artifact_mask)
            artifact_mask = artifact_mask & ~color_mask
        
        # Morphological operations - scale kernel size with DPI
        dpi_scale = render_dpi / 120.0
        kernel_size = max(5, int(5 * dpi_scale))
        if kernel_size % 2 == 0:
            kernel_size += 1  # Ensure odd size
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        artifact_mask = artifact_mask.astype(np.uint8) * 255
        artifact_mask = cv2.morphologyEx(artifact_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        artifact_mask = cv2.dilate(artifact_mask, kernel, iterations=3)
        artifact_mask = artifact_mask > 0
        
        # Đổ màu nền
        if is_color:
            for c in range(3):
                channel = result[zy:zy+zh, zx:zx+zw, c]
                channel[artifact_mask] = bg_color[c]
        else:
            result[zy:zy+zh, zx:zx+zw][artifact_mask] = bg_gray
        
        return result
    
    def _process_safe_zone(self, image: np.ndarray, safe_zone, zone: Zone,
                           render_dpi: int = 120) -> np.ndarray:
        """
        Xử lý safe zone (polygon-based) thay vì rectangle.

        Args:
            image: Ảnh gốc
            safe_zone: SafeZone object từ zone_optimizer
            zone: Zone gốc (để lấy threshold)
            render_dpi: DPI used to render the image (default 120 for preview)

        Returns:
            Ảnh đã xử lý
        """
        result = image.copy()
        h, w = image.shape[:2]
        is_color = len(image.shape) == 3

        # Lấy bounding box của safe zone
        x1, y1, x2, y2 = safe_zone.bbox
        x1 = max(0, min(x1, w - 1))
        y1 = max(0, min(y1, h - 1))
        x2 = min(x2, w)
        y2 = min(y2, h)

        zw, zh = x2 - x1, y2 - y1
        if zw <= 0 or zh <= 0:
            return result

        # Lấy màu nền
        bg_color = self.get_background_color(image)

        # Tạo mask từ polygon (trong local coords)
        polygon_mask = safe_zone.to_mask(w, h)
        local_polygon_mask = polygon_mask[y1:y2, x1:x2]

        # Vùng cần xử lý
        region = image[y1:y2, x1:x2]

        # Chuyển sang grayscale để phân tích
        if is_color:
            gray_region = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
            bg_gray = int(0.114 * bg_color[0] + 0.587 * bg_color[1] + 0.299 * bg_color[2])
        else:
            gray_region = region.copy()
            bg_gray = bg_color[0]

        # Tìm pixel tối hơn nền
        diff = bg_gray - gray_region.astype(np.int16)
        artifact_mask = diff > zone.threshold

        # Bảo vệ chữ đen - chỉ khi text protection được bật
        if self._text_protection.enabled:
            zone_id_lower = zone.id.lower()
            is_edge_or_corner = zone_id_lower.startswith('margin_') or zone_id_lower.startswith('corner_')
            text_threshold = 50 if is_edge_or_corner else 80  # Giảm cho cạnh/góc
            text_mask = gray_region < text_threshold
            artifact_mask = artifact_mask & ~text_mask

        # Bảo vệ màu đỏ/xanh nếu được bật
        if self.protect_red and is_color:
            color_mask = self.is_red_or_blue(region, artifact_mask)
            artifact_mask = artifact_mask & ~color_mask

        # Chỉ xử lý trong polygon mask
        artifact_mask = artifact_mask & (local_polygon_mask > 0)

        # Morphological operations - scale kernel size with DPI
        dpi_scale = render_dpi / 120.0
        kernel_size = max(5, int(5 * dpi_scale))
        if kernel_size % 2 == 0:
            kernel_size += 1  # Ensure odd size
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        artifact_mask = artifact_mask.astype(np.uint8) * 255
        artifact_mask = cv2.morphologyEx(artifact_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        artifact_mask = cv2.dilate(artifact_mask, kernel, iterations=3)

        # Giới hạn lại trong polygon sau morphology
        artifact_mask = (artifact_mask > 0) & (local_polygon_mask > 0)

        # Đổ màu nền
        if is_color:
            for c in range(3):
                channel = result[y1:y2, x1:x2, c]
                channel[artifact_mask] = bg_color[c]
        else:
            result[y1:y2, x1:x2][artifact_mask] = bg_gray

        return result

    def _process_zone_with_protection(self, image: np.ndarray, zone: Zone,
                                        protected_regions: List, w: int, h: int,
                                        render_dpi: int = 120) -> np.ndarray:
        """
        Xử lý zone với bảo vệ các vùng protected (fallback khi không có zone_optimizer).

        Args:
            image: Ảnh cần xử lý
            zone: Zone cần xử lý (removal)
            protected_regions: Danh sách ProtectedRegion cần bảo vệ
            w: Chiều rộng ảnh
            h: Chiều cao ảnh
            render_dpi: DPI used to render the image (default 120 for preview)

        Returns:
            Ảnh đã xử lý
        """
        if not zone.enabled:
            return image

        result = image.copy()
        is_color = len(image.shape) == 3

        # Lấy tọa độ vùng (với edge padding cho góc/cạnh)
        zx, zy, zw, zh = zone.to_pixels_with_edge_padding(w, h, padding=10, render_dpi=render_dpi)

        # Đảm bảo không vượt quá biên
        zx = max(0, min(zx, w - 1))
        zy = max(0, min(zy, h - 1))
        zw = min(zw, w - zx)
        zh = min(zh, h - zy)

        if zw <= 0 or zh <= 0:
            return result

        # Tạo protection mask từ tất cả protected regions
        protection_mask = np.zeros((zh, zw), dtype=bool)
        for region in protected_regions:
            # Lấy bbox của protected region
            rx1, ry1, rx2, ry2 = region.bbox

            # Tính intersection với zone
            ix1 = max(zx, rx1)
            iy1 = max(zy, ry1)
            ix2 = min(zx + zw, rx2)
            iy2 = min(zy + zh, ry2)

            if ix1 < ix2 and iy1 < iy2:
                # Có intersection - mark các pixel này là protected
                local_x1 = ix1 - zx
                local_y1 = iy1 - zy
                local_x2 = ix2 - zx
                local_y2 = iy2 - zy
                protection_mask[local_y1:local_y2, local_x1:local_x2] = True

        # Lấy màu nền
        bg_color = self.get_background_color(image)

        # Vùng cần xử lý
        region = image[zy:zy+zh, zx:zx+zw]

        # Chuyển sang grayscale để phân tích
        if is_color:
            gray_region = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
            bg_gray = int(0.114 * bg_color[0] + 0.587 * bg_color[1] + 0.299 * bg_color[2])
        else:
            gray_region = region.copy()
            bg_gray = bg_color[0]

        # Tìm pixel tối hơn nền
        diff = bg_gray - gray_region.astype(np.int16)
        artifact_mask = diff > zone.threshold

        # Bảo vệ chữ đen - chỉ khi text protection được bật
        if self._text_protection.enabled:
            zone_id_lower = zone.id.lower()
            is_edge_or_corner = zone_id_lower.startswith('margin_') or zone_id_lower.startswith('corner_')
            text_threshold = 50 if is_edge_or_corner else 80  # Giảm cho cạnh/góc
            text_mask = gray_region < text_threshold
            artifact_mask = artifact_mask & ~text_mask

        # Bảo vệ màu đỏ/xanh nếu được bật
        if self.protect_red and is_color:
            color_mask = self.is_red_or_blue(region, artifact_mask)
            artifact_mask = artifact_mask & ~color_mask

        # Loại trừ các vùng protected khỏi artifact_mask
        artifact_mask = artifact_mask & ~protection_mask

        # Morphological operations - scale kernel size with DPI
        dpi_scale = render_dpi / 120.0
        kernel_size = max(5, int(5 * dpi_scale))
        if kernel_size % 2 == 0:
            kernel_size += 1  # Ensure odd size
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        artifact_mask = artifact_mask.astype(np.uint8) * 255
        artifact_mask = cv2.morphologyEx(artifact_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        artifact_mask = cv2.dilate(artifact_mask, kernel, iterations=3)

        # Giới hạn lại không được xử lý vùng protected sau morphology
        artifact_mask = (artifact_mask > 0) & ~protection_mask

        # Đổ màu nền
        if is_color:
            for c in range(3):
                channel = result[zy:zy+zh, zx:zx+zw, c]
                channel[artifact_mask] = bg_color[c]
        else:
            result[zy:zy+zh, zx:zx+zw][artifact_mask] = bg_gray

        return result

    def process_image(self, image: np.ndarray, zones: List[Zone],
                      protected_regions: Optional[List] = None,
                      render_dpi: int = 120) -> np.ndarray:
        """
        Xử lý ảnh với nhiều vùng.

        Nếu text protection được bật, sẽ:
        1. Detect layout để tìm vùng text (hoặc dùng regions đã detect)
        2. Tính safe zones bằng Hybrid Polygon
        3. Chỉ xử lý trong safe zones (không chồng lên text)

        Custom protect zones (zone_type='protect') được bỏ qua khi xóa
        và được thêm vào danh sách protected regions.

        Args:
            image: Ảnh cần xử lý
            zones: Danh sách vùng cần xử lý
            protected_regions: Danh sách vùng protected đã detect (optional, tránh detect lại)
            render_dpi: DPI used to render the image (default 120 for preview)

        Returns:
            Ảnh đã xử lý
        """
        result = image.copy()
        h, w = image.shape[:2]

        # Tách zones thành removal zones và protection zones
        removal_zones = []
        custom_protect_regions = []

        for zone in zones:
            if not zone.enabled:
                continue

            if getattr(zone, 'zone_type', 'remove') == 'protect':
                # Custom protect zone -> convert to ProtectedRegion
                from .layout_detector import ProtectedRegion
                x, y, zw, zh = zone.to_pixels(w, h, render_dpi)
                custom_protect_regions.append(ProtectedRegion(
                    bbox=(x, y, x + zw, y + zh),
                    label='custom_protect',
                    confidence=1.0
                ))
            else:
                removal_zones.append(zone)


        # Combine AI-detected regions with custom protect regions
        all_protected = list(protected_regions or []) + custom_protect_regions

        # Sử dụng regions đã detect hoặc detect mới
        if protected_regions is None and self._text_protection.enabled:
            detected_regions = self.detect_protected_regions(image)
            all_protected = detected_regions + custom_protect_regions

        # Nếu có protected regions (AI hoặc custom), cố gắng sử dụng zone_optimizer
        if all_protected and self.zone_optimizer is not None:
            for zone in removal_zones:
                # Convert zone to bbox (với edge padding cho góc/cạnh)
                user_bbox = zone.to_bbox_with_edge_padding(w, h, padding=10, render_dpi=render_dpi)

                # Optimize zone to get safe zones (avoiding protected regions)
                safe_zones = self.zone_optimizer.optimize(user_bbox, all_protected)

                # Process each safe zone
                for safe_zone in safe_zones:
                    result = self._process_safe_zone(result, safe_zone, zone, render_dpi)
        elif all_protected:
            # Fallback: subtract protected regions from removal zones manually
            for zone in removal_zones:
                result = self._process_zone_with_protection(result, zone, all_protected, w, h, render_dpi)
        else:
            # Original behavior - no protection
            for zone in removal_zones:
                result = self.process_zone(result, zone, render_dpi)

        return result

    def process_image_with_regions(self, image: np.ndarray, zones: List[Zone],
                                     render_dpi: int = 120):
        """
        Xử lý ảnh và trả về cả protected regions (cho preview overlay).

        Args:
            image: Ảnh cần xử lý
            zones: Danh sách vùng cần xử lý
            render_dpi: DPI used to render the image (default 120 for preview)

        Returns:
            Tuple[np.ndarray, List[ProtectedRegion]]: (ảnh đã xử lý, danh sách vùng protected)
        """
        protected_regions = []
        if self._text_protection.enabled:
            protected_regions = self.detect_protected_regions(image)

        # Truyền regions đã detect để tránh detect lại trong process_image
        result = self.process_image(image, zones, protected_regions=protected_regions, render_dpi=render_dpi)
        return result, protected_regions


# Preset zones
# Default pixel sizes for staple marks (typical at 150 DPI)
DEFAULT_CORNER_WIDTH_PX = 130   # Fixed corner width
DEFAULT_CORNER_HEIGHT_PX = 130  # Fixed corner height
DEFAULT_EDGE_DEPTH_PX = 50      # Fixed edge depth (into page, halved from 100)

PRESET_ZONES = {
    'corner_tl': Zone(
        id='corner_tl',
        name='Góc trên trái',
        x=0.0, y=0.0,
        width=0.12, height=0.12,  # Fallback % values
        threshold=3,
        size_mode='fixed',
        width_px=DEFAULT_CORNER_WIDTH_PX,
        height_px=DEFAULT_CORNER_HEIGHT_PX
    ),
    'corner_tr': Zone(
        id='corner_tr',
        name='Góc trên phải',
        x=0.88, y=0.0,
        width=0.12, height=0.12,
        threshold=5,
        size_mode='fixed',
        width_px=DEFAULT_CORNER_WIDTH_PX,
        height_px=DEFAULT_CORNER_HEIGHT_PX
    ),
    'corner_bl': Zone(
        id='corner_bl',
        name='Góc dưới trái',
        x=0.0, y=0.88,
        width=0.12, height=0.12,
        threshold=5,
        size_mode='fixed',
        width_px=DEFAULT_CORNER_WIDTH_PX,
        height_px=DEFAULT_CORNER_HEIGHT_PX
    ),
    'corner_br': Zone(
        id='corner_br',
        name='Góc dưới phải',
        x=0.88, y=0.88,
        width=0.12, height=0.12,
        threshold=5,
        size_mode='fixed',
        width_px=DEFAULT_CORNER_WIDTH_PX,
        height_px=DEFAULT_CORNER_HEIGHT_PX
    ),
    'margin_left': Zone(
        id='margin_left',
        name='Viền trái',
        x=0.0, y=0.0,
        width=0.08, height=1.0,  # 100% of page height + overflow
        threshold=8,
        size_mode='hybrid',
        width_px=DEFAULT_EDGE_DEPTH_PX,  # Fixed depth
        height_px=0  # Use % for length
    ),
    'margin_right': Zone(
        id='margin_right',
        name='Viền phải',
        x=0.92, y=0.0,
        width=0.08, height=1.0,  # 100% of page height + overflow
        threshold=8,
        size_mode='hybrid',
        width_px=DEFAULT_EDGE_DEPTH_PX,
        height_px=0
    ),
}
