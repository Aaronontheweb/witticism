#!/usr/bin/env python3
"""
Simple test script to verify WhisperX voice transcription works.
Hold ENTER to record, release to transcribe.
"""

import sys
from pathlib import Path
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

print("Testing WhisperX voice transcription...")

# Import our modules
from witticism.core.whisperx_engine import WhisperXEngine
from witticism.core.audio_capture import PushToTalkCapture

def main():
    print("\nInitializing WhisperX engine (this may take a moment)...")
    
    # Initialize engine with tiny model for faster testing
    engine = WhisperXEngine(model_size="tiny", device="auto")
    engine.load_models()
    
    device_info = engine.get_device_info()
    print(f"Device: {device_info['device']}")
    print(f"Models loaded: {device_info['models_loaded']}")
    
    # Initialize audio capture
    print("\nInitializing audio capture...")
    audio_capture = PushToTalkCapture(sample_rate=16000)
    
    # List audio devices
    devices = audio_capture.get_audio_devices()
    print("\nAvailable audio devices:")
    for device in devices:
        print(f"  [{device['index']}] {device['name']} ({device['channels']} channels)")
    
    print("\n" + "="*50)
    print("VOICE TRANSCRIPTION TEST")
    print("="*50)
    print("\nInstructions:")
    print("1. Press and HOLD Enter to start recording")
    print("2. Speak clearly into your microphone")
    print("3. RELEASE Enter to stop and transcribe")
    print("4. Type 'quit' to exit\n")
    
    while True:
        input("Press and HOLD Enter to record (or type 'quit' to exit): ")
        
        user_input = input().strip().lower()
        if user_input == 'quit':
            break
            
        print("🎤 Recording... (speak now, then press Enter to stop)")
        audio_capture.start_push_to_talk()
        
        # Wait for user to press Enter again to stop
        input()
        
        print("⏹ Stopping recording...")
        audio_data = audio_capture.stop_push_to_talk()
        
        if len(audio_data) == 0:
            print("❌ No audio captured. Try again.")
            continue
            
        # Convert to float32 for WhisperX
        audio_float = audio_data.astype('float32') / 32768.0
        duration = len(audio_data) / 16000
        print(f"📊 Captured {duration:.1f} seconds of audio")
        
        print("🔄 Transcribing...")
        start_time = time.time()
        
        try:
            result = engine.transcribe(audio_float)
            text = engine.format_result(result)
            processing_time = time.time() - start_time
            
            print(f"\n✅ Transcription complete in {processing_time:.2f}s")
            print(f"📝 Text: {text}\n")
            
        except Exception as e:
            print(f"❌ Transcription failed: {e}\n")
    
    # Cleanup
    audio_capture.cleanup()
    engine.cleanup()
    print("\nGoodbye!")

if __name__ == "__main__":
    main()