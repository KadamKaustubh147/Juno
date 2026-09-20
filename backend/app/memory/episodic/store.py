"""Per-session transcript persistence -- no standalone module yet.

The closest current equivalent is the `messages` table (app/features/sessions/models.py) and
app/features/sessions/service.py's archive()/list_sessions()/list_messages(), which
write every user/assistant turn verbatim for scrollback -- distinct from, and never
read by, the long-term (episodic) memory system next to this file: vector_store.py and retriever.py.
"""
