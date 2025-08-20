#!/bin/bash
# One-command installer for Witticism
# Handles everything: GPU detection, dependencies, auto-start

set -e

echo "🎙️ Installing Witticism..."

# Install system dependencies for pyaudio
if command -v apt-get &> /dev/null; then
    # Debian/Ubuntu
    echo "📦 Installing system dependencies..."
    if ! dpkg -l | grep -q portaudio19-dev; then
        echo "Installing PortAudio development headers (required for voice input)..."
        sudo apt-get update && sudo apt-get install -y portaudio19-dev
    fi
elif command -v dnf &> /dev/null; then
    # Fedora/RHEL
    echo "📦 Installing system dependencies..."
    if ! rpm -qa | grep -q portaudio-devel; then
        echo "Installing PortAudio development headers (required for voice input)..."
        sudo dnf install -y portaudio-devel
    fi
elif command -v pacman &> /dev/null; then
    # Arch Linux
    echo "📦 Installing system dependencies..."
    if ! pacman -Q portaudio &> /dev/null; then
        echo "Installing PortAudio (required for voice input)..."
        sudo pacman -S --noconfirm portaudio
    fi
fi

# 1. Install pipx if not present
if ! command -v pipx &> /dev/null; then
    echo "📦 Installing pipx package manager..."
    python3 -m pip install --user pipx
    python3 -m pipx ensurepath
    export PATH="$HOME/.local/bin:$PATH"
    echo "✓ pipx installed"
else
    echo "✓ pipx already installed"
fi

# 2. Detect GPU and install with right CUDA
if nvidia-smi &> /dev/null; then
    CUDA_VERSION=$(nvidia-smi | grep "CUDA Version" | sed 's/.*CUDA Version: \([0-9]*\.[0-9]*\).*/\1/')
    echo "🎮 GPU detected with CUDA $CUDA_VERSION"
    
    if [[ $(echo "$CUDA_VERSION >= 12.1" | bc) -eq 1 ]]; then
        INDEX_URL="https://download.pytorch.org/whl/cu121"
    elif [[ $(echo "$CUDA_VERSION >= 11.8" | bc) -eq 1 ]]; then
        INDEX_URL="https://download.pytorch.org/whl/cu118"
    else
        INDEX_URL="https://download.pytorch.org/whl/cpu"
    fi
else
    echo "💻 No GPU detected - using CPU version"
    INDEX_URL="https://download.pytorch.org/whl/cpu"
fi

# 3. Install Witticism
echo "📦 Installing Witticism with dependencies..."
echo "⏳ This may take several minutes as PyTorch and WhisperX are large packages"
echo ""
pipx install witticism --verbose --pip-args="--index-url $INDEX_URL --extra-index-url https://pypi.org/simple --verbose"

# 4. Generate and install icons
echo "🎨 Setting up application icons..."

# Generate icons inline using Python
python3 << 'EOF' 2>/dev/null || echo "⚠️  Could not generate custom icons"
import sys
import os
from pathlib import Path

try:
    from PyQt5.QtGui import QIcon, QPixmap, QPainter, QFont, QColor
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication
    
    # Create QApplication (required for Qt)
    app = QApplication(sys.argv)
    
    # Icon sizes to generate
    sizes = [16, 24, 32, 48, 64, 128, 256, 512]
    
    for size in sizes:
        # Create pixmap
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Calculate dimensions
        margin = size // 8
        circle_size = size - (2 * margin)
        
        # Draw green circle background
        painter.setBrush(QColor(76, 175, 80))  # Green
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(margin, margin, circle_size, circle_size)
        
        # Draw "W" text
        painter.setPen(Qt.white)
        font_size = size // 3
        font = QFont("Arial", font_size, QFont.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "W")
        
        painter.end()
        
        # Save icon
        icon_dir = Path.home() / ".local/share/icons/hicolor" / f"{size}x{size}" / "apps"
        icon_dir.mkdir(parents=True, exist_ok=True)
        icon_path = icon_dir / "witticism.png"
        pixmap.save(str(icon_path), "PNG")
        print(f"  Generated {size}x{size} icon")
    
    # Also save to pixmaps for legacy support
    pixmaps_dir = Path.home() / ".local/share/pixmaps"
    pixmaps_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate main 512x512 icon for pixmaps
    pixmap = QPixmap(512, 512)
    pixmap.fill(Qt.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    
    margin = 512 // 8
    circle_size = 512 - (2 * margin)
    
    painter.setBrush(QColor(76, 175, 80))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(margin, margin, circle_size, circle_size)
    
    painter.setPen(Qt.white)
    font = QFont("Arial", 512 // 3, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "W")
    
    painter.end()
    
    pixmap.save(str(pixmaps_dir / "witticism.png"), "PNG")
    print("  Generated main icon")
    
except ImportError:
    print("PyQt5 not available, skipping icon generation")
    sys.exit(1)
EOF

# Update icon cache if available
if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

# 5. Set up desktop entry for launcher
echo "🚀 Creating desktop launcher entry..."
desktop_dir="$HOME/.local/share/applications"
mkdir -p "$desktop_dir"

# Find witticism executable
if command -v witticism &> /dev/null; then
    WITTICISM_EXEC="witticism"
elif [ -f "$HOME/.local/bin/witticism" ]; then
    WITTICISM_EXEC="$HOME/.local/bin/witticism"
else
    WITTICISM_EXEC="witticism"
fi

# Create desktop entry for application launcher
cat > "$desktop_dir/witticism.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Witticism
Comment=WhisperX-powered voice transcription tool
Exec=${WITTICISM_EXEC}
Icon=witticism
Terminal=false
Categories=Utility;AudioVideo;Accessibility;
Keywords=voice;transcription;speech;whisper;dictation;
StartupNotify=false
EOF

# Update desktop database if available
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$desktop_dir" 2>/dev/null || true
fi

# Update icon cache if available
if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

# 6. Set up auto-start
echo "⚙️  Setting up auto-start..."
mkdir -p ~/.config/autostart

cat > ~/.config/autostart/witticism.desktop << EOF
[Desktop Entry]
Type=Application
Name=Witticism
Comment=Voice transcription that types anywhere
Exec=${WITTICISM_EXEC}
Icon=witticism
StartupNotify=false
Terminal=false
X-GNOME-Autostart-enabled=true
EOF

echo "✅ Installation complete!"
echo ""
echo "Witticism will:"
echo "  • Appear in your application launcher"
echo "  • Start automatically when you log in"
echo "  • Run in your system tray"
echo "  • Use GPU acceleration (if available)"
echo ""
echo "To start now: witticism"
echo "To start from launcher: Look for 'Witticism' in your apps menu"
echo "To disable auto-start: rm ~/.config/autostart/witticism.desktop"