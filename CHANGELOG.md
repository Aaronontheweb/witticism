# Changelog

All notable changes to Witticism will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.0] - 2025-09-09

### 🚀 Stable Release: Windows Platform Support & Polish

This stable release represents the completion of Windows platform support with major installer improvements, bug fixes, and documentation enhancements building on the beta1 foundation.

### ✨ Improvements Since Beta1

#### 🪟 Windows Installer Polish & Bug Fixes
- **Fixed PowerShell syntax errors** that caused installation failures on some Windows systems ([#81](https://github.com/Aaronontheweb/witticism/issues/81))
- **Enhanced installer UX** with version parameter support (`install.ps1 -Version 0.6.0`)
- **Added cleanup functionality** with `-Cleanup` flag for clean reinstallation
- **Improved progress indicators** during lengthy WhisperX downloads (2-3 minutes) with detailed explanations
- **Enhanced desktop shortcut icon detection** using bundled Witticism assets with intelligent fallback
- **Better timeout handling** for installation testing and verification
- **Comprehensive uninstall documentation** with multiple removal options

#### 📚 Documentation Enhancements  
- **Fixed Windows installation command** in README.md ([#78](https://github.com/Aaronontheweb/witticism/issues/78))
- **Improved Windows integration documentation** with detailed uninstall instructions
- **Enhanced error messaging** and troubleshooting guidance for Windows users

### 🔧 All Windows Features (from 0.6.0-beta1)

#### Complete Windows Platform Support
- **Full Windows compatibility** with cross-platform architecture
- **PowerShell installer (install.ps1)** - One-line installation with automated Python management  
- **Automated Python 3.12 setup** - Handles WhisperX compatibility automatically
- **Auto-start functionality** - Silent background startup via Windows startup folder
- **Desktop integration** - Shortcuts and proper Windows application integration

#### Cross-Platform Architecture
- **Platform-specific sleep monitoring** - Windows uses PowerShell/WMI, Linux uses DBus
- **Cross-platform file locking** - Prevents multi-instance issues on both platforms
- **Conditional dependencies** - pydbus Linux-only, preventing Windows conflicts
- **Unicode console compatibility** - ASCII fallbacks for Windows terminals

### 📊 Platform Compatibility
- **Windows** - Full support with CPU-only transcription, auto-start, and silent operation
- **Linux** - Maintains all existing functionality including GPU acceleration and systemd integration
- **Future-ready** - Architecture prepared for macOS support

This release transforms Witticism into a mature, cross-platform voice transcription tool with polished installation experiences on both Windows and Linux platforms.

## [0.6.0-beta1] - 2025-09-09

### 🚀 Major Beta Release: Complete Windows Platform Support

This beta release introduces comprehensive Windows support, bringing Witticism to Windows users with a complete cross-platform architecture while maintaining full Linux compatibility.

### ✨ New Features

#### 🪟 Windows Platform Support
- **Complete Windows compatibility** - First-class Windows support with cross-platform architecture
- **PowerShell installer (install.ps1)** - One-line Windows installation with automated Python management
- **Automated Python 3.12 setup** - Handles Python version compatibility issues automatically for WhisperX
- **Auto-start functionality** - Silent background startup via Windows startup folder integration
- **Desktop integration** - Shortcuts and proper Windows application integration

#### 🔧 Cross-Platform Architecture  
- **Platform-specific sleep monitoring** - Windows uses PowerShell/WMI events, Linux continues using DBus
- **Cross-platform file locking** - Windows msvcrt implementation, Linux fcntl (prevents multi-instance issues)
- **Conditional dependencies** - pydbus now Linux-only using platform markers, preventing Windows installation issues
- **Unicode console compatibility** - ASCII fallbacks for Windows terminal compatibility

#### 🎯 Enhanced Installation Experience
- **Smart GPU detection** - Automatic CUDA version detection and PyTorch index selection on Windows
- **CPU-optimized setup** - Installs CPU-only PyTorch for maximum Windows compatibility  
- **Dual installation methods** - Supports both pipx and direct pip installation with automatic fallback
- **Comprehensive error handling** - Clear error messages and troubleshooting guidance for Windows users

#### 📚 Documentation & Guides
- **INSTALL_WINDOWS.md** - Comprehensive Windows installation guide with troubleshooting
- **Updated README.md** - Added Windows installation instructions alongside existing Linux guide
- **Cross-platform compatibility notes** - Clear documentation of platform-specific features

### 🔧 Fixed

#### NVIDIA Suspend/Resume Fix (Linux)
- **Root cause identified and fixed** - CUDA crashes after suspend/resume were caused by nvidia_uvm kernel module corruption  
- **Automatic system configuration** - Linux installer now configures NVIDIA to preserve GPU memory across suspend cycles
- **Idempotent installation** - Configuration is checked and only applied if needed, safe for re-runs and upgrades
- Fixes months of SIGABRT crashes that occurred after system suspend/resume cycles on Linux systems
- Solution based on research from PyTorch forums and Ask Ubuntu community

#### Cross-Platform Compatibility
- **Headless environment support** - Application now works in CI environments without display (fixes --version in GitHub Actions)
- **Python version constraints** - Limited to Python <3.13 for WhisperX compatibility across platforms
- **Unicode handling** - Fixed console output issues on Windows terminals

### 🧪 Testing & CI
- **Automated installer testing** - GitHub Actions workflow tests both Linux and Windows installers  
- **Idempotency verification** - Ensures installer scripts can be run multiple times safely
- **Version verification** - Confirms functionality after installation on both platforms
- **Cross-platform CI** - Comprehensive testing pipeline for both Linux and Windows environments

### 🚀 Technical Improvements
- **Smart dependency management** - Platform-specific dependencies prevent installation conflicts
- **Enhanced error handling** - Better error messages and fallback behavior across platforms  
- **Modular architecture** - Clean separation of platform-specific and shared components
- **Installation verification** - Built-in testing and verification of successful installation

### 📊 Platform Compatibility
- **Windows** - Full support with CPU-only transcription, auto-start, and silent background operation
- **Linux** - Maintains all existing functionality including GPU acceleration and systemd integration  
- **Future-ready** - Architecture prepared for macOS support in future releases

This beta release represents a major milestone, transforming Witticism from a Linux-only application into a truly cross-platform voice transcription tool. Windows users can now enjoy the same push-to-talk transcription experience that Linux users have had, with a streamlined one-command installation process.

## [0.5.0] - 2025-08-24

### 🎯 Major Release: Observability & Recovery

This release focuses on enhanced user notifications, comprehensive diagnostics, and improved system reliability. The v0.5.0 "Observability & Recovery" milestone brings unprecedented visibility into system performance and health.

### ✨ New Features

#### CUDA Health Diagnostics
- **CUDA Health Check API** - New comprehensive diagnostic interface accessible via system tray "Test CUDA" menu item
- Real-time GPU device detection with detailed hardware information display
- Comprehensive CUDA context validation with actionable recommendations
- Background health checking that doesn't block UI operations

#### Enhanced Visual Feedback
- **Dynamic status indicators** showing actual GPU device names (e.g., "Running on NVIDIA GTX 1080")
- **Enhanced tooltips** with clear fallback mode indication and performance context
- **Visual compute mode feedback** distinguishing between CUDA acceleration and CPU fallback
- Improved tray icon system with contextual status colors

#### System Diagnostics & Recovery
- **Diagnostics mode** with `--diagnostics` flag for comprehensive system health reporting
- **System status dashboard** providing centralized view of application health
- **Progressive error recovery** with guided user assistance for common issues
- **Manual CUDA recovery** option directly accessible from system tray

#### Configuration & Usability
- **Dynamic hotkey updates** - Change hotkeys without application restart
- **Structured state change logging** for improved debugging and issue resolution
- Enhanced initialization flow with better error handling and user feedback

### 🔧 Fixed
- **Hotkey configuration binding** - Resolved F9/F12 configuration inconsistency where config showed F12 but F9 actually worked
- **Startup CPU fallback notification** - Users now receive clear notification when CUDA is unavailable at startup
- **Critical initialization ordering** - Fixed dependency resolution and component initialization sequence
- **CUDA startup fallback** notification timing improved for better user awareness

### 🚀 Improved
- **Observability**: Complete visibility into GPU/CPU operation modes and system health
- **User Experience**: Clear visual feedback about performance modes and system status  
- **Reliability**: Enhanced error recovery with progressive guidance for users
- **Diagnostics**: Comprehensive health checking and system status reporting
- **Configuration**: Live configuration updates without restart requirements

### 📊 Technical Details
- Added comprehensive CUDA validation infrastructure leveraging existing dependency validator
- Implemented threaded health checks to maintain UI responsiveness
- Enhanced tooltip system with dynamic device information display
- Integrated system tray diagnostics with existing validation components
- All features built upon existing infrastructure for maximum reliability

This release completes the foundational observability and recovery systems that make Witticism more transparent, reliable, and user-friendly. Users now have complete visibility into their system's performance characteristics and immediate access to diagnostic tools.

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

[Unreleased]: https://github.com/Aaronontheweb/witticism/compare/0.6.0...HEAD
[0.6.0]: https://github.com/Aaronontheweb/witticism/compare/v0.6.0-beta1...0.6.0
[0.6.0-beta1]: https://github.com/Aaronontheweb/witticism/compare/0.5.0...v0.6.0-beta1
[0.5.0]: https://github.com/Aaronontheweb/witticism/compare/0.4.6...0.5.0
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