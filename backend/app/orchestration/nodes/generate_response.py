"""Node: call the LLM to generate the assistant's reply.

Registered in the graph under the name "chatbot" (see graph_builder.py) -- the chat
service filters the token stream on that node name, so it must not change.

The system message is built from the prompt files (persona + the current script section)
plus this turn's memory_context and running summary.

Short-term memory: every turn, only a token-capped window of the raw history is
sent to the model (`trim_messages`) -- a safety net against context-window overflows.
"""

from langchain_core.messages import SystemMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages

from app.orchestration.llm_client import llm, render_prompt
from app.orchestration.script_loader import FIRST_SECTION, section_text
from app.orchestration.state import State

# How much of the raw history to actually send the LLM each turn. Model window is 131k
# tokens; this is just a guard-rail against a handful of oversized messages, not a lever
# you'll feel day to day since `summarize` keeps the raw history short anyway.
MAX_TOKENS = 8000

# Appended (not templated) only on the turn a section change actually happened.
NEW_SECTION_NOTE = (
    "You have just entered this part of the conversation. Open it naturally: acknowledge what the "
    "patient just said, then lead into the first thing you need to do here."
)


def _entered_new_section(state: State) -> bool:
    """True if select_next_section moved to a different section on this turn.

    `section_complete` is re-derived every turn by assess_completion, so when it's set the
    newest `transitions` entry is this turn's. A dispatcher that failed to choose records
    from == to, which is not a move.
    """
    transitions = state.get("transitions") or []
    return bool(state.get("section_complete")) and bool(transitions) and transitions[-1]["from"] != transitions[-1]["to"]


def generate_response(state: State):
    summary = state.get("summary", "")
    memory_context = state.get("memory_context", "")
    section = state.get("current_section") or FIRST_SECTION
    messages = state["messages"]

    system_parts = [
        render_prompt("system_prompt.txt"),
        render_prompt("response_prompt.txt", section_name=section, section_text=section_text(section)),
    ]
    if _entered_new_section(state):
        system_parts.append(NEW_SECTION_NOTE)

    # Memories before summary -- memories are patient-specific facts (retrieved fresh every
    # turn, so they matter regardless of how the chat has drifted); the summary is this
    # conversation's own recent thread. Both are optional independently.
    if memory_context:
        system_parts.append(f"Relevant things you remember about this patient:\n{memory_context}")
    if summary:
        system_parts.append(f"Summary of the conversation so far:\n{summary}")

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
