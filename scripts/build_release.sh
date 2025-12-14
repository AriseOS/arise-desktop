#!/bin/bash

# Complete release build script for Ami
# Builds Python daemon binary and Tauri application

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== Ami Complete Release Build ===${NC}"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Step 1: Build Python daemon binary
echo -e "${YELLOW}Step 1: Building Python daemon binary...${NC}"
"${SCRIPT_DIR}/build_daemon.sh"

if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Failed to build daemon binary${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Daemon binary built${NC}"
echo ""

# Step 2: Update tauri.conf.json to include resources
echo -e "${YELLOW}Step 2: Configuring Tauri resources...${NC}"

TAURI_CONF="${PROJECT_ROOT}/src/clients/desktop_app/src-tauri/tauri.conf.json"
TAURI_CONF_BACKUP="${TAURI_CONF}.backup"

# Backup original config
cp "${TAURI_CONF}" "${TAURI_CONF_BACKUP}"

# Add resources configuration (Tauri 2.x resource map format)
if command -v jq &> /dev/null; then
    # Use jq if available
    jq '.bundle.resources = {"resources/ami-daemon": "ami-daemon"}' "${TAURI_CONF}" > "${TAURI_CONF}.tmp"
    mv "${TAURI_CONF}.tmp" "${TAURI_CONF}"
else
    # Fallback: use sed (less robust but works)
    sed -i.bak 's/"bundle": {/"bundle": { "resources": {"resources\/ami-daemon": "ami-daemon"}/' "${TAURI_CONF}"
    rm -f "${TAURI_CONF}.bak"
fi

echo -e "${GREEN}✓ Resources configured${NC}"
echo ""

# Step 3: Build frontend first
echo -e "${YELLOW}Step 3: Building frontend...${NC}"
cd "${PROJECT_ROOT}/src/clients/desktop_app"
npm run build

if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Failed to build frontend${NC}"
    # Restore original config
    mv "${TAURI_CONF_BACKUP}" "${TAURI_CONF}"
    exit 1
fi

echo -e "${GREEN}✓ Frontend built${NC}"
echo ""

# Step 4: Build Tauri application
echo -e "${YELLOW}Step 4: Building Tauri application...${NC}"
npx tauri build --bundles app

if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Failed to build Tauri application${NC}"
    # Restore original config
    mv "${TAURI_CONF_BACKUP}" "${TAURI_CONF}"
    exit 1
fi

# Restore original config
mv "${TAURI_CONF_BACKUP}" "${TAURI_CONF}"

echo -e "${GREEN}✓ Tauri application built${NC}"
echo ""

# Step 5: Show results
echo -e "${GREEN}=== Build Complete ===${NC}"
echo ""
echo "Release artifacts:"

OS_TYPE="$(uname -s)"
case "${OS_TYPE}" in
    Darwin*)
        echo "  macOS App: ${PROJECT_ROOT}/src/clients/desktop_app/src-tauri/target/release/bundle/macos/Ami.app"
        ;;
    Linux*)
        echo "  Linux Package: ${PROJECT_ROOT}/src/clients/desktop_app/src-tauri/target/release/bundle/"
        ;;
    MINGW*)
        echo "  Windows Installer: ${PROJECT_ROOT}/src/clients/desktop_app/src-tauri/target/release/bundle/msi/"
        ;;
esac

echo ""
echo "Next steps:"
echo "1. Test the release build"
echo "2. Run: open target/release/bundle/macos/Ami.app (macOS)"
echo "3. Verify daemon uses binary: check logs for 'Found bundled daemon binary'"
