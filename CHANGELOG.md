# Changelog

All notable changes to Witticism will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/Aaronontheweb/witticism/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/Aaronontheweb/witticism/compare/v0.2.0...v0.2.2
[0.2.0]: https://github.com/Aaronontheweb/witticism/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Aaronontheweb/witticism/releases/tag/v0.1.0