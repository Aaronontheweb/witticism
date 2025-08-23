# Changelog

All notable changes to Witticism will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.6] - 2025-08-23

### Fixed
- Installation failures caused by unused PyGObject dependency - dependency removed from package requirements
- Package installation now succeeds without requiring system GObject introspection libraries that were intentionally removed

## [0.4.5] - 2025-08-23

### Fixed
- **CRITICAL**: Enhanced CUDA suspend/resume crash protection with comprehensive startup health checks
- Added startup CUDA context validation to prevent crashes from previous suspend/resume corruption
- Fixed install.sh version extraction hanging issue that prevented script completion
- Implemented graceful CPU fallback instead of hard crashes when CUDA context is corrupted
- Added singleton instance protection with automatic zombie lock file cleanup

### Improved
- Application now performs nuclear CUDA cleanup at startup if context is corrupted
- Install script now properly extracts version information without hanging
- Enhanced initialization flow prevents crashes before sleep monitor activation
- Better error handling that maintains application stability during CUDA failures

## [0.4.4] - 2025-08-23

### Fixed
- **CRITICAL**: Resolved persistent SIGABRT crashes during laptop suspend/resume cycles with CUDA systems
- Implemented comprehensive solution using systemd inhibitor locks to prevent kernel/userspace timing race conditions
- Added nuclear GPU cleanup with complete model destruction before system suspend
- Enhanced CUDA health testing and background model restoration after resume
- Fixed fundamental issue where previous recovery attempts failed because kernel had already invalidated CUDA contexts

### Improved
- Proactive suspend/resume handling with guaranteed cleanup time using systemd inhibitors
- Smart fallback to CPU mode when GPU recovery fails, maintaining application stability
- Background model restoration that doesn't block system resume process

## [0.4.3] - 2025-08-22

### Added
- Debug logging documentation to README with instructions for enabling debug mode and locating log files

### Improved
- Simplified installation requirements by removing unnecessary GObject introspection dependencies
- Installation process now only requires PortAudio packages for audio capture functionality

### Fixed
- Model selection not persisting after application upgrades or restarts - menu selection now correctly reflects saved configuration

## [0.4.2] - 2025-08-21

### Added
- PyGObject as pip dependency for sleep monitoring functionality
- System dependency detection for GObject Introspection development libraries

### Improved
- Install script now installs minimal development libraries needed for PyGObject compilation
- Sleep monitoring system dependencies are automatically handled during installation
- Manual installation instructions updated with correct system dependencies

### Fixed
- Missing PyGObject dependency that prevented sleep monitoring from working
- Silent failure of suspend/resume CUDA recovery due to missing GObject Introspection
- Install script not detecting all required system dependencies for sleep monitoring

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

[Unreleased]: https://github.com/Aaronontheweb/witticism/compare/0.4.6...HEAD
[0.4.6]: https://github.com/Aaronontheweb/witticism/compare/0.4.5...0.4.6
[0.4.5]: https://github.com/Aaronontheweb/witticism/compare/0.4.4...0.4.5
[0.4.4]: https://github.com/Aaronontheweb/witticism/compare/0.4.3...0.4.4
[0.4.3]: https://github.com/Aaronontheweb/witticism/compare/v0.4.2...0.4.3
[0.4.2]: https://github.com/Aaronontheweb/witticism/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/Aaronontheweb/witticism/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/Aaronontheweb/witticism/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Aaronontheweb/witticism/compare/v0.2.4...v0.3.0
[0.2.4]: https://github.com/Aaronontheweb/witticism/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/Aaronontheweb/witticism/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/Aaronontheweb/witticism/compare/v0.2.0...v0.2.2
[0.2.0]: https://github.com/Aaronontheweb/witticism/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Aaronontheweb/witticism/releases/tag/v0.1.0