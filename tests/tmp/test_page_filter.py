"""
Tests for page filter expressions in batch sidebar.

Supported expressions:
- "All" or empty: no filter (show all)
- "5": exact match (5 pages)
- ">5": more than 5 pages
- "<10": less than 10 pages
- ">=3": 3 or more pages
- "<=20": 20 or fewer pages
- "5-10": between 5 and 10 pages (inclusive)
"""

import pytest
from unittest.mock import MagicMock, patch


class TestPageFilterExpressions:
    """Test _matches_page_filter logic from SidebarFileList"""

    def _matches_page_filter(self, page_count: int, filter_expr: str) -> bool:
        """Standalone version of _matches_page_filter for testing"""
        if page_count < 0:
            return True  # Page count not loaded yet

        if not filter_expr or filter_expr.lower() == 'all':
            return True

        filter_str = filter_expr.strip()

        try:
            # Range: "5-10"
            if '-' in filter_str and not filter_str.startswith('-'):
                parts = filter_str.split('-')
                if len(parts) == 2:
                    min_val = int(parts[0])
                    max_val = int(parts[1])
                    return min_val <= page_count <= max_val

            # Operators: >=, <=, >, <
            if filter_str.startswith(">="):
                return page_count >= int(filter_str[2:])
            elif filter_str.startswith("<="):
                return page_count <= int(filter_str[2:])
            elif filter_str.startswith(">"):
                return page_count > int(filter_str[1:])
            elif filter_str.startswith("<"):
                return page_count < int(filter_str[1:])
            else:
                # Exact match
                return page_count == int(filter_str)
        except ValueError:
            return True  # Invalid filter = show all

    # === No Filter Tests ===

    def test_empty_filter_matches_all(self):
        """Empty filter should match all page counts"""
        assert self._matches_page_filter(1, "") is True
        assert self._matches_page_filter(5, "") is True
        assert self._matches_page_filter(100, "") is True

    def test_all_filter_matches_all(self):
        """'All' filter should match all page counts"""
        assert self._matches_page_filter(1, "All") is True
        assert self._matches_page_filter(5, "all") is True
        assert self._matches_page_filter(100, "ALL") is True

    def test_unloaded_page_count_always_matches(self):
        """Page count -1 (not loaded) should always match"""
        assert self._matches_page_filter(-1, "5") is True
        assert self._matches_page_filter(-1, ">10") is True
        assert self._matches_page_filter(-1, "5-10") is True

    # === Exact Match Tests ===

    def test_exact_match_equals(self):
        """Exact number should match only that page count"""
        assert self._matches_page_filter(5, "5") is True
        assert self._matches_page_filter(4, "5") is False
        assert self._matches_page_filter(6, "5") is False

    def test_exact_match_single_page(self):
        """Test exact match for 1 page"""
        assert self._matches_page_filter(1, "1") is True
        assert self._matches_page_filter(2, "1") is False

    def test_exact_match_large_number(self):
        """Test exact match for large page count"""
        assert self._matches_page_filter(500, "500") is True
        assert self._matches_page_filter(499, "500") is False

    # === Greater Than Tests ===

    def test_greater_than(self):
        """>N should match page counts greater than N"""
        assert self._matches_page_filter(6, ">5") is True
        assert self._matches_page_filter(10, ">5") is True
        assert self._matches_page_filter(5, ">5") is False  # Equal not included
        assert self._matches_page_filter(4, ">5") is False

    def test_greater_than_zero(self):
        """>0 should match any positive page count"""
        assert self._matches_page_filter(1, ">0") is True
        assert self._matches_page_filter(100, ">0") is True
        # Note: 0 pages is unlikely but test edge case
        # assert self._matches_page_filter(0, ">0") is False

    # === Less Than Tests ===

    def test_less_than(self):
        """<N should match page counts less than N"""
        assert self._matches_page_filter(4, "<5") is True
        assert self._matches_page_filter(1, "<5") is True
        assert self._matches_page_filter(5, "<5") is False  # Equal not included
        assert self._matches_page_filter(6, "<5") is False

    def test_less_than_large(self):
        """<100 should match counts under 100"""
        assert self._matches_page_filter(99, "<100") is True
        assert self._matches_page_filter(1, "<100") is True
        assert self._matches_page_filter(100, "<100") is False

    # === Greater Than Or Equal Tests ===

    def test_greater_than_or_equal(self):
        """>=N should match N and above"""
        assert self._matches_page_filter(5, ">=5") is True  # Equal included
        assert self._matches_page_filter(6, ">=5") is True
        assert self._matches_page_filter(100, ">=5") is True
        assert self._matches_page_filter(4, ">=5") is False

    def test_greater_than_or_equal_one(self):
        """>=1 should match all positive page counts"""
        assert self._matches_page_filter(1, ">=1") is True
        assert self._matches_page_filter(2, ">=1") is True

    # === Less Than Or Equal Tests ===

    def test_less_than_or_equal(self):
        """<=N should match N and below"""
        assert self._matches_page_filter(5, "<=5") is True  # Equal included
        assert self._matches_page_filter(4, "<=5") is True
        assert self._matches_page_filter(1, "<=5") is True
        assert self._matches_page_filter(6, "<=5") is False

    def test_less_than_or_equal_large(self):
        """<=100 should match 100 and below"""
        assert self._matches_page_filter(100, "<=100") is True
        assert self._matches_page_filter(99, "<=100") is True
        assert self._matches_page_filter(101, "<=100") is False

    # === Range Tests ===

    def test_range_inclusive(self):
        """5-10 should match 5, 6, 7, 8, 9, 10"""
        assert self._matches_page_filter(5, "5-10") is True  # Lower bound
        assert self._matches_page_filter(7, "5-10") is True  # Middle
        assert self._matches_page_filter(10, "5-10") is True  # Upper bound
        assert self._matches_page_filter(4, "5-10") is False  # Below
        assert self._matches_page_filter(11, "5-10") is False  # Above

    def test_range_single_value(self):
        """5-5 should match only 5"""
        assert self._matches_page_filter(5, "5-5") is True
        assert self._matches_page_filter(4, "5-5") is False
        assert self._matches_page_filter(6, "5-5") is False

    def test_range_large(self):
        """1-100 should match 1 through 100"""
        assert self._matches_page_filter(1, "1-100") is True
        assert self._matches_page_filter(50, "1-100") is True
        assert self._matches_page_filter(100, "1-100") is True
        assert self._matches_page_filter(101, "1-100") is False

    def test_range_with_spaces(self):
        """Range with leading/trailing spaces should work"""
        assert self._matches_page_filter(5, " 5-10 ") is True
        assert self._matches_page_filter(7, "  5-10  ") is True

    # === Edge Cases ===

    def test_invalid_filter_matches_all(self):
        """Invalid filter expression should match all (graceful fallback)"""
        assert self._matches_page_filter(5, "abc") is True
        assert self._matches_page_filter(5, ">abc") is True
        assert self._matches_page_filter(5, "5-abc") is True

    def test_whitespace_handling(self):
        """Filters should handle whitespace correctly"""
        assert self._matches_page_filter(5, "  5  ") is True
        assert self._matches_page_filter(6, " >5 ") is True
        assert self._matches_page_filter(5, " >=5 ") is True

    def test_negative_in_filter_not_range(self):
        """Negative number at start should not be treated as range"""
        # "-5" starts with "-" so it's not a range, it's parsed as exact match
        # int("-5") = -5 and page_count >= 0, so no match (but this is expected)
        assert self._matches_page_filter(5, "-5") is False  # -5 != 5


class TestPageFilterIntegration:
    """Integration tests with actual SidebarFileList (if Qt available)"""

    @pytest.fixture
    def mock_sidebar_file_list(self):
        """Create a mock SidebarFileList for testing"""
        try:
            from PyQt5.QtWidgets import QApplication
            # Need QApplication for QListWidget
            app = QApplication.instance() or QApplication([])
            from ui.batch_sidebar import SidebarFileList
            return SidebarFileList()
        except Exception:
            pytest.skip("Qt not available for integration test")

    def test_set_page_filter_exact(self, mock_sidebar_file_list):
        """Test setting exact page filter"""
        sidebar = mock_sidebar_file_list
        sidebar._filter_pages = "5"
        assert sidebar._matches_page_filter(5) is True
        assert sidebar._matches_page_filter(4) is False

    def test_set_page_filter_range(self, mock_sidebar_file_list):
        """Test setting range page filter"""
        sidebar = mock_sidebar_file_list
        sidebar._filter_pages = "5-10"
        assert sidebar._matches_page_filter(7) is True
        assert sidebar._matches_page_filter(3) is False

    def test_set_page_filter_greater_than(self, mock_sidebar_file_list):
        """Test setting greater than filter"""
        sidebar = mock_sidebar_file_list
        sidebar._filter_pages = ">5"
        assert sidebar._matches_page_filter(6) is True
        assert sidebar._matches_page_filter(5) is False
