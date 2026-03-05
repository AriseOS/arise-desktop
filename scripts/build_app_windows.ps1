Param(
    [switch]$SkipFrontend,
    [switch]$SkipDaemon,
    [switch]$SkipArchive,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "=== Arise Portable Build - Electron (Windows) ===" -ForegroundColor Green

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

$ElectronDist   = Join-Path $ProjectRoot 'release'
$PortableOutDir = Join-Path $ProjectRoot 'portable'
$PortableBinDir = Join-Path $PortableOutDir 'ArisePortable'

if (-not (Test-Path $PortableBinDir)) {
    New-Item -ItemType Directory -Path $PortableBinDir -Force | Out-Null
}

# Step 1: Build TypeScript daemon (optional)
if (-not $SkipDaemon) {
    Invoke-Step "Step 1: Building TypeScript daemon..." {
        $daemonTsDir = Join-Path $ProjectRoot 'daemon-ts'
        Set-Location $daemonTsDir

        Write-Host "Installing daemon-ts dependencies..." -ForegroundColor Yellow
        npm ci

        Write-Host "Building TypeScript daemon..." -ForegroundColor Yellow
        npm run build

        Write-Host "Pruning devDependencies for packaging..." -ForegroundColor Yellow
        npm ci --omit=dev

        Write-Host "TypeScript daemon built successfully" -ForegroundColor Green
    }
} else {
    Write-Host "Skipping daemon build (per --SkipDaemon)." -ForegroundColor Yellow
}

# Step 2: Build frontend dist output (optional)
if (-not $SkipFrontend) {
    Invoke-Step "Step 2: Building frontend (npm run build)..." {
        Set-Location $ProjectRoot
        npm run build
    }
} else {
    Write-Host "Skipping frontend build (per --SkipFrontend)." -ForegroundColor Yellow
}

# Step 3: Build Electron app
Invoke-Step "Step 3: Building Electron application (npx electron-builder)..." {
    Set-Location $ProjectRoot

    # Clean previous electron-builder output to prevent stale files
    if (Test-Path $ElectronDist) {
        Remove-Item $ElectronDist -Recurse -Force
        Write-Host "Cleaned previous release directory" -ForegroundColor Yellow
    }

    npx electron-builder --win
}

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
        $zipPath = Join-Path $PortableOutDir 'ArisePortable.zip'
        if (Test-Path $zipPath) {
            Remove-Item $zipPath -Force
        }

        Set-Location $PortableOutDir
        Compress-Archive -Path 'ArisePortable/*' -DestinationPath $zipPath
        Write-Host "Portable package archived to: $zipPath" -ForegroundColor Green
    }
} else {
    Write-Host "Skipping ZIP archive creation (per --SkipArchive)." -ForegroundColor Yellow
}

Write-Host "`n=== Portable build complete ===" -ForegroundColor Green
Write-Host "Portable directory: $PortableBinDir" -ForegroundColor Green
if (-not $SkipArchive) {
    Write-Host "ZIP archive:     $(Join-Path $PortableOutDir 'ArisePortable.zip')" -ForegroundColor Green
}
