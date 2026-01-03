<#
.SYNOPSIS
    Downloads and prepares a minimal Git Bash bundle for Windows packaging.

.DESCRIPTION
    This script downloads PortableGit and extracts only the essential files
    needed for Claude Code CLI to run. This reduces the bundle size significantly.

.NOTES
    Run this script before building the Windows app to ensure git-bash is available.
#>

param(
    [string]$OutputDir = "src/clients/desktop_app/ami_daemon/resources/git-bash"
)

$ErrorActionPreference = "Stop"

# PortableGit download URL (64-bit)
$GitVersion = "2.47.1"
$GitDownloadUrl = "https://github.com/git-for-windows/git/releases/download/v${GitVersion}.windows.1/PortableGit-${GitVersion}-64-bit.7z.exe"
$TempDir = Join-Path $env:TEMP "git-bash-extract"
$DownloadPath = Join-Path $TempDir "PortableGit.7z.exe"

Write-Host "=== Preparing Git Bash for Windows Build ===" -ForegroundColor Cyan

# Create temp directory
if (Test-Path $TempDir) {
    Remove-Item -Recurse -Force $TempDir
}
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

# Download PortableGit
Write-Host "Downloading PortableGit v${GitVersion}..." -ForegroundColor Yellow
Invoke-WebRequest -Uri $GitDownloadUrl -OutFile $DownloadPath -UseBasicParsing

# Extract using 7z (self-extracting archive)
Write-Host "Extracting PortableGit..." -ForegroundColor Yellow
$ExtractDir = Join-Path $TempDir "PortableGit"
& $DownloadPath -y -o"$ExtractDir" | Out-Null

# Create output directory
$OutputPath = Join-Path (Get-Location) $OutputDir
if (Test-Path $OutputPath) {
    Remove-Item -Recurse -Force $OutputPath
}
New-Item -ItemType Directory -Path $OutputPath -Force | Out-Null

Write-Host "Copying essential files to $OutputPath..." -ForegroundColor Yellow

# Essential directories and files for bash to work
$EssentialItems = @(
    # Core bash and utilities
    "usr/bin/bash.exe",
    "usr/bin/sh.exe",
    "usr/bin/env.exe",
    "usr/bin/cat.exe",
    "usr/bin/ls.exe",
    "usr/bin/cp.exe",
    "usr/bin/mv.exe",
    "usr/bin/rm.exe",
    "usr/bin/mkdir.exe",
    "usr/bin/grep.exe",
    "usr/bin/sed.exe",
    "usr/bin/awk.exe",
    "usr/bin/head.exe",
    "usr/bin/tail.exe",
    "usr/bin/wc.exe",
    "usr/bin/sort.exe",
    "usr/bin/uniq.exe",
    "usr/bin/tr.exe",
    "usr/bin/cut.exe",
    "usr/bin/tee.exe",
    "usr/bin/xargs.exe",
    "usr/bin/find.exe",
    "usr/bin/which.exe",
    "usr/bin/dirname.exe",
    "usr/bin/basename.exe",
    "usr/bin/readlink.exe",
    "usr/bin/realpath.exe",
    "usr/bin/pwd.exe",
    "usr/bin/echo.exe",
    "usr/bin/printf.exe",
    "usr/bin/test.exe",
    "usr/bin/true.exe",
    "usr/bin/false.exe",
    "usr/bin/sleep.exe",
    "usr/bin/date.exe",
    "usr/bin/touch.exe",

    # Required DLLs for MSYS2
    "usr/bin/msys-2.0.dll",
    "usr/bin/msys-iconv-2.dll",
    "usr/bin/msys-intl-8.dll",
    "usr/bin/msys-pcre2-8-0.dll",
    "usr/bin/msys-gmp-10.dll",
    "usr/bin/msys-mpfr-6.dll",
    "usr/bin/msys-readline8.dll",
    "usr/bin/msys-ncursesw6.dll",

    # Etc config files
    "etc/profile",
    "etc/bash.bashrc",
    "etc/nsswitch.conf",
    "etc/fstab"
)

# Copy essential items
foreach ($item in $EssentialItems) {
    $SourcePath = Join-Path $ExtractDir $item
    $DestPath = Join-Path $OutputPath $item

    if (Test-Path $SourcePath) {
        $DestDir = Split-Path $DestPath -Parent
        if (-not (Test-Path $DestDir)) {
            New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
        }
        Copy-Item -Path $SourcePath -Destination $DestPath -Force
        Write-Host "  Copied: $item" -ForegroundColor Gray
    } else {
        Write-Host "  Missing: $item" -ForegroundColor DarkYellow
    }
}

# Create a minimal /tmp directory
$TmpDir = Join-Path $OutputPath "tmp"
New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null

# Calculate size
$Size = (Get-ChildItem -Recurse -Path $OutputPath | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host ""
Write-Host "=== Git Bash Bundle Complete ===" -ForegroundColor Green
Write-Host "Location: $OutputPath" -ForegroundColor Cyan
Write-Host "Size: $([math]::Round($Size, 2)) MB" -ForegroundColor Cyan

# Cleanup
Remove-Item -Recurse -Force $TempDir

Write-Host ""
Write-Host "To use this in your app, set CLAUDE_CODE_GIT_BASH_PATH to:" -ForegroundColor Yellow
Write-Host "  <app_dir>/resources/git-bash/usr/bin/bash.exe" -ForegroundColor White
