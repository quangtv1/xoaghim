"""
Tests for Zone Drawing and Undo functionality
Tests custom zone add/delete/edit and preset zone toggle undo
"""

import pytest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtTest import QSignalSpy

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ui.undo_manager import UndoManager, UndoAction
from ui.settings_panel import SettingsPanel
from ui.zone_item import ZoneItem, ZoneSignals


# Initialize QApplication for PyQt5 tests
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


class TestUndoManager:
    """Test UndoManager class"""

    def test_undo_manager_creation(self):
        """Test UndoManager initialization"""
        manager = UndoManager()
        assert manager.count() == 0
        assert not manager.can_undo()

    def test_push_action(self):
        """Test pushing action to undo stack"""
        manager = UndoManager()
        action = UndoAction(
            action_type='add',
            zone_id='custom_1',
            page_idx=-1,
            after_data=(0.1, 0.1, 0.2, 0.2),
            zone_type='remove'
        )
        manager.push(action)
        assert manager.count() == 1
        assert manager.can_undo()

    def test_undo_returns_action(self):
        """Test undo returns the pushed action"""
        manager = UndoManager()
        action = UndoAction(
            action_type='add',
            zone_id='custom_1',
            page_idx=-1,
            after_data=(0.1, 0.1, 0.2, 0.2),
            zone_type='remove'
        )
        manager.push(action)

        result = manager.undo()
        assert result is not None
        assert result.zone_id == 'custom_1'
        assert result.action_type == 'add'
        assert manager.count() == 0

    def test_undo_empty_stack(self):
        """Test undo on empty stack returns None"""
        manager = UndoManager()
        result = manager.undo()
        assert result is None

    def test_max_undo_limit(self):
        """Test that undo stack respects max limit (79)"""
        manager = UndoManager()

        # Push 100 actions
        for i in range(100):
            action = UndoAction(
                action_type='add',
                zone_id=f'custom_{i}',
                page_idx=-1,
                after_data=(0.1, 0.1, 0.2, 0.2),
                zone_type='remove'
            )
            manager.push(action)

        # Should only have 79 actions
        assert manager.count() == 79

        # First action should be custom_21 (100 - 79 = 21)
        # Pop all and check the oldest
        last_action = None
        while manager.can_undo():
            last_action = manager.undo()

        assert last_action.zone_id == 'custom_21'

    def test_clear_stack(self):
        """Test clearing undo stack"""
        manager = UndoManager()
        for i in range(5):
            action = UndoAction(
                action_type='add',
                zone_id=f'custom_{i}',
                page_idx=-1,
                after_data=(0.1, 0.1, 0.2, 0.2),
                zone_type='remove'
            )
            manager.push(action)

        assert manager.count() == 5
        manager.clear()
        assert manager.count() == 0
        assert not manager.can_undo()

    def test_disabled_push(self):
        """Test that disabled manager doesn't record actions"""
        manager = UndoManager()
        manager.set_enabled(False)

        action = UndoAction(
            action_type='add',
            zone_id='custom_1',
            page_idx=-1,
            after_data=(0.1, 0.1, 0.2, 0.2),
            zone_type='remove'
        )
        manager.push(action)

        assert manager.count() == 0

        # Re-enable and push
        manager.set_enabled(True)
        manager.push(action)
        assert manager.count() == 1


class TestUndoAction:
    """Test UndoAction dataclass"""

    def test_add_action(self):
        """Test add action creation"""
        action = UndoAction(
            action_type='add',
            zone_id='custom_1',
            page_idx=-1,
            before_data=None,
            after_data=(0.1, 0.1, 0.2, 0.2),
            zone_type='remove'
        )
        assert action.action_type == 'add'
        assert action.before_data is None
        assert action.after_data == (0.1, 0.1, 0.2, 0.2)

    def test_delete_action(self):
        """Test delete action creation"""
        action = UndoAction(
            action_type='delete',
            zone_id='custom_1',
            page_idx=-1,
            before_data=(0.1, 0.1, 0.2, 0.2),
            after_data=None,
            zone_type='remove'
        )
        assert action.action_type == 'delete'
        assert action.before_data == (0.1, 0.1, 0.2, 0.2)
        assert action.after_data is None

    def test_edit_action(self):
        """Test edit action creation"""
        action = UndoAction(
            action_type='edit',
            zone_id='corner_tl',
            page_idx=0,
            before_data=(50, 50),
            after_data=(100, 100),
            zone_type='remove'
        )
        assert action.action_type == 'edit'
        assert action.before_data == (50, 50)
        assert action.after_data == (100, 100)


class TestZoneItem:
    """Test ZoneItem widget"""

    def test_zone_item_creation(self, qapp):
        """Test ZoneItem initialization"""
        rect = QRectF(10, 10, 100, 100)
        zone = ZoneItem('custom_1', rect, 'remove')

        assert zone.zone_id == 'custom_1'
        assert zone.zone_type == 'remove'
        assert zone.rect() == rect

    def test_zone_item_protect_type(self, qapp):
        """Test ZoneItem with protect type"""
        rect = QRectF(10, 10, 100, 100)
        zone = ZoneItem('protect_1', rect, 'protect')

        assert zone.zone_type == 'protect'

    def test_zone_item_selection(self, qapp):
        """Test ZoneItem selection state"""
        rect = QRectF(10, 10, 100, 100)
        zone = ZoneItem('custom_1', rect, 'remove')

        assert not zone._selected
        zone.set_selected(True)
        assert zone._selected

        # Check z-value changes
        assert zone.zValue() == 50  # Selected z-value

    def test_zone_item_bounds(self, qapp):
        """Test ZoneItem bounds constraint"""
        rect = QRectF(10, 10, 100, 100)
        zone = ZoneItem('custom_1', rect, 'remove')

        bounds = QRectF(0, 0, 500, 500)
        zone.set_bounds(bounds)
        assert zone._bounds == bounds

    def test_zone_item_normalized_rect(self, qapp):
        """Test normalized rect calculation"""
        rect = QRectF(100, 100, 200, 200)
        zone = ZoneItem('custom_1', rect, 'remove')

        # Normalize to 1000x1000 image
        normalized = zone.get_normalized_rect(1000, 1000)
        assert normalized == (0.1, 0.1, 0.2, 0.2)


class TestSettingsPanelZoneSignals:
    """Test SettingsPanel zone-related signals"""

    def test_zone_preset_toggled_signal_exists(self, qapp):
        """Test that zone_preset_toggled signal exists"""
        panel = SettingsPanel()
        assert hasattr(panel, 'zone_preset_toggled')
        panel.close()

    def test_toggle_preset_zone_method_exists(self, qapp):
        """Test that toggle_preset_zone method exists"""
        panel = SettingsPanel()
        assert hasattr(panel, 'toggle_preset_zone')
        assert callable(panel.toggle_preset_zone)
        panel.close()

    def test_toggle_preset_zone_corner(self, qapp):
        """Test toggling a corner zone"""
        panel = SettingsPanel()

        # Get initial state (may vary based on saved config)
        initial_state = panel._zones['corner_tl'].enabled

        # Toggle to opposite state
        panel.toggle_preset_zone('corner_tl', not initial_state)
        assert panel._zones['corner_tl'].enabled == (not initial_state)

        # Toggle back
        panel.toggle_preset_zone('corner_tl', initial_state)
        assert panel._zones['corner_tl'].enabled == initial_state

        panel.close()

    def test_toggle_preset_zone_edge(self, qapp):
        """Test toggling an edge zone"""
        panel = SettingsPanel()

        # Get initial state (may vary based on saved config)
        initial_state = panel._zones['margin_top'].enabled

        # Toggle to opposite state
        panel.toggle_preset_zone('margin_top', not initial_state)
        assert panel._zones['margin_top'].enabled == (not initial_state)

        # Toggle back
        panel.toggle_preset_zone('margin_top', initial_state)
        assert panel._zones['margin_top'].enabled == initial_state

        panel.close()

    def test_restore_custom_zone(self, qapp):
        """Test restore_custom_zone method"""
        panel = SettingsPanel()

        # Restore a custom zone
        panel.restore_custom_zone('custom_1', 0.1, 0.1, 0.2, 0.2, 'remove')

        assert 'custom_1' in panel._custom_zones
        zone = panel._custom_zones['custom_1']
        assert zone.x == 0.1
        assert zone.y == 0.1
        assert zone.width == 0.2
        assert zone.height == 0.2

        panel.close()

    def test_delete_custom_zone(self, qapp):
        """Test delete_custom_zone method"""
        panel = SettingsPanel()

        # Add a custom zone first
        panel.restore_custom_zone('custom_1', 0.1, 0.1, 0.2, 0.2, 'remove')
        assert 'custom_1' in panel._custom_zones

        # Delete it
        panel.delete_custom_zone('custom_1')
        assert 'custom_1' not in panel._custom_zones

        panel.close()


class TestZoneSignals:
    """Test ZoneSignals class"""

    def test_zone_signals_creation(self, qapp):
        """Test ZoneSignals initialization"""
        signals = ZoneSignals()
        assert hasattr(signals, 'zone_changed')
        assert hasattr(signals, 'zone_selected')
        assert hasattr(signals, 'zone_delete')
        assert hasattr(signals, 'zone_drag_started')
        assert hasattr(signals, 'zone_drag_ended')

    def test_zone_drag_signals(self, qapp):
        """Test zone_drag_started and zone_drag_ended signals"""
        rect = QRectF(10, 10, 100, 100)
        zone = ZoneItem('custom_1', rect, 'remove')

        # Create signal spy for drag_started
        spy_started = QSignalSpy(zone.signals.zone_drag_started)
        spy_ended = QSignalSpy(zone.signals.zone_drag_ended)

        # Emit signals manually to test
        zone.signals.zone_drag_started.emit('custom_1', rect)
        assert len(spy_started) == 1

        zone.signals.zone_drag_ended.emit('custom_1', rect)
        assert len(spy_ended) == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
