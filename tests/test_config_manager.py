#!/usr/bin/env python3
"""
Unit tests for ConfigManager - can run in CI without GPU dependencies
"""

import json
import tempfile
import unittest
from pathlib import Path
import sys

# Add src to path for import
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from witticism.utils.config_manager import ConfigManager


class TestConfigManager(unittest.TestCase):

    def setUp(self):
        """Create a temporary directory for test configs"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_config_path = Path(self.temp_dir) / "test_config.json"

    def tearDown(self):
        """Clean up temporary files"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_default_config_creation(self):
        """Test that default config is created properly"""
        config = ConfigManager("test_app")

        # Override config path to use temp directory
        config.config_dir = Path(self.temp_dir)
        config.config_file = self.test_config_path
        config.config = {}
        config.load_config()

        # Check default values
        self.assertEqual(config.get("model.size"), "base")
        self.assertEqual(config.get("model.language"), "en")
        self.assertEqual(config.get("audio.sample_rate"), 16000)
        self.assertTrue(self.test_config_path.exists())

    def test_get_nested_values(self):
        """Test getting nested configuration values"""
        config = ConfigManager("test_app")
        config.config_dir = Path(self.temp_dir)
        config.config_file = self.test_config_path
        config.load_config()

        # Test nested access
        self.assertEqual(config.get("model.size"), "base")
        self.assertEqual(config.get("audio.channels"), 1)
        self.assertEqual(config.get("ui.start_minimized"), True)

        # Test non-existent keys with default
        self.assertIsNone(config.get("non.existent.key"))
        self.assertEqual(config.get("non.existent.key", "default"), "default")

    def test_set_and_persist_values(self):
        """Test setting values and persistence"""
        config = ConfigManager("test_app")
        config.config_dir = Path(self.temp_dir)
        config.config_file = self.test_config_path
        config.load_config()

        # Set a new value
        config.set("model.size", "large-v3")
        self.assertEqual(config.get("model.size"), "large-v3")

        # Check it was saved to file
        with open(self.test_config_path, 'r') as f:
            saved_config = json.load(f)
        self.assertEqual(saved_config["model"]["size"], "large-v3")

        # Create new config instance and verify persistence
        config2 = ConfigManager("test_app")
        config2.config_dir = Path(self.temp_dir)
        config2.config_file = self.test_config_path
        config2.load_config()
        self.assertEqual(config2.get("model.size"), "large-v3")

    def test_model_persistence_scenario(self):
        """Test the specific scenario reported: model selection persistence"""
        # Initial config with base model
        config = ConfigManager("test_app")
        config.config_dir = Path(self.temp_dir)
        config.config_file = self.test_config_path
        config.load_config()

        initial_model = config.get("model.size")
        self.assertEqual(initial_model, "base")

        # User changes to large model
        config.set("model.size", "large-v3")

        # Simulate application restart - new config instance
        config_after_restart = ConfigManager("test_app")
        config_after_restart.config_dir = Path(self.temp_dir)
        config_after_restart.config_file = self.test_config_path
        config_after_restart.load_config()

        # Should remember large model selection
        self.assertEqual(config_after_restart.get("model.size"), "large-v3")

    def test_deep_merge(self):
        """Test deep merge functionality for partial config updates"""
        config = ConfigManager("test_app")
        config.config_dir = Path(self.temp_dir)
        config.config_file = self.test_config_path

        # Save partial config
        partial_config = {
            "model": {
                "size": "small"
                # Note: other model settings not specified
            }
        }

        with open(self.test_config_path, 'w') as f:
            json.dump(partial_config, f)

        # Load and merge with defaults
        config.load_config()

        # Should have user's value
        self.assertEqual(config.get("model.size"), "small")
        # Should still have defaults for unspecified values
        self.assertEqual(config.get("model.language"), "en")
        self.assertEqual(config.get("model.device"), "auto")

    def test_create_nested_keys(self):
        """Test creating new nested configuration keys"""
        config = ConfigManager("test_app")
        config.config_dir = Path(self.temp_dir)
        config.config_file = self.test_config_path
        config.load_config()

        # Set a completely new nested key
        config.set("custom.feature.enabled", True)
        self.assertEqual(config.get("custom.feature.enabled"), True)

        # Verify structure in saved file
        with open(self.test_config_path, 'r') as f:
            saved_config = json.load(f)
        self.assertTrue(saved_config["custom"]["feature"]["enabled"])

    def test_reset_to_defaults(self):
        """Test resetting configuration to defaults"""
        config = ConfigManager("test_app")
        config.config_dir = Path(self.temp_dir)
        config.config_file = self.test_config_path
        config.load_config()

        # Modify some values
        config.set("model.size", "large-v3")
        config.set("audio.sample_rate", 48000)

        # Reset to defaults
        config.reset_to_defaults()

        # Check values are back to defaults
        self.assertEqual(config.get("model.size"), "base")
        self.assertEqual(config.get("audio.sample_rate"), 16000)

        # Verify persistence of reset
        config2 = ConfigManager("test_app")
        config2.config_dir = Path(self.temp_dir)
        config2.config_file = self.test_config_path
        config2.load_config()
        self.assertEqual(config2.get("model.size"), "base")


if __name__ == "__main__":
    unittest.main()
