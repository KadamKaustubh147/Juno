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
# from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from typing_extensions import TypedDict

from ai.memory.encoding_gate import evaluate
from ai.memory.retrieval import retrieve
from ai.memory.store import insert_memory, search_dense

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

# Per MLflow's own tracing quickstart: point at a running `mlflow server`, set an
# experiment to group traces under, then autolog. Start the server yourself first:
#   uvx mlflow server
# mlflow.set_tracking_uri("http://localhost:5000")
# mlflow.set_experiment("ai-therapist-chatbot")
# mlflow.langchain.autolog()

# How much of the raw history to actually send the LLM each turn. Model window is 131k
# tokens; this is just a guard-rail against a handful of oversized messages, not a lever
# you'll feel day to day since `summarize` below keeps the raw history short anyway.
MAX_TOKENS = 8000

# Once the persisted (raw) history's token count exceeds this, summarize + prune it.
# Kept below MAX_TOKENS so summarize has a chance to compress content before trim_messages
# would otherwise start excluding it from the very next turn's prompt.
SUMMARIZE_AFTER_TOKENS = 6000

# How many memories to pull into context per turn, and how many nearby memories the
# encoding gate looks at when deciding if a message is novel/contradictory. Both are
# small because retrieved memories go straight into the prompt -- too many and they
# start crowding out the actual conversation.
RETRIEVE_LIMIT = 5


# 1. State: what flows through the graph. `add_messages` appends instead of overwriting.
class State(TypedDict):
    messages: Annotated[list, add_messages]
    summary: str
    memory_context: str  # formatted, ready to drop into a SystemMessage; "" if nothing relevant


# 2. The model.

# qwen can used for script based processing tasks
# MODEL_NAME = "qwen/qwen3.6-27b"
MODEL_NAME = "openai/gpt-oss-120b"
llm = ChatOpenAI(model=MODEL_NAME, base_url="https://aicredits.in/v1")


# 3. Nodes.

# TrueMemory context: retrieve_memories runs before chatbot and fills memory_context;
# ingest_memory runs after and writes new memories from this turn. Between them they're
# the whole long-term-memory loop -- everything either side of "ask the model" in this
# node stays as it was.
def retrieve_memories(state: State, config: RunnableConfig) -> dict:
    """Pull this user's memories relevant to what they just said.

    Runs first in the graph, so `state["messages"][-1]` is always the message that
    just came in -- that's what's used as the retrieval query.
    """
    user_id = config["configurable"].get("user_id", "")
    messages = state["messages"]

    if not user_id or not messages:
        return {"memory_context": ""}

    query = messages[-1].content
    if not query:
        return {"memory_context": ""}

    hits = retrieve(user_id, query, limit=RETRIEVE_LIMIT)
    if not hits:
        return {"memory_context": ""}

    memory_context = "\n".join(f"- {hit['content']}" for hit in hits)
    return {"memory_context": memory_context}


def chatbot(state: State):
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


# TODO: same as summarize below -- runs synchronously in-graph, so every turn pays for
# up to two embeddings (one per message) plus a dense search, before the request can
# close. Small (milliseconds), unlike summarize's extra LLM call, but it's still on the
# request path. Move both off it together later.
def ingest_memory(state: State, config: RunnableConfig) -> dict:
    """Run this turn's messages through the encoding gate; store what it admits.

    Runs on BOTH sides of the conversation -- the patient's message and the
    therapist's own reply -- since a thing the bot noticed out loud ("you've
    mentioned insomnia three times") is itself worth remembering later.
    """
    user_id = config["configurable"].get("user_id", "")
    if not user_id:
        return {}

    # The turn that just happened: whatever the user sent in, plus chatbot's reply.
    # Filtering by type (not just "last 2") protects against ingest_memory ever running
    # on a turn shaped differently than expected.
    turn = [m for m in state["messages"][-2:] if isinstance(m, (HumanMessage, AIMessage))]

    for message in turn:
        text = message.content
        if not text:
            continue

        role = "user" if isinstance(message, HumanMessage) else "assistant"

        # Nearest existing memories on the same topic -- what the gate's novelty and
        # prediction-error signals compare this message against. Dense (semantic)
        # search only: the gate wants "does this restate/contradict something we
        # already know", which is a meaning question, not a keyword one -- no need
        # for the lexical side or RRF fusion that `retrieve()` does for prompt context.
        nearby = search_dense(user_id, text, limit=RETRIEVE_LIMIT)
        nearby_texts = [row["content"] for row in nearby]

        decision = evaluate(text, nearby_texts)
        if decision.should_encode:
            insert_memory(user_id, role, text, decision)

    return {}


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


# 4. Wire the graph: START -> retrieve_memories -> chatbot -> ingest_memory -> (summarize) -> END.
graph_builder = StateGraph(State)
graph_builder.add_node("retrieve_memories", retrieve_memories)
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_node("ingest_memory", ingest_memory)
graph_builder.add_node("summarize", summarize)
graph_builder.add_edge(START, "retrieve_memories")
graph_builder.add_edge("retrieve_memories", "chatbot")
graph_builder.add_edge("chatbot", "ingest_memory")
graph_builder.add_conditional_edges("ingest_memory", should_summarize, {"summarize": "summarize", END: END})
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
    # user_id is required for retrieve_memories/ingest_memory to do anything -- without
    # it they silently no-op, same as when the API omits it.
    config = {"configurable": {"thread_id": "1", "user_id": "1"}}

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
