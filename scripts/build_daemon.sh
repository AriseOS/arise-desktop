#!/bin/bash

# Build script for Ami daemon
# Compiles daemon.py into a binary executable using PyInstaller
# Usage: ./build_daemon.sh [--force]
#   --force: Force rebuild even if binary is up to date

set -e  # Exit on error

# Parse arguments
FORCE_REBUILD=false
for arg in "$@"; do
    if [ "$arg" = "--force" ]; then
        FORCE_REBUILD=true
    fi
done

# Color output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Ami Daemon Build Script ===${NC}"

# Detect OS
OS_TYPE="$(uname -s)"
case "${OS_TYPE}" in
    Linux*)     OS=Linux;;
    Darwin*)    OS=macOS;;
    MINGW*)     OS=Windows;;
    *)          OS="UNKNOWN:${OS_TYPE}"
esac

echo -e "${YELLOW}Detected OS: ${OS}${NC}"

# Get project root (scripts/ -> ami/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
echo -e "${YELLOW}Project root: ${PROJECT_ROOT}${NC}"

# Navigate to app_backend directory
cd "${PROJECT_ROOT}/src/app_backend"
echo -e "${YELLOW}Working directory: $(pwd)${NC}"

# Create and use virtual environment for clean build
VENV_DIR="venv-build"
if [ ! -d "${VENV_DIR}" ]; then
    echo -e "${YELLOW}Creating build virtual environment...${NC}"
    python3 -m venv "${VENV_DIR}"
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source "${VENV_DIR}/bin/activate"

# Upgrade pip and install dependencies
echo -e "${YELLOW}Installing dependencies in clean environment...${NC}"
pip install --upgrade pip > /dev/null 2>&1
pip install pyinstaller > /dev/null 2>&1
pip install -r requirements.txt > /dev/null 2>&1
echo -e "${GREEN}✓ Dependencies installed${NC}"

DIST_DIR="dist/ami-daemon"

# Determine binary name based on OS
if [ "$OS" = "Windows" ]; then
    BINARY_NAME="ami-daemon.exe"
else
    BINARY_NAME="ami-daemon"
fi

# Always rebuild (no incremental build optimization)
echo -e "${YELLOW}Building daemon bundle (onedir)...${NC}"

# Clean previous build artifacts
echo -e "${YELLOW}Cleaning previous build artifacts...${NC}"
rm -rf build dist
rm -f ami-daemon ami-daemon.exe
echo -e "${GREEN}✓ Cleaned${NC}"

echo -e "${YELLOW}Running PyInstaller...${NC}"
pyinstaller daemon.spec --clean --noconfirm

# Check if build succeeded (onedir output)
if [ ! -d "${DIST_DIR}" ]; then
    echo -e "${RED}ERROR: Build failed - bundle directory not found (${DIST_DIR})${NC}"
    exit 1
fi

if [ ! -f "${DIST_DIR}/${BINARY_NAME}" ]; then
    echo -e "${RED}ERROR: Executable not found inside ${DIST_DIR}${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Bundle built successfully${NC}"

# Create Tauri resources directory if it doesn't exist
TAURI_RESOURCES_DIR="${PROJECT_ROOT}/src/clients/desktop_app/src-tauri/resources"
mkdir -p "${TAURI_RESOURCES_DIR}"

# Copy bundle to Tauri resources
TARGET_DIR="${TAURI_RESOURCES_DIR}/ami-daemon"
echo -e "${YELLOW}Copying bundle to Tauri resources...${NC}"
rm -rf "${TARGET_DIR}"
cp -R "${DIST_DIR}" "${TARGET_DIR}"

# Make executable runnable (Unix-like systems)
if [ "$OS" != "Windows" ]; then
    chmod +x "${TARGET_DIR}/${BINARY_NAME}"
fi

echo -e "${GREEN}✓ Bundle copied to: ${TARGET_DIR}${NC}"

# Note: Chromium browser is NOT bundled
# It will be auto-installed on first launch via 'playwright install chromium'
echo -e "${YELLOW}Chromium browser will be auto-installed on first app launch${NC}"

# Get bundle size (directory)
if [ "$OS" = "macOS" ] || [ "$OS" = "Linux" ]; then
    BUNDLE_SIZE=$(du -sh "${TARGET_DIR}" | cut -f1)
else
    BUNDLE_SIZE="unknown"
fi

echo -e "${GREEN}Bundle size: ${BUNDLE_SIZE}${NC}"

# Optional: Clean build artifacts
echo -e "${YELLOW}Cleaning build artifacts...${NC}"
rm -rf build
echo -e "${GREEN}✓ Build artifacts cleaned (kept dist/ for reference)${NC}"

echo ""
echo -e "${GREEN}=== Build Complete ===${NC}"
echo -e "Bundle location: ${GREEN}${TARGET_DIR}${NC}"
echo ""

# Deactivate virtual environment
deactivate 2>/dev/null || true

echo "Next steps:"
echo "1. Test the binary: ${TAURI_RESOURCES_DIR}/${BINARY_NAME}"
echo "2. Build Tauri app: cd src/clients/desktop_app/src-tauri && cargo tauri build"
echo ""
