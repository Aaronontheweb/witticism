# Changelog

All notable changes to Witticism will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.1] - 2025-08-20

### Added
- Bundled application icons in pip package for reliable installation
- Auto-upgrade detection in install script

### Improved
- Install script now upgrades existing installations with `--force` flag
- Icon installation no longer requires PyQt5 during setup
- Icons copied directly from installed package location

### Fixed
- Missing application icons after installation
- Install script not upgrading when witticism already installed
- Hardcoded F9 key display in About dialog and system tray menu - now shows actual configured hotkeys

## [0.4.0] - 2025-08-20

### Added
- Custom hotkey input widget with explicit Edit/Save/Cancel workflow
- Individual reset buttons for each keyboard shortcut
- Full desktop integration with application launcher support
- Automatic icon generation and installation at multiple resolutions
- Smart sudo handling in install script (only when needed)
- Desktop entry with proper categories and keywords for launcher discoverability

### Improved
- Hotkey configuration UX to prevent accidental changes
- Keyboard shortcuts now update dynamically without restart
- Settings dialog only shows changes when values actually differ
- Install script is now fully self-contained with inline icon generation
- Better separation between system and user-level installations
- Dialog window sizes optimized for content

### Fixed
- Aggressive hotkey capture behavior that immediately recorded new keys
- False restart requirements for keyboard shortcuts
- Incorrect "Settings Applied" dialog when resetting to defaults
- Install script running as root/sudo when it shouldn't
- Missing launcher integration after installation

### Changed
- Unified desktop entry installation into main install.sh script
- Removed separate desktop entry scripts in favor of integrated approach
- Updated README to accurately reflect current installation process

## [0.3.0] - 2025-08-20

### Added
- `--version` flag to CLI for displaying version information
- Proactive system sleep monitoring to prevent CUDA crashes during suspend/resume cycles
- Cross-platform sleep detection with Linux DBus integration
- Automatic GPU context cleanup before system suspend

### Improved
- Enhanced CUDA error recovery with expanded error pattern detection
- Robust CPU fallback during model loading failures
- Better suspend/resume resilience with proactive monitoring instead of reactive recovery
- Device configuration preservation during fallback operations

### Fixed
- Root cause of CUDA context invalidation crashes after suspend/resume by switching to proactive approach
- Permanent application failures after suspend/resume cycles with improved error recovery

## [0.2.4] - 2025-08-18

### Added
- Model loading progress indicators with percentage and status updates
- Configurable timeouts for model loading (2 min for small, 5 min for large models)
- Automatic fallback to smaller model when loading times out
- Cancel loading functionality via system tray menu
- Real-time progress display in tray tooltips and menu

### Improved
- User experience during model downloads with visibility into progress
- Responsiveness during model loading using threaded operations
- Control over stuck or slow model downloads with cancellation support

## [0.2.3] - 2025-08-18

### Added
- Automatic CUDA error recovery after suspend/resume cycles
- Visual indicators for CPU fallback mode (orange tray icon)
- System notifications when GPU errors occur
- GPU error status in system tray menu

### Fixed
- CUDA context becoming invalid after laptop suspend/resume
- Transcription failures due to GPU errors now automatically fall back to CPU

### Improved
- Better error handling and recovery for GPU-related issues
- Clear user feedback about performance degradation when running on CPU
- Informative tooltips and status messages indicating current device mode

## [0.2.2] - 2025-08-16

### Fixed
- Model persistence across application restarts - selected model now saves and loads correctly
- CI linting warnings and enforcement of code quality checks

### Improved
- CI test discovery to run all unit tests automatically
- Code quality with comprehensive linting checks

## [0.2.0] - 2025-08-16

### Added
- Settings dialog with hot-reloading support
- About dialog with system information and GPU status
- Automatic GPU detection and CUDA version compatibility
- One-command installation script with GPU detection
- Smart upgrade script with settings backup
- GitHub Actions CI/CD pipeline
- PyPI package distribution support
- OIDC publishing to PyPI
- Dynamic versioning from git tags

### Fixed
- CUDA initialization errors on systems with mismatched PyTorch/CUDA versions
- Virtual environment isolation issues
- NumPy compatibility with WhisperX

### Changed
- Improved installation process with pipx support
- Better error handling for GPU initialization
- Updated documentation with clearer installation instructions

## [0.1.0] - 2025-08-15

### Added
- Initial release
- WhisperX-powered voice transcription
- Push-to-talk with F9 hotkey
- System tray integration
- Multiple model support (tiny, base, small, medium, large-v3)
- GPU acceleration with CUDA
- Continuous dictation mode
- Audio device selection
- Configuration persistence

[Unreleased]: https://github.com/Aaronontheweb/witticism/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/Aaronontheweb/witticism/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/Aaronontheweb/witticism/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Aaronontheweb/witticism/compare/v0.2.4...v0.3.0
[0.2.4]: https://github.com/Aaronontheweb/witticism/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/Aaronontheweb/witticism/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/Aaronontheweb/witticism/compare/v0.2.0...v0.2.2
[0.2.0]: https://github.com/Aaronontheweb/witticism/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Aaronontheweb/witticism/releases/tag/v0.1.0