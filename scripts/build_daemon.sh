#!/bin/bash

# Build script for Ami daemon
# Compiles daemon.py into a binary executable using PyInstaller

set -e  # Exit on error

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

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo -e "${RED}ERROR: PyInstaller not found${NC}"
    echo "Please install PyInstaller: pip install pyinstaller"
    exit 1
fi

echo -e "${GREEN}✓ PyInstaller found${NC}"

# Clean previous build artifacts
echo -e "${YELLOW}Cleaning previous build artifacts...${NC}"
rm -rf build dist
rm -f ami-daemon ami-daemon.exe
echo -e "${GREEN}✓ Cleaned${NC}"

# Run PyInstaller
echo -e "${YELLOW}Running PyInstaller...${NC}"
pyinstaller daemon.spec --clean --noconfirm

# Check if build succeeded
if [ ! -f "dist/ami-daemon" ] && [ ! -f "dist/ami-daemon.exe" ]; then
    echo -e "${RED}ERROR: Build failed - binary not found in dist/${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Binary built successfully${NC}"

# Determine binary name based on OS
if [ "$OS" = "Windows" ]; then
    BINARY_NAME="ami-daemon.exe"
else
    BINARY_NAME="ami-daemon"
fi

# Create Tauri resources directory if it doesn't exist
TAURI_RESOURCES_DIR="${PROJECT_ROOT}/src/clients/desktop_app/src-tauri/resources"
mkdir -p "${TAURI_RESOURCES_DIR}"

# Copy binary to Tauri resources
echo -e "${YELLOW}Copying binary to Tauri resources...${NC}"
cp "dist/${BINARY_NAME}" "${TAURI_RESOURCES_DIR}/${BINARY_NAME}"

# Make it executable (Unix-like systems)
if [ "$OS" != "Windows" ]; then
    chmod +x "${TAURI_RESOURCES_DIR}/${BINARY_NAME}"
fi

echo -e "${GREEN}✓ Binary copied to: ${TAURI_RESOURCES_DIR}/${BINARY_NAME}${NC}"

# Get binary size
if [ "$OS" = "macOS" ]; then
    BINARY_SIZE=$(du -h "${TAURI_RESOURCES_DIR}/${BINARY_NAME}" | cut -f1)
elif [ "$OS" = "Linux" ]; then
    BINARY_SIZE=$(du -h "${TAURI_RESOURCES_DIR}/${BINARY_NAME}" | cut -f1)
else
    BINARY_SIZE="unknown"
fi

echo -e "${GREEN}Binary size: ${BINARY_SIZE}${NC}"

# Optional: Clean build artifacts
echo -e "${YELLOW}Cleaning build artifacts...${NC}"
rm -rf build
echo -e "${GREEN}✓ Build artifacts cleaned (kept dist/ for reference)${NC}"

echo ""
echo -e "${GREEN}=== Build Complete ===${NC}"
echo -e "Binary location: ${GREEN}${TAURI_RESOURCES_DIR}/${BINARY_NAME}${NC}"
echo ""
echo "Next steps:"
echo "1. Test the binary: ${TAURI_RESOURCES_DIR}/${BINARY_NAME}"
echo "2. Build Tauri app: cd src/clients/desktop_app/src-tauri && cargo tauri build"
echo ""
