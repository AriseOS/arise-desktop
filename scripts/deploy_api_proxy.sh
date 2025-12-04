#!/bin/bash

# API Proxy Docker Image Build Script
# Builds Docker image on the server

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
DOCKER_IMAGE="${DOCKER_IMAGE:-ami-api-proxy}"
VERSION="${1:-latest}"
TARGET_PLATFORM="${TARGET_PLATFORM:-linux/amd64}"

# Usage
usage() {
    echo "Usage: $0 [version]"
    echo ""
    echo "Environment variables:"
    echo "  DOCKER_IMAGE      - Docker image name (default: ami-api-proxy)"
    echo "  TARGET_PLATFORM   - Target platform (default: linux/amd64)"
    echo ""
    echo "Examples:"
    echo "  # Build with default version"
    echo "  ./scripts/deploy_api_proxy.sh"
    echo ""
    echo "  # Build with specific version"
    echo "  ./scripts/deploy_api_proxy.sh v1.0.0"
    echo ""
    echo "  # Build for ARM64 platform"
    echo "  TARGET_PLATFORM=linux/arm64 ./scripts/deploy_api_proxy.sh"
    exit 1
}

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    usage
fi

echo -e "${GREEN}=== API Proxy Image Build ===${NC}"
echo -e "${YELLOW}Version: ${VERSION}${NC}"
echo -e "${YELLOW}Platform: ${TARGET_PLATFORM}${NC}"
echo ""

# Get project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Build Docker image
echo -e "${YELLOW}Building Docker image...${NC}"

docker build \
    --platform ${TARGET_PLATFORM} \
    -t ${DOCKER_IMAGE}:${VERSION} \
    -f src/api_proxy/Dockerfile \
    .

if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Docker build failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Image built successfully${NC}"

# Get image size
IMAGE_SIZE=$(docker images ${DOCKER_IMAGE}:${VERSION} --format "{{.Size}}")
echo -e "${GREEN}Image size: ${IMAGE_SIZE}${NC}"
echo ""

# Summary
echo -e "${GREEN}=== Build Complete ===${NC}"
echo ""
echo "Image: ${DOCKER_IMAGE}:${VERSION}"
echo "Platform: ${TARGET_PLATFORM}"
echo "Size: ${IMAGE_SIZE}"
echo ""
echo "Next steps:"
echo "  1. Prepare config: /opt/ami/config/api-proxy.yaml"
echo "  2. Run container:"
echo ""
echo "     docker run -d \\"
echo "         --name ami-api-proxy \\"
echo "         --restart unless-stopped \\"
echo "         -p 127.0.0.1:8080:8080 \\"
echo "         -v /opt/ami/config/api-proxy.yaml:/app/src/api_proxy/config/api-proxy.yaml:ro \\"
echo "         -v /opt/ami/logs:/root/.ami/logs \\"
echo "         -v /opt/ami/database:/root/.ami/database \\"
echo "         ${DOCKER_IMAGE}:${VERSION}"
echo ""
