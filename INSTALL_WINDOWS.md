# Windows Installation Guide

## One-Line Installation (Recommended)

Open PowerShell and run:

```powershell
irm https://raw.githubusercontent.com/Aaronontheweb/witticism/windows-support/install.ps1 | iex
```

**That's it!** The script will:

- ✅ **Automatically install Python 3.12** (compatible version) if needed
- ✅ **Handle all dependencies** including WhisperX, PyTorch, PyQt5, PyAudio
- ✅ **Work around Python 3.13 issues** by using Python 3.12
- ✅ **Set up auto-start** on Windows login
- ✅ **Create desktop shortcut**
- ✅ **Test the installation**

No manual Python version management required!

## What The Script Does

### Smart Python Management
- Detects if Python 3.12 is already installed
- If not found, automatically downloads and installs Python 3.12.10
- Uses Python 3.12 specifically to avoid WhisperX compatibility issues
- Handles multiple Python versions gracefully using `py.exe` launcher

### Dependency Installation
- Forces CPU-only PyTorch for maximum compatibility
- Installs WhisperX and all required dependencies
- Falls back to direct pip if pipx fails
- Provides detailed error messages and troubleshooting

### Windows Integration
- Creates desktop shortcut for easy launching
- Sets up silent auto-start via startup folder
- Uses VBS script to launch without console window
- Integrates with Windows system tray

## Manual Installation

If you prefer to install manually:

```powershell
# 1. Install Python 3.12 from python.org
# 2. Install pipx
python -m pip install --user pipx

# 3. Install Witticism with CPU-optimized PyTorch
python -m pipx install witticism --pip-args="--index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple"

# 4. Run Witticism
python -m pipx run witticism
```

## Advanced Options

```powershell
# CPU-only installation (skip GPU detection)
irm https://raw.githubusercontent.com/Aaronontheweb/witticism/windows-support/install.ps1 | iex -CPUOnly

# Skip auto-start setup
irm https://raw.githubusercontent.com/Aaronontheweb/witticism/windows-support/install.ps1 | iex -SkipAutoStart

# Force reinstallation
irm https://raw.githubusercontent.com/Aaronontheweb/witticism/windows-support/install.ps1 | iex -ForceReinstall
```

## Usage

After installation:

1. **Launch**: Double-click desktop shortcut or run from command line
2. **Record**: Hold **F9** key to record speech
3. **Transcribe**: Release **F9** to transcribe and type text
4. **System Tray**: Look for Witticism icon in system tray
5. **Auto-start**: Witticism starts automatically on Windows login

## Troubleshooting

### PowerShell Execution Policy
If you get an execution policy error:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Python 3.13 Issues
The installer automatically uses Python 3.12 to avoid WhisperX compatibility issues with Python 3.13. No manual version management needed.

### Antivirus Blocking
Some antivirus software may block the installation. Try:
- Temporarily disable antivirus during installation
- Add Python and pip to antivirus exclusions
- Run PowerShell as regular user (not Administrator)

### Manual Cleanup
To uninstall:

```powershell
# Remove auto-start files
Remove-Item "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\WitticismAutoStart.*"

# Remove desktop shortcut  
Remove-Item "$env:USERPROFILE\Desktop\Witticism.lnk"

# Uninstall with pipx
python -m pipx uninstall witticism
```

## Why This Approach?

Unlike complex Windows installers, this PowerShell script:

- **Just Works**: Handles all the complexity automatically
- **Stays Updated**: Always installs latest version from source
- **No Bloat**: Only installs what's needed
- **Easy Maintenance**: Simple script vs complex installer build process
- **User Control**: Users can see exactly what's being installed
- **Same Pattern**: Matches the bash installer experience on Linux

Perfect for both developers and end users! 🎙️✨