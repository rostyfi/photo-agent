#!/bin/bash
set -e

# Mark the mounted /app directory as safe for git
git config --global --add safe.directory /app

# Run the provided command (defaults to "pi")
exec "$@"
