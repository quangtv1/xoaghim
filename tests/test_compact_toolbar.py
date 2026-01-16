"""
Tests for Compact Settings Toolbar - Icon-only toolbar for collapsed settings panel
Tests zone toggles, filter changes, draw modes, and sync functionality
"""

import pytest
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QSignalSpy

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.compact_toolbar_icons import CompactIconButton, CompactIconSeparator
from ui.compact_settings_toolbar import CompactSettingsToolbar


# Initialize QApplication for PyQt5 tests
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture
def compact_toolbar(qapp):
    """Create a fresh CompactSettingsToolbar instance for each test"""
    toolbar = CompactSettingsToolbar()
    toolbar.show()
    yield toolbar
    toolbar.close()


class TestCompactIconButton:
    """Test CompactIconButton widget"""
    
    def test_icon_button_creation(self, qapp):
        """Test that icon button can be created with different types"""
        btn = CompactIconButton('corner_tl', 'Top Left Corner')
        assert btn.icon_type == 'corner_tl'
        assert btn.toolTip() == 'Top Left Corner'
        assert btn.width() == 38
        assert btn.height() == 38
        btn.close()
    
    def test_icon_button_checkable(self, qapp):
        """Test that icon button can be made checkable"""
        btn = CompactIconButton('draw_remove', 'Remove Zone')
        btn.setCheckable(True)
        assert btn._checkable is True
        
        btn.setChecked(True)
        assert btn.isChecked() is True
        btn.close()
    
    def test_icon_button_selected_state(self, qapp):
        """Test selected state for non-checkable buttons"""
        btn = CompactIconButton('clear', 'Clear Zones')
        btn.setSelected(True)
        assert btn.isSelected() is True
        
        btn.setSelected(False)
        assert btn.isSelected() is False
        btn.close()
    
    def test_corner_icons_created(self, qapp):
        """Test that corner icons are created properly"""
        corners = [
            ('corner_tl', 'Top Left'),
            ('corner_tr', 'Top Right'),
            ('corner_bl', 'Bottom Left'),
            ('corner_br', 'Bottom Right'),
        ]
        
        for icon_type, desc in corners:
            btn = CompactIconButton(icon_type, desc)
            assert btn.icon_type == icon_type
            btn.close()
    
    def test_edge_icons_created(self, qapp):
        """Test that edge icons are created properly"""
        edges = [
            ('margin_top', 'Top Edge'),
            ('margin_bottom', 'Bottom Edge'),
            ('margin_left', 'Left Edge'),
            ('margin_right', 'Right Edge'),
        ]
        
        for icon_type, desc in edges:
            btn = CompactIconButton(icon_type, desc)
            assert btn.icon_type == icon_type
            btn.close()
    
    def test_draw_mode_icons_created(self, qapp):
        """Test that draw mode icons are created properly"""
        modes = [
            ('draw_remove', 'Remove'),
            ('draw_protect', 'Protect'),
        ]
        
        for icon_type, desc in modes:
            btn = CompactIconButton(icon_type, desc)
            assert btn.icon_type == icon_type
            btn.close()
    
    def test_filter_icons_created(self, qapp):
        """Test that filter icons are created properly"""
        filters = [
            ('filter_all', 'All Pages'),
            ('filter_odd', 'Odd Pages'),
            ('filter_even', 'Even Pages'),
            ('filter_free', 'Current Page'),
        ]
        
        for icon_type, desc in filters:
            btn = CompactIconButton(icon_type, desc)
            assert btn.icon_type == icon_type
            btn.close()
    
    def test_action_icons_created(self, qapp):
        """Test that action icons are created properly"""
        actions = [
            ('clear', 'Clear'),
            ('ai_detect', 'AI Detect'),
            ('collapse', 'Collapse'),
            ('expand', 'Expand'),
        ]
        
        for icon_type, desc in actions:
            btn = CompactIconButton(icon_type, desc)
            assert btn.icon_type == icon_type
            btn.close()


class TestCompactIconSeparator:
    """Test CompactIconSeparator widget"""
    
    def test_separator_creation(self, qapp):
        """Test that separator can be created"""
        sep = CompactIconSeparator()
        assert sep.width() == 8
        assert sep.height() == 38
        sep.close()
    
    def test_separator_disabled(self, qapp):
        """Test that separator is disabled"""
        sep = CompactIconSeparator()
        assert sep.isEnabled() is False
        sep.close()


class TestCompactSettingsToolbar:
    """Test CompactSettingsToolbar widget"""
    
    def test_toolbar_creation(self, compact_toolbar):
        """Test that toolbar creates all required buttons"""
        # Verify toolbar was created
        assert compact_toolbar is not None
        assert compact_toolbar.height() == 42
    
    def test_zone_buttons_created(self, compact_toolbar):
        """Test that all 8 zone buttons are created"""
        zone_ids = [
            'corner_tl', 'corner_tr', 'corner_bl', 'corner_br',
            'margin_top', 'margin_bottom', 'margin_left', 'margin_right'
        ]
        
        for zone_id in zone_ids:
            assert zone_id in compact_toolbar._zone_buttons
            btn = compact_toolbar._zone_buttons[zone_id]
            assert btn.isCheckable() is True
    
    def test_filter_buttons_created(self, compact_toolbar):
        """Test that all 4 filter buttons are created"""
        filter_modes = ['all', 'odd', 'even', 'none']
        
        for mode in filter_modes:
            assert mode in compact_toolbar._filter_buttons
            btn = compact_toolbar._filter_buttons[mode]
            assert btn.isCheckable() is True
    
    def test_draw_mode_buttons_created(self, compact_toolbar):
        """Test that draw mode buttons are created"""
        assert 'draw_remove' in compact_toolbar._draw_buttons
        assert 'draw_protect' in compact_toolbar._draw_buttons
    
    def test_clear_button_exists(self, compact_toolbar):
        """Test that clear button exists"""
        assert hasattr(compact_toolbar, 'clear_btn')
        assert compact_toolbar.clear_btn is not None
    
    def test_ai_detect_button_exists(self, compact_toolbar):
        """Test that AI detect button exists"""
        assert hasattr(compact_toolbar, 'ai_detect_btn')
        assert compact_toolbar.ai_detect_btn is not None
    
    def test_default_filter_is_all(self, compact_toolbar):
        """Test that 'all' filter is checked by default"""
        assert compact_toolbar._filter_buttons['all'].isChecked() is True
        assert compact_toolbar._filter_buttons['odd'].isChecked() is False
        assert compact_toolbar._filter_buttons['even'].isChecked() is False
        assert compact_toolbar._filter_buttons['none'].isChecked() is False
    
    def test_zone_toggle_signal(self, compact_toolbar):
        """Test that zone_toggled signal is emitted when zone is clicked"""
        spy = QSignalSpy(compact_toolbar.zone_toggled)
        
        # Toggle corner_tl button
        compact_toolbar._zone_buttons['corner_tl'].click()
        
        # Signal should be emitted
        assert len(spy) > 0
        compact_toolbar._zone_buttons['corner_tl'].click()  # Reset
    
    def test_set_zone_state(self, compact_toolbar):
        """Test set_zone_state method"""
        # Initially unchecked
        assert compact_toolbar._zone_buttons['corner_tr'].isChecked() is False
        
        # Set to checked
        compact_toolbar.set_zone_state('corner_tr', True)
        assert compact_toolbar._zone_buttons['corner_tr'].isChecked() is True
        
        # Set to unchecked
        compact_toolbar.set_zone_state('corner_tr', False)
        assert compact_toolbar._zone_buttons['corner_tr'].isChecked() is False
    
    def test_set_filter_state(self, compact_toolbar):
        """Test set_filter_state method"""
        # Default is 'all'
        assert compact_toolbar._filter_buttons['all'].isChecked() is True
        
        # Change to 'odd'
        compact_toolbar.set_filter_state('odd')
        assert compact_toolbar._filter_buttons['odd'].isChecked() is True
        assert compact_toolbar._filter_buttons['all'].isChecked() is False
        
        # Change to 'even'
        compact_toolbar.set_filter_state('even')
        assert compact_toolbar._filter_buttons['even'].isChecked() is True
        assert compact_toolbar._filter_buttons['odd'].isChecked() is False
    
    def test_set_draw_mode_state(self, compact_toolbar):
        """Test set_draw_mode_state method"""
        # Initially no draw mode selected
        assert compact_toolbar._draw_buttons['draw_remove'].isChecked() is False
        assert compact_toolbar._draw_buttons['draw_protect'].isChecked() is False
        
        # Set to 'remove'
        compact_toolbar.set_draw_mode_state('remove')
        assert compact_toolbar._draw_buttons['draw_remove'].isChecked() is True
        assert compact_toolbar._draw_buttons['draw_protect'].isChecked() is False
        
        # Set to 'protect'
        compact_toolbar.set_draw_mode_state('protect')
        assert compact_toolbar._draw_buttons['draw_remove'].isChecked() is False
        assert compact_toolbar._draw_buttons['draw_protect'].isChecked() is True
        
        # Set to None
        compact_toolbar.set_draw_mode_state(None)
        assert compact_toolbar._draw_buttons['draw_remove'].isChecked() is False
        assert compact_toolbar._draw_buttons['draw_protect'].isChecked() is False
    
    def test_set_ai_detect_state(self, compact_toolbar):
        """Test set_ai_detect_state method"""
        # Initially unchecked
        assert compact_toolbar.ai_detect_btn.isChecked() is False
        
        # Set to checked
        compact_toolbar.set_ai_detect_state(True)
        assert compact_toolbar.ai_detect_btn.isChecked() is True
        
        # Set to unchecked
        compact_toolbar.set_ai_detect_state(False)
        assert compact_toolbar.ai_detect_btn.isChecked() is False
    
    def test_sync_from_settings(self, compact_toolbar):
        """Test sync_from_settings method"""
        enabled_zones = ['corner_tl', 'corner_br', 'margin_top']
        filter_mode = 'odd'
        draw_mode = 'protect'
        ai_detect = True
        
        compact_toolbar.sync_from_settings(enabled_zones, filter_mode, draw_mode, ai_detect)
        
        # Verify zone states
        assert compact_toolbar._zone_buttons['corner_tl'].isChecked() is True
        assert compact_toolbar._zone_buttons['corner_br'].isChecked() is True
        assert compact_toolbar._zone_buttons['margin_top'].isChecked() is True
        assert compact_toolbar._zone_buttons['corner_tr'].isChecked() is False
        
        # Verify filter state
        assert compact_toolbar._filter_buttons['odd'].isChecked() is True
        assert compact_toolbar._filter_buttons['all'].isChecked() is False
        
        # Verify draw mode state
        assert compact_toolbar._draw_buttons['draw_protect'].isChecked() is True
        assert compact_toolbar._draw_buttons['draw_remove'].isChecked() is False
        
        # Verify AI detect state
        assert compact_toolbar.ai_detect_btn.isChecked() is True
    
    def test_filter_exclusive_selection(self, compact_toolbar):
        """Test that filter buttons are mutually exclusive"""
        # Click odd
        compact_toolbar._filter_buttons['odd'].click()
        assert compact_toolbar._filter_buttons['odd'].isChecked() is True
        assert compact_toolbar._filter_buttons['all'].isChecked() is False
        
        # Click even
        compact_toolbar._filter_buttons['even'].click()
        assert compact_toolbar._filter_buttons['even'].isChecked() is True
        assert compact_toolbar._filter_buttons['odd'].isChecked() is False
        
        # Click all
        compact_toolbar._filter_buttons['all'].click()
        assert compact_toolbar._filter_buttons['all'].isChecked() is True
        assert compact_toolbar._filter_buttons['even'].isChecked() is False
    
    def test_draw_mode_exclusive_selection(self, compact_toolbar):
        """Test that only one draw mode can be active at a time"""
        # Click remove
        compact_toolbar._draw_buttons['draw_remove'].click()
        assert compact_toolbar._draw_buttons['draw_remove'].isChecked() is True
        assert compact_toolbar._draw_buttons['draw_protect'].isChecked() is False
        
        # Click protect - should uncheck remove
        compact_toolbar._draw_buttons['draw_protect'].click()
        assert compact_toolbar._draw_buttons['draw_protect'].isChecked() is True
        assert compact_toolbar._draw_buttons['draw_remove'].isChecked() is False
    
    def test_clear_button_signal(self, compact_toolbar):
        """Test that clear_zones signal is emitted"""
        spy = QSignalSpy(compact_toolbar.clear_zones)
        
        # Click clear button
        compact_toolbar.clear_btn.click()
        
        # Signal should be emitted
        assert len(spy) > 0
    
    def test_ai_detect_button_signal(self, compact_toolbar):
        """Test that ai_detect_toggled signal is emitted"""
        spy = QSignalSpy(compact_toolbar.ai_detect_toggled)
        
        # Click AI detect button
        compact_toolbar.ai_detect_btn.click()
        
        # Signal should be emitted
        assert len(spy) > 0
    
    def test_multiple_zone_selection(self, compact_toolbar):
        """Test that multiple zones can be selected independently"""
        # Select multiple zones
        compact_toolbar.set_zone_state('corner_tl', True)
        compact_toolbar.set_zone_state('corner_br', True)
        compact_toolbar.set_zone_state('margin_top', True)
        
        # Verify all are selected
        assert compact_toolbar._zone_buttons['corner_tl'].isChecked() is True
        assert compact_toolbar._zone_buttons['corner_br'].isChecked() is True
        assert compact_toolbar._zone_buttons['margin_top'].isChecked() is True
        
        # Unselect one
        compact_toolbar.set_zone_state('corner_br', False)
        
        # Verify state
        assert compact_toolbar._zone_buttons['corner_tl'].isChecked() is True
        assert compact_toolbar._zone_buttons['corner_br'].isChecked() is False
        assert compact_toolbar._zone_buttons['margin_top'].isChecked() is True


class TestCompactToolbarIconRendering:
    """Test that icons render without errors"""
    
    def test_corner_icon_rendering(self, qapp):
        """Test that corner icons render"""
        btn = CompactIconButton('corner_tl', 'Test')
        btn.show()
        # Force a repaint
        btn.update()
        btn.close()
    
    def test_draw_mode_icon_rendering(self, qapp):
        """Test that draw mode icons render"""
        icons = ['draw_remove', 'draw_protect']
        for icon_type in icons:
            btn = CompactIconButton(icon_type, 'Test')
            btn.show()
            btn.update()
            btn.close()
    
    def test_filter_icon_rendering(self, qapp):
        """Test that filter icons render"""
        icons = ['filter_all', 'filter_odd', 'filter_even', 'filter_free']
        for icon_type in icons:
            btn = CompactIconButton(icon_type, 'Test')
            btn.show()
            btn.update()
            btn.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
