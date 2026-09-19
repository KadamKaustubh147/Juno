"""Node: call the LLM to generate the assistant's reply.

Registered in the graph under the name "chatbot" (see graph.py) -- the chat
service filters the token stream on that node name, so it must not change.

Short-term memory: every turn, only a token-capped window of the raw history is
sent to the model (`trim_messages`) -- a safety net against context-window overflows.
"""

from langchain_core.messages import SystemMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages

from app.orchestration.llm_client import llm
from app.orchestration.state import State

# How much of the raw history to actually send the LLM each turn. Model window is 131k
# tokens; this is just a guard-rail against a handful of oversized messages, not a lever
# you'll feel day to day since `summarize` keeps the raw history short anyway.
MAX_TOKENS = 8000


def generate_response(state: State):
    summary = state.get("summary", "")
    memory_context = state.get("memory_context", "")
    messages = state["messages"]

    # Memories first, summary second -- memories are patient-specific facts (retrieved
    # fresh every turn, so they matter regardless of how the chat has drifted); the
    # summary is this conversation's own recent thread. Both are optional independently.
    system_parts = []
    if memory_context:
        system_parts.append(f"Relevant things you remember about this patient:\n{memory_context}")
    if summary:
        system_parts.append(f"Summary of the conversation so far:\n{summary}")

    if system_parts:
        messages = [SystemMessage(content="\n\n".join(system_parts))] + messages

    # Cap what's actually sent to the LLM this turn -- doesn't touch persisted state.
    trimmed = trim_messages(
        messages,
        strategy="last",
        token_counter=count_tokens_approximately,
        max_tokens=MAX_TOKENS,
        start_on="human",
        include_system=True,
    )

    response = llm.invoke(trimmed)
    return {"messages": [response]}
