#!/bin/bash

# Unified Build Script for Ami
# Builds, signs, and optionally notarizes the complete macOS application
# TypeScript daemon + Electron + macOS code signing

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DESKTOP_DIR="${PROJECT_ROOT}/src/clients/desktop_app"
DAEMON_TS_DIR="${DESKTOP_DIR}/daemon-ts"
DIST_DIR="${PROJECT_ROOT}/dist"

# Code signing identity
CODESIGN_IDENTITY="${CODESIGN_IDENTITY:-}"

# Notarization settings
SKIP_NOTARIZE="${SKIP_NOTARIZE:-true}"
NOTARIZE_KEYCHAIN_PROFILE="${NOTARIZE_KEYCHAIN_PROFILE:-ami-notary}"

# Parse arguments
CLEAN_BUILD=false
CREATE_DMG=true
SKIP_DAEMON=false
SKIP_ELECTRON=false
SKIP_SIGNING=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --clean)
            CLEAN_BUILD=true
            shift
            ;;
        --no-dmg)
            CREATE_DMG=false
            shift
            ;;
        --no-sign)
            SKIP_SIGNING=true
            shift
            ;;
        --skip-daemon)
            SKIP_DAEMON=true
            shift
            ;;
        --skip-electron)
            SKIP_ELECTRON=true
            shift
            ;;
        --notarize)
            SKIP_NOTARIZE=false
            shift
            ;;
        --identity)
            CODESIGN_IDENTITY="$2"
            shift 2
            ;;
        --help|-h)
            cat <<EOF
Usage: $0 [options]

Build, sign, and package Ami for macOS

Options:
  --clean              Clean build (remove all build artifacts first)
  --no-dmg             Skip DMG creation
  --no-sign            Skip code signing
  --skip-daemon        Skip daemon build (use existing)
  --skip-electron      Skip Electron build (use existing)
  --notarize           Enable notarization
  --identity NAME      Code signing identity
  --help, -h           Show this help

Environment Variables:
  CODESIGN_IDENTITY    Code signing identity (Developer ID Application)
  SKIP_NOTARIZE        Skip notarization (default: true)
  NOTARIZE_KEYCHAIN_PROFILE  Keychain profile for notarization

Examples:
  # Development build (no signing)
  ./scripts/build_app_macos.sh

  # Signed build
  export CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
  ./scripts/build_app_macos.sh

  # Signed build with DMG and notarization
  export CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
  ./scripts/build_app_macos.sh --notarize

  # Clean build
  ./scripts/build_app_macos.sh --clean

EOF
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}=== Ami macOS Build Script (Electron) ===${NC}"
echo ""

# Fail-fast: --notarize requires CODESIGN_IDENTITY
if [ "$SKIP_NOTARIZE" = false ] && [ -z "$CODESIGN_IDENTITY" ]; then
    echo -e "${RED}ERROR: --notarize requires CODESIGN_IDENTITY to be set${NC}"
    echo "Usage: export CODESIGN_IDENTITY=\"Developer ID Application: Your Name (TEAMID)\""
    echo "       $0 --notarize"
    exit 1
fi

# Check if running on macOS
if [ "$(uname -s)" != "Darwin" ]; then
    echo -e "${RED}ERROR: This script only runs on macOS${NC}"
    exit 1
fi

# electron-builder output directory
ELECTRON_DIST="${DESKTOP_DIR}/release"

# Clean build if requested
if [ "$CLEAN_BUILD" = true ]; then
    echo -e "${YELLOW}Cleaning build artifacts...${NC}"
    rm -rf "${DAEMON_TS_DIR}/dist"
    rm -rf "${ELECTRON_DIST}"
    rm -rf "${DESKTOP_DIR}/dist"
    rm -rf "${DIST_DIR}"
    echo -e "${GREEN}✓ Clean complete${NC}"
    echo ""
fi

# Determine if we should sign
SHOULD_SIGN=false
if [ "$SKIP_SIGNING" = true ]; then
    echo -e "${YELLOW}Code signing disabled (--no-sign)${NC}"
    echo ""
elif [ -n "$CODESIGN_IDENTITY" ]; then
    SHOULD_SIGN=true
    echo -e "${BLUE}Code signing enabled: ${CODESIGN_IDENTITY}${NC}"
    echo ""
else
    echo -e "${YELLOW}Code signing disabled (no CODESIGN_IDENTITY set)${NC}"
    echo ""
fi

# Step 1: Build TypeScript daemon
if [ "$SKIP_DAEMON" = false ]; then
    echo -e "${YELLOW}Step 1: Building TypeScript daemon...${NC}"

    cd "${DAEMON_TS_DIR}"

    npm ci
    npm run build

    BUILD_RESULT=$?

    if [ $BUILD_RESULT -ne 0 ]; then
        echo -e "${RED}ERROR: TypeScript daemon build failed${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ TypeScript daemon built${NC}"
    echo ""
else
    echo -e "${YELLOW}Step 1: Skipping daemon build${NC}"
    echo ""
fi

# Step 2: Build Electron application (includes frontend via electron:build)
if [ "$SKIP_ELECTRON" = false ]; then
    echo -e "${YELLOW}Step 2: Building Electron application...${NC}"

    cd "${DESKTOP_DIR}"

    # Build frontend (Vite)
    npm run build

    # Build Electron app (electron-builder produces .app in release/)
    npx electron-builder --mac

    BUILD_RESULT=$?

    if [ $BUILD_RESULT -ne 0 ]; then
        echo -e "${RED}ERROR: Electron build failed${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ Electron application built${NC}"
    echo ""
else
    echo -e "${YELLOW}Step 2: Skipping Electron build${NC}"
    echo ""
fi

# Find the .app bundle produced by electron-builder
APP_PATH=$(find "${ELECTRON_DIST}" -maxdepth 2 -name "*.app" -type d | head -1)

if [ -z "${APP_PATH}" ] || [ ! -d "${APP_PATH}" ]; then
    echo -e "${RED}ERROR: .app bundle not found in ${ELECTRON_DIST}${NC}"
    exit 1
fi

echo -e "${BLUE}App bundle: ${APP_PATH}${NC}"

# Step 3: Sign Ami.app
if [ "$SHOULD_SIGN" = true ]; then
    echo -e "${YELLOW}Step 3: Signing Ami.app...${NC}"

    echo "  Signing Ami.app..."
    codesign --deep --force --options runtime --timestamp \
        --sign "${CODESIGN_IDENTITY}" \
        "${APP_PATH}"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}    ✓ Ami.app signed${NC}"
    else
        echo -e "${RED}ERROR: Failed to sign Ami.app${NC}"
        exit 1
    fi

    # Verify
    echo "  Verifying signatures..."
    codesign --verify --verbose=2 "${APP_PATH}" 2>&1

    echo -e "${GREEN}✓ Signing complete${NC}"
    echo ""
else
    echo -e "${YELLOW}Step 3: Skipping signing (no CODESIGN_IDENTITY)${NC}"
    echo ""
fi

# Step 4: Create DMG (if electron-builder didn't already, or for custom DMG)
if [ "$CREATE_DMG" = true ]; then
    # Check if electron-builder already created a DMG
    EXISTING_DMG=$(find "${ELECTRON_DIST}" -maxdepth 1 -name "*.dmg" | head -1)

    if [ -n "${EXISTING_DMG}" ] && [ "$SHOULD_SIGN" = false ]; then
        echo -e "${YELLOW}Step 4: Using electron-builder DMG${NC}"
        mkdir -p "${DIST_DIR}"
        cp "${EXISTING_DMG}" "${DIST_DIR}/"
        DMG_PATH="${DIST_DIR}/$(basename "${EXISTING_DMG}")"
        echo -e "${GREEN}✓ DMG copied: ${DMG_PATH}${NC}"
    else
        echo -e "${YELLOW}Step 4: Creating DMG...${NC}"

        mkdir -p "${DIST_DIR}"

        VERSION=$(grep '"version"' "${DESKTOP_DIR}/package.json" | head -1 | sed 's/.*"version": *"\([^"]*\)".*/\1/')
        DMG_NAME="Ami-${VERSION}.dmg"
        DMG_PATH="${DIST_DIR}/${DMG_NAME}"

        # Create temporary staging directory
        TMP_DIR=$(mktemp -d)
        DMG_STAGING="${TMP_DIR}/dmg_staging"
        mkdir -p "${DMG_STAGING}"

        cp -R "${APP_PATH}" "${DMG_STAGING}/"
        ln -s /Applications "${DMG_STAGING}/Applications"

        rm -f "${DMG_PATH}"

        hdiutil create \
            -volname "Ami" \
            -srcfolder "${DMG_STAGING}" \
            -ov \
            -format UDZO \
            "${DMG_PATH}"

        rm -rf "${TMP_DIR}"

        echo -e "${GREEN}✓ DMG created: ${DMG_PATH}${NC}"
    fi

    # Sign DMG
    if [ "$SHOULD_SIGN" = true ]; then
        echo "  Signing DMG..."
        codesign --force --timestamp --sign "${CODESIGN_IDENTITY}" "${DMG_PATH}"
        echo -e "${GREEN}    ✓ DMG signed${NC}"
    fi
    echo ""
else
    echo -e "${YELLOW}Step 4: Skipping DMG creation${NC}"
    echo ""
fi

# Step 5: Notarization
if [ "$SHOULD_SIGN" = true ] && [ "$CREATE_DMG" = true ] && [ "$SKIP_NOTARIZE" = false ]; then
    echo -e "${YELLOW}Step 5: Notarizing DMG...${NC}"
    echo "This may take several minutes..."

    xcrun notarytool submit "${DMG_PATH}" \
        --keychain-profile "${NOTARIZE_KEYCHAIN_PROFILE}" \
        --wait

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Notarization successful${NC}"

        # Staple
        echo "  Stapling notarization ticket..."
        xcrun stapler staple "${DMG_PATH}"
        echo -e "${GREEN}    ✓ Stapled${NC}"
    else
        echo -e "${RED}ERROR: Notarization failed${NC}"
        exit 1
    fi
    echo ""
else
    echo -e "${YELLOW}Step 5: Skipping notarization${NC}"
    echo ""
fi

# Summary
echo -e "${GREEN}=== Build Complete ===${NC}"
echo ""
echo "Output:"
echo "  App:  ${APP_PATH}"
if [ "$CREATE_DMG" = true ]; then
    echo "  DMG:  ${DMG_PATH}"
    echo "  Size: $(du -h "${DMG_PATH}" | cut -f1)"
fi
echo ""

if [ "$SHOULD_SIGN" = false ]; then
    echo -e "${YELLOW}⚠️  UNSIGNED - development build only${NC}"
elif [ "$SKIP_NOTARIZE" = true ]; then
    echo -e "${YELLOW}⚠️  SIGNED but NOT NOTARIZED${NC}"
    echo "To notarize, run: ./scripts/build_app_macos.sh --notarize"
else
    echo -e "${GREEN}✅ SIGNED, NOTARIZED, and STAPLED - ready for distribution!${NC}"
fi
echo ""
