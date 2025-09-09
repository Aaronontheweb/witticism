#!/bin/bash
# One-command installer for Witticism
# Handles everything: GPU detection, dependencies, auto-start

set -e

# Parse command line arguments
VERSION=""
FORCE_REINSTALL=false
HELP=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --version)
            VERSION="$2"
            shift 2
            ;;
        --force-reinstall)
            FORCE_REINSTALL=true
            shift
            ;;
        --help|-h)
            HELP=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

if [ "$HELP" = true ]; then
    echo "Witticism Linux/macOS Installer"
    echo ""
    echo "Usage:"
    echo "  ./install.sh                     # Install latest stable version"
    echo "  ./install.sh --version 0.6.0b1   # Install specific version"  
    echo "  ./install.sh --force-reinstall   # Force reinstall even if already installed"
    echo "  ./install.sh --help              # Show this help"
    echo ""
    echo "This script automatically:"
    echo "- Installs system dependencies (asks for sudo only if needed)"
    echo "- Sets up isolated Python environment with pipx"
    echo "- Detects GPU and installs appropriate PyTorch version"
    echo "- Sets up desktop integration and auto-start"
    exit 0
fi

echo "🎙️ Installing Witticism..."

# Check if running as root/sudo (we don't want that)
if [ "$EUID" -eq 0 ]; then 
   echo "❌ Please don't run this installer as root/sudo!"
   echo "   The script will ask for sudo when needed for system packages."
   echo "   Witticism should be installed as your regular user."
   exit 1
fi

# Install system dependencies for pyaudio
NEEDS_DEPS=false
if command -v apt-get &> /dev/null; then
    # Debian/Ubuntu
    MISSING_PACKAGES=()
    if ! dpkg -l | grep -q portaudio19-dev; then
        MISSING_PACKAGES+=("portaudio19-dev")
    fi
    if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
        NEEDS_DEPS=true
        DEPS_CMD="apt-get update && apt-get install -y ${MISSING_PACKAGES[*]}"
        PACKAGE_LIST="${MISSING_PACKAGES[*]}"
    fi
elif command -v dnf &> /dev/null; then
    # Fedora/RHEL
    MISSING_PACKAGES=()
    if ! rpm -qa | grep -q portaudio-devel; then
        MISSING_PACKAGES+=("portaudio-devel")
    fi
    if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
        NEEDS_DEPS=true
        DEPS_CMD="dnf install -y ${MISSING_PACKAGES[*]}"
        PACKAGE_LIST="${MISSING_PACKAGES[*]}"
    fi
elif command -v pacman &> /dev/null; then
    # Arch Linux
    MISSING_PACKAGES=()
    if ! pacman -Q portaudio &> /dev/null; then
        MISSING_PACKAGES+=("portaudio")
    fi
    if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
        NEEDS_DEPS=true
        DEPS_CMD="pacman -S --noconfirm ${MISSING_PACKAGES[*]}"
        PACKAGE_LIST="${MISSING_PACKAGES[*]}"
    fi
fi

if [ "$NEEDS_DEPS" = true ]; then
    echo "📦 System dependencies required: $PACKAGE_LIST"
    echo "   This provides audio input capabilities for voice recording."
    
    # Check if we can use sudo
    if command -v sudo &> /dev/null; then
        echo "   Installing with sudo (you may be prompted for password)..."
        sudo sh -c "$DEPS_CMD" || {
            echo "❌ Failed to install $PACKAGE_LIST"
            echo "   Please install them manually with:"
            echo "   sudo $DEPS_CMD"
            echo ""
            echo "   Then re-run this installer."
            exit 1
        }
        echo "✓ $PACKAGE_LIST installed"
    else
        echo "❌ sudo is required to install system dependencies"
        echo "   Please install $PACKAGE_LIST manually with:"
        echo "   $DEPS_CMD"
        echo ""
        echo "   Then re-run this installer."
        exit 1
    fi
else
    echo "✓ System dependencies already installed"
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

# Function to clean up existing witticism installation
cleanup_existing_witticism() {
    echo "🧹 Checking for existing Witticism installation..."
    
    if pipx list | grep -q "witticism"; then
        echo "   Found pipx installation, removing..."
        pipx uninstall witticism || true
        echo "   ✓ Removed pipx installation"
    fi
    
    if pip list --user | grep -q "witticism"; then
        echo "   Found pip user installation, removing..."  
        pip uninstall witticism -y || true
        echo "   ✓ Removed pip user installation"
    fi
    
    echo "   ✓ Cleanup complete"
}

# Clean up existing installation if force reinstall requested
if [ "$FORCE_REINSTALL" = true ]; then
    cleanup_existing_witticism
fi

# 2. Detect GPU and install with right CUDA
if [ "$WITTICISM_CPU_ONLY" = "1" ]; then
    echo "💻 CPU-only mode forced via environment variable"
    INDEX_URL="https://download.pytorch.org/whl/cpu"
elif nvidia-smi &> /dev/null; then
    CUDA_VERSION=$(nvidia-smi | grep "CUDA Version" | sed 's/.*CUDA Version: \([0-9]*\.[0-9]*\).*/\1/')
    echo "🎮 GPU detected with CUDA $CUDA_VERSION"
    
    if [[ $(echo "$CUDA_VERSION >= 12.1" | bc) -eq 1 ]]; then
        INDEX_URL="https://download.pytorch.org/whl/cu121"
    elif [[ $(echo "$CUDA_VERSION >= 11.8" | bc) -eq 1 ]]; then
        INDEX_URL="https://download.pytorch.org/whl/cu118"
    else
        INDEX_URL="https://download.pytorch.org/whl/cpu"
    fi
    
    # Configure NVIDIA for suspend/resume compatibility (idempotent)
    echo "🔧 Checking NVIDIA suspend/resume configuration..."
    NVIDIA_CONFIG_FILE="/etc/modprobe.d/nvidia-power-management.conf"
    NEEDS_NVIDIA_CONFIG=false
    CONFIG_CHANGED=false
    
    # Check if configuration exists and is correct
    if [ -f "$NVIDIA_CONFIG_FILE" ]; then
        # Check if our specific options are already configured
        if grep -q "NVreg_PreserveVideoMemoryAllocations=1" "$NVIDIA_CONFIG_FILE" 2>/dev/null && \
           grep -q "NVreg_TemporaryFilePath=" "$NVIDIA_CONFIG_FILE" 2>/dev/null; then
            echo "✓ NVIDIA suspend/resume protection already configured"
        else
            echo "  Existing NVIDIA config found but missing suspend/resume options"
            NEEDS_NVIDIA_CONFIG=true
        fi
    else
        echo "  No NVIDIA suspend/resume configuration found"
        NEEDS_NVIDIA_CONFIG=true
    fi
    
    if [ "$NEEDS_NVIDIA_CONFIG" = true ]; then
        echo "  This prevents CUDA crashes after suspend/resume"
        echo "  Installing NVIDIA configuration (requires sudo)..."
        
        # Create or update the configuration file
        if command -v sudo &> /dev/null; then
            # First, backup existing file if present
            if [ -f "$NVIDIA_CONFIG_FILE" ]; then
                sudo cp "$NVIDIA_CONFIG_FILE" "${NVIDIA_CONFIG_FILE}.bak.$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
            fi
            
            # Check if options already exist and update/append as needed
            TEMP_CONFIG=$(mktemp)
            
            # If file exists, start with existing content
            if [ -f "$NVIDIA_CONFIG_FILE" ]; then
                sudo cat "$NVIDIA_CONFIG_FILE" > "$TEMP_CONFIG"
            fi
            
            # Add our options if not present
            if ! grep -q "NVreg_PreserveVideoMemoryAllocations" "$TEMP_CONFIG" 2>/dev/null; then
                echo "options nvidia NVreg_PreserveVideoMemoryAllocations=1" >> "$TEMP_CONFIG"
                CONFIG_CHANGED=true
            fi
            
            if ! grep -q "NVreg_TemporaryFilePath" "$TEMP_CONFIG" 2>/dev/null; then
                echo "options nvidia NVreg_TemporaryFilePath=/tmp" >> "$TEMP_CONFIG"
                CONFIG_CHANGED=true
            fi
            
            # Only update if changes were made
            if [ "$CONFIG_CHANGED" = true ]; then
                sudo cp "$TEMP_CONFIG" "$NVIDIA_CONFIG_FILE" || {
                    echo "⚠️  Failed to configure NVIDIA suspend/resume protection"
                    echo "   You may experience CUDA errors after suspend/resume"
                    echo "   To fix manually, run:"
                    echo "   echo 'options nvidia NVreg_PreserveVideoMemoryAllocations=1' | sudo tee -a $NVIDIA_CONFIG_FILE"
                    echo "   echo 'options nvidia NVreg_TemporaryFilePath=/tmp' | sudo tee -a $NVIDIA_CONFIG_FILE"
                    echo "   sudo update-initramfs -u"
                }
                
                # Update initramfs if configuration was successful
                if [ -f "$NVIDIA_CONFIG_FILE" ] && grep -q "NVreg_PreserveVideoMemoryAllocations" "$NVIDIA_CONFIG_FILE"; then
                    echo "  Updating initramfs (this may take a moment)..."
                    sudo update-initramfs -u 2>/dev/null || {
                        echo "⚠️  Could not update initramfs - changes will apply after next reboot"
                    }
                    
                    # Enable NVIDIA suspend/resume services if they exist
                    if systemctl list-unit-files | grep -q nvidia-suspend.service 2>/dev/null; then
                        sudo systemctl enable nvidia-suspend.service 2>/dev/null || true
                        sudo systemctl enable nvidia-resume.service 2>/dev/null || true
                        echo "✓ NVIDIA suspend/resume services enabled"
                    fi
                    
                    echo "✓ NVIDIA suspend/resume protection configured"
                    
                    # Install systemd sleep hook for nvidia_uvm module reload
                    SLEEP_HOOK_FILE="/usr/lib/systemd/system-sleep/99-nvidia-witticism"
                    
                    if [ ! -f "$SLEEP_HOOK_FILE" ]; then
                        echo "  Installing systemd sleep hook for module reload..."
                        
                        # Create the sleep hook script
                        cat << 'SLEEPHOOK' | sudo tee "$SLEEP_HOOK_FILE" > /dev/null
#!/bin/bash
# Auto-reload nvidia_uvm module after suspend/resume to fix CUDA
# Created by Witticism installer

case "$1" in
    post)
        # After resume - reload nvidia_uvm module
        # Wait for system to stabilize
        sleep 2
        
        # Only reload if nvidia module is loaded
        if lsmod | grep -q "^nvidia " && lsmod | grep -q nvidia_uvm; then
            # Try to reload nvidia_uvm
            rmmod nvidia_uvm 2>/dev/null && modprobe nvidia_uvm 2>/dev/null
        fi
        ;;
esac
SLEEPHOOK
                    
                        # Make it executable
                        sudo chmod +x "$SLEEP_HOOK_FILE" 2>/dev/null || true
                        echo "✓ Systemd sleep hook installed"
                    else
                        echo "✓ Systemd sleep hook already installed"
                    fi
                    
                    echo "  Note: A reboot may be required for full protection"
                fi
            fi
            
            rm -f "$TEMP_CONFIG"
        else
            echo "⚠️  sudo not available - cannot configure NVIDIA suspend/resume protection"
            echo "   You may experience CUDA errors after suspend/resume"
        fi
    fi
else
    echo "💻 No GPU detected - using CPU version"
    INDEX_URL="https://download.pytorch.org/whl/cpu"
fi

# 3. Install/Upgrade Witticism (smart upgrade)
echo "📦 Checking current Witticism installation..."

# Check if witticism is installed and get version info
CURRENT_VERSION=""
PYTORCH_VERSION=""
NEEDS_REINSTALL=false

if pipx list | grep -q "package witticism"; then
    echo "✓ Witticism is already installed"
    
    # Get current version
    CURRENT_VERSION=$(pipx list | grep "package witticism" | sed 's/.*package witticism \([^,]*\).*/\1/')
    echo "  Current version: $CURRENT_VERSION"
    
    # Check PyTorch version in the pipx environment
    PYTORCH_CHECK=$(pipx run --spec witticism python -c "import torch; print(torch.__version__)" 2>/dev/null || echo "")
    if [ -n "$PYTORCH_CHECK" ]; then
        PYTORCH_VERSION="$PYTORCH_CHECK"
        echo "  Current PyTorch version: $PYTORCH_VERSION"
        
        # Check if PyTorch version is compatible (>=2.0.0,<2.4.0)
        if python3 -c "
import sys
version = '$PYTORCH_VERSION'.split('+')[0]  # Remove +cu118 suffix if present
major, minor = map(int, version.split('.')[:2])
if major < 2 or (major == 2 and minor >= 4):
    sys.exit(1)
"; then
            echo "  PyTorch version is compatible"
        else
            echo "  ⚠️  PyTorch version needs updating"
            NEEDS_REINSTALL=true
        fi
    else
        echo "  ⚠️  Could not check PyTorch version"
        NEEDS_REINSTALL=true
    fi
    
    # Check for latest witticism version
    LATEST_VERSION=$(python3 -c "
import urllib.request, json
try:
    response = urllib.request.urlopen('https://pypi.org/pypi/witticism/json')
    data = json.loads(response.read())
    print(data['info']['version'])
except:
    print('unknown')
" 2>/dev/null)
    
    if [ "$LATEST_VERSION" != "unknown" ] && [ "$LATEST_VERSION" != "$CURRENT_VERSION" ]; then
        echo "  📦 New version available: $LATEST_VERSION"
        echo "🔄 Upgrading Witticism (preserving compatible PyTorch)..."
        pipx upgrade witticism --pip-args="--index-url $INDEX_URL --extra-index-url https://pypi.org/simple"
    elif [ "$NEEDS_REINSTALL" = true ]; then
        echo "🔄 Reinstalling due to PyTorch compatibility..."
        echo "⏳ This may take several minutes as PyTorch needs to be updated"
        if [ -n "$VERSION" ]; then
            echo "   Installing specific version: $VERSION"
            pipx install --force "witticism==$VERSION" --verbose --pip-args="--index-url $INDEX_URL --extra-index-url https://pypi.org/simple --verbose"
        else
            pipx install --force witticism --verbose --pip-args="--index-url $INDEX_URL --extra-index-url https://pypi.org/simple --verbose"
        fi
    else
        echo "✓ Witticism is up to date with compatible PyTorch"
    fi
else
    echo "📦 Installing Witticism for the first time..."
    echo "⏳ This may take several minutes as PyTorch and WhisperX are large packages"
    echo ""
    if [ -n "$VERSION" ]; then
        echo "   Installing specific version: $VERSION"
        pipx install "witticism==$VERSION" --verbose --pip-args="--index-url $INDEX_URL --extra-index-url https://pypi.org/simple --verbose"
    else
        pipx install witticism --verbose --pip-args="--index-url $INDEX_URL --extra-index-url https://pypi.org/simple --verbose"
    fi
fi

# 4. Install icons from package
echo "🎨 Setting up application icons..."

# Find the witticism package location
WITTICISM_PKG=""
if [ -d "$HOME/.local/pipx/venvs/witticism" ]; then
    # Find the site-packages directory
    WITTICISM_PKG=$(find "$HOME/.local/pipx/venvs/witticism" -name "witticism" -type d | grep -E "site-packages/witticism$" | head -1)
fi

if [ -z "$WITTICISM_PKG" ]; then
    # Try to find it using Python
    WITTICISM_PKG=$(python3 -c "import witticism, os; print(os.path.dirname(witticism.__file__))" 2>/dev/null || true)
fi

if [ -n "$WITTICISM_PKG" ] && [ -d "$WITTICISM_PKG/assets" ]; then
    echo "  Found bundled icons in package"
    
    # Install icons at various sizes
    for size in 16 24 32 48 64 128 256 512; do
        icon_dir="$HOME/.local/share/icons/hicolor/${size}x${size}/apps"
        mkdir -p "$icon_dir"
        if [ -f "$WITTICISM_PKG/assets/witticism_${size}x${size}.png" ]; then
            cp "$WITTICISM_PKG/assets/witticism_${size}x${size}.png" "$icon_dir/witticism.png"
            echo "  Installed ${size}x${size} icon"
        fi
    done
    
    # Install main icon for legacy applications
    if [ -f "$WITTICISM_PKG/assets/witticism.png" ]; then
        mkdir -p "$HOME/.local/share/pixmaps"
        cp "$WITTICISM_PKG/assets/witticism.png" "$HOME/.local/share/pixmaps/witticism.png"
        echo "  Installed main icon"
    fi
else
    echo "⚠️  Could not find bundled icons in package"
fi

# Update icon cache if available
if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

# 5. Set up desktop entry for launcher (skip in CI)
if [ "$WITTICISM_NO_DESKTOP" != "1" ]; then
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

fi

# 6. Set up auto-start (skip in CI)
if [ "$WITTICISM_NO_DESKTOP" != "1" ]; then
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
fi

echo "✅ Installation complete!"
echo ""
if [ "$WITTICISM_NO_DESKTOP" != "1" ]; then
    echo "Witticism will:"
    echo "  • Appear in your application launcher"
    echo "  • Start automatically when you log in"
    echo "  • Run in your system tray"
    echo "  • Use GPU acceleration (if available)"
    echo ""
    echo "To start now: witticism"
    echo "To start from launcher: Look for 'Witticism' in your apps menu"
    echo "To disable auto-start: rm ~/.config/autostart/witticism.desktop"
else
    echo "Witticism installed successfully (desktop integration skipped for CI)."
    echo "To start: witticism"
fi