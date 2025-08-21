#!/usr/bin/env python3
"""
Test script to demonstrate the new progress indicator and timeout functionality.
This is a simple test to verify the model loading progress tracking works.
"""

import sys
import time
from pathlib import Path

# Add src to path so we can import our modules
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from witticism.core.whisperx_engine import WhisperXEngine


def progress_callback(status: str, progress: int):
    """Progress callback that prints updates."""
    print(f"Progress: {progress:3d}% - {status}")


def test_progress_loading():
    """Test model loading with progress indicators."""
    print("Testing model loading with progress indicators...")
    
    # Create engine with small model for faster testing
    engine = WhisperXEngine(
        model_size="tiny",
        device="auto",
        language="en"
    )
    
    print("\n=== Test 1: Normal loading with progress ===")
    try:
        engine.load_models(progress_callback=progress_callback, timeout=120)
        print("✓ Models loaded successfully")
    except Exception as e:
        print(f"✗ Loading failed: {e}")
        return False
    
    print("\n=== Test 2: Model change with progress ===")
    try:
        engine.change_model("base", progress_callback=progress_callback, timeout=60)
        print("✓ Model changed successfully")
    except Exception as e:
        print(f"✗ Model change failed: {e}")
        return False
    
    print("\n=== Test 3: Timeout test (very short timeout) ===")
    try:
        # Try loading a larger model with very short timeout to test fallback
        engine.change_model("small", progress_callback=progress_callback, timeout=1)
        print("✓ Loading completed (unexpected - timeout should have occurred)")
    except TimeoutError as e:
        print(f"✓ Timeout handled correctly: {e}")
    except Exception as e:
        print(f"? Other error occurred: {e}")
    
    print("\n=== Test 4: Check loading state methods ===")
    status, progress = engine.get_loading_progress()
    print(f"Loading status: {status}")
    print(f"Loading progress: {progress}%")
    print(f"Is loading: {engine.is_loading()}")
    
    print("\n=== Test 5: Cancellation test ===")
    def slow_progress_callback(status: str, progress: int):
        print(f"Progress: {progress:3d}% - {status}")
        # Simulate checking for cancellation during progress updates
        time.sleep(0.1)
    
    # Start loading in background to test cancellation
    import threading
    
    def load_with_cancel():
        try:
            engine.change_model("medium", slow_progress_callback, timeout=30)
        except Exception as e:
            print(f"Loading interrupted: {e}")
    
    loading_thread = threading.Thread(target=load_with_cancel)
    loading_thread.start()
    
    # Cancel after a short time
    time.sleep(2)
    print("Cancelling loading...")
    engine.cancel_loading()
    
    loading_thread.join(timeout=5)
    print("✓ Cancellation test completed")
    
    return True


if __name__ == "__main__":
    print("Model Loading Progress and Timeout Test")
    print("=" * 50)
    
    success = test_progress_loading()
    
    print("\n" + "=" * 50)
    if success:
        print("✓ All tests completed")
    else:
        print("✗ Some tests failed")