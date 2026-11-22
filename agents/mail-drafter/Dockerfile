# Use uv's ARM64 Python base image
# Build from the repo root so this Dockerfile can reach shared/:
#   docker build -f agents/mail-drafter/Dockerfile -t mail-drafter .
FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

# This agent's own dependency set
COPY agents/mail-drafter/pyproject.toml agents/mail-drafter/uv.lock ./
RUN uv sync --frozen --no-cache

# Code shared across agents
COPY shared/ ./shared/

# This agent's own code
COPY agents/mail-drafter/*.py ./
COPY agents/mail-drafter/.env ./

# Expose port
EXPOSE 8080

# Run application
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
