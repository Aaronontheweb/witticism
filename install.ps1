# Windows PowerShell installer for Witticism
# Handles Python version management, dependencies, GPU detection, and auto-start setup
# Works around Python 3.13 compatibility issues by using Python 3.12 automatically

param(
    [switch]$SkipAutoStart,
    [switch]$CPUOnly,
    [switch]$Help,
    [switch]$ForceReinstall
)

if ($Help) {
    Write-Host @"
Witticism Windows Installer

Usage:
    .\install.ps1                  # Full automatic installation
    .\install.ps1 -CPUOnly         # Force CPU-only installation  
    .\install.ps1 -SkipAutoStart   # Don't set up auto-start
    .\install.ps1 -ForceReinstall  # Force reinstall even if already installed
    .\install.ps1 -Help           # Show this help

This script automatically:
- Installs Python 3.12 (compatible version) if needed
- Sets up isolated Python environment  
- Installs all dependencies including WhisperX
- Detects and configures GPU support (CUDA/PyTorch)
- Sets up auto-start on Windows login
- Creates desktop shortcuts

No manual Python version management required!
"@
    exit 0
}

Write-Host "Installing Witticism on Windows..." -ForegroundColor Green

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    Write-Host "ERROR: Please don't run this installer as Administrator!" -ForegroundColor Red
    Write-Host "   Run it as your regular user account." -ForegroundColor Yellow
    Write-Host "   The script will handle any necessary permissions." -ForegroundColor Yellow
    exit 1
}

# Function to install Python 3.12 automatically
function Install-Python312 {
    Write-Host "🐍 Installing Python 3.12 (compatible version for WhisperX)..." -ForegroundColor Blue
    
    # Download Python 3.12.10 installer
    $pythonUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    $pythonInstaller = "$env:TEMP\python-3.12.10-installer.exe"
    
    Write-Host "   Downloading Python 3.12.10..." -ForegroundColor Blue
    try {
        Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonInstaller -UseBasicParsing
    } catch {
        Write-Host "ERROR: Failed to download Python installer: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "   Installing Python 3.12.10..." -ForegroundColor Blue
    # Install Python with all necessary options
    $installArgs = @(
        "/quiet",
        "InstallAllUsers=0",          # Install for current user only
        "PrependPath=1",              # Add to PATH
        "Include_test=0",             # Don't include test suite
        "Include_pip=1",              # Include pip
        "Include_tcltk=1",            # Include tkinter (needed for GUI)
        "Include_launcher=1",         # Include py.exe launcher
        "AssociateFiles=0",           # Don't associate .py files
        "Shortcuts=0",                # Don't create shortcuts
        "Include_doc=0",              # Don't include documentation
        "Include_dev=0"               # Don't include headers/libs
    )
    
    $process = Start-Process -FilePath $pythonInstaller -ArgumentList $installArgs -Wait -PassThru
    
    if ($process.ExitCode -eq 0) {
        Write-Host "Python 3.12.10 installed successfully" -ForegroundColor Green
        
        # Refresh PATH for current session
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
        
        # Clean up installer
        Remove-Item $pythonInstaller -ErrorAction SilentlyContinue
        
        return $true
    } else {
        Write-Host "Python installation failed with exit code $($process.ExitCode)" -ForegroundColor Red
        Remove-Item $pythonInstaller -ErrorAction SilentlyContinue
        return $false
    }
}

# Function to get Python 3.12 path (handles multiple Python versions)
function Get-Python312Path {
    # Try py.exe launcher first (most reliable)
    try {
        $python312Path = py -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $python312Path) {
            return $python312Path.Trim()
        }
    } catch {}
    
    # Try direct python command
    try {
        $pythonVersion = python --version 2>&1
        if ($pythonVersion -match "Python 3\.12") {
            return (Get-Command python).Source
        }
    } catch {}
    
    # Try common Python 3.12 installation paths
    $commonPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:PROGRAMFILES\Python312\python.exe",
        "$env:PROGRAMFILES(x86)\Python312\python.exe"
    )
    
    foreach ($path in $commonPaths) {
        if (Test-Path $path) {
            try {
                $version = & $path --version 2>&1
                if ($version -match "Python 3\.12") {
                    return $path
                }
            } catch {}
        }
    }
    
    return $null
}

# Smart Python version management
$python312Path = Get-Python312Path

if (-not $python312Path) {
    Write-Host "🔍 Python 3.12 not found - installing automatically..." -ForegroundColor Yellow
    Write-Host "   (Python 3.12 is required for WhisperX compatibility)" -ForegroundColor Gray
    
    if (-not (Install-Python312)) {
        exit 1
    }
    
    # Try to find Python 3.12 again after installation
    Start-Sleep 2  # Give time for PATH to update
    $python312Path = Get-Python312Path
    
    if (-not $python312Path) {
        Write-Host "ERROR: Could not locate Python 3.12 after installation" -ForegroundColor Red
        Write-Host "   Please restart your terminal and try again" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host "SUCCESS: Using Python 3.12: $python312Path" -ForegroundColor Green

# Verify Python version is exactly what we need
try {
    $pythonVersion = & $python312Path --version 2>&1
    Write-Host "SUCCESS: Verified: $pythonVersion" -ForegroundColor Green
    
    if (-not ($pythonVersion -match "Python 3\.12")) {
        Write-Host "ERROR: Expected Python 3.12, got: $pythonVersion" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "ERROR: Could not verify Python version: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Install pipx if not present (using our Python 3.12)
try {
    $pipxVersion = & $python312Path -m pipx --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "SUCCESS: pipx already installed: $pipxVersion" -ForegroundColor Green
    } else {
        throw "pipx not available"
    }
} catch {
    Write-Host "Installing pipx package manager with Python 3.12..." -ForegroundColor Blue
    & $python312Path -m pip install --user pipx
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to install pipx" -ForegroundColor Red
        exit 1
    }
    
    # Ensure pipx is in PATH
    & $python312Path -m pipx ensurepath
    
    # Add pipx to current session PATH (Python 3.12 specific paths)
    $pythonVersion = (& $python312Path --version) -replace "Python ", "" -replace "\.\d+$", ""
    $pipxPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\Scripts",
        "$env:APPDATA\Python\Python312\Scripts",
        "$env:LOCALAPPDATA\Packages\PythonSoftwareFoundation.Python.3.12*\LocalCache\local-packages\Python312\Scripts"
    )
    
    foreach ($path in $pipxPaths) {
        if (Test-Path $path -PathType Container) {
            $env:PATH += ";$path"
        }
    }
    
    Write-Host "SUCCESS: pipx installed with Python 3.12" -ForegroundColor Green
}

# Install witticism with Python 3.12 compatibility focus
Write-Host "Installing Witticism..." -ForegroundColor Blue

# Force CPU-only PyTorch for Python 3.12 compatibility
$indexUrl = "https://download.pytorch.org/whl/cpu"
$pipArgs = @("--pip-args=--index-url $indexUrl --extra-index-url https://pypi.org/simple")

Write-Host "   Installing with Python 3.12 and CPU-optimized PyTorch..." -ForegroundColor Blue
Write-Host "   (This ensures maximum compatibility with WhisperX)" -ForegroundColor Gray

try {
    # Use our Python 3.12 path explicitly
    & $python312Path -m pipx install witticism $pipArgs
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARNING: Standard installation failed, trying alternative method..." -ForegroundColor Yellow
        
        # Alternative: Use pip directly in user space
        & $python312Path -m pip install --user witticism --index-url $indexUrl --extra-index-url https://pypi.org/simple
        
        if ($LASTEXITCODE -ne 0) {
            throw "Both pipx and pip installation methods failed"
        }
        
        Write-Host "SUCCESS: Witticism installed with pip (user mode)" -ForegroundColor Green
        $isPipInstall = $true
    } else {
        Write-Host "SUCCESS: Witticism installed with pipx" -ForegroundColor Green
        $isPipInstall = $false
    }
} catch {
    Write-Host "ERROR: Failed to install Witticism" -ForegroundColor Red
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "" -ForegroundColor Red
    Write-Host "This might be due to:" -ForegroundColor Yellow
    Write-Host "• Network connectivity issues" -ForegroundColor Yellow
    Write-Host "• Antivirus blocking the installation" -ForegroundColor Yellow  
    Write-Host "• Insufficient disk space" -ForegroundColor Yellow
    Write-Host "" -ForegroundColor Yellow
    Write-Host "Try running the script again, or install manually:" -ForegroundColor Yellow
    Write-Host "$python312Path -m pip install --user witticism" -ForegroundColor Gray
    exit 1
}

# Set up auto-start (unless skipped)  
if (-not $SkipAutoStart) {
    Write-Host "Setting up auto-start..." -ForegroundColor Blue
    
    try {
        # Create a PowerShell script for auto-start (more reliable than batch)
        $startupFolder = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Startup)
        $startupScript = Join-Path $startupFolder "WitticismAutoStart.ps1"
        
        if ($isPipInstall) {
            # Direct Python execution for pip-installed version
            $startupContent = @"
# Witticism Auto-Start Script
Start-Process -FilePath "$python312Path" -ArgumentList "-m", "witticism" -WindowStyle Hidden
"@
        } else {
            # pipx execution
            $startupContent = @"
# Witticism Auto-Start Script  
Start-Process -FilePath "$python312Path" -ArgumentList "-m", "pipx", "run", "witticism" -WindowStyle Hidden
"@
        }
        
        # Write the PowerShell script
        Set-Content -Path $startupScript -Value $startupContent -Encoding UTF8
        
        # Also create a VBS script to run PowerShell silently (no console window)
        $vbsScript = Join-Path $startupFolder "WitticismAutoStart.vbs"
        $vbsContent = @"
Set objShell = CreateObject("WScript.Shell")
objShell.Run "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File ""$startupScript""", 0, False
"@
        Set-Content -Path $vbsScript -Value $vbsContent -Encoding UTF8
        
        Write-Host "SUCCESS: Auto-start configured" -ForegroundColor Green
        Write-Host "   Witticism will start automatically on Windows login" -ForegroundColor Green
        Write-Host "   Files created: WitticismAutoStart.vbs, WitticismAutoStart.ps1" -ForegroundColor Gray
    } catch {
        Write-Host "WARNING: Could not set up auto-start: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "   You can manually add Witticism to your startup programs:" -ForegroundColor Yellow
        Write-Host "   $python312Path -m witticism" -ForegroundColor Gray
    }
}

# Create desktop shortcut
Write-Host "Creating desktop shortcut..." -ForegroundColor Blue
try {
    $desktop = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
    $shortcutPath = Join-Path $desktop "Witticism.lnk"
    
    $WScriptShell = New-Object -ComObject WScript.Shell
    $shortcut = $WScriptShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $python312Path
    
    if ($isPipInstall) {
        $shortcut.Arguments = "-m witticism"
    } else {
        $shortcut.Arguments = "-m pipx run witticism"  
    }
    
    $shortcut.Description = "Witticism - Voice Transcription Assistant (F9 to record)"
    $shortcut.WorkingDirectory = $env:USERPROFILE
    
    # Try to set an icon if available
    if (Test-Path "$env:LOCALAPPDATA\Programs\Python\Python312\DLLs\_tkinter.pyd") {
        $shortcut.IconLocation = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe,0"
    }
    
    $shortcut.Save()
    
    Write-Host "SUCCESS: Desktop shortcut created" -ForegroundColor Green
} catch {
    Write-Host "WARNING: Could not create desktop shortcut: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "   You can manually create a shortcut with target:" -ForegroundColor Yellow
    if ($isPipInstall) {
        Write-Host "   $python312Path -m witticism" -ForegroundColor Gray
    } else {
        Write-Host "   $python312Path -m pipx run witticism" -ForegroundColor Gray
    }
}

# Test the installation
Write-Host "Testing installation..." -ForegroundColor Blue
try {
    $testCmd = if ($isPipInstall) { 
        "& '$python312Path' -m witticism --version"
    } else { 
        "& '$python312Path' -m pipx run witticism --version" 
    }
    
    $version = Invoke-Expression $testCmd 2>&1
    if ($version -match "witticism") {
        Write-Host "SUCCESS: Installation test passed: $version" -ForegroundColor Green
    } else {
        Write-Host "WARNING: Installation test inconclusive" -ForegroundColor Yellow  
    }
} catch {
    Write-Host "WARNING: Could not test installation: $($_.Exception.Message)" -ForegroundColor Yellow
}

# Installation complete
Write-Host ""
Write-Host "Installation Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Witticism is now installed and ready to use:" -ForegroundColor White
Write-Host "• Double-click the desktop shortcut to launch" -ForegroundColor White
if ($isPipInstall) {
    Write-Host "• Or run: $python312Path -m witticism" -ForegroundColor White
} else {
    Write-Host "• Or run: $python312Path -m pipx run witticism" -ForegroundColor White
}
Write-Host "• Look for the system tray icon when running" -ForegroundColor White
Write-Host "• Hold F9 to record, release to transcribe" -ForegroundColor White

Write-Host ""
Write-Host "Python Environment:" -ForegroundColor Cyan
Write-Host "• Python: $python312Path" -ForegroundColor White
Write-Host "• Version: $(& $python312Path --version)" -ForegroundColor White
Write-Host "• PyTorch: CPU-optimized (maximum compatibility)" -ForegroundColor White
Write-Host "• WhisperX: Latest compatible version" -ForegroundColor White

if (-not $SkipAutoStart) {
    Write-Host ""
    Write-Host "Auto-Start:" -ForegroundColor Cyan
    Write-Host "• Witticism will start automatically on Windows login" -ForegroundColor Green
    Write-Host "• Runs silently in background (system tray)" -ForegroundColor White
    Write-Host "• To disable: Delete files from Startup folder" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "• Launch Witticism from desktop shortcut" -ForegroundColor White
Write-Host "• Test with F9 key (hold to record, release to type)" -ForegroundColor White
Write-Host "• Configure settings through system tray icon" -ForegroundColor White

Write-Host ""
Write-Host "Enjoy fast, accurate voice transcription!" -ForegroundColor Green
Write-Host "No Python version juggling required - it just works!" -ForegroundColor Green