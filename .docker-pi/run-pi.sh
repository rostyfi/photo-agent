#!/bin/bash
set -euo pipefail

# Navigate to the docker directory
cd "$(dirname "$0")"

# Ensure pi-config directory exists (Docker can't create dirs on NFS due to root squash)
mkdir -p "$(dirname "$0")/pi-config"

# Check for .env file
if [ ! -f .env ]; then
    echo "⚠️  No .env file found!"
    echo "   Copy .env.example to .env and fill in your API key:"
    echo ""
    echo "     cp .env.example .env"
    echo "     # then edit .env and uncomment your provider's key"
    echo ""
    echo "   Supported providers: Anthropic, OpenAI, Google, DeepSeek, Groq,"
    echo "   Mistral, xAI, Cerebras, OpenRouter, Together AI, Fireworks, HuggingFace"
    echo ""
    echo "   You can also use /login inside the container for OAuth-based auth."
    echo ""
fi

# Export current user IDs for the Dockerfile to prevent root-owned files
export USER_ID=$(id -u)
export GROUP_ID=$(id -g)

# Build and run in detached mode
PROJECT_NAME="pi-$(openssl rand -hex 4)"
docker-compose -p "$PROJECT_NAME" up -d --build

echo "----------------------------------------------------------------"
echo "Pi Agent container is built and running (Project: $PROJECT_NAME)."
if [ ! -f .env ]; then
    echo "⚠️  No .env file — you'll need to authenticate via /login or"
    echo "   pass API keys manually with: docker-compose -p $PROJECT_NAME exec -e KEY=... pi-agent bash"
else
    echo "✅ .env file detected — API keys will be passed to the container."
fi
echo "----------------------------------------------------------------"

# Attach to the container's shell by default (one-command workflow).
# Use --detach / -d to skip attaching and leave it running in the background.
if [ "${1:-}" = "--detach" ] || [ "${1:-}" = "-d" ]; then
    echo "Detached mode — container running in background."
    echo "Attach later with: docker-compose -p $PROJECT_NAME exec pi-agent bash"
else
    echo "Attaching to container…"
    echo "Run 'pi' once inside to start the agent."
    docker-compose -p "$PROJECT_NAME" exec pi-agent bash
fi
