# Build from the repo root so the workspace lockfile and packages/ are reachable:
#   docker build -f agents/mail-drafter/Dockerfile -t mail-drafter .
FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

WORKDIR /app

# 1) Install third-party dependencies only (cached layer, rebuilt only when
#    a pyproject.toml or the lockfile changes).
COPY pyproject.toml uv.lock ./
COPY packages/shared/pyproject.toml packages/shared/pyproject.toml
COPY agents/mail-drafter/pyproject.toml agents/mail-drafter/pyproject.toml
RUN uv sync --frozen --no-default-groups --package mail-drafter --no-install-workspace

# 2) Copy shared code and this agent's code, then install the workspace members.
COPY packages/shared/ packages/shared/
COPY agents/mail-drafter/ agents/mail-drafter/
RUN uv sync --frozen --no-default-groups --package mail-drafter

# NOTE: agents/mail-drafter/.env is copied in with the agent directory above and
# read by mail_drafter.config. Real environment variables override it.
# TODO: move these values to the AgentCore runtime's environmentVariables and
# stop shipping .env in the image (see .dockerignore).

EXPOSE 8080

CMD ["/app/.venv/bin/uvicorn", "mail_drafter.main:app", "--host", "0.0.0.0", "--port", "8080"]
