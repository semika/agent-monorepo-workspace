from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage, AnyMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
import operator
from config import settings
from langchain_aws import ChatBedrockConverse
from langgraph.graph import START, END, StateGraph, MessagesState
import os

@tool
def add(a:int, b:int) -> int:
    """This function will add two integers"""
    return a+b

@tool
def sub(a:int, b:int) -> int:
    """This function will subtract second parameter value from the first parameter"""
    return a-b

@tool
def mul(a:int, b:int) -> int:
    """This function will perform multipication of two provided numbers"""
    return a*b

@tool
def div(a:int, b:int) -> int:
    """This function will perform divisionn of two provided numbers.
    The first parameter will be divided by the second parameter."""
    return a / b

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]

def llm(state:AgentState) -> AgentState:
    ## Reference documentation - https://reference.langchain.com/python/langchain-aws/chat_models/bedrock_converse/ChatBedrockConverse
    model = ChatBedrockConverse(
        # claude sonet will have to be used via inference profile.
        model_id=settings.model_id,  # cross-region inference profile
        region_name=settings.aws_region,
        temperature=1,
        provider='anthropic'
    )
    model = model.bind_tools([add, sub, mul, div])

    system_msg = SystemMessage("""

        You are a person with lots of knowledge about the world.

    """)
    
    # Use with chat models. Pass the full accumulated history (not just the
    # first message) so the model has context from earlier turns.
    messages = [system_msg] + state["messages"]
    response = model.invoke(messages)  # Returns AIMessage
    state["messages"] = state["messages"] + [response]
    return state   

def should_continue(state:AgentState) -> str:
    last_message = state['messages'][-1]
    if last_message.tool_calls:
        return "continue"
    else:
        return "end"
    
#Initiate the graph 
graph = StateGraph(AgentState)

#Add nodes
graph.add_node("llm",llm)

tool_node = ToolNode(tools=[add, sub, mul, div])
graph.add_node("tool_node", tool_node)

#Add edges
graph.add_edge(START, "llm")
graph.add_conditional_edges(
    "llm",
    should_continue,
    {
        "end": END,
        "continue":"tool_node"
    }
)
graph.add_edge("tool_node", "llm")
graph.add_edge("llm", END)

agent = graph.compile()

# Show the agent
graph_path = os.path.join(os.path.dirname(__file__), "lang-graph-toolnode.png")
with open(graph_path, "wb") as f:
    f.write(agent.get_graph(xray=True).draw_mermaid_png())


def print_stream(stream):
    for update in stream:
        for node_name, node_output in update.items():
            print(f"--- {node_name} ---")
            for message in node_output.get("messages", []):
                message.pretty_print()
            print()

input_state = {"messages": [HumanMessage(content="Add 4 and 2 and then multiply it by six")]}
stream = agent.stream(input_state, stream_mode="updates")
print_stream(stream)
