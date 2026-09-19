"""Nodes that call into the long-term memory layer around each turn.

TrueMemory context: retrieve_memories runs before the LLM call and fills memory_context;
ingest_memory runs after and writes new memories from this turn. Between them they're
the whole long-term-memory loop.
"""

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.memory.encoding_gate import evaluate
from app.memory.retriever import retrieve
from app.memory.semantic.vector_store import insert_memory, search_dense
from app.orchestration.state import State

# How many memories to pull into context per turn, and how many nearby memories the
# encoding gate looks at when deciding if a message is novel/contradictory. Both are
# small because retrieved memories go straight into the prompt -- too many and they
# start crowding out the actual conversation.
RETRIEVE_LIMIT = 5


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

    # role="user": only surface things the patient actually said. ingest_memory
    # also stores admitted assistant replies (see its docstring), but those are
    # long, templated LLM scripts that dominate lexical/semantic overlap for
    # common queries and crowd out the concise, specific facts worth recalling.
    hits = retrieve(user_id, query, limit=RETRIEVE_LIMIT, role="user")
    if not hits:
        return {"memory_context": ""}

    memory_context = "\n".join(f"- {hit['content']}" for hit in hits)
    return {"memory_context": memory_context}


# TODO: same as summarize -- runs synchronously in-graph, so every turn pays for
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
