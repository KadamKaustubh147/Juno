"""App-wide settings, read from the environment (.env in dev)."""

import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
AICREDITS_API_KEY = os.environ["AICREDITS_API_KEY"]


def _sqlalchemy_url(url: str) -> str:
    """Point SQLAlchemy at the psycopg3 driver.

    Managed providers (Aiven included) hand out `postgres://` or `postgresql://`
    URIs; SQLAlchemy 2 rejects the former outright and would default the latter to
    psycopg2, which isn't installed. The raw DATABASE_URL is still what libpq-style
    consumers (the LangGraph checkpointer's psycopg pool) get.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


SQLALCHEMY_DATABASE_URL = _sqlalchemy_url(DATABASE_URL)
