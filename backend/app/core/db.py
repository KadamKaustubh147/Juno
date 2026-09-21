"""psycopg connection pool for the LangGraph checkpointer only.

PostgresSaver needs a raw psycopg pool (dict rows, autocommit) and can't run on a
SQLAlchemy engine, so it keeps its own pool on the same DATABASE_URL. Everything
else goes through the SQLAlchemy engine in app/db/session.py.
"""

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import DATABASE_URL

# A pool (not a single connection) so the FastAPI server can serve concurrent requests
# without each request paying for a fresh TCP/auth handshake or serializing on one socket.
connection_pool = ConnectionPool(
    conninfo=DATABASE_URL,
    max_size=20,
    # Managed Postgres (and any NAT/firewall in between) silently drops idle SSL connections; without
    # this the pool hands out the dead socket and the query fails with "SSL error: unexpected eof".
    # `check` tests a connection as it's handed out (the counterpart of SQLAlchemy's pool_pre_ping in
    # app/db/session.py) and replaces a dead one; `max_idle` retires connections before they go stale.
    check=ConnectionPool.check_connection,
    max_idle=120,
    kwargs={
        "autocommit": True,
        # TCP keepalives keep idle sockets alive through NATs and let the OS notice a half-dead
        # connection in ~1 minute instead of blocking on it for many minutes.
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
        # psycopg returns rows as plain tuples by default (no column names, e.g.
        # `(1, 'alice')`). PostgresSaver's internals read columns by name (row["checkpoint"],
        # row["metadata"], ...), so we tell psycopg to hand back dict-shaped rows instead
        # (e.g. `{"id": 1, "name": "alice"}`) -- this is a documented requirement of
        # PostgresSaver, not optional styling.
        "row_factory": dict_row,
    },
)
