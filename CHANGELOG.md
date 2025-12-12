# Changelog

All notable changes to Witticism will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.3] - 2025-12-11

### 🔧 Fixed

#### Audio Capture Error Resilience
- **Enhanced PortAudio error handling** - Added intelligent error classification and automatic recovery for audio capture failures ([#103](https://github.com/Aaronontheweb/witticism/pull/103))
- **Automatic PyAudio reinitialization** - System now automatically recovers from fatal PortAudio errors (e.g., `-9999` paUnanticipatedHostError)
- **Graceful error state management** - Consecutive error threshold detection prevents infinite retry loops
- **Safe stream cleanup** - Handles corrupted audio state gracefully instead of crashing
- Application now survives audio device disconnections and host errors during recording
- Prevents unhandled exceptions when PortAudio encounters hardware failures

### 📊 Impact
This patch release improves application stability when dealing with audio hardware issues. Key improvements include:
- Application no longer crashes when audio devices are disconnected during recording
- Automatic recovery from transient audio errors without user intervention
- Better error reporting through new `on_error` callback mechanism
- Graceful degradation when audio system encounters fatal errors

## [0.7.2] - 2025-11-20

### 🔧 Fixed

#### Pascal GPU Compatibility (GTX 10-series)
- **Fixed PyTorch 2.8+ incompatibility with Pascal GPUs** - Pinned PyTorch to <2.8.0 to maintain compatibility with GTX 10-series GPUs ([#100](https://github.com/Aaronontheweb/witticism/pull/100))
- PyTorch 2.8.0+ dropped support for Pascal architecture (compute capability 6.x), affecting GTX 1050/1060/1070/1080/1080 Ti
- Users with these GPUs were experiencing silent fallback to CPU mode with 10x+ performance degradation (14s vs <2s for large model inference)
- Install script now automatically detects Pascal GPUs and pins PyTorch <2.8.0 during installation
- Future GPUs (Volta+, compute capability 7.0+) remain unaffected and can use newer PyTorch versions when ready to upgrade

#### cuDNN Library Loading
- **Fixed cuDNN library loading crashes in pipx environments** - Added preloading of cuDNN libraries to prevent runtime crashes ([#100](https://github.com/Aaronontheweb/witticism/pull/100))
- PyTorch bundles cuDNN libraries but doesn't add them to dynamic linker search path, causing "Unable to load libcudnn_cnn.so" errors
- Application would crash during transcription when cuDNN libraries couldn't be located
- Solution preloads all cuDNN libraries using ctypes.CDLL with RTLD_GLOBAL before PyTorch imports them
- Particularly critical for pipx installations where libraries are in isolated virtual environments

### 📊 Impact
This patch release addresses critical GPU compatibility issues that prevented Pascal GPU users from benefiting from GPU acceleration. Key fixes include:
- Restored GPU acceleration for all GTX 10-series users (previously falling back to CPU)
- Eliminated transcription crashes caused by missing cuDNN libraries in pipx environments
- Automatic detection and configuration during installation ensures users get optimal performance
- 10x+ performance improvement for affected users by maintaining GPU acceleration

## [0.7.1] - 2025-11-19

### 🔧 Fixed

#### Critical Dependency Compatibility
- **Fixed torchaudio 2.9+ incompatibility** - Pinned torchaudio to <2.9.0 to prevent WhisperX model loading failures ([#98](https://github.com/Aaronontheweb/witticism/pull/98))
- Torchaudio 2.9.0+ removed the `AudioMetaData` attribute that WhisperX depends on, causing model loading to fail
- Users upgrading to latest PyTorch packages would experience zero text output despite microphone input being detected
- References upstream WhisperX issue: https://github.com/m-bain/whisperX/issues/1270

#### Logging System
- **Fixed logging path expansion** - Logging now works correctly with tilde (~) paths in configuration ([#98](https://github.com/Aaronontheweb/witticism/pull/98))
- **Enabled default file logging** - Changed default log file from `None` to platformdirs-based path (`~/.local/share/witticism/debug.log`)
- Debug logs are now written by default, making troubleshooting significantly easier
- Path expansion uses `.expanduser()` to properly handle Unix home directory shortcuts

#### Error Handling & Diagnostics
- **Fixed silent model loading failures** - Thread exceptions during model loading are now properly propagated to caller ([#98](https://github.com/Aaronontheweb/witticism/pull/98))
- Application now fails fast with clear error messages instead of appearing to start successfully when models fail to load
- Added `loading_error` instance variable to track failures from daemon threads
- Prevents confusing situations where app appears to work but produces no transcription output

#### User Interface
- **Fixed duplicate system tray icons** - Resolved issue where CUDA fallback retry created second tray icon ([#98](https://github.com/Aaronontheweb/witticism/pull/98))
- System tray instance is now reused when CUDA initialization requires CPU fallback
- Users with older GPUs or CUDA compatibility issues no longer see duplicate tray icons

### 📊 Impact
This patch release addresses critical bugs discovered during user troubleshooting that prevented the application from functioning correctly. Key fixes include:
- Text output now works reliably with latest PyTorch/torchaudio versions
- Debugging is significantly easier with working default logging
- Clear error messages replace silent failures during model loading
- Cleaner UI experience for users requiring CUDA fallback to CPU mode

## [0.7.0] - 2025-11-17

### 🔧 Fixed

#### Application State Persistence
- **Fixed text typing failure after quit and relaunch** - Resolved issue where text insertion would fail silently after quitting and relaunching the application ([#96](https://github.com/Aaronontheweb/witticism/pull/96))
- Application state now properly resets between sessions, ensuring consistent text typing behavior

#### Windows Installation & GPU Support
- **Fixed Windows installer CUDA detection** - PowerShell installer now properly detects and configures CUDA support on Windows systems ([#91](https://github.com/Aaronontheweb/witticism/pull/91))
- Windows users with NVIDIA GPUs can now take advantage of GPU acceleration during installation
- Improved GPU detection logic prevents installation failures on CUDA-enabled systems

#### Windows Installer Reliability
- **Fixed PowerShell Get-ChildItem syntax error** - Resolved syntax error in icon detection that caused installer failures on some Windows configurations ([#90](https://github.com/Aaronontheweb/witticism/pull/90))
- Icon detection now works correctly across all Windows PowerShell versions
- Installation completes successfully without syntax-related failures

### 📚 Documentation

#### Windows Troubleshooting
- **Added Windows debug log locations** - Comprehensive documentation for locating debug logs on Windows systems ([#92](https://github.com/Aaronontheweb/witticism/pull/92))
- **Added force reinstall instructions** - Step-by-step guide for performing clean reinstallation when needed
- Improved troubleshooting documentation helps Windows users resolve issues more effectively

### 📊 Impact
This release focuses on polish and reliability improvements for Windows users. Key improvements include:
- More reliable text insertion after application restarts
- Better GPU acceleration support during Windows installation
- Improved installer reliability across different Windows configurations
- Enhanced troubleshooting documentation for Windows-specific issues

## [0.6.2] - 2025-09-10

### 🔧 Fixed

#### Windows Installation Reliability
- **Resolved Windows compilation failures** - Switched from `webrtcvad>=2.0.10` to `webrtcvad-wheels>=2.0.14` to eliminate Visual C++ Build Tools requirement ([#88](https://github.com/Aaronontheweb/witticism/pull/88))
- **Eliminated installation errors** - Windows users no longer encounter "Microsoft Visual C++ 14.0 or greater is required" error during installation
- **Pre-compiled binary wheels** - Installation now uses pre-built binaries for Windows, macOS, and Linux instead of requiring compilation
- **Maintained functionality** - Same API compatibility and voice activity detection performance as original webrtcvad

### 📊 Impact
This patch release resolves the most common Windows installation issue by switching to a dependency that provides pre-compiled binary wheels. Windows users can now install Witticism instantly without needing Visual Studio Build Tools, while maintaining identical functionality and performance.

## [0.6.1] - 2025-09-10

### 🪟 Windows Integration & UX Improvements

This patch release focuses on polishing the Windows experience with improved desktop integration and installation user experience.

### ✨ Improved

#### Windows Desktop Integration
- **Enhanced desktop shortcuts** - Added native Windows .ico file with multi-resolution support (16x16 to 256x256) for proper taskbar and desktop icons ([#85](https://github.com/Aaronontheweb/witticism/pull/85))
- **Fixed PyPI distribution** - Witticism.ico now included in PyPI packages, ensuring production installs display proper icons instead of Python defaults ([#86](https://github.com/Aaronontheweb/witticism/pull/86))
- **Improved Windows installer** - PowerShell installer now prioritizes .ico files with PNG fallback for maximum compatibility

#### Installation User Experience  
- **Progress indicators** - Added clear progress messages during PyTorch compatibility checks and package downloads ([#83](https://github.com/Aaronontheweb/witticism/pull/83))
- **Prevents installer confusion** - Users now see "Checking PyTorch compatibility (this may take a moment)..." instead of apparent freezing during 1-2 minute operations
- **Better upgrade messaging** - Clear timing expectations for upgrade operations that download large packages

#### Quality & Reliability
- **Comprehensive Windows testing** - Re-enabled full Windows installation test suite with beta version support ([#79](https://github.com/Aaronontheweb/witticism/pull/79))
- **Enhanced CI coverage** - Both automated PowerShell installer and manual installation methods now tested on every release
- **Installation reliability** - Early detection of Windows-specific installation issues through comprehensive CI testing

### 📊 Impact
This release completes the Windows platform experience by addressing the final polish items for desktop integration and installation UX. Windows users now get:
- Proper application icons in all contexts (desktop, taskbar, file explorer)
- Clear feedback during installation operations 
- Confidence in installation reliability through comprehensive automated testing

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

[Unreleased]: https://github.com/Aaronontheweb/witticism/compare/v0.7.3...HEAD
[0.7.3]: https://github.com/Aaronontheweb/witticism/compare/v0.7.1...v0.7.3
[0.7.2]: https://github.com/Aaronontheweb/witticism/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/Aaronontheweb/witticism/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/Aaronontheweb/witticism/compare/0.6.2...v0.7.0
[0.6.2]: https://github.com/Aaronontheweb/witticism/compare/0.6.1...0.6.2
[0.6.1]: https://github.com/Aaronontheweb/witticism/compare/0.6.0...0.6.1
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