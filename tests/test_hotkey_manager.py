#!/usr/bin/env python3
"""
Unit tests for HotkeyManager - tests configuration integration without GUI dependencies
"""

import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import Mock, patch

# Add src to path for import
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from witticism.utils.config_manager import ConfigManager


class TestHotkeyManagerConfig(unittest.TestCase):
    """Test HotkeyManager configuration integration without keyboard dependencies"""

    def setUp(self):
        """Create a temporary directory for test configs"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_config_path = Path(self.temp_dir) / "test_config.json"

    def tearDown(self):
        """Clean up temporary files"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_test_config(self, hotkey_value="f12"):
        """Helper to create a test config with specified hotkey"""
        config = ConfigManager("test_app")
        config.config_dir = Path(self.temp_dir)
        config.config_file = self.test_config_path
        config.load_config()
        config.set("hotkeys.push_to_talk", hotkey_value)
        return config

    @patch('witticism.core.hotkey_manager.keyboard')
    def test_default_hotkey_without_config(self, mock_keyboard):
        """Test that HotkeyManager defaults to F9 when no config is provided"""
        from witticism.core.hotkey_manager import HotkeyManager
        
        # Mock keyboard.Key.f9
        mock_keyboard.Key.f9 = "mock_f9_key"
        
        manager = HotkeyManager()
        self.assertEqual(manager.ptt_key, "mock_f9_key")

    @patch('witticism.core.hotkey_manager.keyboard')
    def test_configured_hotkey_f12(self, mock_keyboard):
        """Test that HotkeyManager uses F12 from config"""
        from witticism.core.hotkey_manager import HotkeyManager
        
        # Mock keyboard keys
        mock_keyboard.Key.f9 = "mock_f9_key"
        mock_keyboard.Key.f12 = "mock_f12_key"
        
        config = self.create_test_config("f12")
        manager = HotkeyManager(config)
        self.assertEqual(manager.ptt_key, "mock_f12_key")

    @patch('witticism.core.hotkey_manager.keyboard')
    def test_configured_hotkey_space(self, mock_keyboard):
        """Test that HotkeyManager uses Space from config"""
        from witticism.core.hotkey_manager import HotkeyManager
        
        # Mock keyboard keys
        mock_keyboard.Key.f9 = "mock_f9_key"
        mock_keyboard.Key.space = "mock_space_key"
        
        config = self.create_test_config("Space")
        manager = HotkeyManager(config)
        self.assertEqual(manager.ptt_key, "mock_space_key")

    @patch('witticism.core.hotkey_manager.keyboard')
    def test_invalid_hotkey_falls_back_to_f9(self, mock_keyboard):
        """Test that invalid hotkey config falls back to F9"""
        from witticism.core.hotkey_manager import HotkeyManager
        
        # Mock keyboard keys
        mock_keyboard.Key.f9 = "mock_f9_key"
        
        config = self.create_test_config("InvalidKey123")
        manager = HotkeyManager(config)
        self.assertEqual(manager.ptt_key, "mock_f9_key")

    @patch('witticism.core.hotkey_manager.keyboard')
    def test_case_insensitive_hotkey_config(self, mock_keyboard):
        """Test that hotkey config is case insensitive"""
        from witticism.core.hotkey_manager import HotkeyManager
        
        # Mock keyboard keys
        mock_keyboard.Key.f9 = "mock_f9_key"
        mock_keyboard.Key.f10 = "mock_f10_key"
        
        # Test lowercase
        config = self.create_test_config("f10")
        manager = HotkeyManager(config)
        self.assertEqual(manager.ptt_key, "mock_f10_key")
        
        # Test uppercase
        config2 = self.create_test_config("F10")
        manager2 = HotkeyManager(config2)
        self.assertEqual(manager2.ptt_key, "mock_f10_key")

    @patch('witticism.core.hotkey_manager.keyboard')
    def test_single_character_hotkey(self, mock_keyboard):
        """Test that single character hotkeys work"""
        from witticism.core.hotkey_manager import HotkeyManager
        
        # Mock keyboard methods
        mock_keyboard.Key.f9 = "mock_f9_key"
        mock_keyboard.KeyCode.from_char = Mock(return_value="mock_char_key")
        
        config = self.create_test_config("x")
        manager = HotkeyManager(config)
        
        # Should call KeyCode.from_char with lowercase
        mock_keyboard.KeyCode.from_char.assert_called_with("x")
        self.assertEqual(manager.ptt_key, "mock_char_key")

    def test_config_integration_scenario(self):
        """Test the real-world scenario: config shows F12 but should actually work"""
        # This is an integration test that verifies the fix for issue #57
        config = self.create_test_config("F12")
        
        # Verify config has correct value
        self.assertEqual(config.get("hotkeys.push_to_talk"), "F12")
        
        # This would previously fail because HotkeyManager ignored config
        # Now it should read the F12 value from config
        with patch('witticism.core.hotkey_manager.keyboard') as mock_keyboard:
            from witticism.core.hotkey_manager import HotkeyManager
            mock_keyboard.Key.f12 = "mock_f12_key"
            mock_keyboard.Key.f9 = "mock_f9_key"
            
            manager = HotkeyManager(config)
            self.assertEqual(manager.ptt_key, "mock_f12_key", 
                           "HotkeyManager should use F12 from config, not hardcoded F9")


if __name__ == "__main__":
    unittest.main()