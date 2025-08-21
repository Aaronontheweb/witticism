# Development Scripts

This directory contains various test and development scripts used during Witticism development. These are not needed for end users but may be useful for developers working on the codebase.

## Scripts

### test_app.py
Test script to verify the application structure without WhisperX dependencies. Useful for testing imports and basic functionality without requiring GPU/ML dependencies.

### test_voice.py  
Simple test script to verify WhisperX voice transcription works. Hold ENTER to record, release to transcribe. Tests the core transcription pipeline.

### test_toggle_mode.py
Test script to verify toggle mode functionality. Tests both push-to-talk and toggle dictation modes to ensure mode switching works correctly.

### test_progress_loading.py
Test script to demonstrate the progress indicator and timeout functionality. Verifies that model loading progress tracking works properly.

### test_minimal.py
Minimal test to verify core functionality with mock components. Uses mock WhisperX implementation for testing without ML dependencies.

## Usage

These scripts are designed to be run from the repository root:

```bash
# Test basic imports without ML dependencies
python3 dev-scripts/test_app.py

# Test voice transcription (requires WhisperX)
python3 dev-scripts/test_voice.py

# Test toggle mode functionality  
python3 dev-scripts/test_toggle_mode.py

# Test model loading progress
python3 dev-scripts/test_progress_loading.py

# Test with mock components
python3 dev-scripts/test_minimal.py
```

**Note**: Most scripts require the development environment to be set up with dependencies installed.