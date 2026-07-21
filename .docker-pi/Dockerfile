# Use a Python 3.12 base image and install Node.js 22 on top
FROM python:3.12-slim

# Install Node.js 22 (required for pi >= 0.75.0) and system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install the pi agent globally
RUN npm install -g @earendil-works/pi-coding-agent@0.80.6

# Create a non-root user to avoid permission issues on the host
ARG USER_ID=1000
ARG GROUP_ID=1000
RUN groupadd -g ${GROUP_ID} piuser && \
    useradd -u ${USER_ID} -g piuser -m piuser

USER piuser
WORKDIR /app

# Entrypoint script that marks /app as git safe.directory
COPY --chown=piuser:piuser entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

# Default command
CMD ["pi"]
