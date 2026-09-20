"""Unified write interface for long-term memory -- thin re-export for this pass.

The actual "decide what's worth storing, then store it" orchestration (search
for nearby memories, run the encoding gate, insert what it admits) still lives
in app/orchestration/nodes/memory_hook.py's `ingest_memory` node, run on both the user's message
and the assistant's reply every turn. Extracting that node's body into a real
write() function here -- and having orchestration call it -- is a separate
follow-up pass; this file just gives callers one place to import "the writer"
pieces from in the meantime.
"""

from app.memory.episodic.encoding_gate import evaluate
from app.memory.episodic.vector_store import insert_memory

__all__ = ["evaluate", "insert_memory"]
