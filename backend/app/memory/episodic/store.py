"""Per-session transcript persistence -- no standalone module yet.

The closest current equivalent is the `messages` table (initdb/02-messages.sql) and
app/features/sessions/service.py's archive()/list_sessions()/list_messages(), which
write every user/assistant turn verbatim for scrollback -- distinct from, and never
read by, the long-term memory system in app/memory/semantic/ and app/memory/retriever.py.
"""
