from typing import TypedDict
from langgraph.graph import StateGraph, START, END
import os

class AgentState(TypedDict):
    number1: int
    number2:int
    operation: str
    result: int


def add(state: AgentState) -> AgentState:
    """This adds two numbers"""
    state['result'] = state['number1'] + state['number2'] 
    return state

def subtract(state:AgentState) -> AgentState:
    """This subtracts number 2 from number 1"""
    state['result'] = state['number1'] - state['number2']
    return state

def decide_next_node(state:AgentState) -> str :
    """This node will decided the next node in the graph"""
    if state['operation'] == '+':
        return 'add_op'
    elif state['operation'] == '-':
        return 'subtract_op'

#initialize graph    
graph = StateGraph(AgentState)

#add nodes
graph.add_node("add_node", add)
graph.add_node("subtract_node", subtract)
graph.add_node("router", lambda state:state)

#add edgets
graph.add_edge(START, "router")
graph.add_conditional_edges(
    "router",
    decide_next_node,
    {
        'add_op': 'add_node',
        'subtract_op': 'subtract_node'
    }    
)
graph.add_edge("add_node", END)
graph.add_edge("subtract_node", END)

agent = graph.compile()

# Write graph as image
# graph_path = os.path.join(os.path.dirname(__file__), "lang-graph-conditional-routing.png")
# with open(graph_path, "wb") as f:
#     f.write(agent.get_graph(xray=True).draw_mermaid_png())

# Invoke agent
input_state = {
    'number1': 10,
    'number2': 4,
    'operation': "-"
}   

response = agent.invoke(input_state)
print(response)