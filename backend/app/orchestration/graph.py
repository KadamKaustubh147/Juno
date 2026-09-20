"""The chat graph, checkpointed to Postgres per `thread_id` so conversations survive restarts.

    START -> retrieve_memories -> assess_completion -> (session_done -> END
                                                        | section_complete -> select_next_section -> chatbot
                                                        | chatbot)
    chatbot -> ingest_memory -> (summarize) -> END

The structure lives in graph_builder.py; this module only attaches the Postgres checkpointer
(which connects at import time -- import graph_builder instead if you don't want a database).
"""

from app.orchestration.checkpointer import checkpointer
from app.orchestration.graph_builder import build_graph

graph = build_graph(checkpointer)
