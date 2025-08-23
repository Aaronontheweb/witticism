#!/usr/bin/env python3
"""
Unit tests for hotkey configuration integration - lightweight tests without heavy dependencies
"""

import unittest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add src to path for import
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestHotkeyConfigurationIntegration(unittest.TestCase):
    """Test hotkey configuration integration with minimal dependencies"""

    @patch('witticism.core.hotkey_manager.keyboard')
    def test_hotkey_manager_accepts_config_manager(self, mock_keyboard):
        """Test that HotkeyManager constructor accepts config_manager parameter"""
        # Mock keyboard keys
        mock_keyboard.Key.f9 = "mock_f9"
        mock_keyboard.Key.f12 = "mock_f12"
        
        # Import after mocking
        from witticism.core.hotkey_manager import HotkeyManager
        
        # Mock config manager
        mock_config = Mock()
        mock_config.get.return_value = "f12"
        
        # This should not raise an error with config_manager parameter
        manager = HotkeyManager(mock_config)
        
        # Should have attempted to get hotkey config
        mock_config.get.assert_called_with("hotkeys.push_to_talk", "f9")

    @patch('witticism.core.hotkey_manager.keyboard')
    def test_hotkey_manager_without_config_uses_default(self, mock_keyboard):
        """Test that HotkeyManager works without config_manager (backward compatibility)"""
        # Mock keyboard keys
        mock_keyboard.Key.f9 = "mock_f9"
        
        # Import after mocking
        from witticism.core.hotkey_manager import HotkeyManager
        
        # This should work without config_manager
        manager = HotkeyManager()
        
        # Should use default F9
        self.assertEqual(manager.ptt_key, "mock_f9")

    @patch('witticism.core.hotkey_manager.keyboard')
    def test_hotkey_manager_calls_update_method(self, mock_keyboard):
        """Test that HotkeyManager calls update_hotkey_from_string when config provided"""
        # Mock keyboard keys
        mock_keyboard.Key.f9 = "mock_f9"
        mock_keyboard.Key.f12 = "mock_f12"
        
        # Import after mocking
        from witticism.core.hotkey_manager import HotkeyManager
        
        # Mock config manager that returns F12
        mock_config = Mock()
        mock_config.get.return_value = "F12"
        
        # Mock the update method
        with patch.object(HotkeyManager, 'update_hotkey_from_string', return_value=True) as mock_update:
            manager = HotkeyManager(mock_config)
            
            # Should have called update method with F12
            mock_update.assert_called_with("F12")

    def test_update_hotkey_from_string_f12(self):
        """Test that update_hotkey_from_string correctly handles F12"""
        # Mock keyboard module completely
        mock_keyboard = Mock()
        mock_keyboard.Key.f12 = "mock_f12_key"
        
        with patch.dict('sys.modules', {'pynput.keyboard': mock_keyboard}):
            from witticism.core.hotkey_manager import HotkeyManager
            
            # Create manager without config to avoid initialization issues
            manager = HotkeyManager()
            
            # Test F12 mapping
            result = manager.update_hotkey_from_string("F12")
            
            # Should return True (successful update)
            self.assertTrue(result)
            # Should have set the key correctly
            self.assertEqual(manager.ptt_key, "mock_f12_key")


if __name__ == "__main__":
    unittest.main()