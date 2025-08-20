#!/bin/bash
# Uninstall desktop entry and icon for Witticism

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo -e "${GREEN}Uninstalling Witticism desktop entry...${NC}"

# Remove desktop entry
desktop_file="$HOME/.local/share/applications/witticism.desktop"
if [ -f "$desktop_file" ]; then
    rm "$desktop_file"
    echo "  Removed desktop entry"
fi

# Remove icons
echo -e "${GREEN}Removing icons...${NC}"
for size in 16 24 32 48 64 128 256 512; do
    icon_file="$HOME/.local/share/icons/hicolor/${size}x${size}/apps/witticism.png"
    if [ -f "$icon_file" ]; then
        rm "$icon_file"
        echo "  Removed ${size}x${size} icon"
    fi
done

# Remove pixmaps icon
pixmap_file="$HOME/.local/share/pixmaps/witticism.png"
if [ -f "$pixmap_file" ]; then
    rm "$pixmap_file"
    echo "  Removed pixmaps icon"
fi

# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
fi

# Update icon cache
if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo -e "${GREEN}Uninstallation complete!${NC}"