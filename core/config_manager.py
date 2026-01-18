"""
Config Manager - Quản lý lưu/load cấu hình zones

Lưu cấu hình vào file JSON trong thư mục user:
- macOS: ~/Library/Application Support/XoaGhim/config.json
- Windows: %APPDATA%/XoaGhim/config.json
- Linux: ~/.config/XoaGhim/config.json
"""

import json
import os
import sys
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


def get_batch_zones_path() -> Path:
    """Get full path to batch zones file (separate from main config)"""
    return get_config_dir() / 'batch_zones.json'


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

    # === Batch zones persistence (for crash recovery) ===

    def _get_batch_zones_path(self) -> Path:
        """Get path to batch zones file"""
        return get_batch_zones_path()

    def _load_batch_zones(self) -> Dict[str, Any]:
        """Load batch zones from file"""
        try:
            path = self._get_batch_zones_path()
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[Config] Failed to load batch zones: {e}")
        return {}

    def _save_batch_zones(self, data: Dict[str, Any]):
        """Save batch zones to file"""
        try:
            path = self._get_batch_zones_path()
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk before closing
        except Exception as e:
            print(f"[Config] Failed to save batch zones: {e}")

    def save_per_file_zones(self, batch_base_dir: str, per_file_zones: Dict[str, Dict[int, Dict[str, tuple]]]):
        """Save per-file zones for crash recovery

        Args:
            batch_base_dir: Base directory of current batch
            per_file_zones: {file_path: {page_idx: {zone_id: zone_data}}}
        """
        data = self._load_batch_zones()
        data['batch_base_dir'] = batch_base_dir

        # Convert page indices from int to str for JSON
        zones_serializable = {}
        for file_path, page_zones in per_file_zones.items():
            zones_serializable[file_path] = {
                str(page_idx): zone_data
                for page_idx, zone_data in page_zones.items()
            }
        data['per_page_zones'] = zones_serializable
        self._save_batch_zones(data)

    def get_per_file_zones(self, batch_base_dir: str) -> Dict[str, Dict[int, Dict[str, tuple]]]:
        """Load per-file zones for batch recovery

        Args:
            batch_base_dir: Base directory to match

        Returns:
            {file_path: {page_idx: {zone_id: zone_data}}} or empty dict if no match
        """
        data = self._load_batch_zones()
        if data.get('batch_base_dir') != batch_base_dir:
            return {}  # Different batch, don't restore

        # Convert page indices from str back to int
        raw_zones = data.get('per_page_zones', {})
        result = {}
        for file_path, page_zones in raw_zones.items():
            result[file_path] = {
                int(page_idx): zone_data
                for page_idx, zone_data in page_zones.items()
            }
        return result

    def save_per_file_custom_zones(self, batch_base_dir: str, per_file_custom_zones: Dict[str, Dict[str, Any]]):
        """Save per-file custom Zone objects for crash recovery

        Args:
            batch_base_dir: Base directory of current batch
            per_file_custom_zones: {file_path: {zone_id: zone_dict}}
        """
        data = self._load_batch_zones()
        data['batch_base_dir'] = batch_base_dir
        data['custom_zones'] = per_file_custom_zones
        self._save_batch_zones(data)

    def get_per_file_custom_zones(self, batch_base_dir: str) -> Dict[str, Dict[str, Any]]:
        """Load per-file custom zones for batch recovery

        Args:
            batch_base_dir: Base directory to match

        Returns:
            {file_path: {zone_id: zone_dict}} or empty dict if no match
        """
        data = self._load_batch_zones()
        if data.get('batch_base_dir') != batch_base_dir:
            return {}  # Different batch, don't restore
        return data.get('custom_zones', {})

    def clear_batch_zones(self):
        """Clear batch zones file (called when opening a different folder)"""
        try:
            path = self._get_batch_zones_path()
            if path.exists():
                path.unlink()
        except Exception as e:
            print(f"[Config] Failed to clear batch zones: {e}")


# Global instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get the global config manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
