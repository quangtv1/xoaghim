"""
Tests for zone_optimizer module
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.zone_optimizer import is_shapely_available, SafeZone

# Skip tests if shapely not available
SHAPELY_AVAILABLE = is_shapely_available()


@unittest.skipUnless(SHAPELY_AVAILABLE, "Shapely not installed")
class TestHybridPolygonOptimizer(unittest.TestCase):
    """Test HybridPolygonOptimizer class"""

    def setUp(self):
        from core.zone_optimizer import HybridPolygonOptimizer
        self.optimizer = HybridPolygonOptimizer(margin=5, min_area=100)

    def test_optimizer_creation(self):
        """Test optimizer can be created"""
        self.assertIsNotNone(self.optimizer)
        self.assertEqual(self.optimizer.margin, 5)
        self.assertEqual(self.optimizer.min_area, 100)

    def test_optimize_no_protected_regions(self):
        """Test optimize with no protected regions returns original zone"""
        from core.layout_detector import ProtectedRegion

        user_zone = (0, 0, 100, 100)
        protected_regions = []

        safe_zones = self.optimizer.optimize(user_zone, protected_regions)

        self.assertEqual(len(safe_zones), 1)
        self.assertEqual(safe_zones[0].coverage, 1.0)

    def test_optimize_with_protected_region(self):
        """Test optimize with a protected region inside"""
        from core.layout_detector import ProtectedRegion

        user_zone = (0, 0, 200, 200)
        protected_regions = [
            ProtectedRegion(bbox=(50, 50, 150, 150), label='text', confidence=0.9)
        ]

        safe_zones = self.optimizer.optimize(user_zone, protected_regions)

        # Should have safe zones (areas not covered by protected region)
        self.assertGreater(len(safe_zones), 0)

        # Total coverage should be less than 1.0
        total_coverage = sum(sz.coverage for sz in safe_zones)
        self.assertLess(total_coverage, 1.0)

    def test_optimize_protected_outside_zone(self):
        """Test optimize when protected region is outside user zone"""
        from core.layout_detector import ProtectedRegion

        user_zone = (0, 0, 100, 100)
        protected_regions = [
            ProtectedRegion(bbox=(200, 200, 300, 300), label='text', confidence=0.9)
        ]

        safe_zones = self.optimizer.optimize(user_zone, protected_regions)

        # Should return original zone since protected region doesn't intersect
        self.assertEqual(len(safe_zones), 1)
        self.assertEqual(safe_zones[0].coverage, 1.0)

    def test_set_margin(self):
        """Test setting margin"""
        self.optimizer.set_margin(10)
        self.assertEqual(self.optimizer.margin, 10)

        # Negative should be clamped to 0
        self.optimizer.set_margin(-5)
        self.assertEqual(self.optimizer.margin, 0)

    def test_set_min_area(self):
        """Test setting minimum area"""
        self.optimizer.set_min_area(200)
        self.assertEqual(self.optimizer.min_area, 200)


@unittest.skipUnless(SHAPELY_AVAILABLE, "Shapely not installed")
class TestSafeZone(unittest.TestCase):
    """Test SafeZone dataclass"""

    def test_safe_zone_bbox(self):
        """Test SafeZone bbox property"""
        from shapely.geometry import box

        polygon = box(10, 20, 110, 220)
        safe_zone = SafeZone(
            polygon=polygon,
            original_zone=(0, 0, 200, 300),
            coverage=0.5
        )

        self.assertEqual(safe_zone.bbox, (10, 20, 110, 220))

    def test_safe_zone_vertices(self):
        """Test SafeZone vertices property"""
        from shapely.geometry import box

        polygon = box(0, 0, 100, 100)
        safe_zone = SafeZone(
            polygon=polygon,
            original_zone=(0, 0, 100, 100),
            coverage=1.0
        )

        vertices = safe_zone.vertices
        self.assertEqual(len(vertices), 4)  # Rectangle has 4 vertices

    def test_safe_zone_area(self):
        """Test SafeZone area property"""
        from shapely.geometry import box

        polygon = box(0, 0, 100, 100)
        safe_zone = SafeZone(
            polygon=polygon,
            original_zone=(0, 0, 100, 100),
            coverage=1.0
        )

        self.assertEqual(safe_zone.area, 10000)


class TestShapelyAvailability(unittest.TestCase):
    """Test shapely availability function"""

    def test_is_shapely_available_returns_bool(self):
        """Test is_shapely_available returns boolean"""
        result = is_shapely_available()
        self.assertIsInstance(result, bool)


if __name__ == '__main__':
    unittest.main()
