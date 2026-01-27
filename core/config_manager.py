"""
Config Manager - Quản lý lưu/load cấu hình zones

Hỗ trợ 2 chế độ:
1. Portable Mode: Lưu .xoaghim.json trong thư mục PDF
   - Copy folder = copy config → hoạt động trên máy khác
   - Dùng relative path cho tên file

2. App Data Mode (fallback): Lưu trong thư mục user
   - macOS: ~/Library/Application Support/XoaGhim/config.json
   - Windows: %APPDATA%/XoaGhim/config.json
   - Linux: ~/.config/XoaGhim/config.json

Ưu tiên: .xoaghim.json > app data
"""

import json
import os
import sys
import hashlib
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


def get_zones_dir() -> Path:
    """Get directory for per-file zone storage"""
    zones_dir = get_config_dir() / 'zones'
    zones_dir.mkdir(parents=True, exist_ok=True)
    return zones_dir


def _path_to_hash(path: str) -> str:
    """Convert absolute path to a short hash for filename"""
    # Use MD5 hash (truncated) for reasonable filename length
    return hashlib.md5(path.encode('utf-8')).hexdigest()[:16]


def _get_zones_file_path(source_path: str) -> Path:
    """Get JSON file path for a specific source (file or folder)

    Args:
        source_path: Absolute path to file or folder

    Returns:
        Path to zones JSON file
    """
    hash_name = _path_to_hash(source_path)
    return get_zones_dir() / f'{hash_name}.json'


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
    """Manages .xoaghim.json in PDF folder (portable mode)"""

    def __init__(self, folder_path: str):
        self._folder_path = folder_path
        self._config_path = get_portable_config_path(folder_path)
        self._data: Dict[str, Any] = {}
        self._dirty = False
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
        """Save config to .xoaghim.json"""
        if not self._dirty:
            return
        try:
            self._data['version'] = PORTABLE_CONFIG_VERSION
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            self._dirty = False
            print(f"[PortableConfig] Saved to {self._config_path}")
        except Exception as e:
            print(f"[PortableConfig] Failed to save: {e}")

    def exists(self) -> bool:
        """Check if .xoaghim.json exists"""
        return self._config_path.exists()

    def get_global_settings(self) -> Dict[str, Any]:
        """Get global zone settings (Zone Chung)"""
        return self._data.get('global_settings', {})

    def save_global_settings(self, settings: Dict[str, Any]):
        """Save global zone settings (Zone Chung)"""
        self._data['global_settings'] = settings
        self._dirty = True
        self._save()

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
        """Save per-file zones with absolute paths converted to relative"""
        # Load existing to preserve zones for files not in current batch
        existing = self._data.get('per_file_zones', {})

        # Convert absolute paths to relative
        zones_serializable = {}
        for file_path, page_zones in per_file_zones.items():
            rel_path = _to_relative_path(file_path, self._folder_path)
            zones_serializable[rel_path] = {
                str(page_idx): zone_data
                for page_idx, zone_data in page_zones.items()
            }

        # Merge: keep existing zones for files not in current update
        for rel_path, page_zones in existing.items():
            if rel_path not in zones_serializable:
                zones_serializable[rel_path] = page_zones

        self._data['per_file_zones'] = zones_serializable
        self._dirty = True
        self._save()

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
        """Save custom zones with absolute paths converted to relative"""
        existing = self._data.get('custom_zones', {})

        zones_serializable = {}
        for file_path, zones in custom_zones.items():
            rel_path = _to_relative_path(file_path, self._folder_path)
            zones_serializable[rel_path] = zones

        # Merge
        for rel_path, zones in existing.items():
            if rel_path not in zones_serializable:
                zones_serializable[rel_path] = zones

        self._data['custom_zones'] = zones_serializable
        self._dirty = True
        self._save()

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
        self._load()

    def set_current_source(self, source_path: str):
        """Set the current folder/file being worked on.

        If source is a folder with .xoaghim.json, enables portable mode.
        Call this when opening a folder or file.
        """
        self._current_source = source_path

        # Check if it's a folder and has/should have .xoaghim.json
        source = Path(source_path)
        if source.is_dir():
            self._portable_config = PortableConfigManager(source_path)
            print(f"[Config] Portable mode: {source_path}")
        elif source.is_file():
            # Single file mode - use parent folder if .xoaghim.json exists there
            parent = source.parent
            portable_path = get_portable_config_path(str(parent))
            if portable_path.exists():
                self._portable_config = PortableConfigManager(str(parent))
                print(f"[Config] Portable mode (single file): {parent}")
            else:
                self._portable_config = None
                print(f"[Config] App data mode: {source_path}")
        else:
            self._portable_config = None

    def clear_current_source(self):
        """Clear current source (when closing file/folder)"""
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
        Otherwise: loads from app data config.json
        """
        # Portable mode: prioritize .xoaghim.json
        if self._portable_config and self._portable_config.exists():
            portable_settings = self._portable_config.get_global_settings()
            if portable_settings:
                return portable_settings

        # Fallback to app data
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
        # Portable mode: save to .xoaghim.json
        if self._portable_config:
            self._portable_config.save_global_settings(zone_config)

        # Always save to app data as well (for default settings)
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

    # === Per-source zone persistence (each file/folder has its own JSON) ===

    def _load_source_zones(self, source_path: str) -> Dict[str, Any]:
        """Load zones for a specific source (file or folder)

        Args:
            source_path: Absolute path to file or folder

        Returns:
            Zone data dict or empty dict if not found
        """
        try:
            zones_file = _get_zones_file_path(source_path)
            if zones_file.exists():
                with open(zones_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Verify source path matches (hash collision protection)
                    if data.get('source_path') == source_path:
                        return data
        except Exception as e:
            print(f"[Config] Failed to load zones for {source_path}: {e}")
        return {}

    def _save_source_zones(self, source_path: str, data: Dict[str, Any]):
        """Save zones for a specific source (file or folder)

        Args:
            source_path: Absolute path to file or folder
            data: Zone data to save
        """
        try:
            zones_file = _get_zones_file_path(source_path)
            data['source_path'] = source_path  # Store source path for verification
            with open(zones_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk
        except Exception as e:
            print(f"[Config] Failed to save zones for {source_path}: {e}")

    def save_per_file_zones(self, source_path: str, per_file_zones: Dict[str, Dict[int, Dict[str, tuple]]]):
        """Save per-file zones for a source (file or folder)

        In portable mode: saves to .xoaghim.json with relative paths
        Otherwise: saves to zones/<hash>.json with absolute paths

        Args:
            source_path: Absolute path to source (file or folder)
            per_file_zones: {file_path: {page_idx: {zone_id: zone_data}}}
        """
        # Portable mode: use .xoaghim.json
        if self._portable_config:
            self._portable_config.save_per_file_zones(per_file_zones)
            return

        # Fallback: use hash-based storage
        data = self._load_source_zones(source_path)

        # Convert page indices from int to str for JSON
        zones_serializable = {}
        for file_path, page_zones in per_file_zones.items():
            zones_serializable[file_path] = {
                str(page_idx): zone_data
                for page_idx, zone_data in page_zones.items()
            }
        data['per_page_zones'] = zones_serializable
        self._save_source_zones(source_path, data)

    def get_per_file_zones(self, source_path: str) -> Dict[str, Dict[int, Dict[str, tuple]]]:
        """Load per-file zones for a source

        In portable mode: loads from .xoaghim.json with relative paths converted
        Otherwise: loads from zones/<hash>.json

        Args:
            source_path: Absolute path to source (file or folder)

        Returns:
            {file_path: {page_idx: {zone_id: zone_data}}} or empty dict
        """
        # Portable mode: use .xoaghim.json
        if self._portable_config and self._portable_config.exists():
            return self._portable_config.get_per_file_zones()

        # Fallback: use hash-based storage
        data = self._load_source_zones(source_path)

        # Convert page indices from str back to int
        raw_zones = data.get('per_page_zones', {})
        result = {}
        for file_path, page_zones in raw_zones.items():
            result[file_path] = {
                int(page_idx): zone_data
                for page_idx, zone_data in page_zones.items()
            }
        return result

    def save_per_file_custom_zones(self, source_path: str, per_file_custom_zones: Dict[str, Dict[str, Any]]):
        """Save per-file custom Zone objects for a source

        In portable mode: saves to .xoaghim.json
        Otherwise: saves to zones/<hash>.json

        Args:
            source_path: Absolute path to source (file or folder)
            per_file_custom_zones: {file_path: {zone_id: zone_dict}}
        """
        # Portable mode: use .xoaghim.json
        if self._portable_config:
            self._portable_config.save_custom_zones(per_file_custom_zones)
            return

        # Fallback: use hash-based storage
        data = self._load_source_zones(source_path)
        data['custom_zones'] = per_file_custom_zones
        self._save_source_zones(source_path, data)

    def get_per_file_custom_zones(self, source_path: str) -> Dict[str, Dict[str, Any]]:
        """Load per-file custom zones for a source

        In portable mode: loads from .xoaghim.json
        Otherwise: loads from zones/<hash>.json

        Args:
            source_path: Absolute path to source (file or folder)

        Returns:
            {file_path: {zone_id: zone_dict}} or empty dict
        """
        # Portable mode: use .xoaghim.json
        if self._portable_config and self._portable_config.exists():
            return self._portable_config.get_custom_zones()

        # Fallback: use hash-based storage
        data = self._load_source_zones(source_path)
        return data.get('custom_zones', {})

    def clear_source_zones(self, source_path: str):
        """Clear zones for a specific source

        In portable mode: clears .xoaghim.json
        Otherwise: deletes zones/<hash>.json
        """
        # Portable mode: clear .xoaghim.json
        if self._portable_config:
            self._portable_config.clear()
            return

        # Fallback: delete hash-based file
        try:
            zones_file = _get_zones_file_path(source_path)
            if zones_file.exists():
                zones_file.unlink()
        except Exception as e:
            print(f"[Config] Failed to clear zones for {source_path}: {e}")

    # Legacy compatibility - redirect to new API
    def clear_batch_zones(self):
        """Legacy: No longer used. Each source has its own zones file."""
        pass  # No-op, kept for compatibility


# Global instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get the global config manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
