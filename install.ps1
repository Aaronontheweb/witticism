# Windows PowerShell installer for Witticism
# Handles dependencies, GPU detection, and auto-start setup

param(
    [switch]$SkipAutoStart,
    [switch]$CPUOnly,
    [switch]$Help
)

if ($Help) {
    Write-Host @"
Witticism Windows Installer

Usage:
    .\install.ps1                  # Full installation with GPU detection
    .\install.ps1 -CPUOnly         # Force CPU-only installation
    .\install.ps1 -SkipAutoStart   # Don't set up auto-start
    .\install.ps1 -Help           # Show this help

This script will:
- Install Python dependencies (pipx, witticism)
- Detect and configure GPU support (CUDA/PyTorch)
- Set up auto-start on login
- Create desktop shortcuts
"@
    exit 0
}

Write-Host "🎙️ Installing Witticism on Windows..." -ForegroundColor Green

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    Write-Host "❌ Please don't run this installer as Administrator!" -ForegroundColor Red
    Write-Host "   Run it as your regular user account." -ForegroundColor Yellow
    Write-Host "   The script will handle any necessary permissions." -ForegroundColor Yellow
    exit 1
}

# Check Python version
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Found: $pythonVersion" -ForegroundColor Green
    
    # Extract version number and check if it's >= 3.9
    if ($pythonVersion -match "Python (\d+)\.(\d+)") {
        $major = [int]$matches[1]
        $minor = [int]$matches[2]
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 9)) {
            Write-Host "❌ Python 3.9+ required, found Python $major.$minor" -ForegroundColor Red
            Write-Host "   Please install Python 3.9 or later from https://python.org" -ForegroundColor Yellow
            exit 1
        }
    }
} catch {
    Write-Host "❌ Python not found!" -ForegroundColor Red
    Write-Host "   Please install Python 3.9+ from https://python.org" -ForegroundColor Yellow
    Write-Host "   Make sure to check 'Add Python to PATH' during installation" -ForegroundColor Yellow
    exit 1
}

# Install pipx if not present
try {
    $pipxVersion = python -m pipx --version 2>&1
    Write-Host "✓ pipx already installed: $pipxVersion" -ForegroundColor Green
} catch {
    Write-Host "📦 Installing pipx package manager..." -ForegroundColor Blue
    python -m pip install --user pipx
    python -m pipx ensurepath
    
    # Add pipx to current session PATH
    $userScripts = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::UserProfile) + "\AppData\Local\Packages\PythonSoftwareFoundation.Python.*\LocalCache\local-packages\Python*\Scripts"
    $env:PATH += ";$userScripts"
    
    Write-Host "✓ pipx installed" -ForegroundColor Green
}

# GPU Detection and PyTorch index selection
$indexUrl = ""
$gpuInfo = ""

if (-not $CPUOnly) {
    Write-Host "🎮 Detecting GPU..." -ForegroundColor Blue
    
    try {
        $nvidiaInfo = nvidia-smi --query-gpu=name,driver_version,cuda_version --format=csv,noheader,nounits 2>$null
        if ($LASTEXITCODE -eq 0) {
            $gpuInfo = $nvidiaInfo | Select-Object -First 1
            Write-Host "✓ NVIDIA GPU detected: $gpuInfo" -ForegroundColor Green
            
            # Extract CUDA version
            $cudaMatch = $nvidiaInfo | Select-String "(\d+\.\d+)"
            if ($cudaMatch) {
                $cudaVersion = [float]$cudaMatch.Matches[0].Groups[1].Value
                if ($cudaVersion -ge 12.1) {
                    $indexUrl = "https://download.pytorch.org/whl/cu121"
                    Write-Host "✓ Using CUDA 12.1+ PyTorch packages" -ForegroundColor Green
                } elseif ($cudaVersion -ge 11.8) {
                    $indexUrl = "https://download.pytorch.org/whl/cu118"
                    Write-Host "✓ Using CUDA 11.8+ PyTorch packages" -ForegroundColor Green
                } else {
                    Write-Host "⚠️ CUDA version $cudaVersion detected - using CPU-only mode" -ForegroundColor Yellow
                    Write-Host "   GPU acceleration requires CUDA 11.8+" -ForegroundColor Yellow
                }
            }
        } else {
            Write-Host "ℹ️ No NVIDIA GPU detected - using CPU-only mode" -ForegroundColor Cyan
        }
    } catch {
        Write-Host "ℹ️ nvidia-smi not available - using CPU-only mode" -ForegroundColor Cyan
    }
} else {
    Write-Host "ℹ️ CPU-only mode requested" -ForegroundColor Cyan
}

# Install witticism with appropriate PyTorch version
Write-Host "📦 Installing Witticism..." -ForegroundColor Blue

$pipArgs = @()
if ($indexUrl) {
    $pipArgs += "--pip-args=--index-url $indexUrl --extra-index-url https://pypi.org/simple"
    Write-Host "   Using GPU-optimized packages..." -ForegroundColor Blue
} else {
    Write-Host "   Using CPU-only packages..." -ForegroundColor Blue
}

try {
    if ($pipArgs.Count -gt 0) {
        python -m pipx install witticism $pipArgs
    } else {
        python -m pipx install witticism
    }
    Write-Host "✓ Witticism installed successfully" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed to install Witticism" -ForegroundColor Red
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Set up auto-start (unless skipped)
if (-not $SkipAutoStart) {
    Write-Host "🚀 Setting up auto-start..." -ForegroundColor Blue
    
    try {
        $startupFolder = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Startup)
        $witticismPath = (python -m pipx list | Select-String "witticism").Line.Split()[0]
        
        # Create batch file for startup
        $batchContent = @"
@echo off
cd /d "%USERPROFILE%"
"$witticismPath" >nul 2>&1
"@
        $batchPath = Join-Path $startupFolder "witticism.bat"
        Set-Content -Path $batchPath -Value $batchContent
        
        Write-Host "✓ Auto-start configured" -ForegroundColor Green
        Write-Host "   Witticism will start automatically on login" -ForegroundColor Green
    } catch {
        Write-Host "⚠️ Could not set up auto-start: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "   You can manually add Witticism to your startup programs" -ForegroundColor Yellow
    }
}

# Create desktop shortcut
Write-Host "🖥️ Creating desktop shortcut..." -ForegroundColor Blue
try {
    $desktop = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
    $shortcutPath = Join-Path $desktop "Witticism.lnk"
    
    $WScriptShell = New-Object -ComObject WScript.Shell
    $shortcut = $WScriptShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "python"
    $shortcut.Arguments = "-m pipx run witticism"
    $shortcut.Description = "Witticism - Voice Transcription Tool"
    $shortcut.WorkingDirectory = $env:USERPROFILE
    $shortcut.Save()
    
    Write-Host "✓ Desktop shortcut created" -ForegroundColor Green
} catch {
    Write-Host "⚠️ Could not create desktop shortcut: $($_.Exception.Message)" -ForegroundColor Yellow
}

# Installation complete
Write-Host ""
Write-Host "🎉 Installation Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Witticism is now installed and ready to use:" -ForegroundColor White
Write-Host "• Double-click the desktop shortcut to launch" -ForegroundColor White
Write-Host "• Or run 'witticism' from any command prompt" -ForegroundColor White
Write-Host "• Look for the green 'W' icon in your system tray" -ForegroundColor White
Write-Host "• Hold F9 to record, release to transcribe" -ForegroundColor White

if ($gpuInfo) {
    Write-Host ""
    Write-Host "GPU Configuration:" -ForegroundColor Cyan
    Write-Host "• GPU: $gpuInfo" -ForegroundColor White
    Write-Host "• CUDA acceleration: Enabled" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Configuration:" -ForegroundColor Cyan
    Write-Host "• Mode: CPU-only (slower but works everywhere)" -ForegroundColor White
    Write-Host "• Tip: Install NVIDIA drivers + CUDA for faster transcription" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Enjoy fast, accurate voice transcription! 🎙️✨" -ForegroundColor Green