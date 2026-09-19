"""Short-term / in-turn conversation buffer -- no standalone module yet.

The closest current equivalent is the raw `messages` list + `summary` string kept in
the LangGraph checkpoint state: token-capped per turn by trim_messages in
app/orchestration/nodes/generate_response.py (MAX_TOKENS), and folded + pruned by
app/orchestration/nodes/summarize.py past SUMMARIZE_AFTER_TOKENS (app/orchestration/edges.py).
"""
