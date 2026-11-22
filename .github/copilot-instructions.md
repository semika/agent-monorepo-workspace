# Copilot instructions for my-custom-agent

## Big picture
- This repo is a small FastAPI wrapper around AWS Bedrock model invocation and Bedrock AgentCore runtime APIs.
- `agent.py` is the real application entrypoint: it defines the FastAPI app, request/response models, local inference endpoints, and the helper used to call a deployed Agent Runtime.
- The main request flow is `POST /invocations` -> extract `input.prompt` -> call `invoke_model_titan()` -> return `{"output": {"message", "timestamp"}}`.
- `POST /invoke-agent-as-user` is for local testing of an already deployed runtime. It forwards `prompt`, `session_id`, and `user_id` into `invoke_as_user()`.
- `main.py` is only a placeholder hello-world script; do not treat it as the service entrypoint.

## Runtime and config conventions
- Keep changes centered in `agent.py` unless you are specifically changing deployment/config behavior.
- `config.py` uses `pydantic-settings` and expects `agent_arn` from `.env`. The current Docker image also copies `.env` into the container, so config changes must consider both local runs and containerized runs.
- AWS region is hard-coded as `us-east-1` across `agent.py`, `deploy_agent.py`, `update_agent.py`, and `invoke_agent.py`. If you make region configurable, update all of them consistently.
- The active local model path is Amazon Titan (`invoke_model_titan`). Claude support exists in `invoke_model_claude()` but is currently commented out at the route level.
- `strands.Agent()` is instantiated in `agent.py` for reference only and is not part of the active inference path.

## Deployment scripts
- `deploy_agent.py`, `update_agent.py`, and `invoke_agent.py` are standalone executable scripts, not reusable library modules.
- These scripts currently contain hard-coded AWS account IDs, ECR URIs, role ARN, runtime IDs, and runtime ARN. Preserve that style unless you are intentionally refactoring the scripts to read config.
- `invoke_agent_runtime` requires a long `runtimeSessionId`; the code comments note it must be 33+ characters.
- `update_agent.py` assumes an existing runtime ID and only updates the container/lifecycle/network config.

## Developer workflows
- Use `uv` commands for local work; the documented run path is `uv run uvicorn agent:app --host 0.0.0.0 --port 8080`.
- There is no test suite in this repo right now. For validation, prefer targeted manual checks against `/ping`, `/invocations`, and if configured, `/invoke-agent-as-user`.
- The Docker image is built for `linux/arm64` and uses the `ghcr.io/astral-sh/uv:python3.11-bookworm-slim` base image even though `pyproject.toml` declares `>=3.13.1`; be careful when changing Python-version-specific code.
- The container startup command is `uv run uvicorn agent:app ...`, so changes to routing or startup behavior should be verified against that path.

## Editing guidance
- Match the current lightweight style: module-level boto3 clients are not shared; helper functions create clients inline where used.
- Preserve the existing API payload shapes. Example request body for local inference is `{"input": {"prompt": "Explain machine learning in simple terms"}}`.
- Preserve the existing response model shape in `InvocationResponse(output=...)` unless you are intentionally changing the external API contract.
- When touching deployment docs or scripts, keep README commands aligned with the actual hard-coded repository name `my-strands-agent` and the account/region values used in code.
- Do not add broad framework scaffolding; this codebase is intentionally a small script-oriented project with one service file and a few AWS utility scripts.
