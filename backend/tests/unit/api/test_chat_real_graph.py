"""POST /chat against the *real* graph (on MemorySaver, fake LLMs).

The other chat tests replay scripted stream items through a fake graph; this one checks that the
shapes the service relies on -- the ("messages" | "updates", data) items, get_state().values, the
"chatbot" node name -- are what LangGraph really produces.
"""

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from app.db.session import session_scope
from app.features.chat import service as chat_service
from app.features.sessions.models import SectionTransition
from app.orchestration.graph_builder import build_graph
from app.orchestration.nodes import assess_completion, generate_response, memory_hook, select_next_section
from tests.unit.api.test_chat import events, new_session, send, stored_messages
from tests.unit.orchestration.fakes import FakeLLM


@pytest.fixture
def real_graph(monkeypatch):
    # user_id is in the config here (the service always sends it), so keep the memory layer off the database.
    monkeypatch.setattr(memory_hook, "retrieve", lambda *a, **k: [])
    monkeypatch.setattr(memory_hook, "search_dense", lambda *a, **k: [])
    monkeypatch.setattr(memory_hook, "evaluate", lambda *a, **k: type("D", (), {"should_encode": False})())

    monkeypatch.setattr(
        generate_response,
        "llm",
        GenericFakeChatModel(messages=iter([AIMessage(content="Hello, welcome."), AIMessage(content="Let us begin.")])),
    )
    assessor = FakeLLM(structured=[{"reasoning": "welcome done", "section_complete": True}])
    monkeypatch.setattr(assess_completion, "judge_llm", assessor)
    monkeypatch.setattr(select_next_section, "judge_llm", FakeLLM())

    graph = build_graph(MemorySaver())
    monkeypatch.setattr(chat_service, "graph", graph)
    return graph


def test_a_first_turn_streams_the_reply_from_the_chatbot_node(client, alice, real_graph):
    sid = new_session(client, alice)

    parsed = events(send(client, alice, sid, "hi"))

    names = [name for name, _ in parsed]
    assert names[0] == "start" and names[-1] == "done"
    assert set(names[1:-1]) == {"token"}
    assert "".join(d["text"] for n, d in parsed if n == "token") == "Hello, welcome."
    assert parsed[-1][1]["current_section"] == "Section 1"
    assert stored_messages(client, alice, sid) == [("user", "hi"), ("assistant", "Hello, welcome.")]


def test_completing_a_section_announces_the_move_and_syncs_the_session_row(client, alice, real_graph):
    sid = new_session(client, alice)
    send(client, alice, sid, "hi")  # turn 1: no assessment yet

    parsed = events(send(client, alice, sid, "no more questions"))  # turn 2: assessor says Section 1 is done

    assert ("section", {"from": "Section 1", "to": "Section 2"}) in parsed
    assert parsed[-1][1]["current_section"] == "Section 2"
    assert parsed[-1][1]["session_done"] is False
    session = client.get(f"/sessions/{sid}", headers=alice).json()
    assert session["current_section"] == "Section 2"
    with session_scope() as db:
        [row] = db.query(SectionTransition).all()
        assert (row.from_section, row.to_section, row.reasoning) == ("Section 1", "Section 2", "single allowed transition")
