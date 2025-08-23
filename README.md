# Witticism

[![CI](https://github.com/Aaronontheweb/witticism/actions/workflows/ci.yml/badge.svg)](https://github.com/Aaronontheweb/witticism/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/witticism.svg)](https://pypi.org/project/witticism/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/downloads/)
[![GitHub release](https://img.shields.io/github/release/Aaronontheweb/witticism.svg)](https://github.com/Aaronontheweb/witticism/releases/latest)

🎙️ **One-command install. Zero configuration. Just works.**

WhisperX-powered voice transcription tool that types text directly at your cursor position. Hold F9 to record, release to transcribe.

## ✨ Features

- **🚀 One-Command Install** - Automatic GPU detection and configuration
- **🎮 True GPU Acceleration** - Full CUDA support, even for older GPUs (GTX 10xx series)
- **⚡ Instant Transcription** - Press F9, speak, release. Text appears at cursor
- **🔄 Continuous Dictation Mode** - Toggle on for hands-free transcription
- **🎯 System Tray Integration** - Runs quietly in background, always ready
- **📦 No Configuration** - Works out of the box with smart defaults
- **🔧 Easy Updates** - Re-run install script to upgrade to latest version

## Why Witticism?

Built to solve real GPU acceleration issues with whisper.cpp. WhisperX provides:
- Proper CUDA/GPU support for faster transcription (2-10x faster than CPU)
- Word-level timestamps and alignment for accuracy
- Better accuracy with less latency
- Native Python integration that actually works

## Installation

### 🚀 Quick Install (Recommended)

**Just run this one command:**

```bash
curl -sSL https://raw.githubusercontent.com/Aaronontheweb/witticism/master/install.sh | bash
```

**That's it!** The installer will:
- ✅ Install system dependencies automatically (asks for sudo only if needed)
- ✅ Detect your GPU automatically (GTX 1080, RTX 3090, etc.)
- ✅ Install the right CUDA/PyTorch versions
- ✅ Create desktop launcher with custom icon
- ✅ Set up auto-start on login
- ✅ Configure the system tray icon
- ✅ Handle all dependencies in an isolated environment

**No Python knowledge required. No CUDA configuration. It just works.**

Note: The installer will ask for your sudo password only if PortAudio needs to be installed. Witticism itself runs as your regular user.

### Manual Installation

If you prefer to install manually:

### Prerequisites

- **Linux** (Ubuntu, Fedora, Debian, etc.)
- **Python 3.10-3.12** (pipx will handle this)
- **NVIDIA GPU** (optional but recommended for faster transcription)

1. Install system dependencies:
```bash
# Debian/Ubuntu
sudo apt-get install portaudio19-dev

# Fedora/RHEL
sudo dnf install portaudio-devel

# Arch Linux
sudo pacman -S portaudio
```

2. Install pipx if needed:
```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```

3. Install Witticism:
```bash
# For CPU-only
pipx install witticism

# For GPU with CUDA 11.8+
pipx install witticism --pip-args="--index-url https://download.pytorch.org/whl/cu118 --extra-index-url https://pypi.org/simple"

# For GPU with CUDA 12.1+
pipx install witticism --pip-args="--index-url https://download.pytorch.org/whl/cu121 --extra-index-url https://pypi.org/simple"
```

4. Set up auto-start (optional):
```bash
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/witticism.desktop << EOF
[Desktop Entry]
Type=Application
Name=Witticism
Exec=$HOME/.local/bin/witticism
StartupNotify=false
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
```

### Desktop Integration

The quick installer automatically sets up desktop integration with launcher icon. If you installed manually, Witticism can still be launched from the terminal with the `witticism` command.

### Upgrading

To upgrade to the latest version, simply re-run the install script:

```bash
curl -sSL https://raw.githubusercontent.com/Aaronontheweb/witticism/master/install.sh | bash
```

The install script is idempotent and will automatically upgrade existing installations to the latest version with all dependencies.

## Usage

### Basic Operation

1. The app runs in your system tray (green "W" icon)
2. **Hold F9** to start recording
3. **Release F9** to stop and transcribe
4. Text appears instantly at your cursor position

**Or use Continuous Mode:**
- Toggle continuous dictation from the tray menu
- Speak naturally - transcription happens automatically
- Perfect for long-form writing

### System Tray Menu

- **Status**: Shows current state (Ready/Recording/Transcribing)
- **Model**: Choose transcription model
  - `tiny/tiny.en`: Fastest, less accurate
  - `base/base.en`: Good balance (default)
  - `small/medium/large-v3`: More accurate, slower
- **Audio Device**: Select input microphone
- **Quit**: Exit application

### Command Line Options

```bash
witticism --model base --log-level INFO
```

Options:
- `--model`: Choose model (tiny, base, small, medium, large-v3)
- `--log-level`: Set logging verbosity (DEBUG, INFO, WARNING, ERROR)
- `--reset-config`: Reset settings to defaults
- `--version`: Show version information

## Configuration

Config file location: `~/.config/witticism/config.json`

Key settings:
```json
{
  "model": {
    "size": "base",
    "device": "auto"
  },
  "hotkeys": {
    "push_to_talk": "f9"
  }
}
```

## Performance

With GTX 1080 GPU:
- **tiny model**: ~0.5s latency, 5-10x realtime
- **base model**: ~1-2s latency, 2-5x realtime  
- **large-v3**: ~3-5s latency, 1-2x realtime

CPU-only fallback available but slower.

## Troubleshooting

### No audio input
- Check microphone permissions
- Try selecting a different audio device from tray menu

### CUDA not detected
```bash
python -c "import torch; print(torch.cuda.is_available())"
```
Should return `True` if CUDA is available.

### Models not loading
First run downloads models (~150MB for base). Ensure stable internet connection.

### Debug logging
By default, witticism logs to `~/.local/share/witticism/debug.log` when debug level is enabled. 

To enable debug logging, either:
- Run with `--log-level DEBUG`
- Edit `~/.config/witticism/config.json` and set `"logging": {"level": "DEBUG", "file": "~/.local/share/witticism/debug.log"}`

Common issues visible in debug logs:
- "No active speech found in audio" - Check microphone connection/volume
- CUDA context errors - Restart after suspend/resume
- Model loading failures - Check GPU memory with `nvidia-smi`

## Development

### Project Structure
```
src/witticism/
├── core/           # Core functionality
│   ├── whisperx_engine.py
│   ├── audio_capture.py
│   ├── hotkey_manager.py
│   └── transcription_pipeline.py
├── ui/             # User interface
│   └── system_tray.py
├── utils/          # Utilities
│   ├── output_manager.py
│   ├── config_manager.py
│   └── logging_config.py
└── main.py         # Entry point
```

## Author

Created by [Aaron Stannard](https://aaronstannard.com/)

## License

Apache-2.0
