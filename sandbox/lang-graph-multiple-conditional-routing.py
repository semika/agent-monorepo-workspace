from typing import TypedDict
from langgraph.graph import StateGraph, START, END
import os

class AgentState(TypedDict):
    number1:int
    number2:int
    number3:int
    number4:int
    operation1: str
    operation2: str
    result1: int
    result2: int

def add1(state:AgentState) -> AgentState :
    state['result1'] = state['number1'] + state['number2']
    return state

def subtract1(state:AgentState) -> AgentState :
    state['result1'] = state['number1'] - state['number2']
    return state

def add2(state:AgentState) -> AgentState :
    state['result2'] = state['number3'] + state['number4']
    return state    

def subtract2(state:AgentState) -> AgentState :
    state['result2'] = state['number3'] - state['number4']
    return state  

def next_node1(state:AgentState) -> str:
    if state['operation1'] == '+':
        return 'add1'
    elif state['operation1'] == '-':
        return 'sub1' 
    
def next_node2(state:AgentState) -> str:
    if state['operation2'] == '+':
        return 'add2'
    elif state['operation2'] == '-':
        return 'sub2'

graph = StateGraph(AgentState)
graph.add_node("add1", add1)
graph.add_node("sub1", subtract1) 
graph.add_node("add2", add2)
graph.add_node("sub2", subtract2) 
graph.add_node("router1", lambda state:state)
graph.add_node("router2", lambda state:state)

#add edges
graph.add_edge(START, "router1")
graph.add_conditional_edges(
    "router1",
    next_node1,
    {
        "add1": "add1",
        "sub1": "sub1"
    }
)
graph.add_edge("add1", "router2")
graph.add_edge("sub1", "router2")
graph.add_conditional_edges(
    "router2",
    next_node2,
    {
        "add2": "add2",
        "sub2": "sub2"
    }
)
graph.add_edge("add2", END)
graph.add_edge("sub2", END)

#Initiate agent
agent = graph.compile()

# Show the agent
graph_path = os.path.join(os.path.dirname(__file__), "lang-graph-multiple-conditional-routing.png")
with open(graph_path, "wb") as f:
    f.write(agent.get_graph(xray=True).draw_mermaid_png())


input_state = {
    "number1":5,
    "number2":4,
    "number3":10,
    "number4":6,
    "operation1": "+",
    "operation2": "-"
}

response = agent.invoke(input_state)
print(response)
