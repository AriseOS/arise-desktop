#!/bin/bash

# API Proxy Deployment Script
# Builds Docker image locally and deploys to remote server

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
DOCKER_IMAGE="${DOCKER_IMAGE:-ami-api-proxy}"
VERSION="${1:-latest}"
DOCKER_REGISTRY="${DOCKER_REGISTRY:-}"  # e.g., "your-username" for Docker Hub
REMOTE_SERVER="${REMOTE_SERVER:-}"
REMOTE_PATH="${REMOTE_PATH:-/opt/ami}"

# Usage
usage() {
    echo "Usage: $0 [version]"
    echo ""
    echo "Environment variables:"
    echo "  DOCKER_IMAGE      - Docker image name (default: ami-api-proxy)"
    echo "  DOCKER_REGISTRY   - Registry prefix (e.g., 'your-username' for Docker Hub)"
    echo "  REMOTE_SERVER     - Remote server (e.g., 'user@server.com')"
    echo "  REMOTE_PATH       - Path on remote server (default: /opt/ami)"
    echo "  TARGET_PLATFORM   - Target platform (default: linux/amd64)"
    echo "                      Common values: linux/amd64, linux/arm64"
    echo ""
    echo "Examples:"
    echo "  # Build only (no push/deploy)"
    echo "  $0"
    echo ""
    echo "  # Build for Intel servers (from Apple Silicon Mac)"
    echo "  TARGET_PLATFORM=linux/amd64 $0 v1.0.0"
    echo ""
    echo "  # Build and push to Docker Hub"
    echo "  DOCKER_REGISTRY=your-username TARGET_PLATFORM=linux/amd64 $0 v1.0.0"
    echo ""
    echo "  # Build, push, and deploy"
    echo "  DOCKER_REGISTRY=your-username REMOTE_SERVER=user@server.com $0 v1.0.0"
    exit 1
}

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    usage
fi

echo -e "${GREEN}=== API Proxy Deployment ===${NC}"
echo -e "${YELLOW}Version: ${VERSION}${NC}"

# Get project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Build full image name
if [ -n "$DOCKER_REGISTRY" ]; then
    FULL_IMAGE="${DOCKER_REGISTRY}/${DOCKER_IMAGE}"
else
    FULL_IMAGE="${DOCKER_IMAGE}"
fi

echo -e "${YELLOW}Image: ${FULL_IMAGE}:${VERSION}${NC}"
echo ""

# Step 1: Build Docker image
echo -e "${YELLOW}Step 1: Building Docker image...${NC}"

# Detect target platform
TARGET_PLATFORM="${TARGET_PLATFORM:-linux/amd64}"
echo -e "${YELLOW}Target platform: ${TARGET_PLATFORM}${NC}"

docker build \
    --platform ${TARGET_PLATFORM} \
    -t ${FULL_IMAGE}:${VERSION} \
    -f src/api_proxy/Dockerfile \
    .

if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Docker build failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Image built successfully${NC}"

# Get image size
IMAGE_SIZE=$(docker images ${FULL_IMAGE}:${VERSION} --format "{{.Size}}")
echo -e "${GREEN}Image size: ${IMAGE_SIZE}${NC}"
echo ""

# Step 2: Push to registry (if configured)
if [ -n "$DOCKER_REGISTRY" ]; then
    echo -e "${YELLOW}Step 2: Pushing to Docker registry...${NC}"

    docker push ${FULL_IMAGE}:${VERSION}

    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: Docker push failed${NC}"
        echo "Make sure you're logged in: docker login"
        exit 1
    fi

    echo -e "${GREEN}✓ Image pushed to registry${NC}"

    # Tag as 'latest' if this is a version tag
    if [[ "${VERSION}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo -e "${YELLOW}Tagging as latest...${NC}"
        docker tag ${FULL_IMAGE}:${VERSION} ${FULL_IMAGE}:latest
        docker push ${FULL_IMAGE}:latest
        echo -e "${GREEN}✓ Latest tag pushed${NC}"
    fi
    echo ""
else
    echo -e "${YELLOW}Step 2: Skipping push (DOCKER_REGISTRY not set)${NC}"
    echo ""
fi

# Step 3: Deploy to remote server (if configured)
if [ -n "$REMOTE_SERVER" ]; then
    echo -e "${YELLOW}Step 3: Deploying to remote server...${NC}"

    if [ -z "$DOCKER_REGISTRY" ]; then
        echo -e "${RED}ERROR: Cannot deploy without DOCKER_REGISTRY${NC}"
        echo "Set DOCKER_REGISTRY to push and deploy"
        exit 1
    fi

    echo -e "${YELLOW}Connecting to ${REMOTE_SERVER}...${NC}"

    ssh ${REMOTE_SERVER} << EOF
        set -e

        echo "Pulling latest image..."
        docker pull ${FULL_IMAGE}:${VERSION}

        echo "Checking if container exists..."
        if docker ps -a --format '{{.Names}}' | grep -q '^ami-api-proxy$'; then
            echo "Stopping existing container..."
            docker stop ami-api-proxy || true
            docker rm ami-api-proxy || true
        fi

        echo "Starting new container..."
        docker run -d \
            --name ami-api-proxy \
            --restart unless-stopped \
            -p 8080:8080 \
            -v ${REMOTE_PATH}/logs:/root/.ami/logs \
            -v ${REMOTE_PATH}/database:/root/.ami/database \
            ${FULL_IMAGE}:${VERSION}

        echo "Waiting for service to start..."
        sleep 5

        echo "Checking health..."
        docker logs ami-api-proxy --tail 20

        curl -f http://localhost:8080/health || (echo "Health check failed" && exit 1)

        echo "✓ Service is healthy"
EOF

    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: Deployment failed${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ Deployed to remote server${NC}"
    echo ""
else
    echo -e "${YELLOW}Step 3: Skipping deployment (REMOTE_SERVER not set)${NC}"
    echo ""
fi

# Summary
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo ""
echo "Image: ${FULL_IMAGE}:${VERSION}"

if [ -n "$DOCKER_REGISTRY" ]; then
    echo "Registry: ✓ Pushed"
else
    echo "Registry: ⊘ Not pushed (local only)"
fi

if [ -n "$REMOTE_SERVER" ]; then
    echo "Deployment: ✓ Deployed to ${REMOTE_SERVER}"
    echo ""
    echo "To check logs:"
    echo "  ssh ${REMOTE_SERVER} 'docker logs -f ami-api-proxy'"
    echo ""
    echo "To check status:"
    echo "  ssh ${REMOTE_SERVER} 'docker ps | grep ami-api-proxy'"
else
    echo "Deployment: ⊘ Not deployed (local only)"
    echo ""
    echo "To run locally:"
    echo "  docker run -d -p 8080:8080 ${FULL_IMAGE}:${VERSION}"
fi
