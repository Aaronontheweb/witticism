#!/bin/bash
# Install desktop entry and icon for Witticism

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Installing Witticism desktop entry...${NC}"

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Ensure we're in the project directory
cd "$PROJECT_DIR"

# Generate icons if they don't exist
if [ ! -f "assets/witticism.png" ]; then
    echo -e "${YELLOW}Generating icons...${NC}"
    python3 scripts/generate_icon.py || {
        echo -e "${RED}Failed to generate icons. Make sure PyQt5 is installed.${NC}"
        exit 1
    }
fi

# Install icons
echo -e "${GREEN}Installing icons...${NC}"
for size in 16 24 32 48 64 128 256 512; do
    icon_dir="$HOME/.local/share/icons/hicolor/${size}x${size}/apps"
    mkdir -p "$icon_dir"
    if [ -f "assets/witticism_${size}x${size}.png" ]; then
        cp "assets/witticism_${size}x${size}.png" "$icon_dir/witticism.png"
        echo "  Installed ${size}x${size} icon"
    fi
done

# Install main icon for legacy applications
if [ -f "assets/witticism.png" ]; then
    mkdir -p "$HOME/.local/share/pixmaps"
    cp "assets/witticism.png" "$HOME/.local/share/pixmaps/witticism.png"
    echo "  Installed pixmaps icon"
fi

# Install desktop entry
echo -e "${GREEN}Installing desktop entry...${NC}"
desktop_dir="$HOME/.local/share/applications"
mkdir -p "$desktop_dir"

# Check if witticism is in PATH
if command -v witticism &> /dev/null; then
    WITTICISM_EXEC="witticism"
    echo "  Found witticism in PATH"
elif [ -f "$HOME/.local/bin/witticism" ]; then
    WITTICISM_EXEC="$HOME/.local/bin/witticism"
    echo "  Found witticism in ~/.local/bin"
else
    # Try to find pipx installation
    PIPX_BIN="$HOME/.local/pipx/venvs/witticism/bin/witticism"
    if [ -f "$PIPX_BIN" ]; then
        WITTICISM_EXEC="$PIPX_BIN"
        echo "  Found witticism in pipx"
    else
        echo -e "${YELLOW}Warning: Could not find witticism executable.${NC}"
        echo -e "${YELLOW}Using 'witticism' as exec path - make sure it's in your PATH.${NC}"
        WITTICISM_EXEC="witticism"
    fi
fi

# Create desktop entry with correct exec path
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

# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$desktop_dir" 2>/dev/null || true
fi

# Update icon cache
if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo -e "${GREEN}Installation complete!${NC}"
echo -e "${GREEN}Witticism should now appear in your application launcher.${NC}"
echo ""
echo "If it doesn't appear immediately, you may need to:"
echo "  1. Log out and log back in"
echo "  2. Or restart your desktop environment"
echo "  3. Or run: killall gnome-shell (for GNOME)"