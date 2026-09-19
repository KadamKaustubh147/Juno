"""Node: fold older turns into a running `summary` and prune them from persisted state.

Once the raw history's token count passes SUMMARIZE_AFTER_TOKENS (see edges.py),
this folds the older turns into `summary` and deletes them from state
(`RemoveMessage`), so what's persisted in Postgres doesn't grow forever either.
"""

from langchain_core.messages import HumanMessage, RemoveMessage

from app.orchestration.llm_client import llm
from app.orchestration.state import State


# TODO: this runs synchronously in-graph, so on whichever turn crosses SUMMARIZE_AFTER_TOKENS,
# the request stays open for this node's LLM call too (its text is filtered out of the
# stream, but the client still waits on it) -- a tail-latency spike on that one turn.
# Later: move this off the request path entirely -- a background task/queue (Celery,
# arq, FastAPI BackgroundTasks, ...) that runs summarization after the reply has already
# been streamed back, rather than as a graph node the request blocks on.
def summarize(state: State):
    existing_summary = state.get("summary", "")
    messages = state["messages"]

    if existing_summary:
        prompt = (
            f"Existing summary:\n{existing_summary}\n\n"
            "Extend the summary above using the new messages below."
        )
    else:
        prompt = "Summarize the conversation above."

    response = llm.invoke(messages + [HumanMessage(content=prompt)])

    # Keep only the last 2 raw messages verbatim; fold everything older into the summary.
    to_delete = messages[:-2]

    return {
        "summary": response.content,
        "messages": [RemoveMessage(id=m.id) for m in to_delete],
    }
