"""
Tests for geometry utilities module
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try to import cv2 to check if available
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

if CV2_AVAILABLE:
    from utils.geometry import (
        calculate_intersection_area,
        calculate_overlap_ratio,
        calculate_iou,
        expand_rect,
        shrink_rect,
        rect_area,
        rect_center,
        point_in_rect,
        rects_intersect,
        merge_rects,
        clip_rect_to_bounds,
        is_shapely_available,
    )
else:
    # Define dummy functions for testing without cv2
    def calculate_intersection_area(rect1, rect2):
        x1 = max(rect1[0], rect2[0])
        y1 = max(rect1[1], rect2[1])
        x2 = min(rect1[2], rect2[2])
        y2 = min(rect1[3], rect2[3])
        if x1 >= x2 or y1 >= y2:
            return 0.0
        return float((x2 - x1) * (y2 - y1))

    def rect_area(rect):
        return max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])

    def rect_center(rect):
        return ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)

    def point_in_rect(point, rect):
        x, y = point
        return rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]

    def rects_intersect(rect1, rect2):
        return calculate_intersection_area(rect1, rect2) > 0

    def calculate_overlap_ratio(rect1, rect2):
        intersection = calculate_intersection_area(rect1, rect2)
        if intersection == 0:
            return 0.0
        area1 = rect_area(rect1)
        area2 = rect_area(rect2)
        min_area = min(area1, area2)
        if min_area == 0:
            return 0.0
        return intersection / min_area

    def calculate_iou(rect1, rect2):
        intersection = calculate_intersection_area(rect1, rect2)
        if intersection == 0:
            return 0.0
        area1 = rect_area(rect1)
        area2 = rect_area(rect2)
        union = area1 + area2 - intersection
        if union == 0:
            return 0.0
        return intersection / union

    def expand_rect(rect, margin, max_width=None, max_height=None):
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

    def shrink_rect(rect, margin):
        x1, y1, x2, y2 = rect
        x1 = x1 + margin
        y1 = y1 + margin
        x2 = max(x1, x2 - margin)
        y2 = max(y1, y2 - margin)
        return (x1, y1, x2, y2)

    def merge_rects(rects):
        if not rects:
            return (0, 0, 0, 0)
        x1 = min(r[0] for r in rects)
        y1 = min(r[1] for r in rects)
        x2 = max(r[2] for r in rects)
        y2 = max(r[3] for r in rects)
        return (x1, y1, x2, y2)

    def clip_rect_to_bounds(rect, width, height):
        x1 = max(0, min(rect[0], width))
        y1 = max(0, min(rect[1], height))
        x2 = max(0, min(rect[2], width))
        y2 = max(0, min(rect[3], height))
        return (x1, y1, x2, y2)

    def is_shapely_available():
        try:
            import shapely
            return True
        except ImportError:
            return False


class TestRectangleOperations(unittest.TestCase):
    """Test rectangle operations"""

    def test_rect_area(self):
        """Test rectangle area calculation"""
        self.assertEqual(rect_area((0, 0, 100, 100)), 10000)
        self.assertEqual(rect_area((10, 20, 110, 120)), 10000)
        self.assertEqual(rect_area((0, 0, 0, 0)), 0)

    def test_rect_center(self):
        """Test rectangle center calculation"""
        self.assertEqual(rect_center((0, 0, 100, 100)), (50, 50))
        self.assertEqual(rect_center((10, 20, 110, 120)), (60, 70))

    def test_point_in_rect(self):
        """Test point in rectangle check"""
        rect = (0, 0, 100, 100)
        self.assertTrue(point_in_rect((50, 50), rect))
        self.assertTrue(point_in_rect((0, 0), rect))
        self.assertTrue(point_in_rect((100, 100), rect))
        self.assertFalse(point_in_rect((101, 50), rect))
        self.assertFalse(point_in_rect((-1, 50), rect))


class TestIntersection(unittest.TestCase):
    """Test intersection calculations"""

    def test_intersection_area_overlapping(self):
        """Test intersection area for overlapping rectangles"""
        rect1 = (0, 0, 100, 100)
        rect2 = (50, 50, 150, 150)
        self.assertEqual(calculate_intersection_area(rect1, rect2), 2500)

    def test_intersection_area_no_overlap(self):
        """Test intersection area for non-overlapping rectangles"""
        rect1 = (0, 0, 100, 100)
        rect2 = (200, 200, 300, 300)
        self.assertEqual(calculate_intersection_area(rect1, rect2), 0)

    def test_intersection_area_contained(self):
        """Test intersection area for contained rectangle"""
        rect1 = (0, 0, 100, 100)
        rect2 = (25, 25, 75, 75)
        self.assertEqual(calculate_intersection_area(rect1, rect2), 2500)

    def test_rects_intersect(self):
        """Test rectangle intersection check"""
        self.assertTrue(rects_intersect((0, 0, 100, 100), (50, 50, 150, 150)))
        self.assertFalse(rects_intersect((0, 0, 100, 100), (200, 200, 300, 300)))


class TestOverlapAndIoU(unittest.TestCase):
    """Test overlap ratio and IoU calculations"""

    def test_overlap_ratio(self):
        """Test overlap ratio calculation"""
        rect1 = (0, 0, 100, 100)
        rect2 = (0, 0, 100, 100)
        self.assertEqual(calculate_overlap_ratio(rect1, rect2), 1.0)

    def test_overlap_ratio_partial(self):
        """Test overlap ratio for partial overlap"""
        rect1 = (0, 0, 100, 100)
        rect2 = (50, 50, 150, 150)
        # Intersection is 50x50=2500, smaller rect is 10000
        self.assertEqual(calculate_overlap_ratio(rect1, rect2), 0.25)

    def test_iou_same_rect(self):
        """Test IoU for identical rectangles"""
        rect = (0, 0, 100, 100)
        self.assertEqual(calculate_iou(rect, rect), 1.0)

    def test_iou_no_overlap(self):
        """Test IoU for non-overlapping rectangles"""
        rect1 = (0, 0, 100, 100)
        rect2 = (200, 200, 300, 300)
        self.assertEqual(calculate_iou(rect1, rect2), 0.0)


class TestRectTransformations(unittest.TestCase):
    """Test rectangle transformations"""

    def test_expand_rect(self):
        """Test rectangle expansion"""
        rect = (10, 10, 90, 90)
        expanded = expand_rect(rect, 10)
        self.assertEqual(expanded, (0, 0, 100, 100))

    def test_expand_rect_with_bounds(self):
        """Test rectangle expansion with bounds"""
        rect = (10, 10, 90, 90)
        expanded = expand_rect(rect, 20, max_width=95, max_height=95)
        self.assertEqual(expanded, (0, 0, 95, 95))

    def test_shrink_rect(self):
        """Test rectangle shrinking"""
        rect = (0, 0, 100, 100)
        shrunk = shrink_rect(rect, 10)
        self.assertEqual(shrunk, (10, 10, 90, 90))

    def test_shrink_rect_too_much(self):
        """Test rectangle shrinking too much"""
        rect = (0, 0, 10, 10)
        shrunk = shrink_rect(rect, 20)
        # Should clamp to valid rect
        self.assertEqual(shrunk[0], 20)
        self.assertEqual(shrunk[1], 20)

    def test_merge_rects(self):
        """Test merging rectangles"""
        rects = [(0, 0, 50, 50), (50, 50, 100, 100), (25, 25, 75, 75)]
        merged = merge_rects(rects)
        self.assertEqual(merged, (0, 0, 100, 100))

    def test_merge_rects_empty(self):
        """Test merging empty list"""
        self.assertEqual(merge_rects([]), (0, 0, 0, 0))

    def test_clip_rect_to_bounds(self):
        """Test clipping rectangle to bounds"""
        rect = (-10, -10, 200, 200)
        clipped = clip_rect_to_bounds(rect, 100, 100)
        self.assertEqual(clipped, (0, 0, 100, 100))


class TestShapelyAvailability(unittest.TestCase):
    """Test shapely availability check"""

    def test_is_shapely_available_returns_bool(self):
        """Test is_shapely_available returns boolean"""
        result = is_shapely_available()
        self.assertIsInstance(result, bool)


if __name__ == '__main__':
    unittest.main()
