#!/usr/bin/env python3
"""
Test script to verify toggle mode functionality.
Tests both push-to-talk and toggle dictation modes.
"""

import sys
from pathlib import Path
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

print("Testing Witticism with Toggle Mode Support")
print("=" * 50)

# Import our modules
from witticism.core.whisperx_engine import WhisperXEngine
from witticism.core.audio_capture import PushToTalkCapture, ContinuousCapture
from witticism.core.hotkey_manager import HotkeyManager

def test_push_to_talk():
    print("\n1. Testing Push-to-Talk Mode")
    print("-" * 30)
    
    # Initialize engine
    print("Initializing WhisperX engine...")
    engine = WhisperXEngine(model_size="tiny", device="auto")
    engine.load_models()
    
    # Initialize audio capture
    print("Initializing push-to-talk capture...")
    ptt_capture = PushToTalkCapture(sample_rate=16000)
    
    print("\nPush-to-Talk ready!")
    print("Press ENTER to start recording, speak, then press ENTER again to stop.")
    input()
    
    print("🎤 Recording...")
    ptt_capture.start_push_to_talk()
    
    input("Press ENTER to stop recording...")
    
    print("⏹ Stopping...")
    audio_data = ptt_capture.stop_push_to_talk()
    
    if len(audio_data) > 0:
        # Convert to float32 for WhisperX
        audio_float = audio_data.astype('float32') / 32768.0
        duration = len(audio_data) / 16000
        print(f"📊 Captured {duration:.1f} seconds of audio")
        
        print("🔄 Transcribing...")
        result = engine.transcribe(audio_float)
        text = engine.format_result(result)
        print(f"📝 Text: {text}")
    else:
        print("❌ No audio captured")
    
    ptt_capture.cleanup()
    engine.cleanup()
    print("✅ Push-to-Talk test complete")

def test_toggle_mode():
    print("\n2. Testing Toggle Dictation Mode")
    print("-" * 30)
    
    # Initialize engine
    print("Initializing WhisperX engine...")
    engine = WhisperXEngine(model_size="tiny", device="auto")
    engine.load_models()
    
    # Track transcribed chunks
    transcribed_chunks = []
    
    def process_chunk(audio_data):
        """Process audio chunk for real-time transcription"""
        print("📦 Processing chunk...")
        audio_float = audio_data.astype('float32') / 32768.0
        
        try:
            result = engine.transcribe(audio_float)
            text = engine.format_result(result)
            if text:
                transcribed_chunks.append(text)
                print(f"📝 Chunk transcribed: {text}")
        except Exception as e:
            print(f"❌ Transcription error: {e}")
    
    # Initialize continuous capture
    print("Initializing continuous capture...")
    continuous_capture = ContinuousCapture(
        chunk_callback=process_chunk,
        sample_rate=16000
    )
    continuous_capture.chunk_duration = 3.0  # Process every 3 seconds
    
    print("\nToggle Dictation ready!")
    print("Press ENTER to START dictation (speak continuously)")
    input()
    
    print("🎤 Dictation ON - Speak now! (Will record for 10 seconds)")
    continuous_capture.start_continuous()
    
    # Let it run for 10 seconds
    time.sleep(10)
    
    print("\n⏹ Stopping dictation...")
    continuous_capture.stop_continuous()
    
    print("\n📄 Full transcription:")
    full_text = " ".join(transcribed_chunks)
    print(full_text if full_text else "(No speech detected)")
    
    continuous_capture.cleanup()
    engine.cleanup()
    print("✅ Toggle Dictation test complete")

def test_hotkey_manager():
    print("\n3. Testing Hotkey Manager Mode Switching")
    print("-" * 30)
    
    hotkey_manager = HotkeyManager()
    
    print(f"Initial mode: {hotkey_manager.mode}")
    
    # Test mode switching
    print("Switching to toggle mode...")
    hotkey_manager.set_mode("toggle")
    print(f"Current mode: {hotkey_manager.mode}")
    
    print("Switching back to push_to_talk mode...")
    hotkey_manager.set_mode("push_to_talk")
    print(f"Current mode: {hotkey_manager.mode}")
    
    print("✅ Hotkey manager test complete")

def main():
    print("\nWitticism Toggle Mode Test Suite")
    print("This will test both push-to-talk and toggle dictation modes.\n")
    
    while True:
        print("\nChoose a test:")
        print("1. Test Push-to-Talk Mode")
        print("2. Test Toggle Dictation Mode")
        print("3. Test Hotkey Manager")
        print("4. Run all tests")
        print("q. Quit")
        
        choice = input("\nEnter your choice: ").strip().lower()
        
        if choice == '1':
            test_push_to_talk()
        elif choice == '2':
            test_toggle_mode()
        elif choice == '3':
            test_hotkey_manager()
        elif choice == '4':
            test_push_to_talk()
            test_toggle_mode()
            test_hotkey_manager()
        elif choice == 'q':
            break
        else:
            print("Invalid choice. Please try again.")
    
    print("\nGoodbye!")

if __name__ == "__main__":
    main()