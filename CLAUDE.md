# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

LangGraph-based agents served via FastAPI and deployed as containers to **AWS Bedrock AgentCore Runtime** (images pushed to ECR, region `ap-southeast-1`). Models are Anthropic Claude on Bedrock via `langchain_aws.ChatBedrockConverse` (cross-region inference profiles). Package management is `uv`. There is no test suite or linter configured.

## Layout

uv **workspace** (root `pyproject.toml` → `[tool.uv.workspace] members = ["packages/*", "agents/*"]`) with a **single root `uv.lock`** and a single root `.venv`.

- `agents/<name>/` — one deployable agent per directory: `pyproject.toml` (depends on `agent-shared` via `[tool.uv.sources] agent-shared = { workspace = true }`), `Dockerfile`, `.env`, code in `src/<name_underscored>/`. Currently only `agents/mail-drafter/` → package `mail_drafter`.
- `packages/shared/` — distribution `agent-shared`, import name `agent_shared` (`agent_shared.config.settings.BaseAgentSettings`, `agent_shared.dynamodb_store.DynamoDBStore`). Declares its own deps (boto3, langgraph, pydantic-settings).
- `sandbox/` — standalone LangGraph learning scripts (`lang-graph-*.py`), not part of any deployment. Their extra libs live in the root `sandbox` dependency group.
- `docs/chat.md` — notes explaining LangGraph state/reducer/checkpoint behaviour and the multi-agent flow design.
- Root `pyproject.toml` is a virtual workspace root (no code); `dev` + `sandbox` groups are installed by default locally.

Always use package-qualified imports (`from mail_drafter.config import settings`, `from agent_shared... import ...`) — never bare `import config` / `import shared`.

## Commands

All from the **repo root**.

- Install everything: `uv sync`
- Run mail-drafter locally: `uv run --package mail-drafter uvicorn mail_drafter.main:app --host 0.0.0.0 --port 8080 --reload`
- Test locally: `POST http://localhost:8080/invocations` with `{"input": {"prompt": "...", "user_id": "...", "session_id": "..."}}`. Health check: `GET /ping`.
- Build & push image (build context must be the repo root):

```sh
docker buildx build --platform linux/arm64 \
  -t 762002331286.dkr.ecr.ap-southeast-1.amazonaws.com/mail-drafter:latest \
  -f agents/mail-drafter/Dockerfile --push .
```

  The Dockerfile runs `uv sync --frozen --no-default-groups --package mail-drafter`, so the image contains only that agent, `agent-shared` and their deps.
- Create/update/invoke the AgentCore runtime: `uv run --package mail-drafter python -m mail_drafter.create_agent_runtime` / `...update_agent_runtime` / `...invoke_agent`, or `aws bedrock-agentcore-control create-agent-runtime|update-agent-runtime --cli-input-json file://agents/mail-drafter/runtime.json --region ap-southeast-1`.
- Add deps: `uv add --package <agent-or-agent-shared> <pkg>`; dev tools `uv add --dev <pkg>`; sandbox-only `uv add --group sandbox <pkg>`. Never create per-agent lockfiles or venvs.

## mail-drafter architecture (`agents/mail-drafter/src/mail_drafter/main.py`)

AgentCore contract: the container serves `POST /invocations` and `GET /ping` on port 8080.

LangGraph `StateGraph(AgentState)` with three nodes:

1. **gatherer_agent** — structured-output (`ClarifierDecision`) check whether the conversation has enough concrete detail to avoid placeholders. If not, calls `interrupt({"question": ...})` and the HTTP response returns `status: "needs_input"`. Caps at `MAX_CLARIFICATION_ROUNDS`. The pending question is cached in state because `interrupt()` re-runs the node from the top on resume — don't remove that guard or the LLM call duplicates.
2. **drafter_agent** — writes the email; pulls the user's past drafts from the store (`get_store().search((user_id, "emails"))`) as style reference, and incorporates reviewer feedback.
3. **reviewer_agent** — uses a separate Opus model (`opus_model_id`) with structured output `ReviewDecision` (`approve`/`revise`). `review_router` loops back to the drafter at most once (`reviewer_calls >= 2` ends).

Multi-turn conversation handling:
- `thread_id = f"{user_id}:{session_id}"`. The endpoint checks `agent.get_state(config).next`; if the thread is paused at an interrupt it resumes with `Command(resume=prompt)`, otherwise it starts with a fresh initial state.
- `messages` uses the `add_messages` reducer, so only the newest message is passed per invoke; history comes from the checkpointer.
- Checkpointer is `InMemorySaver` — conversation state is lost on container restart and not shared across instances.
- Completed drafts are persisted to DynamoDB via `agent_shared.dynamodb_store.DynamoDBStore` (table from `email_history_table`, PK `namespace` = `"#".join(namespace)`, SK `item_key`). This store supports only exact-namespace get/put/search — no semantic search or `list_namespaces`.

Side effects at import time: writes a Mermaid PNG of the graph (`multi-agent-workflow..png`, needs network for rendering) and node outputs are written to `logs/`.

`/invoke-agent-as-user` is a local-testing endpoint that calls the *deployed* runtime via `bedrock-agentcore` `invoke_agent_runtime` (runtime session IDs must be ≥33 chars; a UUID is used).

## Configuration

Settings are pydantic-settings classes: `packages/shared/src/agent_shared/config/settings.py::BaseAgentSettings` (`aws_region`, `mcp_server_arn`, `profile_mcp_server_arn`) extended by each agent's `config.py` (`agent_arn`, `model_id`, `opus_model_id`, `ecr_repository`, `agent_runtime_id`, `email_history_table`). Values come from `agents/<name>/.env` (resolved relative to `config.py`, real env vars override), which is still shipped inside the image — `.dockerignore` has an explicit `!agents/*/.env` exception. Moving these to AgentCore `environmentVariables` is a pending TODO.

## Gotchas

- `.dockerignore` excludes `sandbox/`, `docs/`, `*.png`, `logs/`, `.venv`, and `runtime*.json`.
- `main.py` renders the graph PNG to the agent root (`agents/mail-drafter/multi-agent-workflow..png`) at import time, which needs network access.
