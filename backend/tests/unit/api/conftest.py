"""Fixtures for the HTTP API tests: an in-memory SQLite database and a fake graph.

`app.orchestration.graph` and `.checkpointer` connect to Postgres at import time, so they're
replaced in sys.modules *before* anything imports the routers. SQLite stands in for Postgres
for the tables the API touches (users, therapy_sessions, messages, section_transitions); the
column defaults SQLite lacks (gen_random_uuid(), a microsecond-resolution now()) are filled in
by a before_insert listener.
"""

import sys
import types
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


class FakeGraph:
    """Stands in for the compiled LangGraph graph: replays scripted stream items and checkpoint state."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.items: list = []  # (mode, data) pairs, or an Exception to raise at that point
        self.state: dict = {"current_section": "Section 1", "transitions": [], "session_done": False}
        self.inputs: list = []

    def stream(self, graph_input, config, stream_mode):
        self.inputs.append((graph_input, config, stream_mode))
        for item in self.items:
            if isinstance(item, Exception):
                raise item
            yield item

    def get_state(self, config):
        return SimpleNamespace(values=dict(self.state))


class FakeCheckpointer:
    def __init__(self):
        self.deleted: list[str] = []

    def delete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)


_fake_graph = FakeGraph()
_fake_checkpointer = FakeCheckpointer()
sys.modules["app.orchestration.graph"] = types.SimpleNamespace(graph=_fake_graph)
sys.modules["app.orchestration.checkpointer"] = types.SimpleNamespace(checkpointer=_fake_checkpointer)

# Imported after the stubs are in place.
from fastapi.testclient import TestClient  # noqa: E402

import app.db.session  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.features.auth.models import RefreshToken  # noqa: E402,F401
from app.features.sessions.models import Message, SectionTransition, TherapySession  # noqa: E402
from app.features.users.models import User  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def fake_graph():
    _fake_graph.reset()
    return _fake_graph


@pytest.fixture
def checkpointer():
    _fake_checkpointer.deleted.clear()
    return _fake_checkpointer


@pytest.fixture
def db_engine(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    for model in (User, TherapySession, Message, SectionTransition):
        model.__table__.create(engine)

    clock = datetime(2026, 1, 1, tzinfo=UTC)

    def fill_defaults(mapper, connection, target):
        nonlocal clock
        if target.id is None:
            target.id = uuid.uuid4()
        if target.created_at is None:
            clock += timedelta(seconds=1)  # strictly increasing, so ordering is deterministic
            target.created_at = clock

    event.listen(Base, "before_insert", fill_defaults, propagate=True)
    monkeypatch.setattr(app_session_module(), "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    yield engine
    event.remove(Base, "before_insert", fill_defaults)
    engine.dispose()


def app_session_module():
    return sys.modules["app.db.session"]


@pytest.fixture
def client(db_engine, fake_graph, checkpointer):
    return TestClient(app)


@pytest.fixture
def register(client):
    """register(email) -> (auth headers, user json)."""

    def _register(email="alice@example.com", password="correct horse", full_name=None):
        response = client.post(
            "/auth/register", json={"email": email, "password": password, "full_name": full_name}
        )
        assert response.status_code == 201, response.text
        body = response.json()
        return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]

    return _register


@pytest.fixture
def alice(register):
    return register("alice@example.com")[0]


@pytest.fixture
def bob(register):
    return register("bob@example.com")[0]
