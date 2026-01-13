"""
Tests for layout_detector module
"""
import unittest
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.layout_detector import (
    ProtectedRegion,
    check_text_protection_requirements,
    get_missing_requirements,
    is_text_protection_available,
)


class TestProtectedRegion(unittest.TestCase):
    """Test ProtectedRegion dataclass"""

    def test_create_region(self):
        """Test creating a ProtectedRegion"""
        region = ProtectedRegion(
            bbox=(10, 20, 100, 200),
            label='plain_text',
            confidence=0.85
        )
        self.assertEqual(region.bbox, (10, 20, 100, 200))
        self.assertEqual(region.label, 'plain_text')
        self.assertEqual(region.confidence, 0.85)

    def test_width_property(self):
        """Test width property"""
        region = ProtectedRegion(bbox=(10, 20, 110, 220), label='text', confidence=0.9)
        self.assertEqual(region.width, 100)

    def test_height_property(self):
        """Test height property"""
        region = ProtectedRegion(bbox=(10, 20, 110, 220), label='text', confidence=0.9)
        self.assertEqual(region.height, 200)

    def test_area_property(self):
        """Test area property"""
        region = ProtectedRegion(bbox=(0, 0, 100, 100), label='text', confidence=0.9)
        self.assertEqual(region.area, 10000)

    def test_to_shapely_without_shapely(self):
        """Test to_shapely returns None if shapely not available"""
        region = ProtectedRegion(bbox=(0, 0, 100, 100), label='text', confidence=0.9)
        # This will work if shapely is installed, return None otherwise
        result = region.to_shapely()
        # Just check it doesn't raise an exception
        self.assertTrue(result is None or hasattr(result, 'bounds'))


class TestRequirementChecks(unittest.TestCase):
    """Test requirement checking functions"""

    def test_check_requirements_returns_dict(self):
        """Test check_text_protection_requirements returns a dict"""
        result = check_text_protection_requirements()
        self.assertIsInstance(result, dict)
        self.assertIn('shapely', result)
        self.assertIn('paddleocr', result)
        self.assertIn('paddlepaddle', result)

    def test_check_requirements_values_are_bool(self):
        """Test all values in requirements dict are booleans"""
        result = check_text_protection_requirements()
        for pkg, installed in result.items():
            self.assertIsInstance(installed, bool, f"{pkg} should be bool")

    def test_get_missing_requirements_returns_list(self):
        """Test get_missing_requirements returns a list"""
        result = get_missing_requirements()
        self.assertIsInstance(result, list)

    def test_is_text_protection_available_returns_bool(self):
        """Test is_text_protection_available returns bool"""
        result = is_text_protection_available()
        self.assertIsInstance(result, bool)


if __name__ == '__main__':
    unittest.main()
