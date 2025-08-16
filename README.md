# Witticism

[![CI](https://github.com/Aaronontheweb/witticism/actions/workflows/ci.yml/badge.svg)](https://github.com/Aaronontheweb/witticism/actions/workflows/ci.yml)
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
- **🔧 Auto-Updates** - Built-in upgrade command keeps you current

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
- ✅ Detect your GPU automatically (GTX 1080, RTX 3090, etc.)
- ✅ Install the right CUDA/PyTorch versions
- ✅ Set up auto-start on login
- ✅ Configure the system tray icon
- ✅ Handle all dependencies in an isolated environment

**No Python knowledge required. No CUDA configuration. It just works.**

### Manual Installation

If you prefer to install manually:

### Prerequisites

- **Linux** (Ubuntu, Fedora, Debian, etc.)
- **Python 3.10-3.12** (installed automatically if needed)
- **NVIDIA GPU** (optional but recommended for faster transcription)

1. Install system dependencies:
```bash
sudo apt-get install portaudio19-dev
```

2. Install with pipx:
```bash
pipx install witticism
```

3. For GPU support with CUDA (optional but recommended):
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
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

### Upgrading

To upgrade to the latest version:

```bash
pipx upgrade witticism
```

Or use the upgrade script (recommended):
```bash
curl -sSL https://raw.githubusercontent.com/Aaronontheweb/witticism/master/upgrade.sh | bash
```

**Note**: The upgrade script will automatically stop any running Witticism instance during the upgrade and restart it afterward if auto-start is configured.

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
