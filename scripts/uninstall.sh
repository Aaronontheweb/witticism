#!/bin/bash
# Uninstaller for Witticism (Linux)
# Reverses everything install.sh lays down on Linux:
#   - running process
#   - pipx / pip user installation + ~/.local/bin/witticism stub
#   - desktop entry, autostart entry, hicolor + pixmap icons
#   - optional GNOME Shell extension (via witticism-platform)
#   - config/data directories (only with --purge; kept by default so
#     settings survive a reinstall)

set -e

# ---- argument parsing -------------------------------------------------------
PURGE=false
HELP=false

for arg in "$@"; do
    case "$arg" in
        --purge)      PURGE=true ;;
        --help|-h)    HELP=true ;;
        *)            echo "Unknown option: $arg (use --help for usage)"; exit 1 ;;
    esac
done

if [ "$HELP" = true ]; then
    cat <<'EOF'
Witticism Linux Uninstaller

Usage:
  ./uninstall.sh            # Uninstall Witticism (keeps your config/settings)
  ./uninstall.sh --purge    # Uninstall AND delete config & data directories
  ./uninstall.sh --help     # Show this help

This script reverses everything install.sh creates:
  - stops any running witticism process
  - removes the pipx (and pip-user) installation + ~/.local/bin/witticism stub
  - removes the desktop launcher entry and autostart entry
  - removes the hicolor + pixmap icons
  - removes the optional GNOME Shell extension if present
  - with --purge, also deletes ~/.config/witticism and ~/.local/share/witticism
EOF
    exit 0
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

echo -e "${GREEN}🗑️  Uninstalling Witticism...${NC}"

# ---- 0. stop any running process -------------------------------------------
if pgrep -x witticism &> /dev/null; then
    echo "   Stopping running Witticism process..."
    pkill -x witticism || true
    sleep 1
    echo -e "${GREEN}   [OK] Stopped Witticism${NC}"
else
    echo "   No running Witticism process"
fi

# ---- 1. optional GNOME Shell extension --------------------------------------
# This MUST run before the pipx removal so `witticism-platform` is still on
# PATH; it both removes the extension directory AND cleans the GNOME
# enabled-extensions gsettings entry.
if [ -d "$HOME/.local/share/gnome-shell/extensions/witticism@stannardlabs.com" ]; then
    echo "   Removing optional GNOME Shell extension..."
    if command -v witticism-platform &> /dev/null; then
        witticism-platform uninstall-gnome-extension 2>/dev/null || true
    fi
    # Direct fallback if the platform CLI is gone but the directory remains.
    if [ -d "$HOME/.local/share/gnome-shell/extensions/witticism@stannardlabs.com" ]; then
        rm -rf "$HOME/.local/share/gnome-shell/extensions/witticism@stannardlabs.com"
    fi
    echo -e "${GREEN}   [OK] Removed GNOME extension${NC}"
else
    echo "   No GNOME Shell extension found"
fi

# ---- 2. pipx installation ---------------------------------------------------
if command -v pipx &> /dev/null && pipx list 2>/dev/null | grep -q "witticism"; then
    echo "   Removing pipx installation..."
    pipx uninstall witticism || true
    if pipx list 2>/dev/null | grep -q "witticism"; then
        echo -e "${RED}   [FAIL] pipx still lists witticism${NC}"
    else
        echo -e "${GREEN}   [OK] Removed pipx installation${NC}"
    fi
else
    echo "   No pipx installation found"
fi

# ---- 3. pip user installation (fallback) ------------------------------------
if pip list --user 2>/dev/null | grep -qi "^witticism"; then
    echo "   Removing pip user installation..."
    pip uninstall witticism -y || true
    echo -e "${GREEN}   [OK] Removed pip user installation${NC}"
else
    echo "   No pip user installation found"
fi

# ---- 4. remove ~/.local/bin/witticism stub ----------------------------------
if [ -f "$HOME/.local/bin/witticism" ]; then
    rm -f "$HOME/.local/bin/witticism"
    echo -e "${GREEN}   [OK] Removed ~/.local/bin/witticism${NC}"
fi

# ---- 5. desktop entry + autostart -------------------------------------------
desktop_file="$HOME/.local/share/applications/witticism.desktop"
if [ -f "$desktop_file" ]; then
    rm -f "$desktop_file"
    echo -e "${GREEN}   [OK] Removed desktop launcher entry${NC}"
else
    echo "   No desktop launcher entry found"
fi

autostart_file="$HOME/.config/autostart/witticism.desktop"
if [ -f "$autostart_file" ]; then
    rm -f "$autostart_file"
    echo -e "${GREEN}   [OK] Removed autostart entry${NC}"
else
    echo "   No autostart entry found"
fi

# ---- 6. icons + refresh caches ----------------------------------------------
echo "   Removing icons..."
for size in 16 24 32 48 64 128 256 512; do
    icon="$HOME/.local/share/icons/hicolor/${size}x${size}/apps/witticism.png"
    if [ -f "$icon" ]; then
        rm -f "$icon"
        echo -e "${GREEN}      Removed ${size}x${size} icon${NC}"
    fi
done

pixmap="$HOME/.local/share/pixmaps/witticism.png"
if [ -f "$pixmap" ]; then
    rm -f "$pixmap"
    echo -e "${GREEN}      Removed pixmap icon${NC}"
fi

if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

# ---- 7. systemd NVIDIA sleep hook (best-effort, requires sudo) ---------------
# install.sh only lays this down on GPU machines; CI runners won't have it.
# The sleep hook has a Witticism-unique name so removal is safe. The NVIDIA
# power-management config (/etc/modprobe.d/nvidia-power-management.conf) and the
# standard nvidia-suspend/resume services are intentionally NOT reverted here:
# that config may predate Witticism (install.sh backs it up rather than owning
# it) and disabling those services could break a user who depends on them. The
# config is inert once Witticism is gone. We only remove the hook we own.
sleep_hook="/usr/lib/systemd/system-sleep/99-nvidia-witticism"
if [ -f "$sleep_hook" ]; then
    echo "   Removing NVIDIA sleep hook (may prompt for sudo)..."
    if command -v sudo &> /dev/null && sudo rm -f "$sleep_hook" 2>/dev/null; then
        echo -e "${GREEN}   [OK] Removed NVIDIA sleep hook${NC}"
    else
        echo -e "${YELLOW}   Could not remove NVIDIA sleep hook (sudo required)."
        echo -e "   Remove manually: sudo rm -f $sleep_hook${NC}"
    fi
else
    echo "   No NVIDIA sleep hook found"
fi
echo -e "${GREEN}   [OK] NVIDIA power-management config left in place (harmless; see --help)${NC}"

# ---- 8. config / data (only with --purge) -----------------------------------
if [ "$PURGE" = true ]; then
    for dir in "$HOME/.config/witticism" "$HOME/.local/share/witticism"; do
        if [ -d "$dir" ]; then
            rm -rf "$dir"
            echo -e "${GREEN}   [OK] Deleted $dir${NC}"
        fi
    done
else
    echo -e "${YELLOW}   Keeping config & data (use --purge to remove them)${NC}"
fi

echo ""
echo -e "${GREEN}✅ Witticism uninstalled.${NC}"
echo "   Config was kept at ~/.config/witticism (use --purge to delete)."
