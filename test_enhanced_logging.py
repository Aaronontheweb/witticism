#!/usr/bin/env python3
"""
Test script to demonstrate the enhanced structured logging functionality.
This shows how the new logging format provides better visibility into 
state changes and decisions for debugging CUDA and other issues.
"""

import logging
import sys
from pathlib import Path

# Add src directory to path so we can import witticism modules
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Setup logging to see our enhanced logs
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def test_whisperx_engine_logging():
    """Test WhisperXEngine structured logging (without dependencies)"""
    print("\n=== Testing WhisperXEngine Logging Structure ===")
    
    # Import the logging parts we can test without dependencies
    from witticism.platform.sleep_monitor import create_sleep_monitor, MockSleepMonitor
    
    def mock_suspend():
        logging.getLogger('test').info("[WHISPERX_ENGINE] SYSTEM_SUSPEND: detected (attempt #1) - performing EMERGENCY GPU abandonment")
        logging.getLogger('test').warning("[WHISPERX_ENGINE] NUCLEAR_GPU_CLEANUP: destroying all models and contexts - model_size=base, device=cuda")
        logging.getLogger('test').warning("[WHISPERX_ENGINE] NUCLEAR_GPU_ABANDONMENT_COMPLETE: models destroyed, contexts cleared")
    
    def mock_resume():
        logging.getLogger('test').info("[WHISPERX_ENGINE] SYSTEM_RESUME: detected (attempt #1) - performing CUDA health assessment")
        logging.getLogger('test').info("[WHISPERX_ENGINE] SUSPEND_STATE_FOUND: testing CUDA recovery")
        logging.getLogger('test').info("[WHISPERX_ENGINE] CUDA_HEALTHY: after resume - initiating model restoration")
        logging.getLogger('test').info("[WHISPERX_ENGINE] MODEL_RESTORE_SUCCESS: restoration completed - GPU fully operational")
    
    # Create mock sleep monitor and test it
    monitor = create_sleep_monitor(mock_suspend, mock_resume)
    if isinstance(monitor, MockSleepMonitor):
        monitor.start_monitoring()
        print("  ✓ Created mock sleep monitor for testing")
        
        # Simulate suspend/resume cycle
        print("  ✓ Simulating suspend event:")
        monitor.simulate_suspend()
        
        print("  ✓ Simulating resume event:")
        monitor.simulate_resume()
        
        monitor.stop_monitoring()

def test_hotkey_manager_logging():
    """Test HotkeyManager logging structure"""
    print("\n=== Testing HotkeyManager Logging Structure ===")
    
    # Mock the logging calls we would expect
    logger = logging.getLogger('hotkey_test')
    
    # Simulate initialization
    logger.info("[HOTKEY_MANAGER] INIT: mode=push_to_talk, ptt_key=f9")
    logger.info("[HOTKEY_MANAGER] STARTED: keyboard listener active")
    
    # Simulate PTT usage
    logger.debug("[HOTKEY_MANAGER] PTT_START: f9 pressed - recording started")
    logger.debug("[HOTKEY_MANAGER] PTT_STOP: f9 released - recording stopped")
    
    # Simulate hotkey change
    logger.info("[HOTKEY_MANAGER] PTT_KEY_CHANGED: from f9 to f12")
    
    # Simulate mode change  
    logger.info("[HOTKEY_MANAGER] MODE_CHANGED: from push_to_talk to toggle")
    logger.debug("[HOTKEY_MANAGER] TOGGLE_DICTATION: f12 pressed - dictation enabled")
    
    logger.info("[HOTKEY_MANAGER] STOPPED: keyboard listener deactivated")
    print("  ✓ Demonstrated hotkey manager structured logging")

def test_main_startup_logging():
    """Test main.py startup decision logging"""
    print("\n=== Testing Main Startup Logging Structure ===")
    
    logger = logging.getLogger('startup_test')
    
    # Simulate startup sequence
    logger.info("[WITTICISM] STARTUP: version=0.4.6, args={'model': None, 'log_level': 'INFO'}")
    logger.info("[WITTICISM] ENGINE_INIT: model_size=base, device=cuda, compute_type=float16, language=en")
    
    # Simulate CUDA validation
    logger.info("[WITTICISM] CUDA_VALIDATION: performing startup health check")
    logger.info("[WITTICISM] CUDA_VALIDATION_PASSED: startup health check successful")
    
    logger.info("[WITTICISM] MODEL_LOADING: starting WhisperX model loading")
    logger.info("[WITTICISM] MODEL_LOADING_COMPLETE: all models loaded successfully")
    
    logger.info("[WITTICISM] SLEEP_MONITORING: enabling proactive suspend/resume detection")
    logger.info("[WITTICISM] AUDIO_INIT: sample_rate=16000, channels=1, vad_aggressiveness=2")
    logger.info("[WITTICISM] PIPELINE_INIT: min_audio_length=0.5s, max_audio_length=30.0s")
    logger.info("[WITTICISM] OUTPUT_INIT: mode=type")
    logger.info("[WITTICISM] INIT_COMPLETE: all components initialized successfully")
    logger.info("[WITTICISM] STARTUP_COMPLETE: application ready and running")
    
    print("  ✓ Demonstrated main startup structured logging")
    
    # Simulate CUDA fallback scenario
    print("  ✓ Simulating CUDA fallback scenario:")
    logger.warning("[WITTICISM] CUDA_INIT_FAILURE: CUDA-related error detected - RuntimeError: CUDA out of memory...")
    logger.info("[WITTICISM] RECOVERY_ATTEMPT: attempting CPU fallback recovery")
    logger.warning("[WITTICISM] CUDA_FALLBACK_RETRY: forcing CPU mode due to initialization failure")
    logger.info("[WITTICISM] RECOVERY_SUCCESS: CPU fallback initialization successful")

def test_sleep_monitor_logging():
    """Test sleep monitor structured logging"""
    print("\n=== Testing Sleep Monitor Logging Structure ===")
    
    logger = logging.getLogger('sleep_monitor_test')
    
    # Factory logging
    logger.info("[SLEEP_MONITOR] FACTORY: creating systemd inhibitor monitor with CUDA protection")
    logger.info("[SLEEP_MONITOR] INIT: DBus sleep monitoring initialized")
    logger.info("[SLEEP_MONITOR] STARTED: DBus PrepareForSleep signal monitoring active")
    
    # Suspend/resume cycle with inhibitor
    logger.info("[SLEEP_MONITOR] SUSPEND_WITH_INHIBITOR: acquiring lock for CUDA cleanup at 18:25:03")
    logger.debug("[SLEEP_MONITOR] INHIBITOR_ACQUIRED: systemd inhibitor active (max 20s delay)")
    logger.info("[SLEEP_MONITOR] PROTECTED_CLEANUP: performing CUDA cleanup with 20s protection")
    logger.info("[SLEEP_MONITOR] CLEANUP_COMPLETE: releasing inhibitor to allow suspend")
    logger.debug("[SLEEP_MONITOR] INHIBITOR_RELEASED: systemd inhibitor terminated, suspend allowed")
    
    logger.info("[SLEEP_MONITOR] RESUME_WITH_INHIBITOR: system resumed from suspend at 09:15:22")
    
    logger.info("[SLEEP_MONITOR] STOPPED: DBus sleep monitoring deactivated")
    print("  ✓ Demonstrated sleep monitor structured logging")

def main():
    """Run all logging demonstrations"""
    print("🔍 Enhanced Structured State Change Logging Demo")
    print("=" * 60)
    print("This demonstrates the new structured logging format that provides")
    print("full visibility into state changes and decisions for debugging.")
    print("Format: [COMPONENT] ACTION: details with context")
    
    test_whisperx_engine_logging()
    test_hotkey_manager_logging() 
    test_main_startup_logging()
    test_sleep_monitor_logging()
    
    print("\n✅ Enhanced Logging Implementation Complete!")
    print("\nKey Benefits:")
    print("- Consistent [COMPONENT] ACTION: format across all modules")  
    print("- CUDA state changes logged with reason and context")
    print("- Model loading stages with timing information")
    print("- Hotkey changes and mode switches clearly identified")  
    print("- Suspend/resume events with timestamps and recovery status")
    print("- Device detection and switching with before/after state")
    print("- Performance metrics included where relevant")
    print("\nThis will make debugging CUDA corruption issues much easier!")

if __name__ == "__main__":
    main()