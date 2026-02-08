Param(
    [switch]$SkipFrontend,
    [switch]$SkipDaemon,
    [switch]$SkipArchive,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "=== Ami Portable Build (Windows) ===" -ForegroundColor Green

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "Script directory: $ScriptDir" -ForegroundColor Yellow
Write-Host "Project root:    $ProjectRoot" -ForegroundColor Yellow

function Invoke-Step {
    param(
        [string]$Title,
        [scriptblock]$Action
    )

    Write-Host "`n==> $Title" -ForegroundColor Yellow
    & $Action
}

$DesktopDir    = Join-Path $ProjectRoot 'src/clients/desktop_app'
$SrcTauriDir   = Join-Path $DesktopDir 'src-tauri'
$ResourcesDir  = Join-Path $SrcTauriDir 'resources'
$PortableOutDir = Join-Path $DesktopDir 'portable'
$PortableBinDir = Join-Path $PortableOutDir 'AmiPortable'

if (-not (Test-Path $PortableBinDir)) {
    New-Item -ItemType Directory -Path $PortableBinDir -Force | Out-Null
}

# Step 0: Prepare Git Bash bundle for Claude Code CLI
Invoke-Step "Step 0: Preparing Git Bash bundle for Claude Code CLI..." {
    $gitBashScript = Join-Path $ScriptDir 'prepare_git_bash_windows.ps1'
    # Use explicit path separators for Windows
    $gitBashOutputDir = Join-Path $ProjectRoot 'src' | Join-Path -ChildPath 'clients' | Join-Path -ChildPath 'desktop_app' | Join-Path -ChildPath 'ami_daemon' | Join-Path -ChildPath 'resources' | Join-Path -ChildPath 'git-bash'

    Write-Host "Git Bash output directory: $gitBashOutputDir" -ForegroundColor Cyan

    # Check if git-bash bundle already exists
    $bashExe = Join-Path $gitBashOutputDir 'usr' | Join-Path -ChildPath 'bin' | Join-Path -ChildPath 'bash.exe'
    if (Test-Path $bashExe) {
        Write-Host "Git Bash bundle already exists at: $gitBashOutputDir" -ForegroundColor Green
        Write-Host "Skipping download. Delete the directory to force re-download." -ForegroundColor Yellow
    } else {
        if (Test-Path $gitBashScript) {
            Write-Host "Downloading and preparing Git Bash..." -ForegroundColor Yellow
            & $gitBashScript -OutputDir $gitBashOutputDir
        } else {
            Write-Warning "Git Bash preparation script not found: $gitBashScript"
            Write-Warning "Claude Code CLI may not work without Git Bash on Windows."
        }
    }
}

# Step 1: Build Python daemon bundle (optional)
if (-not $SkipDaemon) {
    Invoke-Step "Step 1: Building Python daemon bundle (PyInstaller)..." {
        $backendDir = Join-Path $ProjectRoot 'src/clients/desktop_app/ami_daemon'
        Set-Location $backendDir

        $venvDir = 'venv-build'
        if (-not (Test-Path $venvDir)) {
            Write-Host "Creating build virtual environment..." -ForegroundColor Yellow
            python -m venv $venvDir
            Write-Host "Virtual environment created" -ForegroundColor Green
        }

        $venvPython = Join-Path $venvDir 'Scripts/python.exe'
        if (-not (Test-Path $venvPython)) {
            throw "Virtual environment python not found at $venvPython"
        }

        Write-Host "Installing daemon build dependencies..." -ForegroundColor Yellow
        & $venvPython -m pip install --upgrade pip | Out-Null
        & $venvPython -m pip install pyinstaller | Out-Null
        & $venvPython -m pip install -e "$ProjectRoot[desktop,memory]" | Out-Null

        Write-Host "Cleaning previous daemon build artifacts..." -ForegroundColor Yellow
        if (Test-Path 'build') { Remove-Item 'build' -Recurse -Force }
        if (Test-Path 'dist')  { Remove-Item 'dist'  -Recurse -Force }
        if (Test-Path 'ami-daemon.exe') { Remove-Item 'ami-daemon.exe' -Force }
        if (Test-Path 'ami-daemon')     { Remove-Item 'ami-daemon'     -Force }

        Write-Host "Running PyInstaller (daemon.spec)..." -ForegroundColor Yellow
        & $venvPython -m PyInstaller 'daemon.spec' --clean --noconfirm

        $distDir = Join-Path 'dist' 'ami-daemon'
        $binary  = Join-Path $distDir 'ami-daemon.exe'

        if (-not (Test-Path $distDir)) {
            throw "Daemon bundle directory not found: $distDir"
        }
        if (-not (Test-Path $binary)) {
            throw "Daemon executable not found: $binary"
        }

        Write-Host "Daemon bundle built at: $distDir" -ForegroundColor Green

        if (-not (Test-Path $ResourcesDir)) {
            New-Item -ItemType Directory -Path $ResourcesDir -Force | Out-Null
        }

        $targetDir = Join-Path $ResourcesDir 'ami-daemon'
        if (Test-Path $targetDir) {
            Remove-Item $targetDir -Recurse -Force
        }

        Copy-Item $distDir $targetDir -Recurse
        Write-Host "Daemon bundle copied to: $targetDir" -ForegroundColor Green
    }
} else {
    Write-Host "Skipping daemon build (per --SkipDaemon)." -ForegroundColor Yellow
}

# Step 2: Build frontend dist output (optional)
if (-not $SkipFrontend) {
    Invoke-Step "Step 2: Building frontend (npm run build)..." {
        Set-Location $DesktopDir
        npm run build
    }
} else {
    Write-Host "Skipping frontend build (per --SkipFrontend)." -ForegroundColor Yellow
}

# Step 3: Build Tauri app (release exe)
Invoke-Step "Step 3: Building Tauri application binary (npx tauri build)..." {
    Set-Location $DesktopDir
    npx tauri build
}

# Step 4: Assemble portable directory
Invoke-Step "Step 4: Assembling portable directory..." {
    if (Test-Path $PortableBinDir) {
        if (-not $Force) {
            Remove-Item $PortableBinDir -Recurse -Force
        } else {
            Remove-Item $PortableBinDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    New-Item -ItemType Directory -Path $PortableBinDir -Force | Out-Null

    $portableBin = Join-Path $PortableBinDir 'ami-desktop'
    if (-not (Test-Path $portableBin)) {
        New-Item -ItemType Directory -Path $portableBin | Out-Null
    }

    $exeSource = Join-Path $SrcTauriDir 'target/release/ami-desktop.exe'
    if (-not (Test-Path $exeSource)) {
        throw "ami-desktop.exe not found at $exeSource"
    }

    Copy-Item $exeSource $PortableBinDir -Force

    # Copy Tauri resources directory (includes ami-daemon if present)
    if (Test-Path $ResourcesDir) {
        Copy-Item $ResourcesDir (Join-Path $PortableBinDir 'resources') -Recurse -Force
        Write-Host "Resources copied to portable directory" -ForegroundColor Green
    } else {
        Write-Warning "Resources directory not found at $ResourcesDir"
    }
}

# Step 5: Create ZIP archive if not skipped
if (-not $SkipArchive) {
    Invoke-Step "Step 5: Creating portable ZIP archive..." {
        $zipPath = Join-Path $PortableOutDir 'AmiPortable.zip'
        if (Test-Path $zipPath) {
            Remove-Item $zipPath -Force
        }

        Set-Location $PortableOutDir
        Compress-Archive -Path 'AmiPortable/*' -DestinationPath $zipPath
        Write-Host "Portable package archived to: $zipPath" -ForegroundColor Green
    }
} else {
    Write-Host "Skipping ZIP archive creation (per --SkipArchive)." -ForegroundColor Yellow
}

Write-Host "`n=== Portable build complete ===" -ForegroundColor Green
Write-Host "Portable directory: $PortableBinDir" -ForegroundColor Green
if (-not $SkipArchive) {
    Write-Host "ZIP archive:     $(Join-Path $PortableOutDir 'AmiPortable.zip')" -ForegroundColor Green
}
