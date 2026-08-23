"""Minimal LangChain + LangGraph boilerplate, wired to Groq.

Short-term memory strategy:
- Every turn, `chatbot` sends the model only a token-capped window of the raw
  history (`trim_messages`) -- a safety net against context-window overflows.
- Once the raw history's token count passes SUMMARIZE_AFTER_TOKENS, `summarize`
  folds the older turns into a running `summary` string and deletes them from
  state (`RemoveMessage`), so what's persisted in Postgres doesn't grow forever
  either. The threshold is token-based (not message-count) and set below
  MAX_TOKENS on purpose: it needs to fire *before* `trim_messages` would
  otherwise start silently excluding old content from the model's view.
"""

import os
from typing import Annotated

import mlflow
import mlflow.langchain
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, RemoveMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from typing_extensions import TypedDict

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

# Per MLflow's own tracing quickstart: point at a running `mlflow server`, set an
# experiment to group traces under, then autolog. Start the server yourself first:
#   uvx mlflow server
mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("ai-therapist-chatbot")
mlflow.langchain.autolog()

# How much of the raw history to actually send the LLM each turn. Model window is 131k
# tokens; this is just a guard-rail against a handful of oversized messages, not a lever
# you'll feel day to day since `summarize` below keeps the raw history short anyway.
MAX_TOKENS = 8000

# Once the persisted (raw) history's token count exceeds this, summarize + prune it.
# Kept below MAX_TOKENS so summarize has a chance to compress content before trim_messages
# would otherwise start excluding it from the very next turn's prompt.
SUMMARIZE_AFTER_TOKENS = 6000


# 1. State: what flows through the graph. `add_messages` appends instead of overwriting.
class State(TypedDict):
    messages: Annotated[list, add_messages]
    summary: str


# 2. The model.

# qwen can used for script based processing tasks
# MODEL_NAME = "qwen/qwen3.6-27b"
MODEL_NAME = "openai/gpt-oss-20b"
llm = ChatGroq(model=MODEL_NAME)


# 3. Nodes.
def chatbot(state: State):
    summary = state.get("summary", "")
    messages = state["messages"]

    if summary:
        messages = [SystemMessage(content=f"Summary of the conversation so far:\n{summary}")] + messages

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


def should_summarize(state: State) -> str:
    token_count = count_tokens_approximately(state["messages"])
    return "summarize" if token_count > SUMMARIZE_AFTER_TOKENS else END


# 4. Wire the graph: START -> chatbot -> (summarize) -> END.
graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_node("summarize", summarize)
graph_builder.add_edge(START, "chatbot")
graph_builder.add_conditional_edges("chatbot", should_summarize, {"summarize": "summarize", END: END})
graph_builder.add_edge("summarize", END)

# Postgres-backed checkpointer -- conversation history survives process restarts.
# A pool (not a single connection) so the FastAPI server can serve concurrent requests
# without each request paying for a fresh TCP/auth handshake or serializing on one socket.
connection_pool = ConnectionPool(
    conninfo=DATABASE_URL,
    max_size=20,
    kwargs={
        "autocommit": True,
        # psycopg returns rows as plain tuples by default (no column names, e.g.
        # `(1, 'alice')`). PostgresSaver's internals read columns by name (row["checkpoint"],
        # row["metadata"], ...), so we tell psycopg to hand back dict-shaped rows instead
        # (e.g. `{"id": 1, "name": "alice"}`) -- this is a documented requirement of
        # PostgresSaver, not optional styling.
        "row_factory": dict_row,
    },
)
checkpointer = PostgresSaver(connection_pool)
checkpointer.setup()  # idempotent -- creates the checkpoint tables on first run only

# Named `graph` (not `app`) so api/server.py can import it without clashing with the FastAPI `app`.
graph = graph_builder.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "1"}}

    print("Type 'quit' to exit.")

    while True:
        user_input = input("You: ")

        if user_input.lower() in ("quit", "exit"):
            break

        print("AI: ", end="", flush=True)

        # stream_mode="messages" yields (chunk, metadata) as the LLM produces tokens, from
        # *any* node that calls the LLM -- including `summarize`, if it runs this turn. Its
        # metadata["langgraph_node"] tells us which node emitted the chunk, so we only print
        # the actual reply, not the internal summary text.
        for chunk, metadata in graph.stream(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config,
            stream_mode="messages",
        ):
            if metadata.get("langgraph_node") == "chatbot":
                print(chunk.content, end="", flush=True)

        print()
