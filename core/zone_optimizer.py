"""
Zone Optimizer - Hybrid Polygon Algorithm

Chức năng:
- Nhận user zone và protected regions từ layout detector
- Tính toán safe zones bằng cách trừ các vùng text khỏi user zone
- Return danh sách SafeZone (polygon-based)
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional, Union
import numpy as np

try:
    from shapely.geometry import Polygon, MultiPolygon, box, GeometryCollection
    from shapely.ops import unary_union
    from shapely.validation import make_valid
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False

from .layout_detector import ProtectedRegion


@dataclass
class SafeZone:
    """Vùng an toàn có thể xóa (không chứa text)"""
    polygon: 'Polygon'  # Shapely Polygon
    original_zone: Tuple[int, int, int, int]  # User's original zone bbox
    coverage: float  # Tỷ lệ diện tích so với zone gốc (0.0-1.0)

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        """Get bounding box (x1, y1, x2, y2)"""
        minx, miny, maxx, maxy = self.polygon.bounds
        return (int(minx), int(miny), int(maxx), int(maxy))

    @property
    def vertices(self) -> List[Tuple[int, int]]:
        """Get polygon vertices as list of (x, y) tuples"""
        if self.polygon.is_empty:
            return []
        coords = list(self.polygon.exterior.coords)
        return [(int(x), int(y)) for x, y in coords[:-1]]  # Exclude closing point

    @property
    def area(self) -> float:
        """Get polygon area"""
        return self.polygon.area

    def to_mask(self, width: int, height: int) -> np.ndarray:
        """Convert polygon to binary mask"""
        import cv2
        mask = np.zeros((height, width), dtype=np.uint8)
        if not self.vertices:
            return mask
        pts = np.array(self.vertices, dtype=np.int32)
        cv2.fillPoly(mask, [pts], 255)
        return mask

    def to_contour(self) -> np.ndarray:
        """Convert polygon to OpenCV contour format"""
        return np.array(self.vertices, dtype=np.int32).reshape((-1, 1, 2))


class HybridPolygonOptimizer:
    """
    Tối ưu vùng xóa bằng thuật toán Hybrid Polygon.

    Trừ các vùng protected (text, table, ...) khỏi user zone
    để tạo safe zones không chồng lấn nội dung quan trọng.
    """

    def __init__(self,
                 margin: int = 5,
                 simplify_tolerance: float = 2.0,
                 min_area: float = 100.0):
        """
        Khởi tạo optimizer.

        Args:
            margin: Lề an toàn xung quanh vùng protected (pixels)
            simplify_tolerance: Độ đơn giản hóa polygon (Douglas-Peucker)
            min_area: Diện tích tối thiểu của safe zone (pixels^2)
        """
        if not SHAPELY_AVAILABLE:
            raise ImportError("Shapely library required. Install: pip install shapely>=2.0.0")

        self.margin = margin
        self.simplify_tolerance = simplify_tolerance
        self.min_area = min_area

    def optimize(self,
                 user_zone: Tuple[int, int, int, int],
                 protected_regions: List[ProtectedRegion]) -> List[SafeZone]:
        """
        Tính toán safe zones từ user zone và protected regions.

        7-step algorithm:
        1. Convert user zone to Shapely Polygon
        2. Filter regions that intersect with user zone
        3. Apply buffer margin to protected regions
        4. Union all buffered regions
        5. Subtract from user zone
        6. Extract and simplify polygons
        7. Filter by min_area and validate

        Args:
            user_zone: (x1, y1, x2, y2) vùng user chọn
            protected_regions: Danh sách ProtectedRegion từ layout detector

        Returns:
            List[SafeZone]: Danh sách vùng an toàn có thể xóa
        """
        print(f"[DEBUG ZoneOptimizer] optimize called:")
        print(f"[DEBUG ZoneOptimizer]   user_zone={user_zone}")
        print(f"[DEBUG ZoneOptimizer]   protected_regions count={len(protected_regions)}")
        print(f"[DEBUG ZoneOptimizer]   margin={self.margin}")

        # Step 1: Convert user zone to Shapely Polygon
        x1, y1, x2, y2 = user_zone
        user_polygon = box(x1, y1, x2, y2)
        original_area = user_polygon.area

        if original_area <= 0:
            print("[DEBUG ZoneOptimizer]   original_area <= 0, returning []")
            return []

        # Step 2: Filter relevant regions (intersection check)
        relevant_regions = []
        for region in protected_regions:
            region_poly = region.to_shapely()
            if region_poly is not None and user_polygon.intersects(region_poly):
                relevant_regions.append(region)
                print(f"[DEBUG ZoneOptimizer]   INTERSECTS: {region.label} bbox={region.bbox}")
            else:
                print(f"[DEBUG ZoneOptimizer]   no intersect: {region.label} bbox={region.bbox}")

        # No protected regions in zone -> return original zone as safe
        if not relevant_regions:
            print("[DEBUG ZoneOptimizer]   No relevant regions, returning full zone")
            return [SafeZone(
                polygon=user_polygon,
                original_zone=user_zone,
                coverage=1.0
            )]

        # Step 3: Apply buffer margin to protected regions
        buffered_regions = []
        for region in relevant_regions:
            region_poly = region.to_shapely()
            if region_poly is not None:
                buffered = region_poly.buffer(self.margin)
                if buffered.is_valid and not buffered.is_empty:
                    buffered_regions.append(buffered)

        if not buffered_regions:
            return [SafeZone(
                polygon=user_polygon,
                original_zone=user_zone,
                coverage=1.0
            )]

        # Step 4: Union all buffered regions
        try:
            protection_union = unary_union(buffered_regions)
            if not protection_union.is_valid:
                protection_union = make_valid(protection_union)
        except Exception as e:
            print(f"[ZoneOptimizer] Union error: {e}")
            return [SafeZone(
                polygon=user_polygon,
                original_zone=user_zone,
                coverage=1.0
            )]

        # Step 5: Subtract protected regions from user zone
        try:
            safe_geometry = user_polygon.difference(protection_union)
            if not safe_geometry.is_valid:
                safe_geometry = make_valid(safe_geometry)
        except Exception as e:
            print(f"[ZoneOptimizer] Difference error: {e}")
            return []

        # Step 6: Extract polygons from result
        polygons = self._extract_polygons(safe_geometry)

        # Step 7: Simplify, validate, and filter by min_area
        safe_zones = []
        for poly in polygons:
            # Simplify polygon
            simplified = poly.simplify(self.simplify_tolerance, preserve_topology=True)

            # Validate
            if not simplified.is_valid:
                simplified = make_valid(simplified)

            # Skip if too small or empty
            if simplified.is_empty or simplified.area < self.min_area:
                continue

            # Skip if not a Polygon (could be a line after simplification)
            if not isinstance(simplified, Polygon):
                continue

            # Calculate coverage
            coverage = simplified.area / original_area

            safe_zones.append(SafeZone(
                polygon=simplified,
                original_zone=user_zone,
                coverage=coverage
            ))

        print(f"[DEBUG ZoneOptimizer]   Returning {len(safe_zones)} safe zones")
        for i, sz in enumerate(safe_zones):
            print(f"[DEBUG ZoneOptimizer]   safe_zone[{i}]: bbox={sz.bbox}, coverage={sz.coverage:.2f}")
        return safe_zones

    def _extract_polygons(self, geometry) -> List['Polygon']:
        """
        Extract all Polygon objects from various geometry types.

        Handles: Polygon, MultiPolygon, GeometryCollection
        """
        if geometry is None or geometry.is_empty:
            return []

        if isinstance(geometry, Polygon):
            return [geometry] if not geometry.is_empty else []

        if isinstance(geometry, MultiPolygon):
            return [p for p in geometry.geoms if isinstance(p, Polygon) and not p.is_empty]

        if isinstance(geometry, GeometryCollection):
            polygons = []
            for geom in geometry.geoms:
                polygons.extend(self._extract_polygons(geom))
            return polygons

        return []

    def optimize_multiple(self,
                          zones: List[Tuple[int, int, int, int]],
                          protected_regions: List[ProtectedRegion]) -> List[List[SafeZone]]:
        """
        Optimize multiple zones at once.

        Args:
            zones: List of user zones
            protected_regions: Protected regions for all zones

        Returns:
            List of SafeZone lists, one per input zone
        """
        return [self.optimize(zone, protected_regions) for zone in zones]

    def set_margin(self, margin: int):
        """Set safety margin (pixels)"""
        self.margin = max(0, margin)

    def set_simplify_tolerance(self, tolerance: float):
        """Set polygon simplification tolerance"""
        self.simplify_tolerance = max(0.0, tolerance)

    def set_min_area(self, area: float):
        """Set minimum safe zone area (pixels^2)"""
        self.min_area = max(0.0, area)


def is_shapely_available() -> bool:
    """Check if Shapely is available"""
    return SHAPELY_AVAILABLE


def optimize_zone(user_zone: Tuple[int, int, int, int],
                  protected_regions: List[ProtectedRegion],
                  margin: int = 5) -> List[SafeZone]:
    """
    Convenience function to optimize a single zone.

    Args:
        user_zone: (x1, y1, x2, y2)
        protected_regions: List of ProtectedRegion
        margin: Safety margin in pixels

    Returns:
        List[SafeZone]
    """
    if not SHAPELY_AVAILABLE:
        print("[ZoneOptimizer] Shapely not available. Returning original zone.")
        return []

    optimizer = HybridPolygonOptimizer(margin=margin)
    return optimizer.optimize(user_zone, protected_regions)
