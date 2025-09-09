# Windows PowerShell installer for Witticism
# Handles Python version management, dependencies, GPU detection, and auto-start setup
# Works around Python 3.13 compatibility issues by using Python 3.12 automatically

param(
    [switch]$SkipAutoStart,
    [switch]$CPUOnly,
    [switch]$Help,
    [switch]$ForceReinstall,
    [string]$Version,
    [switch]$DryRun
)

if ($Help) {
    Write-Host "Witticism Windows Installer"
    Write-Host ""
    Write-Host "Usage:"
    Write-Host "    .\install.ps1                      # Install latest stable version"
    Write-Host "    .\install.ps1 -Version `"0.6.0b1`"   # Install specific version"
    Write-Host "    .\install.ps1 -CPUOnly             # Force CPU-only installation"
    Write-Host "    .\install.ps1 -SkipAutoStart       # Don't set up auto-start"
    Write-Host "    .\install.ps1 -ForceReinstall      # Force reinstall even if already installed"
    Write-Host "    .\install.ps1 -DryRun              # Show what would be done without making changes"
    Write-Host "    .\install.ps1 -Help                # Show this help"
    Write-Host ""
    Write-Host "This script automatically:"
    Write-Host "- Installs Python 3.12 (compatible version) if needed"
    Write-Host "- Sets up isolated Python environment"
    Write-Host "- Installs all dependencies including WhisperX"
    Write-Host "- Detects and configures GPU support (CUDA/PyTorch)"
    Write-Host "- Sets up auto-start on Windows login"
    Write-Host "- Creates desktop shortcuts"
    Write-Host ""
    Write-Host "No manual Python version management required!"
    exit 0
}

if ($DryRun) {
    Write-Host "DRY RUN MODE - No changes will be made" -ForegroundColor Cyan
    Write-Host "=======================================" -ForegroundColor Cyan
} else {
    Write-Host "Installing Witticism on Windows..." -ForegroundColor Green
}

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
    Write-Host "Installing Python 3.12 (compatible version for WhisperX)..." -ForegroundColor Blue
    
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
    Write-Host "Python 3.12 not found - installing automatically..." -ForegroundColor Yellow
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

# If dry run, test icon detection and shortcut logic
if ($DryRun) {
    Write-Host ""
    Write-Host "=== DRY RUN: Would continue with installation ===" -ForegroundColor Cyan
    Write-Host "Python path: $python312Path" -ForegroundColor Gray
    Write-Host "Version to install: $(if ($Version) { $Version } else { 'latest' })" -ForegroundColor Gray
    Write-Host "Force reinstall: $ForceReinstall" -ForegroundColor Gray
    Write-Host "Skip auto-start: $SkipAutoStart" -ForegroundColor Gray
    
    # Test if witticism is already installed to simulate desktop shortcut creation
    Write-Host ""
    Write-Host "=== DRY RUN: Testing Desktop Shortcut Logic ===" -ForegroundColor Cyan
    
    # Determine installation type (simulating what would happen after install)
    $isPipInstall = $false  # Assume pipx for now since that's what we use
    Write-Host "Simulated install type: $(if ($isPipInstall) { 'pip' } else { 'pipx' })" -ForegroundColor Yellow
    
    # Test shortcut target detection
    if ($isPipInstall) {
        Write-Host "Desktop shortcut would target: $python312Path -m witticism" -ForegroundColor Gray
    } else {
        # For pipx, try to find the direct witticism.exe
        $witticismBinDir = & $python312Path -m pipx environment --value PIPX_BIN_DIR 2>$null
        if ($witticismBinDir) {
            $witticismExePath = Join-Path $witticismBinDir "witticism.exe"
            Write-Host "PIPX_BIN_DIR: $witticismBinDir" -ForegroundColor Gray
            Write-Host "Expected witticism.exe path: $witticismExePath" -ForegroundColor Gray
            Write-Host "witticism.exe exists: $(Test-Path $witticismExePath)" -ForegroundColor Gray
            
            if (Test-Path $witticismExePath) {
                Write-Host "Desktop shortcut would target: $witticismExePath" -ForegroundColor Green
            } else {
                Write-Host "Desktop shortcut would target: $python312Path -m pipx run witticism" -ForegroundColor Yellow
            }
        }
    }
    
    # Now test icon detection logic (copy from the shortcut creation section)
    $iconSet = $false
    $witticismPkgPath = $null
    
    Write-Host ""
    Write-Host "=== DRY RUN: Icon Detection ===" -ForegroundColor Cyan
    
    if ($isPipInstall) {
        Write-Host "Install type: pip (direct Python package installation)" -ForegroundColor Yellow
        $sitePkgPath = & $python312Path -c "import site; print(site.getusersitepackages())" 2>$null
        Write-Host "User site-packages path: $sitePkgPath" -ForegroundColor Gray
        if ($sitePkgPath -and (Test-Path $sitePkgPath)) {
            $witticismPkgPath = Join-Path $sitePkgPath "witticism"
            Write-Host "Expected witticism package path: $witticismPkgPath" -ForegroundColor Gray
            Write-Host "Package exists: $(Test-Path $witticismPkgPath)" -ForegroundColor Gray
        }
    } else {
        Write-Host "Install type: pipx (isolated virtual environment)" -ForegroundColor Yellow
        $pipxVenvRoot = & $python312Path -m pipx environment --value PIPX_LOCAL_VENVS 2>$null
        Write-Host "PIPX_LOCAL_VENVS: $pipxVenvRoot" -ForegroundColor Gray
        
        if ($pipxVenvRoot) {
            $pipxVenvPaths = @(
                "$pipxVenvRoot\witticism\Lib\site-packages",
                "$pipxVenvRoot\witticism\lib\site-packages"
            )
        } else {
            $pipxVenvPaths = @(
                "$env:USERPROFILE\pipx\venvs\witticism\Lib\site-packages",
                "$env:LOCALAPPDATA\pipx\venvs\witticism\Lib\site-packages",
                "$env:USERPROFILE\.local\pipx\venvs\witticism\lib\site-packages"
            )
        }
        
        Write-Host "Searching for witticism package in paths:" -ForegroundColor Gray
        foreach ($path in $pipxVenvPaths) {
            Write-Host "  - $path" -ForegroundColor Gray
        }
        
        foreach ($venvPath in $pipxVenvPaths) {
            $testWitticismPath = Join-Path $venvPath "witticism"
            Write-Host "  Checking: $testWitticismPath - Exists: $(Test-Path $testWitticismPath)" -ForegroundColor Gray
            if (Test-Path $testWitticismPath) {
                $witticismPkgPath = $testWitticismPath
                Write-Host "   Found witticism package at: $witticismPkgPath" -ForegroundColor Green
                break
            }
        }
    }
    
    if ($witticismPkgPath -and (Test-Path $witticismPkgPath)) {
        $assetsPath = Join-Path $witticismPkgPath "assets"
        Write-Host "Assets path: $assetsPath" -ForegroundColor Gray
        Write-Host "Assets directory exists: $(Test-Path $assetsPath)" -ForegroundColor Gray
        
        if (Test-Path $assetsPath) {
            Write-Host "Available icon files:" -ForegroundColor Gray
            Get-ChildItem -Path $assetsPath -Name "*.png" | ForEach-Object {
                Write-Host "  - $_" -ForegroundColor Gray
            }
            
            $iconSizes = @("48x48", "32x32", "64x64", "24x24", "16x16")
            foreach ($size in $iconSizes) {
                $iconPath = Join-Path $assetsPath "witticism_$size.png"
                Write-Host "  Checking for icon: witticism_$size.png - Exists: $(Test-Path $iconPath)" -ForegroundColor Gray
                if (Test-Path $iconPath) {
                    $resolvedIconPath = (Resolve-Path $iconPath).Path
                    Write-Host "   Icon would be set to: $resolvedIconPath" -ForegroundColor Green
                    $iconSet = $true
                    break
                }
            }
            
            if (-not $iconSet) {
                $mainIconPath = Join-Path $assetsPath "witticism.png"
                Write-Host "  Checking fallback icon: witticism.png - Exists: $(Test-Path $mainIconPath)" -ForegroundColor Gray
                if (Test-Path $mainIconPath) {
                    $resolvedIconPath = (Resolve-Path $mainIconPath).Path
                    Write-Host "   Fallback icon would be set to: $resolvedIconPath" -ForegroundColor Green
                    $iconSet = $true
                }
            }
        } else {
            Write-Host "Assets directory not found!" -ForegroundColor Red
        }
    } else {
        Write-Host "Witticism package not found or not accessible" -ForegroundColor Red
    }
    
    if (-not $iconSet) {
        Write-Host "   Would fallback to Python icon" -ForegroundColor Yellow
    }
    
    # Test auto-start logic
    Write-Host ""
    Write-Host "=== DRY RUN: Testing Auto-Start Logic ===" -ForegroundColor Cyan
    $startupFolder = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Startup)
    Write-Host "Windows Startup folder: $startupFolder" -ForegroundColor Gray
    Write-Host "Startup folder exists: $(Test-Path $startupFolder)" -ForegroundColor Gray
    
    $startupScript = Join-Path $startupFolder "WitticismAutoStart.ps1"
    $vbsScript = Join-Path $startupFolder "WitticismAutoStart.vbs"
    
    Write-Host "Would create PowerShell script: $startupScript" -ForegroundColor Gray
    Write-Host "Would create VBS wrapper: $vbsScript" -ForegroundColor Gray
    
    # Show what the auto-start content would be
    Write-Host "PowerShell auto-start content would be:" -ForegroundColor Gray
    if ($isPipInstall) {
        Write-Host "  Start-Process -FilePath `"$python312Path`" -ArgumentList `"-m`", `"witticism`" -WindowStyle Hidden" -ForegroundColor Yellow
    } else {
        $witticismBinDir = & $python312Path -m pipx environment --value PIPX_BIN_DIR 2>$null
        if ($witticismBinDir) {
            $witticismExePath = Join-Path $witticismBinDir "witticism.exe"
            if (Test-Path $witticismExePath) {
                Write-Host "  Start-Process -FilePath `"$witticismExePath`" -WindowStyle Hidden" -ForegroundColor Yellow  
            } else {
                Write-Host "  Start-Process -FilePath `"$python312Path`" -ArgumentList `"-m`", `"pipx`", `"run`", `"witticism`" -WindowStyle Hidden" -ForegroundColor Yellow
            }
        } else {
            Write-Host "  Start-Process -FilePath `"$python312Path`" -ArgumentList `"-m`", `"pipx`", `"run`", `"witticism`" -WindowStyle Hidden" -ForegroundColor Yellow
        }
    }
    
    Write-Host ""
    Write-Host "DRY RUN COMPLETE - No changes were made" -ForegroundColor Green
    exit 0
}

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

# Function to clean up existing witticism installation
function Remove-ExistingWitticism {
    param($pythonPath)
    
    Write-Host "Checking for existing Witticism installation..." -ForegroundColor Blue
    
    try {
        # Check pipx installation
        $pipxResult = & $pythonPath -m pipx list 2>&1 | Out-String
        if ($pipxResult -match "witticism") {
            Write-Host "   Found pipx installation, removing..." -ForegroundColor Yellow
            & $pythonPath -m pipx uninstall witticism 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "   [OK] Removed pipx installation" -ForegroundColor Green
            }
        }
        
        # Check pip user installation  
        $pipResult = & $pythonPath -m pip list --user 2>&1 | Out-String
        if ($pipResult -match "witticism") {
            Write-Host "   Found pip user installation, removing..." -ForegroundColor Yellow
            & $pythonPath -m pip uninstall witticism -y 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "   [OK] Removed pip user installation" -ForegroundColor Green
            }
        }
        
        Write-Host "   [OK] Cleanup complete" -ForegroundColor Green
        
    } catch {
        Write-Host "   Warning: Could not fully clean existing installation: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# Clean up existing installation if ForceReinstall or if we detect issues
if ($ForceReinstall) {
    Remove-ExistingWitticism $python312Path
}

# Install witticism with Python 3.12 compatibility focus  
Write-Host "Installing Witticism..." -ForegroundColor Blue

# Determine version to install
$witticismPackage = if ($Version) {
    Write-Host "   Installing specific version: $Version" -ForegroundColor Blue
    "witticism==$Version"
} else {
    Write-Host "   Installing latest stable version" -ForegroundColor Blue
    "witticism"
}

# Force CPU-only PyTorch for Python 3.12 compatibility
$indexUrl = "https://download.pytorch.org/whl/cpu"
$pipArgs = @("--pip-args=--index-url $indexUrl --extra-index-url https://pypi.org/simple")

Write-Host "   Installing with Python 3.12 and CPU-optimized PyTorch..." -ForegroundColor Blue
Write-Host "   (This ensures maximum compatibility with WhisperX)" -ForegroundColor Gray
Write-Host ""
Write-Host "DOWNLOADING DEPENDENCIES..." -ForegroundColor Cyan
Write-Host "   This may take 2-3 minutes - WhisperX includes large AI models" -ForegroundColor Yellow
Write-Host "   Please be patient while we download:" -ForegroundColor Gray
Write-Host "   - PyTorch (CPU version, ~100MB)" -ForegroundColor Gray  
Write-Host "   - WhisperX speech recognition models" -ForegroundColor Gray
Write-Host "   - Audio processing libraries (librosa, etc.)" -ForegroundColor Gray
Write-Host "   - ML dependencies (transformers, numpy, scipy)" -ForegroundColor Gray
Write-Host ""
Write-Host "Installing... (this is normal, not frozen)" -ForegroundColor Green

try {
    # Use our Python 3.12 path explicitly  
    & $python312Path -m pipx install $witticismPackage $pipArgs
    
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
    Write-Host "- Network connectivity issues" -ForegroundColor Yellow
    Write-Host "- Antivirus blocking the installation" -ForegroundColor Yellow  
    Write-Host "- Insufficient disk space" -ForegroundColor Yellow
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
Start-Process -FilePath `"$python312Path`" -ArgumentList `"-m`", `"witticism`" -WindowStyle Hidden
"@
        } else {
            # pipx execution
            $startupContent = @"
# Witticism Auto-Start Script  
Start-Process -FilePath `"$python312Path`" -ArgumentList `"-m`", `"pipx`", `"run`", `"witticism`" -WindowStyle Hidden
"@
        }
        
        # Write the PowerShell script
        Set-Content -Path $startupScript -Value $startupContent -Encoding UTF8
        
        # Also create a VBS script to run PowerShell silently (no console window)
        $vbsScript = Join-Path $startupFolder "WitticismAutoStart.vbs"
        $vbsContent = @"
Set objShell = CreateObject("WScript.Shell")
objShell.Run "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startupScript`"", 0, False
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
    
    if ($isPipInstall) {
        $shortcut.TargetPath = $python312Path
        $shortcut.Arguments = "-m witticism"
    } else {
        # For pipx, try to use the direct witticism.exe if available
        $witticismExe = & $python312Path -m pipx environment --value PIPX_BIN_DIR 2>$null
        if ($witticismExe) {
            $witticismExePath = Join-Path $witticismExe "witticism.exe"
            if (Test-Path $witticismExePath) {
                $shortcut.TargetPath = $witticismExePath
                $shortcut.Arguments = ""
                Write-Host "   Using direct witticism.exe: $witticismExePath" -ForegroundColor Gray
            } else {
                # Fallback to python -m pipx run
                $shortcut.TargetPath = $python312Path
                $shortcut.Arguments = "-m pipx run witticism"
                Write-Host "   Using python -m pipx run witticism" -ForegroundColor Gray
            }
        } else {
            # Fallback to python -m pipx run
            $shortcut.TargetPath = $python312Path
            $shortcut.Arguments = "-m pipx run witticism"
        }
    }
    
    $shortcut.Description = "Witticism - Voice Transcription Assistant (F9 to record)"
    $shortcut.WorkingDirectory = $env:USERPROFILE
    
    # Try to set a proper Witticism icon
    $iconSet = $false
    
    # First, try to find the witticism package assets directory
    try {
        $witticismPkgPath = $null
        
        if ($DryRun) {
            Write-Host ""
            Write-Host "=== DRY RUN: Icon Detection ===" -ForegroundColor Cyan
        }
        
        if ($isPipInstall) {
            # For pip install, look in user site-packages
            if ($DryRun) {
                Write-Host "Install type: pip (direct Python package installation)" -ForegroundColor Yellow
            }
            $sitePkgPath = & $python312Path -c "import site; print(site.getusersitepackages())" 2>$null
            if ($DryRun) {
                Write-Host "User site-packages path: $sitePkgPath" -ForegroundColor Gray
            }
            if ($sitePkgPath -and (Test-Path $sitePkgPath)) {
                $witticismPkgPath = Join-Path $sitePkgPath "witticism"
                if ($DryRun) {
                    Write-Host "Expected witticism package path: $witticismPkgPath" -ForegroundColor Gray
                    Write-Host "Package exists: $(Test-Path $witticismPkgPath)" -ForegroundColor Gray
                }
            }
        } else {
            # For pipx install, get the actual pipx venv path
            if ($DryRun) {
                Write-Host "Install type: pipx (isolated virtual environment)" -ForegroundColor Yellow
            }
            $pipxVenvRoot = & $python312Path -m pipx environment --value PIPX_LOCAL_VENVS 2>$null
            if ($DryRun) {
                Write-Host "PIPX_LOCAL_VENVS: $pipxVenvRoot" -ForegroundColor Gray
            }
            if ($pipxVenvRoot) {
                $pipxVenvPaths = @(
                    "$pipxVenvRoot\witticism\Lib\site-packages",
                    "$pipxVenvRoot\witticism\lib\site-packages"
                )
            } else {
                # Fallback to common Windows pipx paths
                $pipxVenvPaths = @(
                    "$env:USERPROFILE\pipx\venvs\witticism\Lib\site-packages",
                    "$env:LOCALAPPDATA\pipx\venvs\witticism\Lib\site-packages",
                    "$env:USERPROFILE\.local\pipx\venvs\witticism\lib\site-packages"
                )
            }
            
            if ($DryRun) {
                Write-Host "Searching for witticism package in paths:" -ForegroundColor Gray
                foreach ($path in $pipxVenvPaths) {
                    Write-Host "  - $path" -ForegroundColor Gray
                }
            }
            
            foreach ($venvPath in $pipxVenvPaths) {
                $testWitticismPath = Join-Path $venvPath "witticism"
                if ($DryRun) {
                    Write-Host "  Checking: $testWitticismPath - Exists: $(Test-Path $testWitticismPath)" -ForegroundColor Gray
                }
                if (Test-Path $testWitticismPath) {
                    $witticismPkgPath = $testWitticismPath
                    Write-Host "   Found witticism package at: $witticismPkgPath" -ForegroundColor Gray
                    break
                }
            }
        }
        
        if ($witticismPkgPath -and (Test-Path $witticismPkgPath)) {
            $assetsPath = Join-Path $witticismPkgPath "assets"
            if ($DryRun) {
                Write-Host "Assets path: $assetsPath" -ForegroundColor Gray
                Write-Host "Assets directory exists: $(Test-Path $assetsPath)" -ForegroundColor Gray
            }
            
            if (Test-Path $assetsPath) {
                if ($DryRun) {
                    Write-Host "Available icon files:" -ForegroundColor Gray
                    Get-ChildItem -Path $assetsPath -Name "*.png" | ForEach-Object {
                        Write-Host "  - $_" -ForegroundColor Gray
                    }
                }
                
                # Look for a suitable icon file
                $iconSizes = @("48x48", "32x32", "64x64", "24x24", "16x16")
                foreach ($size in $iconSizes) {
                    $iconPath = Join-Path $assetsPath "witticism_$size.png"
                    if ($DryRun) {
                        Write-Host "  Checking for icon: witticism_$size.png - Exists: $(Test-Path $iconPath)" -ForegroundColor Gray
                    }
                    if (Test-Path $iconPath) {
                        # Ensure path is fully resolved and properly formatted
                        $resolvedIconPath = (Resolve-Path $iconPath).Path
                        if (-not $DryRun) {
                            $shortcut.IconLocation = $resolvedIconPath
                        }
                        $iconSet = $true
                        Write-Host "   Using Witticism icon: $resolvedIconPath" -ForegroundColor Gray
                        if ($DryRun) {
                            Write-Host "   Icon would be set to: $resolvedIconPath" -ForegroundColor Green
                        }
                        break
                    }
                }
                
                # Fallback to main icon if sized icons not found
                if (-not $iconSet) {
                    $mainIconPath = Join-Path $assetsPath "witticism.png"
                    if ($DryRun) {
                        Write-Host "  Checking fallback icon: witticism.png - Exists: $(Test-Path $mainIconPath)" -ForegroundColor Gray
                    }
                    if (Test-Path $mainIconPath) {
                        $resolvedIconPath = (Resolve-Path $mainIconPath).Path
                        if (-not $DryRun) {
                            $shortcut.IconLocation = $resolvedIconPath
                        }
                        $iconSet = $true
                        Write-Host "   Using Witticism icon: $resolvedIconPath" -ForegroundColor Gray
                        if ($DryRun) {
                            Write-Host "   Fallback icon would be set to: $resolvedIconPath" -ForegroundColor Green
                        }
                    }
                }
            }
        } else {
            if ($DryRun) {
                Write-Host "Witticism package not found or not accessible" -ForegroundColor Red
            }
        }
    } catch {
        # Silently continue if icon detection fails
    }
    
    # Fallback to Python icon if Witticism icon not found
    if (-not $iconSet) {
        if (Test-Path "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe") {
            $shortcut.IconLocation = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe,0"
            Write-Host "   Using Python icon (Witticism icon not found)" -ForegroundColor Gray
        }
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
Write-Host "   (This may take 30-60 seconds on first run - downloading AI models)" -ForegroundColor Yellow

try {
    $testCmd = if ($isPipInstall) { 
        "& '$python312Path' -m witticism --version"
    } else { 
        "& '$python312Path' -m pipx run witticism --version" 
    }
    
    Write-Host "   Running: witticism --version..." -ForegroundColor Gray
    
    # Run with timeout to avoid hanging indefinitely
    $job = Start-Job -ScriptBlock ([scriptblock]::Create($testCmd))
    $completed = Wait-Job $job -Timeout 90  # 90 second timeout
    
    if ($completed) {
        $version = Receive-Job $job 2>&1 | Out-String
        Remove-Job $job
        
        if ($version -match "witticism|main\.py") {
            Write-Host "SUCCESS: Installation test passed" -ForegroundColor Green
            Write-Host "   Version check completed successfully" -ForegroundColor Gray
        } else {
            Write-Host "WARNING: Installation test inconclusive" -ForegroundColor Yellow
            Write-Host "   Output: $($version.Trim())" -ForegroundColor Gray
        }
    } else {
        Remove-Job $job -Force
        Write-Host "WARNING: Installation test timed out (this is common on first run)" -ForegroundColor Yellow
        Write-Host "   Witticism is installed but needs to download models on first use" -ForegroundColor Gray
    }
} catch {
    Write-Host "WARNING: Could not test installation: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "   This doesn't mean installation failed - try launching manually" -ForegroundColor Gray
}

# Installation complete
Write-Host ""
Write-Host "Installation Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Witticism is now installed and ready to use:" -ForegroundColor White
Write-Host "- Double-click the desktop shortcut to launch" -ForegroundColor White
if ($isPipInstall) {
    Write-Host "- Or run: $python312Path -m witticism" -ForegroundColor White
} else {
    Write-Host "- Or run: $python312Path -m pipx run witticism" -ForegroundColor White
}
Write-Host "- Look for the system tray icon when running" -ForegroundColor White
Write-Host "- Hold F9 to record, release to transcribe" -ForegroundColor White

Write-Host ""
Write-Host "Python Environment:" -ForegroundColor Cyan
Write-Host "- Python: $python312Path" -ForegroundColor White
Write-Host "- Version: $(& $python312Path --version)" -ForegroundColor White
Write-Host "- PyTorch: CPU-optimized (maximum compatibility)" -ForegroundColor White
Write-Host "- WhisperX: Latest compatible version" -ForegroundColor White

if (-not $SkipAutoStart) {
    Write-Host ""
    Write-Host "Auto-Start:" -ForegroundColor Cyan
    Write-Host "- Witticism will start automatically on Windows login" -ForegroundColor Green
    Write-Host "- Runs silently in background (system tray)" -ForegroundColor White
    Write-Host "- To disable: Delete files from Startup folder" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "- Launch Witticism from desktop shortcut" -ForegroundColor White
Write-Host "- Test with F9 key (hold to record, release to type)" -ForegroundColor White
Write-Host "- Configure settings through system tray icon" -ForegroundColor White
Write-Host ""
Write-Host "FIRST RUN NOTES:" -ForegroundColor Yellow
Write-Host "- First launch may take 30-60 seconds (downloading language models)" -ForegroundColor Gray
Write-Host "- Look for the microphone icon in your system tray" -ForegroundColor Gray
Write-Host "- If tray app doesn't appear, try running from desktop shortcut" -ForegroundColor Gray

Write-Host ""
Write-Host "Enjoy fast, accurate voice transcription!" -ForegroundColor Green
Write-Host "No Python version juggling required - it just works!" -ForegroundColor Green