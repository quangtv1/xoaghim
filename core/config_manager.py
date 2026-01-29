"""
Config Manager - Quản lý lưu/load cấu hình zones

Portable Mode: Lưu .xoaghim.json trong thư mục PDF
- Copy folder = copy config → hoạt động trên máy khác
- Dùng relative path cho tên file
- ONLY source of truth for zones

App Data (config.json): UI preferences only (zoom, toolbar state, sidebar width)
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Portable config filename
PORTABLE_CONFIG_NAME = '.xoaghim.json'
PORTABLE_CONFIG_VERSION = '1.0'


def get_config_dir() -> Path:
    """Get platform-specific config directory"""
    if sys.platform == 'darwin':
        # macOS
        config_dir = Path.home() / 'Library' / 'Application Support' / 'XoaGhim'
    elif sys.platform == 'win32':
        # Windows
        appdata = os.environ.get('APPDATA', str(Path.home()))
        config_dir = Path(appdata) / 'XoaGhim'
    else:
        # Linux/Unix
        config_dir = Path.home() / '.config' / 'XoaGhim'

    # Create directory if not exists
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_path() -> Path:
    """Get full path to config file"""
    return get_config_dir() / 'config.json'


def get_portable_config_path(folder_path: str) -> Path:
    """Get .xoaghim.json path for a folder"""
    return Path(folder_path) / PORTABLE_CONFIG_NAME


def _to_relative_path(file_path: str, base_folder: str) -> str:
    """Convert absolute path to relative path (using / separator for portability)"""
    try:
        rel = Path(file_path).relative_to(base_folder)
        return str(rel).replace('\\', '/')
    except ValueError:
        # file_path is not under base_folder, return as-is
        return file_path


def _to_absolute_path(relative_path: str, base_folder: str) -> str:
    """Convert relative path to absolute path"""
    return str(Path(base_folder) / relative_path)


class PortableConfigManager:
    """Manages .xoaghim.json in PDF folder (portable mode)

    Supports deferred saving with configurable auto-save interval:
    - interval = 0: save immediately on every change (legacy behavior)
    - interval > 0: save periodically, plus force save on critical events
    """

    def __init__(self, folder_path: str):
        self._folder_path = folder_path
        self._config_path = get_portable_config_path(folder_path)
        self._data: Dict[str, Any] = {}
        self._dirty = False
        self._auto_save_interval = 0  # Minutes, 0 = immediate save
        self._auto_save_timer = None  # QTimer instance (lazy init)
        self._load()

    def _load(self):
        """Load config from .xoaghim.json"""
        try:
            if self._config_path.exists():
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
                print(f"[PortableConfig] Loaded from {self._config_path}")
        except Exception as e:
            print(f"[PortableConfig] Failed to load: {e}")
            self._data = {}

    def _save(self):
        """Save config to .xoaghim.json (internal - use force_save for external calls)"""
        if not self._dirty:
            return
        try:
            self._data['version'] = PORTABLE_CONFIG_VERSION
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
                f.flush()
                # Removed os.fsync() - let OS handle disk buffering for better performance
            self._dirty = False
            print(f"[PortableConfig] Saved to {self._config_path}")
        except Exception as e:
            print(f"[PortableConfig] Failed to save: {e}")

    def set_auto_save_interval(self, minutes: int):
        """Set auto-save interval in minutes.

        Args:
            minutes: 0 = immediate save, >0 = periodic save every N minutes
        """
        self._auto_save_interval = max(0, minutes)

        # Stop existing timer
        if self._auto_save_timer:
            self._auto_save_timer.stop()

        # Start new timer if interval > 0
        if self._auto_save_interval > 0:
            try:
                from PyQt5.QtCore import QTimer
            except ImportError:
                from PySide6.QtCore import QTimer
            if not self._auto_save_timer:
                self._auto_save_timer = QTimer()
                self._auto_save_timer.timeout.connect(self._periodic_save)
            self._auto_save_timer.start(self._auto_save_interval * 60 * 1000)
            print(f"[PortableConfig] Auto-save timer set to {minutes} minute(s)")

    def _periodic_save(self):
        """Called by timer - save if dirty"""
        if self._dirty:
            print("[PortableConfig] Periodic auto-save triggered")
            self._save()

    def mark_dirty(self):
        """Mark data as changed. Saves immediately if interval=0, else waits for timer."""
        self._dirty = True
        if self._auto_save_interval == 0:
            self._save()  # Immediate save (legacy behavior)

    def force_save(self):
        """Force save immediately - use for critical events (file switch, app close)"""
        if self._dirty:
            print("[PortableConfig] Force save triggered")
            self._save()

    def get_auto_save_interval(self) -> int:
        """Get current auto-save interval in minutes"""
        return self._auto_save_interval

    def cleanup(self):
        """Stop timer and cleanup resources"""
        if self._auto_save_timer:
            self._auto_save_timer.stop()
            self._auto_save_timer = None

    def exists(self) -> bool:
        """Check if .xoaghim.json exists"""
        return self._config_path.exists()

    def get_global_settings(self) -> Dict[str, Any]:
        """Get global zone settings (Zone Chung)"""
        return self._data.get('global_settings', {})

    def save_global_settings(self, settings: Dict[str, Any]):
        """Save global zone settings (Zone Chung) - only marks dirty if data changed"""
        old_settings = self._data.get('global_settings', {})
        if settings != old_settings:
            self._data['global_settings'] = settings
            self.mark_dirty()

    def get_per_file_zones(self) -> Dict[str, Dict[int, Dict[str, Any]]]:
        """Get per-file zones with relative paths converted to absolute"""
        raw_zones = self._data.get('per_file_zones', {})
        result = {}
        for rel_path, page_zones in raw_zones.items():
            abs_path = _to_absolute_path(rel_path, self._folder_path)
            # Only include if file exists
            if Path(abs_path).exists():
                result[abs_path] = {
                    int(page_idx): zone_data
                    for page_idx, zone_data in page_zones.items()
                }
        return result

    def save_per_file_zones(self, per_file_zones: Dict[str, Dict[int, Dict[str, Any]]]):
        """Save per-file zones - only marks dirty if data changed"""
        zones_serializable = {}
        for file_path, page_zones in per_file_zones.items():
            rel_path = _to_relative_path(file_path, self._folder_path)
            zones_serializable[rel_path] = {
                str(page_idx): zone_data
                for page_idx, zone_data in page_zones.items()
            }
        old_zones = self._data.get('per_file_zones', {})
        if zones_serializable != old_zones:
            self._data['per_file_zones'] = zones_serializable
            self.mark_dirty()

    def get_custom_zones(self) -> Dict[str, Dict[str, Any]]:
        """Get custom zones with relative paths converted to absolute"""
        raw_zones = self._data.get('custom_zones', {})
        result = {}
        for rel_path, zones in raw_zones.items():
            abs_path = _to_absolute_path(rel_path, self._folder_path)
            if Path(abs_path).exists():
                result[abs_path] = zones
        return result

    def save_custom_zones(self, custom_zones: Dict[str, Dict[str, Any]]):
        """Save custom zones - only marks dirty if data changed"""
        zones_serializable = {}
        for file_path, zones in custom_zones.items():
            rel_path = _to_relative_path(file_path, self._folder_path)
            zones_serializable[rel_path] = zones
        old_zones = self._data.get('custom_zones', {})
        if zones_serializable != old_zones:
            self._data['custom_zones'] = zones_serializable
            self.mark_dirty()

    def clear(self):
        """Clear all data and delete file"""
        self._data = {}
        self._dirty = False
        try:
            if self._config_path.exists():
                self._config_path.unlink()
        except Exception as e:
            print(f"[PortableConfig] Failed to delete: {e}")


class ConfigManager:
    """Manages zone configuration persistence

    Supports portable mode: when a folder has .xoaghim.json,
    zone configs are stored there (with relative paths) instead of app data.
    """

    def __init__(self):
        self._config_path = get_config_path()
        self._config: Dict[str, Any] = {}
        self._current_source: Optional[str] = None  # Current folder/file being worked on
        self._portable_config: Optional[PortableConfigManager] = None
        self._warned_hash_files = False
        self._load()
        self._check_obsolete_hash_files()

    def _check_obsolete_hash_files(self):
        """One-time check for obsolete hash-based zone files."""
        if self._warned_hash_files:
            return
        zones_dir = get_config_dir() / 'zones'
        if zones_dir.exists():
            hash_files = list(zones_dir.glob('*.json'))
            if hash_files:
                print(f"[Config] Found {len(hash_files)} obsolete hash files in {zones_dir}")
                print("[Config] These are no longer used - zones now stored in .xoaghim.json per folder")
                print("[Config] You can safely delete the 'zones' folder to clean up")
                self._warned_hash_files = True

    def set_current_source(self, source_path: str):
        """Set the current folder/file being worked on.

        Always enables portable mode - saves to .xoaghim.json in:
        - Folder itself (if source is folder)
        - Parent folder (if source is file)
        """
        # Cleanup previous portable config
        if self._portable_config:
            self._portable_config.force_save()  # Save pending changes
            self._portable_config.cleanup()

        self._current_source = source_path

        # Always enable portable mode
        source = Path(source_path)
        if source.is_dir():
            # Folder mode: save .xoaghim.json in the folder
            self._portable_config = PortableConfigManager(source_path)
            print(f"[Config] Portable mode (folder): {source_path}")
        elif source.is_file():
            # Single file mode: save .xoaghim.json in parent folder
            parent = str(source.parent)
            self._portable_config = PortableConfigManager(parent)
            print(f"[Config] Portable mode (single file): {parent}")
        else:
            self._portable_config = None
            print(f"[Config] No portable mode: {source_path}")

        # Apply auto-save interval to new portable config
        if self._portable_config:
            interval = self.get_auto_save_interval()
            if interval > 0:
                self._portable_config.set_auto_save_interval(interval)

    def clear_current_source(self):
        """Clear current source (when closing file/folder)"""
        if self._portable_config:
            self._portable_config.force_save()  # Save pending changes
            self._portable_config.cleanup()
        self._current_source = None
        self._portable_config = None

    def is_portable_mode(self) -> bool:
        """Check if currently in portable mode"""
        return self._portable_config is not None

    def create_portable_config(self, folder_path: str):
        """Create .xoaghim.json for a folder to enable portable mode"""
        self._portable_config = PortableConfigManager(folder_path)
        # Initialize with current global settings
        self._portable_config.save_global_settings(self.get_zone_config())
        self._current_source = folder_path
        print(f"[Config] Created portable config: {folder_path}")

    def _load(self):
        """Load config from file"""
        try:
            if self._config_path.exists():
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
        except Exception as e:
            print(f"[Config] Failed to load config: {e}")
            self._config = {}

    def _save(self):
        """Save config to file"""
        try:
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Config] Failed to save config: {e}")

    def get_zone_config(self) -> Dict[str, Any]:
        """Get zone configuration

        In portable mode: loads from .xoaghim.json (global_settings)
        If no .xoaghim.json exists: return empty config (all zones disabled)
        """
        # Portable mode: load from .xoaghim.json ONLY
        if self._portable_config:
            if self._portable_config.exists():
                portable_settings = self._portable_config.get_global_settings()
                if portable_settings:
                    return portable_settings
            # No .xoaghim.json or empty → return default (all zones disabled)
            return {
                'enabled_zones': [],
                'zone_sizes': {},
                'custom_zones': {},
                'threshold': 5,
                'filter_mode': 'all',
                'text_protection': True,
                'batch_render': True,
            }

        # Non-portable mode: load from app data
        return self._config.get('zones', {})

    def save_zone_config(self, zone_config: Dict[str, Any]):
        """Save zone configuration

        In portable mode: saves to .xoaghim.json (global_settings)
        Otherwise: saves to app data config.json

        zone_config format:
        {
            'enabled_zones': ['corner_tl', 'corner_tr'],  # List of enabled zone IDs
            'zone_sizes': {
                'corner_tl': {'width': 12.0, 'height': 12.0},
                'margin_left': {'width': 5.0, 'height': 100.0},
                ...
            },
            'threshold': 5,
            'filter_mode': 'all',  # 'all', 'odd', 'even', 'none'
            'text_protection': True,
        }
        """
        print(f"[Config] save_zone_config called, portable_config={self._portable_config is not None}")
        # Portable mode: save to .xoaghim.json ONLY (no sync to app data)
        if self._portable_config:
            print(f"[Config] Saving to portable config: {self._portable_config._config_path}")
            self._portable_config.save_global_settings(zone_config)
            return  # Don't sync to app data - each folder has its own config

        # Non-portable mode: save to app data
        self._config['zones'] = zone_config
        self._save()

    def get_ui_config(self) -> Dict[str, Any]:
        """Get UI state configuration (toolbar collapsed, etc.)"""
        return self._config.get('ui', {})

    def save_ui_config(self, ui_config: Dict[str, Any]):
        """Save UI state configuration

        ui_config format:
        {
            'toolbar_collapsed': True/False,  # Settings toolbar collapsed state
        }
        """
        self._config['ui'] = ui_config
        self._save()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value"""
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        """Set a config value and save"""
        self._config[key] = value
        self._save()

    # === Per-source zone persistence (portable mode only - .xoaghim.json) ===

    def save_per_file_zones(self, source_path: str, per_file_zones: Dict[str, Dict[int, Dict[str, tuple]]]):
        """Save per-file zones to .xoaghim.json (portable mode only)

        Args:
            source_path: Absolute path to source (file or folder)
            per_file_zones: {file_path: {page_idx: {zone_id: zone_data}}}
        """
        if self._portable_config:
            self._portable_config.save_per_file_zones(per_file_zones)

    def get_per_file_zones(self, source_path: str) -> Dict[str, Dict[int, Dict[str, tuple]]]:
        """Load per-file zones from .xoaghim.json (portable mode only)

        Args:
            source_path: Absolute path to source (file or folder)

        Returns:
            {file_path: {page_idx: {zone_id: zone_data}}} or empty dict
        """
        if self._portable_config:
            return self._portable_config.get_per_file_zones()
        return {}

    def save_per_file_custom_zones(self, source_path: str, per_file_custom_zones: Dict[str, Dict[str, Any]]):
        """Save per-file custom zones to .xoaghim.json (portable mode only)

        Args:
            source_path: Absolute path to source (file or folder)
            per_file_custom_zones: {file_path: {zone_id: zone_dict}}
        """
        if self._portable_config:
            self._portable_config.save_custom_zones(per_file_custom_zones)

    def get_per_file_custom_zones(self, source_path: str) -> Dict[str, Dict[str, Any]]:
        """Load per-file custom zones from .xoaghim.json (portable mode only)

        Args:
            source_path: Absolute path to source (file or folder)

        Returns:
            {file_path: {zone_id: zone_dict}} or empty dict
        """
        if self._portable_config:
            return self._portable_config.get_custom_zones()
        return {}

    def clear_source_zones(self, source_path: str):
        """Clear zones for current source (clears .xoaghim.json)"""
        if self._portable_config:
            self._portable_config.clear()

    # Legacy compatibility - redirect to new API
    def clear_batch_zones(self):
        """Legacy: No longer used. Each source has its own zones file."""
        pass  # No-op, kept for compatibility

    # === Auto-save interval management ===

    def set_auto_save_interval(self, minutes: int):
        """Set auto-save interval for portable config.

        Args:
            minutes: 0 = immediate save, >0 = periodic save every N minutes
        """
        # Save to app config for persistence across sessions
        self._config['auto_save_interval'] = minutes
        self._save()

        # Apply to current portable config if active
        if self._portable_config:
            self._portable_config.set_auto_save_interval(minutes)

    def get_auto_save_interval(self) -> int:
        """Get auto-save interval setting (in minutes)"""
        return self._config.get('auto_save_interval', 0)

    def force_save(self):
        """Force save all pending changes immediately.

        Call this on critical events: file switch, app close, etc.
        """
        if self._portable_config:
            self._portable_config.force_save()

    def cleanup(self):
        """Cleanup resources (stop timers, etc.)"""
        if self._portable_config:
            self._portable_config.cleanup()


# Global instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get the global config manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
