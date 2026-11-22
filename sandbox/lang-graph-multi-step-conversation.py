from langgraph.graph import START, END, StateGraph, MessagesState
from langgraph.checkpoint.memory import InMemorySaver
from config import settings
from langchain_aws import ChatBedrockConverse
from langchain.messages import HumanMessage, AIMessage, SystemMessage
from langchain.messages import AnyMessage
from typing_extensions import TypedDict, Annotated
import operator
class AgentState(TypedDict) :
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

    system_msg = SystemMessage("""

        You are a person with lots of knowledge about the world.

    """)
    
    # Use with chat models. Pass the full accumulated history (not just the
    # first message) so the model has context from earlier turns.
    messages = [system_msg] + state["messages"]
    response = model.invoke(messages)  # Returns AIMessage
    state["messages"] = state["messages"] + [response]
    return state


checkpointer = InMemorySaver()

graph = StateGraph(AgentState)
graph.add_node(llm)
graph.add_edge(START, "llm")
graph.add_edge("llm", END)
graph = graph.compile(checkpointer=checkpointer)
#print(graph)

# Approch 1 - Using HumanMessage object
user_input = "How can I help you..?"
print("AI :" + user_input)

# Fixed thread_id so every invoke() in this session shares the same
# checkpointed state. Use a different thread_id per user/session in a
# real app so conversations don't bleed into each other.
thread_config = {"configurable": {"thread_id": "cli-session-1"}}

while user_input != 'exit':
    user_input = input("User:")
    prompt_message = HumanMessage(content=user_input)
    response = graph.invoke({"messages": [prompt_message]}, thread_config)
    print(response.get('messages')[-1].text)

## Approach 2 - Using Json style format for human message. Since role is 'user', it will automatically
## create HumanMessage internally.

#graph.invoke({"messages": [{"role": "user", "content": "What is the largest country in the world"}]})    
