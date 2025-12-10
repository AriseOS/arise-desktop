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

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo -e "${RED}ERROR: PyInstaller not found${NC}"
    echo "Please install PyInstaller: pip install pyinstaller"
    exit 1
fi

echo -e "${GREEN}✓ PyInstaller found${NC}"

# Determine binary name based on OS
if [ "$OS" = "Windows" ]; then
    BINARY_NAME="ami-daemon.exe"
else
    BINARY_NAME="ami-daemon"
fi

# Check if we need to rebuild
NEED_REBUILD=false

if [ "$FORCE_REBUILD" = true ]; then
    echo -e "${YELLOW}--force flag set, rebuilding${NC}"
    NEED_REBUILD=true
elif [ ! -f "dist/${BINARY_NAME}" ]; then
    echo -e "${YELLOW}Binary not found, need to build${NC}"
    NEED_REBUILD=true
else
    # Check if source files are newer than binary
    if [ "daemon.py" -nt "dist/${BINARY_NAME}" ] || \
       [ "daemon.spec" -nt "dist/${BINARY_NAME}" ] || \
       find ../.. -name "*.py" -path "*/src/app_backend/*" -newer "dist/${BINARY_NAME}" | grep -q .; then
        echo -e "${YELLOW}Source files changed, need to rebuild${NC}"
        NEED_REBUILD=true
    else
        echo -e "${GREEN}✓ Binary is up to date, skipping build${NC}"
    fi
fi

if [ "$NEED_REBUILD" = true ]; then
    # Clean previous build artifacts
    echo -e "${YELLOW}Cleaning previous build artifacts...${NC}"
    rm -rf build dist
    rm -f ami-daemon ami-daemon.exe
    echo -e "${GREEN}✓ Cleaned${NC}"

    # Run PyInstaller
    echo -e "${YELLOW}Running PyInstaller...${NC}"
    pyinstaller daemon.spec --clean --noconfirm
else
    echo -e "${GREEN}Skipping PyInstaller build (use --force to rebuild)${NC}"
fi

# Check if build succeeded
if [ ! -f "dist/ami-daemon" ] && [ ! -f "dist/ami-daemon.exe" ]; then
    echo -e "${RED}ERROR: Build failed - binary not found in dist/${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Binary built successfully${NC}"

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

# Note: Chromium browser is NOT bundled
# It will be auto-installed on first launch via 'playwright install chromium'
echo -e "${YELLOW}Chromium browser will be auto-installed on first app launch${NC}"

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
