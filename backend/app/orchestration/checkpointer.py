"""Postgres-backed LangGraph checkpointer -- conversation history survives process restarts."""

from langgraph.checkpoint.postgres import PostgresSaver

from app.core.db import connection_pool

checkpointer = PostgresSaver(connection_pool)
checkpointer.setup()  # idempotent -- creates the checkpoint tables on first run only
