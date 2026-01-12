"""
Geometry Utilities

Chức năng:
- Chuyển đổi giữa các định dạng geometry (Shapely, OpenCV, numpy mask)
- Tính toán intersection, overlap
- Helper functions cho layout protection
"""

from typing import Tuple, List, Optional, Union
import numpy as np
import cv2

try:
    from shapely.geometry import Polygon, box
    from shapely.validation import make_valid
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False


def rect_to_polygon(rect: Tuple[int, int, int, int]) -> Optional['Polygon']:
    """
    Convert rectangle (x1, y1, x2, y2) to Shapely Polygon.

    Args:
        rect: (x1, y1, x2, y2) bounding box

    Returns:
        Shapely Polygon or None if Shapely not available
    """
    if not SHAPELY_AVAILABLE:
        return None
    x1, y1, x2, y2 = rect
    return box(x1, y1, x2, y2)


def polygon_to_mask(polygon: 'Polygon',
                    width: int,
                    height: int,
                    fill_value: int = 255) -> np.ndarray:
    """
    Convert Shapely Polygon to binary mask.

    Args:
        polygon: Shapely Polygon
        width: Mask width
        height: Mask height
        fill_value: Value for filled area (default 255)

    Returns:
        numpy array (height, width) với giá trị 0 hoặc fill_value
    """
    mask = np.zeros((height, width), dtype=np.uint8)

    if polygon is None or polygon.is_empty:
        return mask

    # Get exterior coordinates
    coords = np.array(polygon.exterior.coords, dtype=np.int32)
    cv2.fillPoly(mask, [coords], fill_value)

    # Handle holes (interior rings)
    for interior in polygon.interiors:
        hole_coords = np.array(interior.coords, dtype=np.int32)
        cv2.fillPoly(mask, [hole_coords], 0)

    return mask


def mask_to_polygon(mask: np.ndarray,
                    threshold: int = 127) -> Optional['Polygon']:
    """
    Convert binary mask to Shapely Polygon.

    Args:
        mask: Binary mask (numpy array)
        threshold: Threshold for binary conversion

    Returns:
        Shapely Polygon or None
    """
    if not SHAPELY_AVAILABLE:
        return None

    # Threshold mask
    _, binary = cv2.threshold(mask, threshold, 255, cv2.THRESH_BINARY)

    # Find contours
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    # Get largest contour
    largest = max(contours, key=cv2.contourArea)

    # Convert to polygon
    coords = [(int(p[0][0]), int(p[0][1])) for p in largest]

    if len(coords) < 3:
        return None

    try:
        poly = Polygon(coords)
        if not poly.is_valid:
            poly = make_valid(poly)
        return poly
    except Exception:
        return None


def polygon_to_contour(polygon: 'Polygon') -> np.ndarray:
    """
    Convert Shapely Polygon to OpenCV contour format.

    Args:
        polygon: Shapely Polygon

    Returns:
        numpy array shape (N, 1, 2) for OpenCV
    """
    if polygon is None or polygon.is_empty:
        return np.array([], dtype=np.int32)

    coords = list(polygon.exterior.coords)
    # Remove closing point (OpenCV doesn't need it)
    coords = coords[:-1] if coords[0] == coords[-1] else coords

    return np.array(coords, dtype=np.int32).reshape((-1, 1, 2))


def contour_to_polygon(contour: np.ndarray) -> Optional['Polygon']:
    """
    Convert OpenCV contour to Shapely Polygon.

    Args:
        contour: OpenCV contour (N, 1, 2)

    Returns:
        Shapely Polygon or None
    """
    if not SHAPELY_AVAILABLE:
        return None

    if contour is None or len(contour) < 3:
        return None

    coords = [(int(p[0][0]), int(p[0][1])) for p in contour]

    try:
        poly = Polygon(coords)
        if not poly.is_valid:
            poly = make_valid(poly)
        return poly
    except Exception:
        return None


def calculate_intersection_area(rect1: Tuple[int, int, int, int],
                                 rect2: Tuple[int, int, int, int]) -> float:
    """
    Calculate intersection area between two rectangles.

    Args:
        rect1: (x1, y1, x2, y2)
        rect2: (x1, y1, x2, y2)

    Returns:
        Intersection area in pixels^2
    """
    x1 = max(rect1[0], rect2[0])
    y1 = max(rect1[1], rect2[1])
    x2 = min(rect1[2], rect2[2])
    y2 = min(rect1[3], rect2[3])

    if x1 >= x2 or y1 >= y2:
        return 0.0

    return float((x2 - x1) * (y2 - y1))


def calculate_overlap_ratio(rect1: Tuple[int, int, int, int],
                            rect2: Tuple[int, int, int, int]) -> float:
    """
    Calculate overlap ratio (IoU-like) between two rectangles.

    Args:
        rect1: (x1, y1, x2, y2)
        rect2: (x1, y1, x2, y2)

    Returns:
        Overlap ratio (0.0 - 1.0)
    """
    intersection = calculate_intersection_area(rect1, rect2)

    if intersection == 0:
        return 0.0

    area1 = (rect1[2] - rect1[0]) * (rect1[3] - rect1[1])
    area2 = (rect2[2] - rect2[0]) * (rect2[3] - rect2[1])

    # Overlap ratio relative to smaller rectangle
    min_area = min(area1, area2)

    if min_area == 0:
        return 0.0

    return intersection / min_area


def calculate_iou(rect1: Tuple[int, int, int, int],
                  rect2: Tuple[int, int, int, int]) -> float:
    """
    Calculate Intersection over Union (IoU) between two rectangles.

    Args:
        rect1: (x1, y1, x2, y2)
        rect2: (x1, y1, x2, y2)

    Returns:
        IoU ratio (0.0 - 1.0)
    """
    intersection = calculate_intersection_area(rect1, rect2)

    if intersection == 0:
        return 0.0

    area1 = (rect1[2] - rect1[0]) * (rect1[3] - rect1[1])
    area2 = (rect2[2] - rect2[0]) * (rect2[3] - rect2[1])
    union = area1 + area2 - intersection

    if union == 0:
        return 0.0

    return intersection / union


def expand_rect(rect: Tuple[int, int, int, int],
                margin: int,
                max_width: Optional[int] = None,
                max_height: Optional[int] = None) -> Tuple[int, int, int, int]:
    """
    Expand rectangle by margin in all directions.

    Args:
        rect: (x1, y1, x2, y2)
        margin: Pixels to expand
        max_width: Maximum x2 value
        max_height: Maximum y2 value

    Returns:
        Expanded rectangle (x1, y1, x2, y2)
    """
    x1, y1, x2, y2 = rect

    x1 = max(0, x1 - margin)
    y1 = max(0, y1 - margin)
    x2 = x2 + margin
    y2 = y2 + margin

    if max_width is not None:
        x2 = min(x2, max_width)
    if max_height is not None:
        y2 = min(y2, max_height)

    return (x1, y1, x2, y2)


def shrink_rect(rect: Tuple[int, int, int, int],
                margin: int) -> Tuple[int, int, int, int]:
    """
    Shrink rectangle by margin in all directions.

    Args:
        rect: (x1, y1, x2, y2)
        margin: Pixels to shrink

    Returns:
        Shrunk rectangle (x1, y1, x2, y2)
    """
    x1, y1, x2, y2 = rect

    x1 = x1 + margin
    y1 = y1 + margin
    x2 = max(x1, x2 - margin)
    y2 = max(y1, y2 - margin)

    return (x1, y1, x2, y2)


def rect_area(rect: Tuple[int, int, int, int]) -> int:
    """Calculate rectangle area"""
    return max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])


def rect_center(rect: Tuple[int, int, int, int]) -> Tuple[int, int]:
    """Get rectangle center point"""
    return ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)


def point_in_rect(point: Tuple[int, int],
                  rect: Tuple[int, int, int, int]) -> bool:
    """Check if point is inside rectangle"""
    x, y = point
    return rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]


def rects_intersect(rect1: Tuple[int, int, int, int],
                    rect2: Tuple[int, int, int, int]) -> bool:
    """Check if two rectangles intersect"""
    return calculate_intersection_area(rect1, rect2) > 0


def merge_rects(rects: List[Tuple[int, int, int, int]]) -> Tuple[int, int, int, int]:
    """
    Merge multiple rectangles into bounding box.

    Args:
        rects: List of (x1, y1, x2, y2)

    Returns:
        Bounding box containing all rectangles
    """
    if not rects:
        return (0, 0, 0, 0)

    x1 = min(r[0] for r in rects)
    y1 = min(r[1] for r in rects)
    x2 = max(r[2] for r in rects)
    y2 = max(r[3] for r in rects)

    return (x1, y1, x2, y2)


def clip_rect_to_bounds(rect: Tuple[int, int, int, int],
                        width: int,
                        height: int) -> Tuple[int, int, int, int]:
    """
    Clip rectangle to image bounds.

    Args:
        rect: (x1, y1, x2, y2)
        width: Image width
        height: Image height

    Returns:
        Clipped rectangle
    """
    x1 = max(0, min(rect[0], width))
    y1 = max(0, min(rect[1], height))
    x2 = max(0, min(rect[2], width))
    y2 = max(0, min(rect[3], height))
    return (x1, y1, x2, y2)


def is_shapely_available() -> bool:
    """Check if Shapely library is available"""
    return SHAPELY_AVAILABLE
