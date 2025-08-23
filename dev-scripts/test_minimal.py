#!/usr/bin/env python3
"""
Minimal test to verify core functionality with mock components.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Test the mock WhisperX
print("Testing mock WhisperX implementation...")

from witticism.core.mock_whisperx import load_model
import numpy as np

# Create mock audio data
audio = np.random.randn(16000 * 5).astype(np.float32)  # 5 seconds at 16kHz

# Test model loading
model = load_model("base", "cpu", "int8", "en")
print(f"✓ Mock model loaded: {model.model_size}")

# Test transcription
result = model.transcribe(audio)
print(f"✓ Mock transcription: {result['segments'][0]['text']}")

# Test config manager
from witticism.utils.config_manager import ConfigManager
config = ConfigManager()
print(f"✓ Config manager working, path: {config.get_config_path()}")

# Test output manager
try:
    from witticism.utils.output_manager import OutputManager
    output = OutputManager()
    print("✓ Output manager initialized")
except ImportError as e:
    print(f"✗ Output manager needs pynput: {e}")

print("\nBasic functionality test complete!")
print("\nNote: To run the full application with real transcription:")
print("1. Use Python 3.12 or lower")
print("2. Install system dependency: sudo apt-get install portaudio19-dev")
print("3. Create venv: python3.12 -m venv venv")
print("4. Install deps: ./venv/bin/pip install -r requirements.txt")
print("5. Run: ./venv/bin/python -m witticism.main")