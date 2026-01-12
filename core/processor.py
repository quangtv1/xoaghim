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
    """Vùng xử lý"""
    id: str
    name: str
    x: float  # % từ trái (0.0 - 1.0)
    y: float  # % từ trên (0.0 - 1.0)
    width: float  # % chiều rộng (0.0 - 1.0)
    height: float  # % chiều cao (0.0 - 1.0)
    threshold: int = 5
    enabled: bool = True
    
    def to_pixels(self, img_width: int, img_height: int) -> Tuple[int, int, int, int]:
        """Chuyển đổi % sang pixels: (x, y, w, h)"""
        x = int(self.x * img_width)
        y = int(self.y * img_height)
        w = int(self.width * img_width)
        h = int(self.height * img_height)
        return (x, y, w, h)

    def to_bbox(self, img_width: int, img_height: int) -> Tuple[int, int, int, int]:
        """Chuyển đổi sang bbox format: (x1, y1, x2, y2)"""
        x, y, w, h = self.to_pixels(img_width, img_height)
        return (x, y, x + w, y + h)


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

        # Sử dụng local detector (YOLO DocLayNet - recommended)
        if self._layout_detector is None:
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
        print(f"[DEBUG] detect_protected_regions: enabled={self._text_protection.enabled}, use_remote={self._text_protection.use_remote}")

        if not self._text_protection.enabled:
            print("[DEBUG] Text protection disabled")
            return []

        detector = self.layout_detector
        print(f"[DEBUG] detector type: {type(detector)}")

        if detector is None:
            print("[DEBUG] detector is None")
            return []

        is_avail = detector.is_available()
        print(f"[DEBUG] detector.is_available() = {is_avail}")

        if not is_avail:
            print("[DEBUG] detector not available")
            return []

        regions = detector.detect(
            image,
            protected_labels=self._text_protection.protected_labels
        )
        print(f"[DEBUG] Detected {len(regions)} regions")
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
    
    def process_zone(self, image: np.ndarray, zone: Zone) -> np.ndarray:
        """Xử lý một vùng cụ thể"""
        if not zone.enabled:
            return image
        
        result = image.copy()
        h, w = image.shape[:2]
        is_color = len(image.shape) == 3
        
        # Lấy tọa độ vùng
        zx, zy, zw, zh = zone.to_pixels(w, h)
        
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
        
        # Bảo vệ chữ đen (gray < 80)
        text_mask = gray_region < 80
        artifact_mask = artifact_mask & ~text_mask
        
        # Bảo vệ màu đỏ/xanh nếu được bật
        if self.protect_red and is_color:
            color_mask = self.is_red_or_blue(region, artifact_mask)
            artifact_mask = artifact_mask & ~color_mask
        
        # Morphological operations
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
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
    
    def _process_safe_zone(self, image: np.ndarray, safe_zone, zone: Zone) -> np.ndarray:
        """
        Xử lý safe zone (polygon-based) thay vì rectangle.

        Args:
            image: Ảnh gốc
            safe_zone: SafeZone object từ zone_optimizer
            zone: Zone gốc (để lấy threshold)

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

        # Bảo vệ chữ đen (gray < 80)
        text_mask = gray_region < 80
        artifact_mask = artifact_mask & ~text_mask

        # Bảo vệ màu đỏ/xanh nếu được bật
        if self.protect_red and is_color:
            color_mask = self.is_red_or_blue(region, artifact_mask)
            artifact_mask = artifact_mask & ~color_mask

        # Chỉ xử lý trong polygon mask
        artifact_mask = artifact_mask & (local_polygon_mask > 0)

        # Morphological operations
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
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

    def process_image(self, image: np.ndarray, zones: List[Zone],
                      protected_regions: Optional[List] = None) -> np.ndarray:
        """
        Xử lý ảnh với nhiều vùng.

        Nếu text protection được bật, sẽ:
        1. Detect layout để tìm vùng text (hoặc dùng regions đã detect)
        2. Tính safe zones bằng Hybrid Polygon
        3. Chỉ xử lý trong safe zones (không chồng lên text)

        Args:
            image: Ảnh cần xử lý
            zones: Danh sách vùng cần xử lý
            protected_regions: Danh sách vùng protected đã detect (optional, tránh detect lại)

        Returns:
            Ảnh đã xử lý
        """
        result = image.copy()
        h, w = image.shape[:2]

        print(f"[DEBUG process_image] text_protection.enabled={self._text_protection.enabled}")
        print(f"[DEBUG process_image] zone_optimizer={self.zone_optimizer}")

        # Nếu text protection được bật và khả dụng
        if self._text_protection.enabled and self.zone_optimizer is not None:
            # Sử dụng regions đã detect hoặc detect mới
            if protected_regions is None:
                protected_regions = self.detect_protected_regions(image)
            print(f"[DEBUG process_image] Using {len(protected_regions)} protected regions")

            for zone in zones:
                if not zone.enabled:
                    continue

                # Convert zone to bbox
                user_bbox = zone.to_bbox(w, h)
                print(f"[DEBUG process_image] Zone '{zone.name}' bbox={user_bbox}")

                # Optimize zone to get safe zones (avoiding text)
                safe_zones = self.zone_optimizer.optimize(user_bbox, protected_regions)
                print(f"[DEBUG process_image] Got {len(safe_zones)} safe zones after optimization")

                # Process each safe zone
                for i, safe_zone in enumerate(safe_zones):
                    print(f"[DEBUG process_image] Processing safe_zone {i}: bbox={safe_zone.bbox}, coverage={safe_zone.coverage:.2f}")
                    result = self._process_safe_zone(result, safe_zone, zone)
        else:
            # Original behavior - no text protection
            print(f"[DEBUG process_image] Using original behavior (no text protection)")
            for zone in zones:
                if zone.enabled:
                    result = self.process_zone(result, zone)

        return result

    def process_image_with_regions(self, image: np.ndarray, zones: List[Zone]):
        """
        Xử lý ảnh và trả về cả protected regions (cho preview overlay).

        Returns:
            Tuple[np.ndarray, List[ProtectedRegion]]: (ảnh đã xử lý, danh sách vùng protected)
        """
        protected_regions = []
        if self._text_protection.enabled:
            protected_regions = self.detect_protected_regions(image)

        # Truyền regions đã detect để tránh detect lại trong process_image
        result = self.process_image(image, zones, protected_regions=protected_regions)
        return result, protected_regions


# Preset zones
PRESET_ZONES = {
    'corner_tl': Zone(
        id='corner_tl',
        name='Góc trên trái',
        x=0.0, y=0.0,
        width=0.12, height=0.12,
        threshold=3
    ),
    'corner_tr': Zone(
        id='corner_tr',
        name='Góc trên phải',
        x=0.88, y=0.0,
        width=0.12, height=0.12,
        threshold=5
    ),
    'corner_bl': Zone(
        id='corner_bl',
        name='Góc dưới trái',
        x=0.0, y=0.88,
        width=0.12, height=0.12,
        threshold=5
    ),
    'corner_br': Zone(
        id='corner_br',
        name='Góc dưới phải',
        x=0.88, y=0.88,
        width=0.12, height=0.12,
        threshold=5
    ),
    'margin_left': Zone(
        id='margin_left',
        name='Viền trái',
        x=0.0, y=0.0,
        width=0.08, height=1.0,
        threshold=8
    ),
    'margin_right': Zone(
        id='margin_right',
        name='Viền phải',
        x=0.92, y=0.0,
        width=0.08, height=1.0,
        threshold=8
    ),
}
