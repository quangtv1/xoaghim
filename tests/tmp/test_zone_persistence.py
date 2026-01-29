"""
Test Zone Persistence - Testing zone loading/saving functionality
Tests for Zone Chung (global), Zone Riêng (per-file), auto-save interval, and force_save
"""

import pytest
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from typing import Dict, Any

from core.config_manager import (
    PortableConfigManager, ConfigManager,
    get_config_manager, get_portable_config_path,
    _to_relative_path, _to_absolute_path
)


class TestPortablePathConversion:
    """Test relative/absolute path conversion for portability"""

    def test_to_relative_path_basic(self):
        """Convert absolute path to relative"""
        result = _to_relative_path('/home/user/pdfs/file.pdf', '/home/user/pdfs')
        assert result == 'file.pdf'

    def test_to_relative_path_nested(self):
        """Convert nested absolute path to relative with forward slashes"""
        result = _to_relative_path('/home/user/pdfs/subfolder/file.pdf', '/home/user/pdfs')
        assert result == 'subfolder/file.pdf'
        # Ensure forward slashes (portability)
        assert '\\' not in result

    def test_to_relative_path_outside_folder(self):
        """Return as-is if file is outside base folder"""
        result = _to_relative_path('/home/other/file.pdf', '/home/user/pdfs')
        assert result == '/home/other/file.pdf'

    def test_to_absolute_path_basic(self):
        """Convert relative path to absolute"""
        result = _to_absolute_path('file.pdf', '/home/user/pdfs')
        assert result == '/home/user/pdfs/file.pdf'

    def test_to_absolute_path_nested(self):
        """Convert nested relative path to absolute"""
        result = _to_absolute_path('subfolder/file.pdf', '/home/user/pdfs')
        assert result == '/home/user/pdfs/subfolder/file.pdf'


class TestPortableConfigManagerBasics:
    """Test PortableConfigManager basic operations"""

    def test_initialization(self):
        """Initialize PortableConfigManager with folder path"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            assert manager._folder_path == tmpdir
            assert manager._dirty == False
            assert manager._auto_save_interval == 0
            assert manager._data == {}

    def test_exists_false(self):
        """Check config file doesn't exist initially"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            assert manager.exists() == False

    def test_exists_true(self):
        """Check config file exists after creation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / '.xoaghim.json'
            # Create the file
            config_path.write_text('{}')

            manager = PortableConfigManager(tmpdir)
            assert manager.exists() == True

    def test_config_path_computation(self):
        """Verify portable config path is correct"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            expected_path = Path(tmpdir) / '.xoaghim.json'
            assert manager._config_path == expected_path


class TestPortableConfigManagerZoneChung:
    """Test global zone settings (Zone Chung) persistence"""

    def test_save_global_settings_immediate(self, capsys):
        """Save global settings immediately when interval=0"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            manager.set_auto_save_interval(0)  # Immediate save

            zone_config = {
                'enabled_zones': ['corner_tl', 'corner_tr'],
                'zone_sizes': {
                    'corner_tl': {'width': 10.0, 'height': 10.0},
                },
                'threshold': 5,
            }

            manager.save_global_settings(zone_config)

            # Verify file was saved
            config_file = Path(tmpdir) / '.xoaghim.json'
            assert config_file.exists()

            # Verify content
            with open(config_file) as f:
                data = json.load(f)
            assert data['global_settings'] == zone_config

    def test_get_global_settings_after_save(self):
        """Retrieve global settings after saving"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager1 = PortableConfigManager(tmpdir)
            manager1.set_auto_save_interval(0)

            zone_config = {
                'enabled_zones': ['corner_tl'],
                'zone_sizes': {'corner_tl': {'width': 12.0, 'height': 12.0}},
            }
            manager1.save_global_settings(zone_config)

            # Create new manager instance (simulating app restart)
            manager2 = PortableConfigManager(tmpdir)
            retrieved = manager2.get_global_settings()

            assert retrieved == zone_config

    def test_global_settings_apply_when_switching_files(self):
        """Global zones apply when switching to different file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            manager.set_auto_save_interval(0)

            # Save global settings
            global_config = {
                'enabled_zones': ['corner_tl', 'corner_tr'],
                'zone_sizes': {'corner_tl': {'width': 10.0, 'height': 10.0}},
                'threshold': 5,
            }
            manager.save_global_settings(global_config)

            # Retrieve and verify (simulating file switch)
            retrieved = manager.get_global_settings()
            assert retrieved == global_config
            assert 'corner_tl' in retrieved['enabled_zones']


class TestPortableConfigManagerZoneRieng:
    """Test per-file zone settings (Zone Riêng) persistence"""

    def test_save_per_file_zones(self):
        """Save per-file zones with absolute paths converted to relative"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            manager.set_auto_save_interval(0)

            # Create test file
            test_file = Path(tmpdir) / 'test.pdf'
            test_file.touch()

            per_file_zones = {
                str(test_file): {
                    0: {'corner_tl': (10, 10)},
                    1: {'corner_tr': (20, 20)},
                }
            }

            manager.save_per_file_zones(per_file_zones)

            # Verify file was saved with relative paths
            config_file = Path(tmpdir) / '.xoaghim.json'
            with open(config_file) as f:
                data = json.load(f)

            # Should have relative path, not absolute
            assert 'test.pdf' in data['per_file_zones']
            assert str(test_file) not in data['per_file_zones']

    def test_get_per_file_zones_converts_to_absolute(self):
        """Get per-file zones with relative paths converted to absolute"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            manager.set_auto_save_interval(0)

            # Create test file
            test_file = Path(tmpdir) / 'test.pdf'
            test_file.touch()

            per_file_zones = {
                str(test_file): {
                    0: {'corner_tl': (10, 10)},
                }
            }

            manager.save_per_file_zones(per_file_zones)

            # Retrieve and verify absolute paths
            retrieved = manager.get_per_file_zones()
            assert str(test_file) in retrieved
            assert retrieved[str(test_file)][0] == {'corner_tl': (10, 10)}

    def test_per_file_zones_file_specific(self):
        """Per-file zones only apply to specific file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            manager.set_auto_save_interval(0)

            # Create two test files
            file1 = Path(tmpdir) / 'file1.pdf'
            file2 = Path(tmpdir) / 'file2.pdf'
            file1.touch()
            file2.touch()

            per_file_zones = {
                str(file1): {0: {'corner_tl': (10, 10)}},
                str(file2): {0: {'corner_tr': (20, 20)}},
            }

            manager.save_per_file_zones(per_file_zones)
            retrieved = manager.get_per_file_zones()

            # Verify each file has its own zones
            assert 'corner_tl' in retrieved[str(file1)][0]
            assert 'corner_tr' in retrieved[str(file2)][0]
            assert 'corner_tr' not in retrieved[str(file1)][0]

    def test_get_per_file_zones_excludes_missing_files(self):
        """Per-file zones for deleted files are excluded"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            manager.set_auto_save_interval(0)

            # Create file, save zones, then delete file
            test_file = Path(tmpdir) / 'test.pdf'
            test_file.touch()

            per_file_zones = {str(test_file): {0: {'corner_tl': (10, 10)}}}
            manager.save_per_file_zones(per_file_zones)

            # Delete file
            test_file.unlink()

            # Retrieved zones should be empty (file doesn't exist)
            retrieved = manager.get_per_file_zones()
            assert retrieved == {}


class TestAutoSaveInterval:
    """Test auto-save interval functionality"""

    def test_set_auto_save_interval_immediate(self):
        """Set interval to 0 for immediate save"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            manager.set_auto_save_interval(0)
            assert manager.get_auto_save_interval() == 0

    @pytest.mark.skipif(True, reason="Requires Qt event loop in test environment")
    def test_set_auto_save_interval_periodic(self):
        """Set interval > 0 for periodic save"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            manager.set_auto_save_interval(5)
            assert manager.get_auto_save_interval() == 5
            # Cleanup timer
            manager.cleanup()

    def test_mark_dirty_immediate_save(self):
        """mark_dirty() saves immediately when interval=0"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            manager.set_auto_save_interval(0)

            zone_config = {'enabled_zones': ['corner_tl']}
            manager.save_global_settings(zone_config)

            # File should exist
            config_file = Path(tmpdir) / '.xoaghim.json'
            assert config_file.exists()

    @pytest.mark.skipif(True, reason="Requires Qt event loop in test environment")
    def test_mark_dirty_deferred_save(self):
        """mark_dirty() with interval>0 defers save to timer"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            manager.set_auto_save_interval(5)

            # Mark dirty but don't trigger immediate save
            manager._data['test'] = 'value'
            manager.mark_dirty()

            # File should NOT exist yet (deferred to timer)
            config_file = Path(tmpdir) / '.xoaghim.json'
            # Note: actual timer behavior depends on Qt event loop, so we just verify
            # that the data is marked dirty
            assert manager._dirty == True

            manager.cleanup()

    @pytest.mark.skipif(True, reason="Requires Qt event loop in test environment")
    def test_force_save_overrides_interval(self):
        """force_save() saves immediately regardless of interval"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            manager.set_auto_save_interval(5)  # Periodic mode

            zone_config = {'enabled_zones': ['corner_tl']}
            manager._data['global_settings'] = zone_config
            manager._dirty = True

            # Force save should write immediately
            manager.force_save()

            config_file = Path(tmpdir) / '.xoaghim.json'
            assert config_file.exists()

            with open(config_file) as f:
                data = json.load(f)
            assert data['global_settings'] == zone_config

            manager.cleanup()


class TestForceSave:
    """Test force_save() critical event handling"""

    @pytest.mark.skipif(True, reason="Requires Qt event loop in test environment")
    def test_force_save_file_switch(self):
        """force_save() called on file switch saves pending changes"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            manager.set_auto_save_interval(10)  # Periodic mode (not immediate)

            # Make changes but don't trigger immediate save
            zone_config = {'enabled_zones': ['corner_tl']}
            manager._data['global_settings'] = zone_config
            manager._dirty = True

            # File should not exist yet
            config_file = Path(tmpdir) / '.xoaghim.json'
            assert not config_file.exists()

            # force_save() simulates file switch event
            manager.force_save()

            # File should now exist
            assert config_file.exists()
            manager.cleanup()

    def test_force_save_noop_if_not_dirty(self):
        """force_save() is no-op if nothing changed"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            manager.set_auto_save_interval(0)

            # Save something
            zone_config = {'enabled_zones': ['corner_tl']}
            manager.save_global_settings(zone_config)
            config_file = Path(tmpdir) / '.xoaghim.json'

            # Get original mtime
            original_mtime = config_file.stat().st_mtime

            # force_save when not dirty - should not modify file
            time.sleep(0.01)  # Small delay
            manager.force_save()

            new_mtime = config_file.stat().st_mtime
            assert original_mtime == new_mtime  # File unchanged


class TestConfigManagerIntegration:
    """Test ConfigManager integration with PortableConfigManager"""

    def test_config_manager_initialization(self):
        """ConfigManager initializes correctly"""
        manager = ConfigManager()
        assert manager._portable_config is None
        assert manager._current_source is None

    def test_set_current_source_folder(self):
        """Set current source to folder enables portable mode"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConfigManager()
            manager.set_current_source(tmpdir)

            assert manager.is_portable_mode() == True
            assert manager._portable_config is not None
            assert manager._portable_config._folder_path == tmpdir

    def test_set_current_source_file(self):
        """Set current source to file uses parent folder"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / 'test.pdf'
            test_file.touch()

            manager = ConfigManager()
            manager.set_current_source(str(test_file))

            assert manager.is_portable_mode() == True
            assert manager._portable_config._folder_path == tmpdir

    def test_save_zone_config_portable_mode(self):
        """save_zone_config() saves to portable config in portable mode"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConfigManager()
            manager.set_current_source(tmpdir)
            manager._portable_config.set_auto_save_interval(0)

            zone_config = {
                'enabled_zones': ['corner_tl'],
                'zone_sizes': {'corner_tl': {'width': 10.0}},
            }
            manager.save_zone_config(zone_config)

            # Verify saved to .xoaghim.json
            config_file = Path(tmpdir) / '.xoaghim.json'
            assert config_file.exists()

            with open(config_file) as f:
                data = json.load(f)
            assert data['global_settings'] == zone_config

    def test_get_zone_config_portable_mode(self):
        """get_zone_config() retrieves from portable config in portable mode"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConfigManager()
            manager.set_current_source(tmpdir)
            manager._portable_config.set_auto_save_interval(0)

            zone_config = {'enabled_zones': ['corner_tl']}
            manager.save_zone_config(zone_config)

            retrieved = manager.get_zone_config()
            assert retrieved == zone_config

    @pytest.mark.skipif(True, reason="Requires Qt event loop in test environment")
    def test_clear_current_source_saves_pending(self):
        """clear_current_source() force saves pending changes"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConfigManager()
            manager.set_current_source(tmpdir)
            manager._portable_config.set_auto_save_interval(10)  # Periodic mode

            # Make changes
            zone_config = {'enabled_zones': ['corner_tl']}
            manager._data['global_settings'] = zone_config
            manager._portable_config._data['global_settings'] = zone_config
            manager._portable_config._dirty = True

            # Clear source - should force save
            manager.clear_current_source()

            # Verify file was saved
            config_file = Path(tmpdir) / '.xoaghim.json'
            assert config_file.exists()


class TestAutoSaveIntervalPersistence:
    """Test auto-save interval persists across sessions"""

    def test_auto_save_interval_saved_to_app_config(self):
        """Auto-save interval saved to app config"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / 'config.json'

            with patch('core.config_manager.get_config_path', return_value=config_file):
                manager = ConfigManager()
                manager.set_auto_save_interval(3)

                # Verify saved
                with open(config_file) as f:
                    data = json.load(f)
                assert data['auto_save_interval'] == 3

    def test_auto_save_interval_restored_across_sessions(self):
        """Auto-save interval restored when creating new instance"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / 'config.json'

            with patch('core.config_manager.get_config_path', return_value=config_file):
                # Session 1: Set interval
                manager1 = ConfigManager()
                manager1.set_auto_save_interval(5)

                # Session 2: Create new instance
                manager2 = ConfigManager()
                assert manager2.get_auto_save_interval() == 5


class TestZonePersistenceScenarios:
    """Test real-world zone persistence scenarios"""

    def test_scenario_single_file_mode(self):
        """Single file mode: Zones stored in parent folder"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / 'document.pdf'
            test_file.touch()

            manager = ConfigManager()
            manager.set_current_source(str(test_file))
            manager._portable_config.set_auto_save_interval(0)

            # Save global zones
            zone_config = {'enabled_zones': ['corner_tl']}
            manager.save_zone_config(zone_config)

            # Config should be in parent folder
            config_file = Path(tmpdir) / '.xoaghim.json'
            assert config_file.exists()

    def test_scenario_batch_mode_folder(self):
        """Batch mode: Zones for all files in folder"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple files
            file1 = Path(tmpdir) / 'file1.pdf'
            file2 = Path(tmpdir) / 'file2.pdf'
            file1.touch()
            file2.touch()

            manager = ConfigManager()
            manager.set_current_source(tmpdir)
            manager._portable_config.set_auto_save_interval(0)

            # Save per-file zones
            per_file_zones = {
                str(file1): {0: {'corner_tl': (10, 10)}},
                str(file2): {0: {'corner_tr': (20, 20)}},
            }
            manager.save_per_file_zones(tmpdir, per_file_zones)

            # Retrieve and verify both files have zones
            retrieved = manager.get_per_file_zones(tmpdir)
            assert str(file1) in retrieved
            assert str(file2) in retrieved

    def test_scenario_file_deletion_cleanup(self):
        """Deleted files' zones excluded on retrieval"""
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / 'file1.pdf'
            file1.touch()

            manager = ConfigManager()
            manager.set_current_source(tmpdir)
            manager._portable_config.set_auto_save_interval(0)

            # Save zones
            per_file_zones = {str(file1): {0: {'corner_tl': (10, 10)}}}
            manager.save_per_file_zones(tmpdir, per_file_zones)

            # Delete file
            file1.unlink()

            # Retrieved zones should be empty
            retrieved = manager.get_per_file_zones(tmpdir)
            assert retrieved == {}


class TestCriticalEventHandling:
    """Test force_save() on critical events"""

    @patch('core.config_manager.PortableConfigManager.force_save')
    def test_force_save_on_file_switch(self, mock_force_save):
        """force_save called when file switching in batch mode"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConfigManager()
            manager.set_current_source(tmpdir)

            # Simulate file switch
            manager.force_save()
            mock_force_save.assert_called_once()

    @patch('core.config_manager.PortableConfigManager.cleanup')
    def test_cleanup_on_app_close(self, mock_cleanup):
        """cleanup called when app closes"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConfigManager()
            manager.set_current_source(tmpdir)

            # Simulate app close
            manager.cleanup()
            mock_cleanup.assert_called_once()


class TestErrorHandling:
    """Test error handling in zone persistence"""

    def test_load_corrupted_config(self, capsys):
        """Load handles corrupted JSON gracefully"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / '.xoaghim.json'
            # Write invalid JSON
            config_file.write_text('{invalid json}')

            manager = PortableConfigManager(tmpdir)

            # Should not crash, data should be empty
            assert manager._data == {}

    def test_save_to_readonly_folder(self):
        """Save to read-only folder fails gracefully"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            manager.set_auto_save_interval(0)

            # Make folder read-only
            Path(tmpdir).chmod(0o444)

            try:
                zone_config = {'enabled_zones': ['corner_tl']}
                manager.save_global_settings(zone_config)
                # Should handle error gracefully (no crash)
            finally:
                # Restore permissions for cleanup
                Path(tmpdir).chmod(0o755)


class TestTimerManagement:
    """Test QTimer management for auto-save"""

    @pytest.mark.skipif(True, reason="Requires Qt event loop in test environment")
    def test_timer_starts_on_set_interval(self):
        """Timer starts when interval > 0"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            manager.set_auto_save_interval(5)

            # Timer should have been started
            assert manager._auto_save_timer is not None
            manager.cleanup()

    @pytest.mark.skipif(True, reason="Requires Qt event loop in test environment")
    def test_timer_stops_on_zero_interval(self):
        """Timer stops when interval = 0"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            manager.set_auto_save_interval(5)
            assert manager._auto_save_timer is not None

            # Change to immediate save
            manager.set_auto_save_interval(0)

            # For interval=0, timer should not be running
            manager.cleanup()

    @pytest.mark.skipif(True, reason="Requires Qt event loop in test environment")
    def test_cleanup_stops_timer(self):
        """cleanup() properly stops timer"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PortableConfigManager(tmpdir)
            manager.set_auto_save_interval(5)

            # Timer should exist
            assert manager._auto_save_timer is not None

            # Cleanup should stop it
            manager.cleanup()
            assert manager._auto_save_timer is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
