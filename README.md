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

### Activating python virtual environment in locally

> source .venv/bin/activate

### Installing new python library using 'uv' command
ex 01:
> uv init
> uv add langchain deepagents 
> uv sync

ex 02: 

> uv add langchain
> un sync

### How to start Fast API applicaiton locally
> uv run uvicorn agent:app --host 0.0.0.0 --port 8080

The following is the new command to start after restuctring

> cd agents/mail-drafter
> PYTHONPATH=$(pwd)/../.. uv run uvicorn main:app --host 0.0.0.0 --port 8080

The reason is as follows.
shared isn't installed as a package into agents/mail-drafter's own .venv — it only resolves inside Docker, where the flat COPY layout puts shared/ as a sibling of main.py in /app (which is on sys.path via CWD). If you run main.py locally straight from inside agents/mail-drafter (not via Docker), import shared... will fail because shared/ is two directories up. Easiest fix for local dev: run with the repo root on PYTHONPATH, e.g. PYTHONPATH=$(pwd)/../.. uv run uvicorn main:app --reload from inside agents/mail-drafter.

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

> aws ecr create-repository --repository-name my-strands-agent --region us-east-1

2. Login to ECR

> aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin 762002331286.dkr.ecr.ap-southeast-1.amazonaws.com

3. Build the docker image and publish it to ECR. When using 'buildx', we can specify additional
paramters like --platform.

> docker buildx build --platform linux/arm64 -t 762002331286.dkr.ecr.ap-southeast-1.amazonaws.com/agent-repository:latest --push .

New command after refactoring

> docker buildx build --platform linux/arm64 -t 762002331286.dkr.ecr.ap-southeast-1.amazonaws.com/mail-drafter:latest -f agents/mail-drafter/Dockerfile --push .

4. Verify that the image was published to ECR properly.

> aws ecr describe-images --repository-name my-strands-agent --region us-east-1

### Creating agent at AWS agent run time
Run the following python script to create the agent

> uv run deploy_agent.py

If you want to update the existing agent, you run the following command

> uv run update_agent.py

Creating the run time using command line

> aws bedrock-agentcore-control create-agent-runtime \
    --cli-input-json file://runtime.json \
    --region ap-southeast-1

If you want to update the run time using commaand line

> aws bedrock-agentcore-control update-agent-runtime \
    --cli-input-json file://runtime.json \
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

> uv run invoke_agent.py

Notes:

- the prompt is currently hard-coded in `invoke_agent.py` as `Explain machine learning in simple terms`
- `runtimeSessionId` is also hard-coded and must be at least 33 characters long
- the script is intended for quick runtime testing from the command line
- if you want to pass dynamic `prompt`, `session_id`, and `user_id`, use the local FastAPI endpoint `POST /invoke-agent-as-user` instead

### Sharing code into git

.gitignore file should be as follows.

```
# uv / python
.venv/
venv/
__pycache__/
*.pyc
.python-version

# OS
.DS_Store

```

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
