import json
import uuid
from types import SimpleNamespace

from app.db.session import session_scope
from app.features.chat.schemas import ChatRequest
from app.features.chat.service import stream_reply
from app.features.sessions.models import Message, SectionTransition


def token(text: str, node: str = "chatbot"):
    return ("messages", (SimpleNamespace(content=text), {"langgraph_node": node}))


def moved(src: str, dst: str, reasoning: str = "why"):
    return ("updates", {"select_next_section": {"current_section": dst, "transitions": [{"from": src, "to": dst, "reasoning": reasoning}]}})


def events(response) -> list[tuple[str, dict]]:
    """Parse an SSE body into [(event, data), ...]."""
    parsed = []
    for frame in response.text.split("\n\n"):
        if not frame:
            continue
        lines = frame.split("\n")
        assert lines[0].startswith("event: ") and lines[1].startswith("data: ") and len(lines) == 2, frame
        parsed.append((lines[0][len("event: "):], json.loads(lines[1][len("data: "):])))
    return parsed


def send(client, headers, session_id: str, message: str = "hello"):
    return client.post("/chat", headers=headers, json={"thread_id": session_id, "message": message})


def new_session(client, headers) -> str:
    return client.post("/sessions", headers=headers).json()["id"]


def stored_messages(client, headers, session_id: str) -> list[tuple[str, str]]:
    page = client.get(f"/sessions/{session_id}/messages", headers=headers).json()
    return [(m["role"], m["content"]) for m in page["messages"]]


def test_the_reply_streams_as_sse_events_in_order(client, alice, fake_graph):
    sid = new_session(client, alice)
    fake_graph.items = [token("Hel"), token("lo\nthere"), token("hidden", node="summarize")]

    response = send(client, alice, sid, "hi")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    parsed = events(response)
    assert [name for name, _ in parsed] == ["start", "token", "token", "done"]
    assert [d["text"] for n, d in parsed if n == "token"] == ["Hel", "lo\nthere"]  # newline survives as JSON
    start, done = parsed[0][1], parsed[-1][1]
    assert done["current_section"] == "Section 1" and done["session_done"] is False

    history = client.get(f"/sessions/{sid}/messages", headers=alice).json()["messages"]
    assert [(m["role"], m["content"]) for m in history] == [("user", "hi"), ("assistant", "Hel" "lo\nthere")]
    assert history[0]["id"] == start["user_message_id"]
    assert history[1]["id"] == done["message_id"]


def test_the_graph_is_run_for_this_thread_and_user(client, alice, register, fake_graph):
    headers, user = register("carol@example.com")
    sid = new_session(client, headers)

    send(client, headers, sid, "hi")

    [(graph_input, config, stream_mode)] = fake_graph.inputs
    assert graph_input == {"messages": [{"role": "user", "content": "hi"}]}
    assert config == {"configurable": {"thread_id": sid, "user_id": user["id"]}}
    assert stream_mode == ["messages", "updates"]


def test_a_section_change_is_announced_and_recorded(client, alice, fake_graph):
    sid = new_session(client, alice)
    transition = {"from": "Section 1", "to": "Section 2", "reasoning": "welcome done"}
    fake_graph.items = [moved("Section 1", "Section 2", "welcome done"), token("Now, ")]
    fake_graph.state = {"current_section": "Section 2", "transitions": [transition], "session_done": False}

    parsed = events(send(client, alice, sid))

    assert [name for name, _ in parsed] == ["start", "section", "token", "done"]
    assert parsed[1][1] == {"from": "Section 1", "to": "Section 2"}
    assert parsed[-1][1]["current_section"] == "Section 2"
    assert client.get(f"/sessions/{sid}", headers=alice).json()["current_section"] == "Section 2"
    with session_scope() as db:
        rows = db.query(SectionTransition).all()
        assert [(r.from_section, r.to_section, r.reasoning) for r in rows] == [("Section 1", "Section 2", "welcome done")]


def test_transitions_are_recorded_once_across_turns(client, alice, fake_graph):
    sid = new_session(client, alice)
    first = {"from": "Section 1", "to": "Section 2", "reasoning": "a"}
    second = {"from": "Section 2", "to": "Section 4", "reasoning": "b"}
    fake_graph.items = [token("x")]

    fake_graph.state = {"current_section": "Section 2", "transitions": [first], "session_done": False}
    send(client, alice, sid)
    fake_graph.state = {"current_section": "Section 4", "transitions": [first, second], "session_done": False}
    send(client, alice, sid)

    with session_scope() as db:
        rows = db.query(SectionTransition).order_by(SectionTransition.created_at).all()
        assert [r.to_section for r in rows] == ["Section 2", "Section 4"]


def test_a_dispatch_that_stays_put_is_not_announced(client, alice, fake_graph):
    sid = new_session(client, alice)
    fake_graph.items = [moved("Section 2", "Section 2", "could not choose"), token("x")]

    parsed = events(send(client, alice, sid))

    assert "section" not in [name for name, _ in parsed]


def test_reply_messages_are_tagged_with_the_section_they_were_written_in(client, alice, fake_graph):
    sid = new_session(client, alice)
    fake_graph.items = [token("Section two opener")]
    fake_graph.state = {"current_section": "Section 2", "transitions": [], "session_done": False}

    send(client, alice, sid, "ready")

    with session_scope() as db:
        by_role = {m.role.value: m.section_at_time for m in db.query(Message).all()}
    assert by_role == {"user": "Section 1", "assistant": "Section 2"}


def test_the_terminal_section_completing_ends_the_session(client, alice, fake_graph):
    sid = new_session(client, alice)
    fake_graph.items = [token("Take care.")]
    fake_graph.state = {"current_section": "Section 8", "transitions": [], "session_done": True}

    done = events(send(client, alice, sid))[-1][1]

    assert done["session_done"] is True
    body = client.get(f"/sessions/{sid}", headers=alice).json()
    assert body["status"] == "completed" and body["ended_at"] is not None


def test_a_finished_session_gets_no_reply_and_nothing_archived_for_it(client, alice, fake_graph):
    sid = new_session(client, alice)
    fake_graph.items = []  # the graph ends without calling the chatbot node
    fake_graph.state = {"current_section": "Section 8", "transitions": [], "session_done": True}

    parsed = events(send(client, alice, sid, "one more thing"))

    assert [name for name, _ in parsed] == ["start", "done"]
    assert parsed[-1][1]["message_id"] is None
    assert stored_messages(client, alice, sid) == [("user", "one more thing")]


def test_a_mid_stream_failure_sends_an_error_event_and_keeps_the_partial_reply(client, alice, fake_graph):
    sid = new_session(client, alice)
    fake_graph.items = [token("Half of a "), RuntimeError("provider blew up")]

    parsed = events(send(client, alice, sid))

    assert [name for name, _ in parsed] == ["start", "token", "error"]
    assert "provider blew up" not in json.dumps(parsed)  # internals aren't leaked to the client
    assert stored_messages(client, alice, sid) == [("user", "hello"), ("assistant", "Half of a ")]


def test_closing_the_stream_early_still_archives_what_was_sent(client, alice, fake_graph):
    sid = new_session(client, alice)
    fake_graph.items = [token("Only "), token("this"), token("never sent")]
    user = client.get("/users/me", headers=alice).json()
    request = ChatRequest(thread_id=uuid.UUID(sid), message="hi")

    stream = stream_reply(uuid.UUID(user["id"]), request, uuid.uuid4())
    assert next(stream).startswith("event: start")
    assert "Only " in next(stream)
    stream.close()  # what a client disconnect does

    assert stored_messages(client, alice, sid) == [("assistant", "Only ")]


def test_unknown_or_foreign_sessions_fail_before_streaming(client, alice, bob, fake_graph):
    sid = new_session(client, alice)

    foreign = send(client, bob, sid)
    missing = send(client, bob, str(uuid.uuid4()))

    assert foreign.status_code == missing.status_code == 404
    assert foreign.headers["content-type"].startswith("application/json")
    assert fake_graph.inputs == []
    assert stored_messages(client, alice, sid) == []  # bob's message wasn't archived into alice's session


def test_chat_validates_its_input_and_needs_a_token(client, alice, fake_graph):
    sid = new_session(client, alice)

    assert send(client, alice, sid, "").status_code == 422
    assert client.post("/chat", headers=alice, json={"message": "hi"}).status_code == 422
    assert client.post("/chat", json={"thread_id": sid, "message": "hi"}).status_code == 401
    assert fake_graph.inputs == []
