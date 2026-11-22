# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

LangGraph-based agents served via FastAPI and deployed as containers to **AWS Bedrock AgentCore Runtime** (images pushed to ECR, region `ap-southeast-1`). Models are Anthropic Claude on Bedrock via `langchain_aws.ChatBedrockConverse` (cross-region inference profiles). Package management is `uv`. There is no test suite or linter configured.

## Layout

- `agents/<name>/` — one self-contained deployable agent per directory, each with its **own** `pyproject.toml`, `uv.lock`, `.env`, and `Dockerfile`. Currently only `agents/mail-drafter/`.
- `shared/` — code reused across agents (`shared/config/settings.py` base pydantic settings, `shared/dynamodb_store.py`). Not installed as a package — see import note below.
- `sandbox/` — standalone LangGraph learning scripts (`lang-graph-*.py`), each runnable on its own; not part of any deployment.
- `docs/chat.md` — notes explaining LangGraph state/reducer/checkpoint behaviour and the multi-agent flow design.
- Root `main.py` / `pyproject.toml` are placeholders.

## Commands

Run the mail-drafter agent locally (repo root must be on `PYTHONPATH` so `import shared...` resolves; inside Docker it works because `shared/` is copied next to `main.py` in `/app`):

```sh
cd agents/mail-drafter
PYTHONPATH=$(pwd)/../.. uv run uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

Test locally: `POST http://localhost:8080/invocations` with `{"input": {"prompt": "...", "user_id": "...", "session_id": "..."}}`. Health check: `GET /ping`.

Build & push image — **must be run from the repo root** (Dockerfile copies `shared/`):

```sh
docker buildx build --platform linux/arm64 \
  -t 762002331286.dkr.ecr.ap-southeast-1.amazonaws.com/mail-drafter:latest \
  -f agents/mail-drafter/Dockerfile --push .
```

Create/update the AgentCore runtime (from `agents/mail-drafter/`): `uv run create_agent_runtime.py` / `uv run update_agent_runtime.py`, or `aws bedrock-agentcore-control create-agent-runtime|update-agent-runtime --cli-input-json file://runtime.json --region ap-southeast-1`. Invoke the deployed runtime with `uv run invoke_agent.py`.

Add deps: `uv add <pkg>` inside the relevant agent directory (each agent has its own lockfile; the Dockerfile runs `uv sync --frozen`).

## mail-drafter architecture (`agents/mail-drafter/main.py`)

AgentCore contract: the container serves `POST /invocations` and `GET /ping` on port 8080.

LangGraph `StateGraph(AgentState)` with three nodes:

1. **gatherer_agent** — structured-output (`ClarifierDecision`) check whether the conversation has enough concrete detail to avoid placeholders. If not, calls `interrupt({"question": ...})` and the HTTP response returns `status: "needs_input"`. Caps at `MAX_CLARIFICATION_ROUNDS`. The pending question is cached in state because `interrupt()` re-runs the node from the top on resume — don't remove that guard or the LLM call duplicates.
2. **drafter_agent** — writes the email; pulls the user's past drafts from the store (`get_store().search((user_id, "emails"))`) as style reference, and incorporates reviewer feedback.
3. **reviewer_agent** — uses a separate Opus model (`opus_model_id`) with structured output `ReviewDecision` (`approve`/`revise`). `review_router` loops back to the drafter at most once (`reviewer_calls >= 2` ends).

Multi-turn conversation handling:
- `thread_id = f"{user_id}:{session_id}"`. The endpoint checks `agent.get_state(config).next`; if the thread is paused at an interrupt it resumes with `Command(resume=prompt)`, otherwise it starts with a fresh initial state.
- `messages` uses the `add_messages` reducer, so only the newest message is passed per invoke; history comes from the checkpointer.
- Checkpointer is `InMemorySaver` — conversation state is lost on container restart and not shared across instances.
- Completed drafts are persisted to DynamoDB via `shared.dynamodb_store.DynamoDBStore` (table from `email_history_table`, PK `namespace` = `"#".join(namespace)`, SK `item_key`). This store supports only exact-namespace get/put/search — no semantic search or `list_namespaces`.

Side effects at import time: writes a Mermaid PNG of the graph (`multi-agent-workflow..png`, needs network for rendering) and node outputs are written to `logs/`.

`/invoke-agent-as-user` is a local-testing endpoint that calls the *deployed* runtime via `bedrock-agentcore` `invoke_agent_runtime` (runtime session IDs must be ≥33 chars; a UUID is used).

## Configuration

Settings are pydantic-settings classes: `shared/config/settings.py::BaseAgentSettings` (`aws_region`, `mcp_server_arn`, `profile_mcp_server_arn`) extended by each agent's `config.py` (`agent_arn`, `model_id`, `opus_model_id`, `ecr_repository`, `agent_runtime_id`, `email_history_table`). Values come from `agents/<name>/.env`, which the Dockerfile copies into the image.

## Gotchas

- `pyproject.toml` requires Python `>=3.13.1` but the Dockerfile base image is `uv:python3.11-bookworm-slim`.
- `.dockerignore` excludes `sandbox/`, `docs/`, `*.png`, `logs/`.
