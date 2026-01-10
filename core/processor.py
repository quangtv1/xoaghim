"""
Core processor - Xử lý xóa vết ghim
"""

import cv2
import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass


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


class StapleRemover:
    """Xử lý xóa vết ghim"""
    
    def __init__(self, protect_red: bool = True):
        self.protect_red = protect_red
    
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
    
    def process_image(self, image: np.ndarray, zones: List[Zone]) -> np.ndarray:
        """Xử lý ảnh với nhiều vùng"""
        result = image.copy()
        
        for zone in zones:
            if zone.enabled:
                result = self.process_zone(result, zone)
        
        return result


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
