from typing import TypedDict, List
from langgraph.graph import StateGraph, START, END
import os


class AgentState(TypedDict):
    name: str
    age: str
    skills: List[str]
    result: str

def first_node(state:AgentState) -> AgentState:
    """This is the first node"""
    state["result"]=f"{state['name']}, Welcome to the system"
    return state


def second_node(state:AgentState)-> AgentState:
    """This is the second node"""
    skills = ", ".join(state['skills'])
    state['result'] = state['result'] + f"You have skills in {skills}"
    return state

def third_node(state:AgentState) -> AgentState:
    """This is the third node"""
    state['result'] = state['result'] + f"You are {state['age']} years old"
    return state

#Initialize graph
graph = StateGraph(AgentState)

#Add nodes to the graph
graph.add_node("first_node", first_node)
graph.add_node("second_node", second_node)
graph.add_node("third_node", third_node)

#Add edges to the graph
graph.add_edge(START, "first_node")
graph.add_edge("first_node", "second_node")
graph.add_edge("second_node", "third_node")
graph.add_edge("third_node", END)

agent = graph.compile()

# Display agent
# Show the agent
graph_path = os.path.join(os.path.dirname(__file__), "lang-graph-three-node-example.png")
with open(graph_path, "wb") as f:
    f.write(agent.get_graph(xray=True).draw_mermaid_png())

#Invoke agent

input_state = {
    "name":"Semika Siriwardana",
    "age": 46,
    "skills":['Java', 'C++', '.Net']
}    

response = agent.invoke(input_state)
print(response)

