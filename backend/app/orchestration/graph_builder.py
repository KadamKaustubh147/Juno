
"""Builds the chat graph. Kept apart from graph.py so it can be built without a database.

graph.py imports the Postgres checkpointer, which connects at import time; anything that needs
the graph *shape* on its own (tests) imports `build_graph` from here and passes its own checkpointer.

    START -> retrieve_memories -> assess_completion -> route_after_assessment
                                                        |-- session_done ------> END
                                                        |-- section_complete --> select_next_section -> chatbot
                                                        `-- otherwise ---------> chatbot
    chatbot -> ingest_memory -> should_summarize -> (summarize -> END | END)
"""

from langgraph.graph import END, START, StateGraph

from app.orchestration.edges import route_after_assessment, should_summarize
from app.orchestration.nodes.assess_completion import assess_completion
from app.orchestration.nodes.generate_response import generate_response
from app.orchestration.nodes.memory_hook import ingest_memory, retrieve_memories
from app.orchestration.nodes.select_next_section import select_next_section
from app.orchestration.nodes.summarize import summarize
from app.orchestration.state import State


def build_graph(checkpointer):
    builder = StateGraph(State)
    builder.add_node("retrieve_memories", retrieve_memories)
    builder.add_node("assess_completion", assess_completion)
    builder.add_node("select_next_section", select_next_section)
    builder.add_node("chatbot", generate_response)  # name is load-bearing: the chat service filters the stream on it
    builder.add_node("ingest_memory", ingest_memory)
    builder.add_node("summarize", summarize)

    builder.add_edge(START, "retrieve_memories")
    builder.add_edge("retrieve_memories", "assess_completion")
    builder.add_conditional_edges(
        "assess_completion",
        route_after_assessment,
        {"select_next_section": "select_next_section", "chatbot": "chatbot", END: END},
    )
    builder.add_edge("select_next_section", "chatbot")
    builder.add_edge("chatbot", "ingest_memory")
    builder.add_conditional_edges("ingest_memory", should_summarize, {"summarize": "summarize", END: END})
    builder.add_edge("summarize", END)

    return builder.compile(checkpointer=checkpointer)
