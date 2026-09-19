"""Graph routing functions."""

from langchain_core.messages.utils import count_tokens_approximately
from langgraph.graph import END

from app.orchestration.state import State

# Once the persisted (raw) history's token count exceeds this, summarize + prune it.
# Kept below MAX_TOKENS (nodes/generate_response.py) so summarize has a chance to
# compress content before trim_messages would otherwise start excluding it from the
# very next turn's prompt.
SUMMARIZE_AFTER_TOKENS = 6000


def should_summarize(state: State) -> str:
    token_count = count_tokens_approximately(state["messages"])
    return "summarize" if token_count > SUMMARIZE_AFTER_TOKENS else END
