from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, config, Field
from typing import Dict, Any
from datetime import datetime
from strands import Agent
import logging
import boto3
import json
from botocore.exceptions import ClientError
from uuid_utils import uuid7
from config import settings
from langchain_aws import ChatBedrockConverse
from langchain.tools import tool
from langchain.messages import HumanMessage, AIMessage, SystemMessage
from langchain.agents import create_agent
from dataclasses import dataclass
from langchain.agents.middleware import dynamic_prompt, ModelRequest
from langchain_mcp_adapters.client import MultiServerMCPClient

## For short term memory.
from langgraph.checkpoint.memory import InMemorySaver


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = FastAPI(title="Strands Agent Server", version="1.0.0")

# Initialize Strands agent.
# This is not used in the current implementation but kept for reference.
strands_agent = Agent()

class InvocationRequest(BaseModel):
    input: Dict[str, Any]

class InvocationResponse(BaseModel):
    output: Dict[str, Any]

# create MPC server URL for invoking the agent runtime. 
# This is used for multi-user scenarios where you want to maintain separate sessions or contexts for each user.
# URL-encode the ARN  (colons → %3A, slashes → %2F)
encoded_mcp_arn = settings.mcp_server_arn.replace(":", "%3A").replace("/", "%2F")

AGENTCORE_MCP_URL = (
    f"https://bedrock-agentcore.{settings.aws_region}.amazonaws.com"
    f"/runtimes/{encoded_mcp_arn}/invocations?qualifier=DEFAULT"
)    

@tool
class GetWeather(BaseModel):
    '''Get the current weather in a given location'''

    location: str = Field(..., description="The city and state, e.g. San Francisco, CA")

# Python callable tool. 
# This is an example of a tool that can be called by the agent during the conversation. 
# The tool definition includes the input parameters and their descriptions, which can be used by the agent to understand how to use the tool effectively.
@tool
class GetPopulation(BaseModel):
    '''Get the current population in a given location'''

    location: str = Field(..., description="The city and state, e.g. San Francisco, CA")

# Module-level setup: model, checkpointer, and agent are created once and reused
# across all requests so that conversation history is preserved between calls.
_thinking_params = {
    "thinking": {
        "type": "enabled",
        "budget_tokens": 2000
    }
}

mcp_client = MultiServerMCPClient(
    {
        "math": {
            "transport": "streamable_http",
            "url": AGENTCORE_MCP_URL,
            "headers": {
                #"Authorization": f"Bearer {bearer_token}",
                "Content-Type": "application/json",
            },
        }
    }
)

@dataclass
class Context:
    user_role: str
    deployment_env: str

## Reference documentation - https://reference.langchain.com/python/langchain-aws/chat_models/bedrock_converse/ChatBedrockConverse
_model = ChatBedrockConverse(
    # claude sonet will have to be used via inference profile.
    model_id="arn:aws:bedrock:us-east-1:762002331286:application-inference-profile/226j0yl0j37r",  # cross-region inference profile
    region_name="us-east-1",
    temperature=1,
    provider='anthropic',
    additional_model_request_fields=_thinking_params
)
_checkpointer = InMemorySaver()

@dynamic_prompt
def context_aware_prompt(request: ModelRequest) -> str:
    # Read from Runtime Context: user role and environment
    user_role = request.runtime.context.user_role
    env = request.runtime.context.deployment_env

    base = "You are a person with lots of knowledge about the world, and you are helpful and precise when answering questions."

    if user_role == "admin":
        base += "\nYou have admin access. You can perform all operations."
    elif user_role == "viewer":
        base += "\nYou have read-only access. Guide users to read operations only."

    if env == "production":
        base += "\nBe extra careful with any data modifications."

    return base

#tools = await client.get_tools()
_agent = create_agent(
    model=_model,
    tools=[GetWeather, GetPopulation],
    checkpointer=_checkpointer,
    # System prompt is set here once so it is NOT re-appended to the stored
    # conversation history on every call, preventing duplicate SystemMessages.
    #system_prompt="You are a person with lots of knowledge about the world, and you are helpful and precise when answering questions."
    middleware=[context_aware_prompt],
    context_schema=Context
)

def langchain_bedrock_converse(user_message, user_id, session_id, user_role="viewer", deployment_env="production"):
    # This function demonstrates how to use the Langchain AWS Bedrock Converse wrapper to interact with a Bedrock model.

    thread_id = f"{user_id}:{session_id}"  
    thread_config = {"configurable": {"thread_id": thread_id}}
    context = Context(user_role=user_role, deployment_env=deployment_env)
    #thread_config["context"] = context
    ## Only the new HumanMessage is passed per call.
    ## The system prompt lives in the agent (set at creation via `prompt=`) and the
    ## full conversation history is automatically restored by the checkpointer.
    ## Passing SystemMessage here every call would duplicate it in the stored state.
    human_msg = HumanMessage(user_message)

    #response = _agent.invoke({"messages": [human_msg]}, thread_config, context=context)


    response = _agent.invoke(
        {"messages": [human_msg]},
        config={"configurable": {"thread_id": thread_id}},
        context=Context(user_role=user_role, deployment_env=deployment_env)
    )
    

    #print(response["messages"][-1].content)
    return response

# Claude invocation function
# This function demonstrates how to invoke Anthropic Claude model using Bedrock Runtime API.
def invoke_model_claude(user_message):
    # Use the native inference API to send a text message to Anthropic Claude.

    # Create a Bedrock Runtime client in the AWS Region of your choice.
    bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

    # Set the model ID, e.g., Claude 3 Haiku.
    # Inference profiles are available in Bedrock and can be used directly with the modelId parameter when invoking the model.
    #model_id = "arn:aws:bedrock:us-east-1:762002331286:inference-profile/global.anthropic.claude-sonnet-4-6"
    model_id = settings.model_id

    # Define the prompt for the model.
    prompt = user_message

    # Format the request payload using the model's native structure.
    native_request = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 512,
        "temperature": 0.5,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }
        ],
    }

    # Convert the native request to JSON.
    request = json.dumps(native_request)

    try:
        # Invoke the model with the request.
        response = bedrock.invoke_model(modelId=model_id, body=request)

    except (ClientError, Exception) as e:
        print(f"ERROR: Can't invoke '{model_id}'. Reason: {e}")
        exit(1)

    # Decode the response body.
    model_response = json.loads(response["body"].read())

    # Extract and print the response text.
    response_text = model_response["content"][0]["text"]
    print(response_text)

    return response_text


# Amazon Titan invocation function
# This function demonstrates how to invoke Amazon Titan Text Express model using Bedrock Runtime API.
# This is not related to agent deployment
def invoke_model_titan(user_message):

    logger.info(f"Invoking model 'amazon.titan-text-express-v1' with body: {user_message}")

    bedrock = boto3.client(service_name = 'bedrock-runtime', region_name = 'us-east-1')
    
    try:

        model_id = "amazon.titan-text-express-v1"
        body = json.dumps({
            "inputText": user_message,
            "textGenerationConfig": {
                "maxTokenCount": 3072,
                "stopSequences": [],
                "temperature": 0.7,
                "topP": 0.9
            }
        })
    
        response = bedrock.invoke_model(
            modelId=model_id,
            body=body,
            contentType='application/json',
            accept='application/json'
        )
        response_body_json = json.loads(response['body'].read().decode('utf-8'))
        output = response_body_json["results"][0]["outputText"]

        return output
    
    except (ClientError, Exception) as e:
        logging.error(e)
        return None
    
# This is the main API endpoint for invoking the agent. It receives a prompt in the request body, processes it, and returns the agent's response.   
@app.post("/invocations", response_model=InvocationResponse)
async def invoke_agent(request: InvocationRequest):
    try:
        user_message = request.input.get("prompt", "")
        user_id = request.input.get("user_id")
        session_id = request.input.get("session_id")
        user_role = request.input.get("user_role", "viewer")
        deployment_env = request.input.get("deployment_env", "production")

        if not user_message:
            raise HTTPException(
                status_code=400, 
                detail="No prompt found in input. Please provide a 'prompt' key in the input."
            )

        #result = strands_agent(user_message)
        #result = invoke_model_titan(user_message);
        #result = invoke_model_claude(user_message)
        result = langchain_bedrock_converse(user_message, user_id=user_id, 
                                            session_id=session_id, user_role=user_role, 
                                            deployment_env=deployment_env)
        response = {
            "message": result,
            "timestamp": datetime.utcnow().isoformat()
        }

        return InvocationResponse(output=response)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent processing failed: {str(e)}")

# Invoke the agent runtime as a specific user. 
# This is useful for multi-user scenarios where you want to maintain separate sessions or contexts for each user.
def invoke_as_user(user_id, session_id, prompt):
    try:
        agent_core_client = boto3.client('bedrock-agentcore', region_name='us-east-1')
        payload = json.dumps({
            "input": {"prompt": prompt}
        })

        response = agent_core_client.invoke_agent_runtime( 
            agentRuntimeArn=settings.agent_arn,
            runtimeSessionId = session_id,  # Must be 33+ chars
            payload = payload,
            qualifier="DEFAULT"
        )

        # For detail list of all the supported parameters for invoke_agent_runtime, refer to:
        # https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntime.html

        response_body = response['response'].read()
        response_data = json.loads(response_body)
        print("Agent Response:", response_data)
        return response_data
        
    except Exception as e:
        print(f"Error invoking Agent Runtime: {str(e)}")
        raise e


# This API end point for local testing only.
@app.post("/invoke-agent-as-user", response_model=InvocationResponse)        
async def invoke_agent_as_user(request: InvocationRequest) -> InvocationResponse:
    try:
        prompt = request.input.get("prompt", "")
        session_id = request.input.get("session_id")
        user_id = request.input.get("user_id")

        if (prompt is None or session_id is None or user_id is None):
            raise HTTPException(
                status_code=400, 
                detail="Missing required fields. Please provide 'prompt', 'session_id', and 'user_id' in the input."
            )
        response_data = invoke_as_user(user_id, session_id, prompt)

        return InvocationResponse(output=response_data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent API invocation failed: {str(e)}")

@app.get("/ping")
async def ping():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)