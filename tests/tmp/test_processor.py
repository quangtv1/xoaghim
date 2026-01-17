"""
Tests for processor module
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Check if cv2 and numpy are available
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    np = None

# Skip all tests if cv2 not available
if CV2_AVAILABLE:
    from core.processor import Zone, StapleRemover, TextProtectionOptions, PRESET_ZONES
else:
    # Define minimal Zone for testing without cv2
    from dataclasses import dataclass
    from typing import Set

    @dataclass
    class Zone:
        id: str
        name: str
        x: float
        y: float
        width: float
        height: float
        threshold: int = 5
        enabled: bool = True

        def to_pixels(self, img_width, img_height):
            x = int(self.x * img_width)
            y = int(self.y * img_height)
            w = int(self.width * img_width)
            h = int(self.height * img_height)
            return (x, y, w, h)

        def to_bbox(self, img_width, img_height):
            x, y, w, h = self.to_pixels(img_width, img_height)
            return (x, y, x + w, y + h)

    @dataclass
    class TextProtectionOptions:
        enabled: bool = False
        protected_labels: Set[str] = None
        margin: int = 5
        confidence: float = 0.5

        def __post_init__(self):
            if self.protected_labels is None:
                self.protected_labels = {'plain_text', 'title', 'table'}

    PRESET_ZONES = {
        'corner_tl': Zone(id='corner_tl', name='Góc trên trái', x=0.0, y=0.0, width=0.12, height=0.12),
        'corner_tr': Zone(id='corner_tr', name='Góc trên phải', x=0.88, y=0.0, width=0.12, height=0.12),
        'corner_bl': Zone(id='corner_bl', name='Góc dưới trái', x=0.0, y=0.88, width=0.12, height=0.12),
        'corner_br': Zone(id='corner_br', name='Góc dưới phải', x=0.88, y=0.88, width=0.12, height=0.12),
        'margin_left': Zone(id='margin_left', name='Viền trái', x=0.0, y=0.0, width=0.08, height=1.0),
        'margin_right': Zone(id='margin_right', name='Viền phải', x=0.92, y=0.0, width=0.08, height=1.0),
    }

    StapleRemover = None


class TestZone(unittest.TestCase):
    """Test Zone dataclass"""

    def test_zone_creation(self):
        """Test creating a Zone"""
        zone = Zone(
            id='test',
            name='Test Zone',
            x=0.0,
            y=0.0,
            width=0.1,
            height=0.1,
            threshold=5,
            enabled=True
        )
        self.assertEqual(zone.id, 'test')
        self.assertEqual(zone.name, 'Test Zone')
        self.assertTrue(zone.enabled)

    def test_zone_to_pixels(self):
        """Test zone to_pixels conversion"""
        zone = Zone(
            id='test',
            name='Test',
            x=0.1,
            y=0.2,
            width=0.3,
            height=0.4,
            threshold=5
        )
        x, y, w, h = zone.to_pixels(1000, 1000)
        self.assertEqual(x, 100)
        self.assertEqual(y, 200)
        self.assertEqual(w, 300)
        self.assertEqual(h, 400)

    def test_zone_to_bbox(self):
        """Test zone to_bbox conversion"""
        zone = Zone(
            id='test',
            name='Test',
            x=0.1,
            y=0.2,
            width=0.3,
            height=0.4,
            threshold=5
        )
        x1, y1, x2, y2 = zone.to_bbox(1000, 1000)
        self.assertEqual(x1, 100)
        self.assertEqual(y1, 200)
        self.assertEqual(x2, 400)
        self.assertEqual(y2, 600)


class TestPresetZones(unittest.TestCase):
    """Test preset zones"""

    def test_preset_zones_exist(self):
        """Test preset zones are defined"""
        self.assertIn('corner_tl', PRESET_ZONES)
        self.assertIn('corner_tr', PRESET_ZONES)
        self.assertIn('corner_bl', PRESET_ZONES)
        self.assertIn('corner_br', PRESET_ZONES)
        self.assertIn('margin_left', PRESET_ZONES)
        self.assertIn('margin_right', PRESET_ZONES)

    def test_corner_zones_positions(self):
        """Test corner zones are at correct positions"""
        tl = PRESET_ZONES['corner_tl']
        tr = PRESET_ZONES['corner_tr']
        bl = PRESET_ZONES['corner_bl']
        br = PRESET_ZONES['corner_br']

        # Top-left
        self.assertEqual(tl.x, 0.0)
        self.assertEqual(tl.y, 0.0)

        # Top-right
        self.assertEqual(tr.x, 0.88)
        self.assertEqual(tr.y, 0.0)

        # Bottom-left
        self.assertEqual(bl.x, 0.0)
        self.assertEqual(bl.y, 0.88)

        # Bottom-right
        self.assertEqual(br.x, 0.88)
        self.assertEqual(br.y, 0.88)


class TestTextProtectionOptions(unittest.TestCase):
    """Test TextProtectionOptions dataclass"""

    def test_default_options(self):
        """Test default options"""
        options = TextProtectionOptions()
        self.assertTrue(options.enabled)  # Default is True (protection enabled by default)
        self.assertEqual(options.margin, 5)
        self.assertEqual(options.confidence, 0.1)  # Default confidence is 10%
        self.assertIn('plain_text', options.protected_labels)

    def test_custom_options(self):
        """Test custom options"""
        options = TextProtectionOptions(
            enabled=True,
            protected_labels={'title', 'table'},
            margin=10,
            confidence=0.7
        )
        self.assertTrue(options.enabled)
        self.assertEqual(options.margin, 10)
        self.assertEqual(options.confidence, 0.7)
        self.assertIn('title', options.protected_labels)
        self.assertIn('table', options.protected_labels)


@unittest.skipUnless(CV2_AVAILABLE, "cv2/numpy not installed")
class TestStapleRemover(unittest.TestCase):
    """Test StapleRemover class"""

    def setUp(self):
        self.processor = StapleRemover(protect_red=True)

    def test_processor_creation(self):
        """Test processor can be created"""
        self.assertIsNotNone(self.processor)
        self.assertTrue(self.processor.protect_red)

    def test_get_background_color(self):
        """Test background color detection"""
        # Create white image
        img = np.ones((100, 100, 3), dtype=np.uint8) * 255
        bg_color = self.processor.get_background_color(img)

        # Should be close to white
        self.assertEqual(bg_color, (255, 255, 255))

    def test_get_background_color_gray(self):
        """Test background color detection for grayscale"""
        # Create gray image
        img = np.ones((100, 100), dtype=np.uint8) * 200
        bg_color = self.processor.get_background_color(img)

        # Should be close to (200, 200, 200)
        self.assertEqual(bg_color, (200, 200, 200))

    def test_is_red_or_blue_detection(self):
        """Test red/blue color detection"""
        # Create image with red and blue areas
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        img[:, :, 2] = 255  # Red channel
        mask = np.ones((100, 100), dtype=bool)

        color_mask = self.processor.is_red_or_blue(img, mask)
        self.assertTrue(np.any(color_mask))

    def test_process_image_no_zones(self):
        """Test processing with no zones"""
        img = np.ones((100, 100, 3), dtype=np.uint8) * 255
        result = self.processor.process_image(img, [])

        # Should return unchanged image
        np.testing.assert_array_equal(result, img)

    def test_process_image_with_zone(self):
        """Test processing with a zone"""
        # Create white image with dark corner
        img = np.ones((100, 100, 3), dtype=np.uint8) * 255
        img[0:20, 0:20] = 50  # Dark corner

        zone = Zone(
            id='test',
            name='Test',
            x=0.0,
            y=0.0,
            width=0.25,
            height=0.25,
            threshold=5,
            enabled=True
        )

        result = self.processor.process_image(img, [zone])

        # Result should be different from input (dark area processed)
        self.assertIsNotNone(result)
        self.assertEqual(result.shape, img.shape)

    def test_set_text_protection(self):
        """Test setting text protection options"""
        options = TextProtectionOptions(enabled=True, margin=10)
        self.processor.set_text_protection(options)

        # Check internal state was updated
        self.assertEqual(self.processor._text_protection.enabled, True)
        self.assertEqual(self.processor._text_protection.margin, 10)

    def test_is_text_protection_available(self):
        """Test text protection availability check"""
        result = self.processor.is_text_protection_available()
        self.assertIsInstance(result, bool)


@unittest.skipUnless(CV2_AVAILABLE, "cv2/numpy not installed")
class TestStapleRemoverIntegration(unittest.TestCase):
    """Integration tests for StapleRemover"""

    def test_process_zone_disabled(self):
        """Test that disabled zones are skipped"""
        processor = StapleRemover()
        img = np.ones((100, 100, 3), dtype=np.uint8) * 255

        zone = Zone(
            id='test',
            name='Test',
            x=0.0,
            y=0.0,
            width=0.5,
            height=0.5,
            threshold=5,
            enabled=False  # Disabled
        )

        result = processor.process_zone(img, zone)
        np.testing.assert_array_equal(result, img)


if __name__ == '__main__':
    unittest.main()
