#!/usr/bin/env python3
"""
Unit tests to verify the hotkey configuration fix
"""

import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add src to path for import
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestHotkeyConfigurationFix(unittest.TestCase):
    """Test the fix for issue #57 - hotkey configuration binding"""

    def test_hotkey_manager_constructor_signature(self):
        """Test that HotkeyManager constructor accepts config_manager parameter"""
        # Mock the keyboard module to avoid import issues
        keyboard_mock = MagicMock()
        keyboard_mock.Key.f9 = "F9"
        
        with patch.dict('sys.modules', {'pynput.keyboard': keyboard_mock}):
            # This should import without error
            from witticism.core.hotkey_manager import HotkeyManager
            
            # Test constructor can accept config_manager parameter
            mock_config = Mock()
            mock_config.get.return_value = "f9"
            
            # This should not raise an error - the fix allows config_manager parameter
            manager = HotkeyManager(config_manager=mock_config)
            self.assertIsNotNone(manager)

    def test_hotkey_manager_backward_compatibility(self):
        """Test that HotkeyManager still works without config_manager (backward compatibility)"""
        # Mock the keyboard module
        keyboard_mock = MagicMock()
        keyboard_mock.Key.f9 = "F9"
        
        with patch.dict('sys.modules', {'pynput.keyboard': keyboard_mock}):
            from witticism.core.hotkey_manager import HotkeyManager
            
            # This should work without any parameters (backward compatibility)
            manager = HotkeyManager()
            self.assertIsNotNone(manager)

    def test_global_hotkey_manager_constructor(self):
        """Test that GlobalHotkeyManager also accepts config_manager parameter"""
        # Mock the keyboard module
        keyboard_mock = MagicMock()
        keyboard_mock.Key.f9 = "F9"
        
        with patch.dict('sys.modules', {'pynput.keyboard': keyboard_mock}):
            from witticism.core.hotkey_manager import GlobalHotkeyManager
            
            # Test constructor can accept config_manager parameter
            mock_config = Mock()
            mock_config.get.return_value = "f9"
            
            # This should not raise an error
            manager = GlobalHotkeyManager(config_manager=mock_config)
            self.assertIsNotNone(manager)

    def test_key_mapping_logic_exists(self):
        """Test that the key mapping logic exists in update_hotkey_from_string"""
        # Mock the keyboard module with key mappings
        keyboard_mock = MagicMock()
        keyboard_mock.Key.f9 = "F9"
        keyboard_mock.Key.f12 = "F12"
        
        with patch.dict('sys.modules', {'pynput.keyboard': keyboard_mock}):
            from witticism.core.hotkey_manager import HotkeyManager
            
            manager = HotkeyManager()
            
            # Test that the method exists and has basic functionality
            self.assertTrue(hasattr(manager, 'update_hotkey_from_string'))
            self.assertTrue(callable(manager.update_hotkey_from_string))


if __name__ == "__main__":
    unittest.main()