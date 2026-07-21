# Running Pi Agent in Docker

This setup isolates the Pi coding agent within a Docker container to prevent it from accessing or modifying system files outside of the project directory, while still allowing it to edit the codebase.

## Setup Components

The configuration is located in the `.docker-pi/` directory:
- `Dockerfile`: Defines the environment (Node.js, Python 3.12, Pi Agent).
- `docker-compose.yml`: Manages volumes and networking.
- `run-pi.sh`: A helper script to launch the container with correct user permissions.

## How to Run

### 1. Prerequisites
- Docker and Docker Compose installed on your host machine.
- Access to the project directory.

### 2. Configure Authentication
Copy the example env file and fill in your API key:
```bash
cp .docker-pi/.env.example .docker-pi/.env
# Edit .docker-pi/.env and uncomment your provider's key (e.g., ANTHROPIC_API_KEY)
```

Supported providers: Anthropic, OpenAI, Google Gemini, DeepSeek, Groq, Mistral, xAI, Cerebras, OpenRouter, Together AI, Fireworks, HuggingFace.

Alternatively, skip the `.env` file and authenticate interactively with `/login` inside the container (requires a browser for OAuth).

### 3. Launch the Agent (one command)
Run the helper script from the project root:
```bash
chmod +x .docker-pi/run-pi.sh
./.docker-pi/run-pi.sh
```

This builds, starts the container, and automatically drops you into its shell.

Once inside, start the agent:
```bash
pi
```

To run in detached/background mode instead:
```bash
./.docker-pi/run-pi.sh --detach
# Later: docker exec -it pi-coding-agent bash
```

## Key Security Features
- **Filesystem Isolation**: The agent only sees the project folder and the container's internal OS. It cannot access your host's `/etc`, `/home`, or other sensitive directories.
- **User Mapping**: The script maps your host User ID (`UID`) and Group ID (`GID`) to the container user, ensuring that any files created by the agent are still owned by you on the host.
- **Network Access**: Uses `network_mode: host` so the agent can communicate with your local PostgreSQL and Flask services without needing complex Docker networks.
