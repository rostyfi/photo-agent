#!/usr/bin/env bash
# Setup and run Photo Feature Extractor via Docker Compose
#
# Usage:
#   ./setup.sh                     # Start without mounting a host folder
#   ./setup.sh /path/to/photos     # Mount a host folder into /photos in the container
#   ./setup.sh --no-cache          # Build without using Docker cache
#   ./setup.sh --no-cache /path/to/photos  # Build without cache and mount folder
#   ./setup.sh --port 9000         # Run the app on a custom host port

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

# Display cache status
if [ "$USE_CACHE" = true ]; then
    echo "Using Docker cache: YES"
else
    echo "Using Docker cache: NO (--no-cache specified)"
fi
echo ""

COMPOSE_OVERRIDE="docker-compose.override.yml"

# Handle folder mounting via compose override
if [ -n "$FOLDER_PATH" ]; then
    if [ ! -d "$FOLDER_PATH" ]; then
        echo "Error: '$FOLDER_PATH' is not a directory or does not exist."
        exit 1
    fi

    ABS_FOLDER="$(cd "$FOLDER_PATH" && pwd)"

    cat > "$COMPOSE_OVERRIDE" <<EOF
services:
  photo-agent:
    volumes:
      - "${ABS_FOLDER}:/photos"
    environment:
      - LOCAL_PHOTO_AGENT_REVEAL_MAP=/photos=${ABS_FOLDER}
EOF

    echo "Mounting host folder: $ABS_FOLDER -> /photos"
else
    if [ -f "$COMPOSE_OVERRIDE" ]; then
        rm -f "$COMPOSE_OVERRIDE"
    fi
fi

echo "================================================"
echo "Photo Feature Extractor - Docker Setup"
echo "================================================"

# Use 'docker compose' when available, otherwise fall back to 'docker-compose'
if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

echo "Using compose command: $COMPOSE_CMD"
echo ""

# Build and run
export USER_UID=$(id -u)
export USER_GID=$(id -g)
if [ -n "$DASH_PORT" ]; then
    export LOCAL_PHOTO_AGENT_DASH_PORT="$DASH_PORT"
fi
echo "Building container and starting app (UID=$USER_UID, GID=$USER_GID)..."

# Build command with or without cache
if [ "$USE_CACHE" = true ]; then
    $COMPOSE_CMD up -d --build
else
    echo "Building without Docker cache..."
    $COMPOSE_CMD build --no-cache
    $COMPOSE_CMD up -d
fi

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
echo "   $COMPOSE_CMD logs -f"
echo ""
echo "Stop the app:"
echo "   $COMPOSE_CMD down"
echo ""
