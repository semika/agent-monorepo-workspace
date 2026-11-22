from typing import TypedDict, Sequence, Annotated
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph.message import add_messages
from langchain_core.tools import tool
from config import settings
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import BaseMessage, AnyMessage, SystemMessage, HumanMessage
from langgraph.prebuilt import ToolNode
import os

document_content = ''

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

@tool
def update(content:str) -> str:
    """Update the document with provided content"""
    global document_content
    document_content = content
    return f"The document has been updated successfully, current content is: \n {document_content}"

@tool
def save(filename:str) -> str :
    """Save the current content into a files on the disk and finish the process
    Args : filename, name of the file 
    """

    global document_content
    if not filename.endswith('.txt'):
        filename = filename + '.txt'

    try:
        with open(filename, "w") as file:
            file.write(document_content)
    except Exception as e:
        print(f"Error when saving the document {e}")  
        return f"Error when saving the document {e}"   


def invoke_llm(state:AgentState) -> AgentState:
    ## Reference documentation - https://reference.langchain.com/python/langchain-aws/chat_models/bedrock_converse/ChatBedrockConverse
    model = ChatBedrockConverse(
        # claude sonet will have to be used via inference profile.
        model_id=settings.model_id,  # cross-region inference profile
        region_name=settings.aws_region,
        temperature=1,
        provider='anthropic'
    )
    model = model.bind_tools([update, save])

    system_msg = SystemMessage("""

        You are a email drafter and helpful writing emails. You are going to help the users to update or create documents.
        If the user want to update or modify content, use the 'update' tool with the full content provided.
        If the user want to save the content into the disc and finish, use 'save' tool.
        Make sure always to show current document content after the modificaiton.

        The current document content is {document_content}                                                                                                                   

    """)
    
    if not state['messages']:
        user_input = input("I am ready to accept contents. What would you like to create ?\n")
        user_message = HumanMessage(content=user_input)
    else:
        user_input = input("")
        #print(f"User: {user_input}")  
        user_message = HumanMessage(content=user_input)  
        
    all_messages = [system_msg] + state['messages'] + [user_message]
    response = model.invoke( all_messages)  # Returns AIMessage
    print(f"AI: {response.content}")

    # Check for any tool call request
    if hasattr(response, "tool_calls") and response.tool_calls:
        print(f"Invoking tool: {[tc['name'] for tc in response.tool_calls]}")

    state['messages'] = state["messages"] + [response]    
    return state

def should_continue(state:AgentState) -> str :
    messages = state['messages']
    if not messages:
        return "continue"

    for message in reversed(messages):
        if isinstance(message, ToolMessage) and "saved" in message.content.lower() and "document" in message.content.lower():
            return "end"
    return "continue"

# def should_call_tool(state:AgentState) -> str:
#     messages = state['messages']
#     if not messages:
#         return "no_tool"

#     last_message = messages[-1]
#     if isinstance(last_message, AIMessage) and last_message.tool_calls:
#         return "tool"
#     return "no_tool"

#Init the graph
graph = StateGraph(AgentState)

#Add nodes
graph.add_node("invoke_llm", invoke_llm)

tool_node = ToolNode([update, save])
graph.add_node("tool_node", tool_node)

#Add edges
graph.add_edge(START, "invoke_llm")
graph.add_edge("invoke_llm", "tool_node")
graph.add_conditional_edges(
    "tool_node",
    should_continue,
    {
        "continue": "invoke_llm",
        "end": END
    }
)

agent = graph.compile()

# Show the agent
graph_path = os.path.join(os.path.dirname(__file__), "lang-graph-email-drafter.png")
with open(graph_path, "wb") as f:
    f.write(agent.get_graph(xray=True).draw_mermaid_png())

def print_messages(messages):
    if not messages:
        return
    for message in messages:
        if isinstance(message, ToolMessage):
            print(f"ToolMessage: {message.content}")

def run_agent():
    input_state = {"messages": []}
    for step in agent.stream(input_state):
        if "messages" in step:
            print_messages(step['messages'])

    print("Conversation Ended")  

run_agent()          
