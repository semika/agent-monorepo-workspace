## User
I want to understand how every new message that user inputs  is appened to state['messages'].  At line 51, and 52, when I invoke the graph, I only set the user's latest message only ?

## Agent
Correct — you only pass the latest message, and that's intentional, not a gap. Here's the mechanism:

MessagesState.messages is annotated with a reducer (Annotated[list[AnyMessage], add_messages]), same idea as the operator.add reducer you saw in lang-graph-calculator.py — but add_messages is smarter: it merges by message id rather than blind concatenation (dedupes/updates existing messages, appends genuinely new ones).

The checkpointer holds the authoritative history per thread_id. When you call graph.invoke({"messages": [prompt_message]}, thread_config), LangGraph first loads the last checkpointed state for "cli-session-1" — the full accumulated messages list from all prior turns.

Your input dict is treated as a partial update, not a replacement. LangGraph applies the add_messages reducer to merge [prompt_message] onto the loaded history. Since your new HumanMessage has a fresh id, it gets appended — the result (full history + new message) becomes the actual state handed to the llm node. So by the time state["messages"] is read inside your node, it already contains everything from earlier turns plus this new one.

The node's return value goes through the same merge. Your node returns state["messages"] = state["messages"] + [response] (full list including old messages again) — that's fine because add_messages recognizes the already-known messages by id and doesn't duplicate them; only the new AIMessage (new id) actually gets appended.

After the run reaches END, the merged state is written back to the checkpoint for "cli-session-1", ready to be reloaded on the next invoke.

So the "appending" happens at the framework level (checkpoint load → reducer merge → checkpoint save) around every invoke call, not because you're manually passing the whole list each time.

## Related to multi agent workflow
New flow: clarifier_agent runs first on every turn. It looks at the full conversation and decides READY or NEED_INFO: <question>. If info is missing, it routes to ask_user, which calls interrupt() — this pauses the graph and .invoke() returns immediately with the question, without ever reaching the planner/worker. Only once clarifier_agent says READY does the graph proceed to planner → worker → reviewer.

State/persistence fixes:

State is now a TypedDict (AgentState) with messages: Annotated[list, add_messages], so conversation history accumulates across turns instead of being overwritten.
The endpoint now checks multi_agent.get_state(config).next to tell whether this thread is mid-interrupt. If so, it resumes with Command(resume=user_query) (the user's answer) instead of blowing away state with a fresh initial_state. If not, it starts a new run as before.
Fixed the "user_query": {user_query} bug (was a set literal, not a string).
Fixed the reviewer's dead startswith("Reason:") check (was comparing a lowercased string against a capitalized literal, so it never matched).
session_id is now required — it's the thread key, so a caller must supply one to get continuity.
Response shape: output now includes status: "needs_input" (with the question in message) or "completed" (with the final content), plus session_id so the client knows what to send back on the next turn.

Caveats to know about:

InMemorySaver is process-local — restarting the server loses all in-flight conversations. Fine for dev; swap for a DB-backed checkpointer before production.
Added a MAX_CLARIFICATION_ROUNDS cap (5) so a confused clarifier can't loop forever — mirrors the existing reviewer's reviewer_calls >= 2 cap.
To try it: POST {"input": {"prompt": "Can you create an email requesting a leave?", "user_id": "u1", "session_id": "s1"}} — expect status: needs_input with a question. Send the answer back with the same session_id as the next prompt, repeat until status: completed.
