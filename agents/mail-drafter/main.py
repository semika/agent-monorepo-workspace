import os
import sys
import logging
from typing import Dict, Any, Annotated, TypedDict
from datetime import datetime
import boto3
import json
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt, Command
from langgraph.config import get_store
from langchain_core.messages import BaseMessage, AnyMessage, SystemMessage, HumanMessage, AIMessage
from config import settings
from langchain_aws import ChatBedrockConverse
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from strands import Agent
from shared.dynamodb_store import DynamoDBStore
import uuid
from botocore.exceptions import ClientError, ParamValidationError

LOG_DIR = "logs"
MAX_CLARIFICATION_ROUNDS = 5

class InvocationRequest(BaseModel):
    input: Dict[str, Any]

class InvocationResponse(BaseModel):
    output: Dict[str, Any]

app = FastAPI(title="Strands Agent Server", version="1.0.0")

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s- %(levelname)s - %(message)s",
    handlers=[
        #logging.FileHandler(os.path.join(LOG_DIR, "execution.log"), mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
    )

logger = logging.getLogger(__name__)

def write_text_file(filename:str, content:str):
    filepath = os.path.join(LOG_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

def format_conversation(messages):
    lines = []
    for m in messages:
        role = getattr(m, "type", "user")
        content = getattr(m, "content", str(m))
        lines.append(f"{role}: {content}")
    return "\n".join(lines)

model = ChatBedrockConverse(
        # claude sonet will have to be used via inference profile.
        model_id=settings.model_id,  # cross-region inference profile
        region_name=settings.aws_region,
        temperature=1,
        provider='anthropic'
    )

# Model for reviewer
opus_model = ChatBedrockConverse(
        # claude sonet will have to be used via inference profile.
        model_id=settings.opus_model_id,  # cross-region inference profile
        region_name=settings.aws_region,
        temperature=1,
        provider='anthropic'
    )


class ClarifierDecision(BaseModel):
    ready: bool = Field(description="True if the conversation already contains every concrete detail needed to produce final content with no placeholders. False if anything is missing.")
    question: str = Field(default="", description="If ready is false, a single clear question asking for the missing detail(s). Empty string if ready is true.")

class ReviewDecision(BaseModel):
    decision: str = Field(description="Either 'approve' or 'revise'")
    reason: str = Field(description="The reason for the decision")

clarifier_model = model.with_structured_output(ClarifierDecision)
reviewer_model = opus_model.with_structured_output(ReviewDecision)

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: str
    user_query: str
    draft_response: str
    draft_calls: int
    reviewer_calls: int
    review_decision: str
    review_reason: str
    revision_count: int
    ready: bool
    pending_question: str
    clarification_rounds: int

## Gatherer agent ###
## Checks whether the conversation so far has enough concrete detail to produce final
## content with no placeholders. If not, it asks the user a question and the graph pauses.
## The pending question is cached in state so a resume never re-runs the LLM call -
## interrupt() replays this node from the top, and skipping straight to interrupt()
## when a question is already pending avoids a wasted duplicate call.

def gatherer_agent(state):
    logger.info("Gatherer agent started..!")
    question = state.get("pending_question", "")

    if not question:
        system_msg = SystemMessage(f"""
            You are a requirements-gathering agent in a multi agent AI system.

            Look at the conversation so far and decide whether there is enough concrete
            information to produce the user's requested content with no placeholders left
            to fill in (e.g. no [Your Name], [Date], etc).

            Conversation so far:
            {format_conversation(state.get('messages', []))}
        """)

        decision = clarifier_model.invoke([system_msg])
        logger.info(f"Gatherer decision: {decision}")
        state["clarification_rounds"] = state.get("clarification_rounds", 0) + 1

        if decision.ready or state["clarification_rounds"] >= MAX_CLARIFICATION_ROUNDS:
            state["ready"] = True
            state["pending_question"] = ""
            return state

        question = decision.question

    answer = interrupt({"question": question})
    state["messages"] = [AIMessage(question), HumanMessage(answer)]
    state["pending_question"] = ""
    state["ready"] = False
    return state

def gatherer_router(state) -> str:
    return "drafter_agent" if state.get("ready") else "gatherer_agent"

# This is the drafter agent who plans and writes the final content in one pass

def drafter_agent(state):

    state['draft_calls'] += 1
    logger.info(f"Drafter call # {state['draft_calls']}")

    past_drafts = get_store().search((state['user_id'], "emails"), limit=5)
    past_drafts_text = "\n\n".join(
        f"- {item.value.get('content', '')}" for item in past_drafts
    ) or "No past drafts on file for this user."

    system_msg = SystemMessage(f"""

        You are a drafting agent in a multi agent AI system.

        Conversation with the user (contains all the concrete details you need):
        {format_conversation(state.get('messages', []))}

        Previous reviewer feedback : {state['review_reason']}

        This user's past drafted emails, for tone and style reference only - do not
        copy factual details (names, dates, etc.) from them into the new draft unless
        the user repeated those details in the current conversation:
        {past_drafts_text}

        Write the best possible final, ready-to-send content using the concrete details
        from the conversation. Never use placeholders like [Your Name] - use the actual
        values the user provided. If reviewer feedback exists, explicitly fix those.

    """)

    response = model.invoke([system_msg])
    draft_respose = response.content if hasattr(response, "content") else str(response)
    state['draft_response'] = draft_respose
    write_text_file(f"draft_output_{state['draft_calls']}.txt", draft_respose)
    logger.info(f"Drafter output {[state['draft_calls']]} : {draft_respose}")
    return state

# This is the reviewer agent
# Review can be done by using a different model.
def reviewer_agent(state):
    state['reviewer_calls'] += 1
    logger.info(f"Reviewer call # {state['reviewer_calls']}")

    system_msg = SystemMessage(f"""

        You are a strict reviewer agent.

        Conversation : {format_conversation(state.get('messages', []))}

        Draft response : {state['draft_response']}

        Check for:
        - the content is rich enough for the specified field
        - clarity and simplicity
        - lenth of the email. lenthy emails are hard to read. short and summarize the content so that the read can grab the intention quickly.
        - necessary details are included.
        - actionable recommendations
        - no leftover placeholders (e.g. [Your Name], [Date])

        Decide whether to approve the draft as-is, or ask for a revision, and always
        give a reason for your decision.
    """)

    decision = reviewer_model.invoke([system_msg])
    logger.info(f"Reviewer decision: {decision}")

    state['review_decision'] = decision.decision
    state['review_reason'] = decision.reason

    write_text_file(f"reviewer_output_{state['reviewer_calls']}.txt",
                    f"Decision: {decision.decision}\nReason: {decision.reason}")
    logger.info(f"Reviewer result - Reviewer Calls: {state['reviewer_calls']} Decision: {decision.decision}, Reason: {decision.reason}")

    return state

def review_router(state) -> str:
    if state['review_decision'] == "approve" or state['reviewer_calls'] >= 2:
        return "__end__"

    state['revision_count'] = state['revision_count'] + 1
    return "drafter_agent"

#Define the workflow
workflow = StateGraph(AgentState)

workflow.add_node("gatherer_agent", gatherer_agent)
workflow.add_node("drafter_agent", drafter_agent)
workflow.add_node("reviewer_agent", reviewer_agent)

workflow.set_entry_point("gatherer_agent")
workflow.add_conditional_edges(
    "gatherer_agent",
    gatherer_router,
    {
        "drafter_agent": "drafter_agent",
        "gatherer_agent": "gatherer_agent",
    }
)
workflow.add_edge("drafter_agent", "reviewer_agent")
workflow.add_conditional_edges(
    "reviewer_agent",
    review_router,
    {
        "drafter_agent": "drafter_agent",
        "__end__":END
    }
)

# Compile the workflow
# Use a durable checkpointer in production - backed by a database
checkpointer = InMemorySaver()
store = DynamoDBStore(table_name=settings.email_history_table, region_name=settings.aws_region)
agent = workflow.compile(checkpointer=checkpointer, store=store)

# Show the agent
graph_path = os.path.join(os.path.dirname(__file__), "multi-agent-workflow..png")
with open(graph_path, "wb") as f:
    f.write(agent.get_graph(xray=True).draw_mermaid_png())

@app.post("/invocations", response_model=InvocationResponse)
async def invoke_agent(request: InvocationRequest):
    try:
        logger.info(
            "Agent invocation started session_id=%s",
            request.input,
        )
        user_query = request.input.get("prompt", "")
        user_id = request.input.get("user_id", "")
        session_id = request.input.get("session_id", "")

        if not user_query:
            raise HTTPException(
                status_code=400,
                detail="No prompt found in input. Please provide a 'prompt' key in the input."
            )
        if not session_id:
            raise HTTPException(
                status_code=400,
                detail="No session_id found in input. Please provide a 'session_id' key so the conversation can be resumed across turns."
            )
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="No user_id found in input. Please provide a 'user_id' key so drafted emails can be saved to that user's history."
            )

        thread_id = f"{user_id}:{session_id}"
        config = {"configurable": {"thread_id": thread_id}}

        existing_state = agent.get_state(config)
        is_resuming = bool(existing_state.next)

        if is_resuming:
            result = agent.invoke(Command(resume=user_query), config=config)
        else:
            initial_state = {
                "messages": [HumanMessage(user_query)],
                "user_id": user_id,
                "user_query": user_query,
                "draft_response": "",
                "draft_calls": 0,
                "reviewer_calls": 0,
                "review_decision": "",
                "review_reason": "",
                "revision_count": 0,
                "ready": False,
                "pending_question": "",
                "clarification_rounds": 0,
            }
            result = agent.invoke(initial_state, config=config)

        if result.get("__interrupt__"):
            question = result["__interrupt__"][0].value["question"]
            write_text_file("final_output.txt", f"Clarifying question: {question}")
            logger.info(f"Clarifying question asked: {question}")
            response_payload = {
                "status": "needs_input",
                "message": question,
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat(),
            }
            return InvocationResponse(output=response_payload)

        final_output = f"""
                User query : {result['user_query']}\n
                Draft Response : {result['draft_response']}\n
                Draft calls: {result['draft_calls']}\n
                Reviewer calls: {result['reviewer_calls']}\n
                Review decision: {result['review_decision']}\n
                Revision count: {result['revision_count']}\n
                """
        write_text_file("final_output.txt", final_output)
        logger.info(final_output)
        print(final_output)

        ## save data into the store
        created_at = datetime.utcnow().isoformat()
        store.put((user_id, "emails"), created_at, {
            "session_id": session_id,
            "request_summary": result['user_query'],
            "content": result['draft_response'],
        })

        response_payload = {
            "status": "completed",
            "message": final_output,
            "session_id": session_id,
            "timestamp": created_at,
        }

        return InvocationResponse(output=response_payload)

    except HTTPException as e:
        logger.exception(
            "Agent invocation failed session_id=%s",
            e,
        )
        logger.error("Agent processing failed: %s", "major problem", exc_info=True)
        raise
    except Exception as e:
        logger.error("Agent processing failed: %s", "major problem", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent processing failed: {str(e)}")

@app.get("/emails/{user_id}")
async def get_email_history(user_id: str):
    items = store.search((user_id, "emails"), limit=100)
    return {"user_id": user_id, "emails": [item.dict() for item in items]}

# Invoke the agent runtime as a specific user. 
# This is useful for multi-user scenarios where you want to maintain separate sessions or contexts for each user.
def invoke_as_user(prompt: str, user_id: str, session_id: str | None = None):
    # A UUID is 36 characters, satisfying the AgentCore session ID requirement.
    runtime_session_id = session_id or str(uuid.uuid4())

    agent_core_client = boto3.client(
        "bedrock-agentcore",
        region_name=settings.aws_region,
    )

    # This structure must exactly match what your agent entry point expects.
    request_payload = {
        "input": {
            "prompt": prompt,
            "user_id": user_id,
            "session_id": runtime_session_id,
        }
    }

    # AgentCore expects bytes/file-like data, not a plain Python string.
    payload_bytes = json.dumps(request_payload).encode("utf-8")

    try:
        print("Agent ARN:", settings.agent_arn)
        print("Region:", settings.aws_region)
        print("Runtime session ID:", runtime_session_id)
        print("Payload:", json.dumps(request_payload, indent=2))

        response = agent_core_client.invoke_agent_runtime(
            agentRuntimeArn=settings.agent_arn,
            runtimeSessionId=runtime_session_id,
            qualifier="DEFAULT",
            contentType="application/json",
            accept="application/json",
            payload=payload_bytes,
        )

        response_body = response["response"].read()
        response_text = response_body.decode("utf-8")

        print("Status code:", response.get("statusCode"))
        print("Content type:", response.get("contentType"))
        print("Raw response:", response_text)

        if not response_text:
            return None

        return json.loads(response_text)

    except ParamValidationError as exc:
        print("Invalid Boto3 request parameters:", str(exc))
        raise

    except ClientError as exc:
        error_response = exc.response

        print(
            "AgentCore ClientError:",
            json.dumps(error_response, indent=2, default=str),
        )

        raise

    except Exception as exc:
        print(
            f"Unexpected AgentCore invocation error: "
            f"{type(exc).__name__}: {exc}"
        )
        raise

def invoke_as_user_(user_id, session_id, prompt):
    try:
        agent_core_client = boto3.client('bedrock-agentcore', region_name=settings.aws_region)
        payload = json.dumps({
            "input": {
                "prompt": prompt,
                "user_id": user_id,
                "session_id": session_id
                }
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
        response_data = invoke_as_user(prompt, user_id, session_id)

        return InvocationResponse(output=response_data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent API invocation failed: {str(e)}")
    
@app.get("/ping")
async def ping():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
