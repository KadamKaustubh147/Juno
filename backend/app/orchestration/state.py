"""State that flows through the graph. `add_messages` appends instead of overwriting."""

import operator
from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class State(TypedDict):
    messages: Annotated[list, add_messages]
    summary: str
    memory_context: str  # formatted, ready to drop into a SystemMessage; "" if nothing relevant

    # Script-based dialog policy (see nodes/assess_completion.py, nodes/select_next_section.py).
    # current_section persists across turns via the checkpoint; the flags below are re-derived
    # by assess_completion at the start of every turn.
    current_section: str  # a key of script.json, e.g. "Section 1"
    section_complete: bool  # this turn: the assessor judged the current section finished
    session_done: bool  # the terminal section is finished -- sticky once set, the graph ends every turn with no reply
    thought: str  # the latest assessor/dispatcher reasoning. Stored for debugging; never shown to the patient
    transitions: Annotated[list[dict], operator.add]  # history, {"from", "to", "reasoning"}; appended, never overwritten
