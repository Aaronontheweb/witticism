#!/usr/bin/env python3
"""
Test script to verify the application structure without WhisperX dependencies
"""

import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Test imports
try:
    print("Testing imports...")
    
    # These should work without external dependencies
    from witticism.utils.config_manager import ConfigManager
    from witticism.utils.logging_config import setup_logging
    print("✓ Utils imports successful")
    
    # Test config manager
    config = ConfigManager()
    print(f"✓ Config manager initialized, config path: {config.get_config_path()}")
    
    # Test logging
    setup_logging(level="DEBUG")
    logger = logging.getLogger(__name__)
    logger.info("✓ Logging configured successfully")
    
    # These require external packages
    try:
        from witticism.ui.system_tray import SystemTrayApp
        print("✓ PyQt5 imports successful")
    except ImportError as e:
        print(f"✗ PyQt5 not available: {e}")
    
    try:
        from witticism.core.audio_capture import AudioCapture
        print("✓ Audio capture imports successful (pyaudio, webrtcvad)")
    except ImportError as e:
        print(f"✗ Audio dependencies not available: {e}")
    
    try:
        from witticism.core.hotkey_manager import HotkeyManager
        print("✓ Hotkey manager imports successful (pynput)")
    except ImportError as e:
        print(f"✗ Pynput not available: {e}")
    
    try:
        from witticism.utils.output_manager import OutputManager
        print("✓ Output manager imports successful (pynput, pyperclip)")
    except ImportError as e:
        print(f"✗ Output dependencies not available: {e}")
        
    print("\nApplication structure test complete!")
    
except Exception as e:
    print(f"Error during testing: {e}")
    import traceback
    traceback.print_exc()