from typing import TypedDict, List
from langgraph.graph import StateGraph, START, END
import random
import os

class AgentState(TypedDict):
    name:str
    number:List[int]
    counter:int
    number_guess: int

def greeting_code(state:AgentState) -> AgentState:
    state['name'] = f"Hi There, {state['name']}. Let's start the game ....!"   
    state['counter'] = 0 
    return state

def random_number(state:AgentState) -> AgentState :
    state['number'].append(random.randint(0, 10))
    #state['counter'] += 1
    return state

def guess_number(state:AgentState) -> AgentState:
    number_guess = int(input("Enter your gussing number: "))
    state['number_guess'] = number_guess
    state['counter'] += 1
    return state
    
def should_continue(state:AgentState) -> AgentState:
    
    if state['counter'] < 5:
        if state['number'] == state['number_guess']:
            print("You won the game ...")
            return "won"
        else: 
            print(f"Try agin...! Attempt count = {state['counter']}")
            return 'guess'
    else:
        print(f"Num of attempts exceeded..!, {state['counter']}")
        return 'exit'

#Init graph
graph = StateGraph(AgentState)

#Add nodes
graph.add_node("greeting", greeting_code)
graph.add_node("random_number", random_number)
graph.add_node("guess_number", guess_number)

# Add edges

graph.add_edge(START, "greeting")
graph.add_edge("greeting", "random_number")
graph.add_edge("random_number", "guess_number")
graph.add_conditional_edges(
    "guess_number",
    should_continue,
    {
       "guess": "guess_number",
       "won": END,
       "exit": END
    }
)
graph.add_edge("random_number", END)
agent = graph.compile()

# Display graph
graph_path = os.path.join(os.path.dirname(__file__), "lang-graph-multi-iteration.png")
with open(graph_path, "wb") as f:
    f.write(agent.get_graph(xray=True).draw_mermaid_png())


input_state = {
    "name":"semika",
    "number": []
}
response = agent.invoke(input_state)
print(response)
