import copy
import json
import logging
from pathlib import Path
from typing import Dict, Any
import platformdirs

logger = logging.getLogger(__name__)


class ConfigManager:
    def __init__(self, app_name: str = "witticism"):
        self.app_name = app_name

        # Get platform-specific config directory
        self.config_dir = Path(platformdirs.user_config_dir(app_name))
        self.config_file = self.config_dir / "config.json"

        # Default configuration
        self.default_config = {
            "model": {
                "size": "base",
                "language": "en",
                "device": "auto",
                "compute_type": "auto",
                "enable_diarization": False
            },
            "audio": {
                "device_index": None,
                "sample_rate": 16000,
                "channels": 1,
                "vad_aggressiveness": 2,
                "min_speech_duration": 0.5,
                "max_silence_duration": 1.0
            },
            "hotkeys": {
                "push_to_talk": "f9",
                "toggle_enable": "<ctrl>+<alt>+m"
            },
            "output": {
                "mode": "type",
                "typing_delay": 0.1
            },
            "pipeline": {
                "min_audio_length": 0.5,
                "max_audio_length": 30.0,
                "chunk_duration": 5.0,
                "overlap_duration": 0.5
            },
            "ui": {
                "show_notifications": True,
                "start_minimized": True,
                "autostart": False
            },
            "logging": {
                "level": "INFO",
                "file": None,
                "max_size": 10485760,  # 10MB
                "backup_count": 3
            }
        }

        self.config = {}
        self.load_config()

    def load_config(self) -> Dict[str, Any]:
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    user_config = json.load(f)

                # Merge with defaults
                self.config = self._deep_merge(copy.deepcopy(self.default_config), user_config)
                logger.info(f"Config loaded from {self.config_file}")

            except Exception as e:
                logger.error(f"Failed to load config: {e}")
                self.config = copy.deepcopy(self.default_config)
        else:
            self.config = copy.deepcopy(self.default_config)
            self.save_config()  # Save defaults

        return self.config

    def save_config(self) -> None:
        try:
            # Create config directory if it doesn't exist
            self.config_dir.mkdir(parents=True, exist_ok=True)

            # Save config
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)

            logger.info(f"Config saved to {self.config_file}")

        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        keys = key.split('.')
        config = self.config

        # Navigate to the parent dict
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        # Set the value
        config[keys[-1]] = value

        # Save changes
        self.save_config()

    def _deep_merge(self, base: Dict, update: Dict) -> Dict:
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                base[key] = self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def reset_to_defaults(self) -> None:
        self.config = copy.deepcopy(self.default_config)
        self.save_config()
        logger.info("Config reset to defaults")

    def export_config(self, path: Path) -> None:
        try:
            with open(path, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.info(f"Config exported to {path}")
        except Exception as e:
            logger.error(f"Failed to export config: {e}")

    def import_config(self, path: Path) -> None:
        try:
            with open(path, 'r') as f:
                imported = json.load(f)

            self.config = self._deep_merge(copy.deepcopy(self.default_config), imported)
            self.save_config()
            logger.info(f"Config imported from {path}")

        except Exception as e:
            logger.error(f"Failed to import config: {e}")

    def get_config_path(self) -> Path:
        return self.config_file
