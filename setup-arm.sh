#!/usr/bin/env bash
# ARM64 (Raspberry Pi) setup and run for Local Photo Agent via Docker Compose
#
# This script uses Dockerfile.arm which uses pre-built ARM64 wheels for sqlite-vec
# (available since sqlite-vec 0.1.9a1).
#
# Usage:
#   ./setup-arm.sh                     # Start without mounting a host folder
#   ./setup-arm.sh /path/to/photos     # Mount a host folder into /photos in the container
#   ./setup-arm.sh --no-cache          # Build without using Docker cache
#   ./setup-arm.sh --no-cache /path/to/photos  # Build without cache and mount folder
#   ./setup-arm.sh --port 9000         # Run the app on a custom host port

set -e

# Parse arguments
USE_CACHE=true
FOLDER_PATH=""
DASH_PORT=""

# Process all arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-cache)
            USE_CACHE=false
            shift
            ;;
        --port)
            if [[ -z "$2" ]]; then
                echo "Error: --port requires a value."
                exit 1
            fi
            DASH_PORT="$2"
            shift 2
            ;;
        *)
            # Assume it's a folder path if it's not a flag we recognize
            if [[ "$1" != -* ]]; then
                FOLDER_PATH="$1"
            fi
            shift
            ;;
    esac
done

COMPOSE_OVERRIDE="docker-compose.override.yml"
DOCKERFILE_OVERRIDE="docker-compose.arm.override.yml"

# Handle folder mounting via compose override
if [ -n "$FOLDER_PATH" ]; then
    if [ ! -d "$FOLDER_PATH" ]; then
        echo "Error: '$FOLDER_PATH' is not a directory or does not exist."
        exit 1
    fi

    echo "Changing to folder: $FOLDER_PATH"
    ABS_FOLDER="$(cd "$FOLDER_PATH" && pwd)" || { echo "Error: Failed to change to directory $FOLDER_PATH"; exit 1; }

    cat > "$COMPOSE_OVERRIDE" <<EOF
services:
  photo-agent:
    volumes:
      - "${ABS_FOLDER}:/photos"
EOF

    echo "Mounting host folder: $ABS_FOLDER -> /photos"
    echo "Debug: Folder path processed successfully"
else
    if [ -f "$COMPOSE_OVERRIDE" ]; then
        rm -f "$COMPOSE_OVERRIDE"
    fi
fi

echo "Creating ARM64 Dockerfile override..."
# Create ARM-specific compose override to use Dockerfile.arm
cat > "$DOCKERFILE_OVERRIDE" <<'EOF'
services:
  photo-agent:
    build:
      context: .
      dockerfile: Dockerfile.arm
EOF

echo "ARM64 Dockerfile override created."
echo "================================================"
echo "Local Photo Agent - ARM64 Docker Setup"
echo "================================================"

# Display cache status
if [ "$USE_CACHE" = true ]; then
    echo "Using Docker cache: YES"
else
    echo "Using Docker cache: NO (--no-cache specified)"
fi
echo ""

# Use 'docker compose' when available, otherwise fall back to 'docker-compose'
echo "Checking for docker..."
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed."
    exit 1
fi

# Try docker compose first, fall back to docker-compose
if timeout 3 docker compose version &>/dev/null; then
    COMPOSE_CMD="docker compose"
    echo "Using docker compose plugin"
else
    COMPOSE_CMD="docker-compose"
    echo "Using docker-compose command"
fi

echo "Using compose command: $COMPOSE_CMD"
echo "Using ARM64 Dockerfile (Dockerfile.arm)"
echo ""

# Build and run
export USER_UID=$(id -u)
export USER_GID=$(id -g)
if [ -n "$DASH_PORT" ]; then
    export LOCAL_PHOTO_AGENT_DASH_PORT="$DASH_PORT"
fi
echo "Building container and starting app (UID=$USER_UID, GID=$USER_GID)..."
echo "Using pre-built ARM64 wheels for sqlite-vec..."
echo ""

# Build command with or without cache
if [ "$USE_CACHE" = true ]; then
    $COMPOSE_CMD -f docker-compose.yml -f "$DOCKERFILE_OVERRIDE" -f "$COMPOSE_OVERRIDE" up -d --build
else
    echo "Building without Docker cache..."
    $COMPOSE_CMD -f docker-compose.yml -f "$DOCKERFILE_OVERRIDE" -f "$COMPOSE_OVERRIDE" build --no-cache
    $COMPOSE_CMD -f docker-compose.yml -f "$DOCKERFILE_OVERRIDE" -f "$COMPOSE_OVERRIDE" up -d
fi

# Clean up the temporary arm override file
rm -f "$DOCKERFILE_OVERRIDE"

echo ""
echo "================================================"
echo "Done! The app is running."
echo "================================================"
echo ""
echo "Open in your browser:"
echo "   http://localhost:${DASH_PORT:-8050}"
echo ""
if [ -n "$FOLDER_PATH" ]; then
    echo "Mounted folder inside container:"
    echo "   /photos"
    echo ""
fi
echo "View logs:"
echo "   $COMPOSE_CMD -f docker-compose.yml -f $COMPOSE_OVERRIDE logs -f"
echo ""
echo "Stop the app:"
echo "   $COMPOSE_CMD -f docker-compose.yml -f $COMPOSE_OVERRIDE down"
echo ""
