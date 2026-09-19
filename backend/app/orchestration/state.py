"""State that flows through the graph. `add_messages` appends instead of overwriting."""

from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class State(TypedDict):
    messages: Annotated[list, add_messages]
    summary: str
    memory_context: str  # formatted, ready to drop into a SystemMessage; "" if nothing relevant
