"""
Config Manager - Quản lý lưu/load cấu hình zones

Lưu cấu hình vào file JSON trong thư mục user:
- macOS: ~/Library/Application Support/XoaGhim/config.json
- Windows: %APPDATA%/XoaGhim/config.json
- Linux: ~/.config/XoaGhim/config.json

Zone Riêng (per-file zones) được lưu riêng cho mỗi file/folder:
- zones/<hash>.json - hash từ đường dẫn tuyệt đối
"""

import json
import os
import sys
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional


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


class ConfigManager:
    """Manages zone configuration persistence"""

    def __init__(self):
        self._config_path = get_config_path()
        self._config: Dict[str, Any] = {}
        self._load()

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
        """Get zone configuration"""
        return self._config.get('zones', {})

    def save_zone_config(self, zone_config: Dict[str, Any]):
        """Save zone configuration

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

        Args:
            source_path: Absolute path to source (file or folder)
            per_file_zones: {file_path: {page_idx: {zone_id: zone_data}}}
        """
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

        Args:
            source_path: Absolute path to source (file or folder)

        Returns:
            {file_path: {page_idx: {zone_id: zone_data}}} or empty dict
        """
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

        Args:
            source_path: Absolute path to source (file or folder)
            per_file_custom_zones: {file_path: {zone_id: zone_dict}}
        """
        data = self._load_source_zones(source_path)
        data['custom_zones'] = per_file_custom_zones
        self._save_source_zones(source_path, data)

    def get_per_file_custom_zones(self, source_path: str) -> Dict[str, Dict[str, Any]]:
        """Load per-file custom zones for a source

        Args:
            source_path: Absolute path to source (file or folder)

        Returns:
            {file_path: {zone_id: zone_dict}} or empty dict
        """
        data = self._load_source_zones(source_path)
        return data.get('custom_zones', {})

    def clear_source_zones(self, source_path: str):
        """Clear zones for a specific source"""
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
