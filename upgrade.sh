#!/bin/bash
# Upgrade script for Witticism
# Handles version checking and smart upgrades

set -e

echo "🔄 Checking for Witticism updates..."

# Get current version if installed
if command -v witticism &> /dev/null; then
    CURRENT_VERSION=$(witticism --version 2>/dev/null || echo "unknown")
    echo "Current version: $CURRENT_VERSION"
else
    echo "Witticism not installed. Running installer..."
    curl -sSL https://raw.githubusercontent.com/Aaronontheweb/witticism/master/install.sh | bash
    exit 0
fi

# Get latest version from GitHub
LATEST_VERSION=$(curl -s https://api.github.com/repos/Aaronontheweb/witticism/releases/latest | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')

if [ -z "$LATEST_VERSION" ]; then
    echo "⚠️  Could not check latest version"
    echo "Proceeding with upgrade anyway..."
else
    echo "Latest version: $LATEST_VERSION"
    
    if [ "$CURRENT_VERSION" = "$LATEST_VERSION" ]; then
        echo "✅ Already up to date!"
        exit 0
    fi
fi

# Backup settings
if [ -f "$HOME/.config/witticism/config.yaml" ]; then
    echo "📦 Backing up settings..."
    cp "$HOME/.config/witticism/config.yaml" "$HOME/.config/witticism/config.yaml.backup"
fi

# Stop running instance
if pgrep -f witticism > /dev/null; then
    echo "🛑 Stopping Witticism..."
    pkill -f witticism || true
    sleep 2
fi

# Upgrade
echo "⬆️  Upgrading Witticism..."

# Detect GPU for correct PyTorch installation
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

# Upgrade with pipx
echo "📦 Downloading and installing updates..."
echo "⏳ This may take several minutes for large dependencies"
echo ""
pipx upgrade witticism --verbose --pip-args="--index-url $INDEX_URL --extra-index-url https://pypi.org/simple --verbose"

# Restore settings
if [ -f "$HOME/.config/witticism/config.yaml.backup" ]; then
    echo "📥 Restoring settings..."
    cp "$HOME/.config/witticism/config.yaml.backup" "$HOME/.config/witticism/config.yaml"
fi

# Restart if it was running
if [ -f "$HOME/.config/autostart/witticism.desktop" ]; then
    echo "🚀 Starting Witticism..."
    nohup witticism > /dev/null 2>&1 &
    sleep 2
fi

echo "✅ Upgrade complete!"
echo ""
echo "New version: $(witticism --version 2>/dev/null || echo 'unknown')"
echo ""
echo "Changes in this version:"
curl -s https://api.github.com/repos/Aaronontheweb/witticism/releases/latest | \
    grep '"body":' | sed -E 's/.*"body":"([^"]+)".*/\1/' | sed 's/\\n/\n/g' | head -10