Param(
    [switch]$SkipFrontend,
    [switch]$SkipDaemon,
    [switch]$SkipArchive,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "=== Ami Portable Build - Electron (Windows) ===" -ForegroundColor Green

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

$DesktopDir     = Join-Path $ProjectRoot 'src/clients/desktop_app'
$PortableOutDir = Join-Path $DesktopDir 'portable'
$PortableBinDir = Join-Path $PortableOutDir 'AmiPortable'

if (-not (Test-Path $PortableBinDir)) {
    New-Item -ItemType Directory -Path $PortableBinDir -Force | Out-Null
}

# Step 0: Prepare Git Bash bundle for Claude Code CLI
Invoke-Step "Step 0: Preparing Git Bash bundle for Claude Code CLI..." {
    $gitBashScript = Join-Path $ScriptDir 'prepare_git_bash_windows.ps1'
    $gitBashOutputDir = Join-Path $ProjectRoot 'src' | Join-Path -ChildPath 'clients' | Join-Path -ChildPath 'desktop_app' | Join-Path -ChildPath 'ami_daemon' | Join-Path -ChildPath 'resources' | Join-Path -ChildPath 'git-bash'

    Write-Host "Git Bash output directory: $gitBashOutputDir" -ForegroundColor Cyan

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

# Step 1: Build TypeScript daemon (optional)
if (-not $SkipDaemon) {
    Invoke-Step "Step 1: Building TypeScript daemon..." {
        $daemonTsDir = Join-Path $DesktopDir 'daemon-ts'
        Set-Location $daemonTsDir

        Write-Host "Installing daemon-ts dependencies..." -ForegroundColor Yellow
        npm ci

        Write-Host "Building TypeScript daemon..." -ForegroundColor Yellow
        npm run build

        Write-Host "TypeScript daemon built successfully" -ForegroundColor Green
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

# Step 3: Build Electron app
Invoke-Step "Step 3: Building Electron application (npx electron-builder)..." {
    Set-Location $DesktopDir
    npx electron-builder --win
}

# electron-builder output directory
$ElectronDist = Join-Path $DesktopDir 'release'

# Step 4: Assemble portable directory
Invoke-Step "Step 4: Assembling portable directory..." {
    if (Test-Path $PortableBinDir) {
        Remove-Item $PortableBinDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $PortableBinDir -Force | Out-Null

    # Find the unpacked directory from electron-builder (win-unpacked)
    $unpackedDir = Join-Path $ElectronDist 'win-unpacked'
    if (-not (Test-Path $unpackedDir)) {
        throw "Electron win-unpacked directory not found at $unpackedDir"
    }

    # Copy all files from win-unpacked to portable directory
    Copy-Item "$unpackedDir\*" $PortableBinDir -Recurse -Force
    Write-Host "Electron app copied to portable directory" -ForegroundColor Green
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
