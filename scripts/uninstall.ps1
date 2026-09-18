# Windows PowerShell uninstaller for Witticism
# Reverses everything install.ps1 lays down on Windows:
#   - running witticism/pywit process
#   - pipx (and pip user) installation
#   - desktop shortcut (Witticism.lnk)
#   - Startup folder auto-start shortcut (Witticism.lnk), plus legacy
#     WitticismAutoStart.ps1/.vbs files from older installs
#   - config/data directories (only with -Purge; kept by default)

param(
    [switch]$Purge,
    [switch]$Help
)

if ($Help) {
    Write-Host "Witticism Windows Uninstaller"
    Write-Host ""
    Write-Host "Usage:"
    Write-Host "    .\uninstall.ps1            # Uninstall (keeps config/data)"
    Write-Host "    .\uninstall.ps1 -Purge     # Uninstall AND delete config/data"
    Write-Host "    .\uninstall.ps1 -Help      # Show this help"
    Write-Host ""
    Write-Host "Removes: pipx/pip installation, desktop shortcut, auto-start"
    Write-Host "files, and (with -Purge) app config and data directories."
    exit 0
}

# Color-friendly output helper (Windows PowerShell 5.1 compatible)
function Write-Ok   { Write-Host "   [OK] $($args[0])" -ForegroundColor Green }
function Write-Warn { Write-Host "   $($args[0])" -ForegroundColor Yellow }
function Write-Found { Write-Host "   $($args[0])" -ForegroundColor Gray }

Write-Host "Uninstalling Witticism..." -ForegroundColor Green

# ---- 1. stop any running process --------------------------------------------
$running = Get-Process | Where-Object { $_.ProcessName -match "witticism" }
if ($running) {
    Write-Host "   Stopping running Witticism process..."
    $running | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Ok "Stopped running Witticism process"
} else {
    Write-Found "No running Witticism process found"
}

# ---- 2. locate python + pipx ------------------------------------------------
# Mirror install.ps1's Get-Python312Path exactly, so we uninstall with the
# same interpreter that performed the install (otherwise we could miss the
# actual pipx install and report success while leaving it behind).
function Get-Python312Path {
    try {
        $python312Path = py -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $python312Path) {
            return $python312Path.Trim()
        }
    } catch {}

    try {
        $pythonVersion = python --version 2>&1
        if ($pythonVersion -match "Python 3\.12") {
            return (Get-Command python).Source
        }
    } catch {}

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

$pythonPath = Get-Python312Path

# ---- 3. pipx / pip uninstall ------------------------------------------------
if ($pythonPath) {
    try {
        $pipxList = & $pythonPath -m pipx list 2>&1 | Out-String
        if ($pipxList -match "witticism") {
            Write-Host "   Removing pipx installation..."
            & $pythonPath -m pipx uninstall witticism 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Ok "Removed pipx installation"
            } else {
                Write-Warn "pipx uninstall did not exit cleanly"
            }
        } else {
            Write-Found "No pipx installation found"
        }
    } catch {
        Write-Warn "Could not query pipx: $($_.Exception.Message)"
    }

    try {
        $pipUser = & $pythonPath -m pip list --user 2>&1 | Out-String
        if ($pipUser -match "witticism") {
            Write-Host "   Removing pip user installation..."
            & $pythonPath -m pip uninstall witticism -y 2>$null
            Write-Ok "Removed pip user installation"
        } else {
            Write-Found "No pip user installation found"
        }
    } catch {
        Write-Warn "Could not query pip: $($_.Exception.Message)"
    }
} else {
    Write-Warn "Could not locate Python 3.12. Cannot remove pipx/pip install automatically."
}

# ---- 4. desktop shortcut -----------------------------------------------------
$desktop = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$shortcutPath = Join-Path $desktop "Witticism.lnk"
if (Test-Path $shortcutPath) {
    Remove-Item $shortcutPath -Force -ErrorAction SilentlyContinue
    Write-Ok "Removed desktop shortcut"
} else {
    Write-Found "No desktop shortcut found"
}

# ---- 5. Startup auto-start files --------------------------------------------
$startupFolder = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Startup)
# Current installs use a Startup .LNK shortcut; older installs used a .ps1/.vbs pair.
# Remove all three so no virally-sketchy .vbs or redundant scripts linger.
$startupShortcut = Join-Path $startupFolder "Witticism.lnk"
foreach ($p in @($startupShortcut, (Join-Path $startupFolder "WitticismAutoStart.ps1"), (Join-Path $startupFolder "WitticismAutoStart.vbs"))) {
    $leaf = Split-Path $p -Leaf
    if (Test-Path $p) {
        Remove-Item $p -Force -ErrorAction SilentlyContinue
        Write-Ok "Removed Startup file: $leaf"
    } else {
        Write-Found "No Startup file: $leaf"
    }
}

# ---- 6. config / data (only with -Purge) ------------------------------------
if ($Purge) {
    foreach ($dir in @("$env:APPDATA\witticism", "$env:LOCALAPPDATA\witticism")) {
        if (Test-Path $dir) {
            Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
            Write-Ok "Deleted $dir"
        }
    }
} else {
    Write-Warn "Keeping config & data (use -Purge to remove them)"
}

Write-Host ""
Write-Host "Witticism uninstalled." -ForegroundColor Green
if (-not $Purge) {
    Write-Host "Config kept (use -Purge to delete)." -ForegroundColor Yellow
}
