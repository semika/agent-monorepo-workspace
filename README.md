### Introduction

This python projects creates an agent and deploy it inside AWS agent core runtime.
Using Amazon titan text model.

### The reference documentation

1. The tutorial on how to create a custom agent and deploy
    https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/getting-started-custom.html
2. Agent core application requirements
   https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html

3. Graph enginnering article
   https://www.aibuilderclub.com/blog/graph-engineering-guide-2026      

### Repository layout (uv workspace)

```
pyproject.toml            # workspace root: members + dev/sandbox dependency groups
uv.lock                   # ONE lockfile for every agent and package
packages/shared/          # "agent-shared" package -> import agent_shared
  src/agent_shared/
agents/<name>/            # one deployable agent per folder -> import <name_with_underscores>
  pyproject.toml          # depends on "agent-shared" (workspace = true)
  Dockerfile              # built from the repo root
  .env
  src/<package>/
sandbox/                  # standalone learning scripts (not deployed)
```

All commands below are run from the **repo root**.

### Setting up locally

> uv sync

This creates a single `.venv` at the root with every agent and `agent-shared`
installed in editable mode (changes to `packages/shared` are picked up immediately).
In VS Code select `./.venv/bin/python` as the interpreter.

### Managing dependencies

> uv add --package mail-drafter langchain      # dependency of one agent
> uv add --package agent-shared boto3          # dependency of the shared code
> uv add --dev pytest                          # local tooling only
> uv add --group sandbox some-lib              # used only by sandbox/ scripts

### Adding a new agent

> uv init --package agents/<name>

Then add `"agent-shared"` to its dependencies with
`[tool.uv.sources] agent-shared = { workspace = true }`, and copy
`agents/mail-drafter/Dockerfile` (replace `mail-drafter` / `mail_drafter`).

### How to start Fast API application locally

> uv run --package mail-drafter uvicorn mail_drafter.main:app --host 0.0.0.0 --port 8080 --reload

Settings are read from `agents/mail-drafter/.env`. AWS credentials must be for the
account that owns the Bedrock inference profiles (e.g. `export AWS_PROFILE=...`).

### How to run Fast API end poing via Postman

Set the request as POST with the URL 'http://localhost:8080/invocations'.

Json data payload should be as follows.
```
{
    "input": {"prompt": "Explain machine learning in simple terms"}
}
```

### Deploying the agent into AWS ECR

1. Creating a ECR repository

> aws ecr create-repository --repository-name my-agent-repository --region ap-southeast-1

2. Login to ECR

> aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin 762002331286.dkr.ecr.ap-southeast-1.amazonaws.com

3. Build the docker image and publish it to ECR. When using 'buildx', we can specify additional
paramters like --platform.

> docker buildx build --platform linux/arm64 -t 762002331286.dkr.ecr.ap-southeast-1.amazonaws.com/mail-drafter:latest -f agents/mail-drafter/Dockerfile --push .

4. Verify that the image was published to ECR properly.

> aws ecr describe-images --repository-name mail-drafter --region ap-southeast-1

5. To test the image locally before pushing:

> docker build -f agents/mail-drafter/Dockerfile -t mail-drafter .
> docker run --rm -p 8080:8080 -v ~/.aws:/root/.aws:ro -e AWS_PROFILE=sawen mail-drafter

### Creating agent at AWS agent run time
Run the following python script to create the agent

> uv run --package mail-drafter python -m mail_drafter.create_agent_runtime

If you want to update the existing agent, you run the following command

> uv run --package mail-drafter python -m mail_drafter.update_agent_runtime

Creating the run time using command line

> aws bedrock-agentcore-control create-agent-runtime \
    --cli-input-json file://agents/mail-drafter/runtime.json \
    --region ap-southeast-1

If you want to update the run time using commaand line

> aws bedrock-agentcore-control update-agent-runtime \
    --cli-input-json file://agents/mail-drafter/update-runtime.json \
    --region ap-southeast-1

### Invoking a deployed agent runtime

Use `invoke_agent.py` to send a test prompt directly to an already deployed Bedrock AgentCore runtime.
The script:

- creates a `bedrock-agentcore` client in `us-east-1`
- reads the runtime ARN from `agent_arn` in `.env`
- sends a JSON payload with the shape `{"input": {"prompt": "..."}}`
- invokes `invoke_agent_runtime(...)` using the `DEFAULT` qualifier
- prints the returned runtime response to stdout

Before running the script, make sure your `.env` file contains at least the required runtime settings:

```env
agent_arn=<your-agent-runtime-arn>
model_id=<your-bedrock-model-id>
ecr_repository=my-strands-agent
agent_runtime_id=<your-agent-runtime-id>
```

Run the script with:

> uv run --package mail-drafter python -m mail_drafter.invoke_agent

Notes:

- the prompt is currently hard-coded in `invoke_agent.py` as `Explain machine learning in simple terms`
- `runtimeSessionId` is also hard-coded and must be at least 33 characters long
- the script is intended for quick runtime testing from the command line
- if you want to pass dynamic `prompt`, `session_id`, and `user_id`, use the local FastAPI endpoint `POST /invoke-agent-as-user` instead

### Sharing code into git

See `.gitignore` at the repo root (venvs, caches, build output, `.env` files,
logs and generated `runtime-response.json` are excluded). `.python-version` and
`uv.lock` are committed.

When you switch between two git accounts, you can set the origin URL as follows 
You need to first get the URL in SSH format from github.

ex : git@github.com:semika/my-custom-mcp.git

Then you need to append the prefix:

ex : git@github.com-personal:semika/my-custom-mcp.git

> git remote set-url origin git@github.com-personal:semika/aws-cognito.git

> git push origin master

For detail reference about maintaining two github accounts, refer to the following documentation.

https://www.linkedin.com/pulse/multiple-github-accounts-same-mac-hesham-osama/

### Reference documentations

Agent skills standard : https://agentskills.io/home

Lang Chain Agents : https://docs.langchain.com/oss/python/langchain/agents 

Agent Tools : https://docs.langchain.com/oss/python/langchain/tools
