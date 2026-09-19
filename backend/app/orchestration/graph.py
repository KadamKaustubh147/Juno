"""The chat graph: START -> retrieve_memories -> chatbot -> ingest_memory -> (summarize) -> END.

Checkpointed to Postgres per `thread_id`, so conversations survive restarts.
"""

from langgraph.graph import END, START, StateGraph

from app.orchestration.checkpointer import checkpointer
from app.orchestration.edges import should_summarize
from app.orchestration.nodes.generate_response import generate_response
from app.orchestration.nodes.memory_hook import ingest_memory, retrieve_memories
from app.orchestration.nodes.summarize import summarize
from app.orchestration.state import State

graph_builder = StateGraph(State)
graph_builder.add_node("retrieve_memories", retrieve_memories)
graph_builder.add_node("chatbot", generate_response)
graph_builder.add_node("ingest_memory", ingest_memory)
graph_builder.add_node("summarize", summarize)
graph_builder.add_edge(START, "retrieve_memories")
graph_builder.add_edge("retrieve_memories", "chatbot")
graph_builder.add_edge("chatbot", "ingest_memory")
graph_builder.add_conditional_edges("ingest_memory", should_summarize, {"summarize": "summarize", END: END})
graph_builder.add_edge("summarize", END)

graph = graph_builder.compile(checkpointer=checkpointer)
