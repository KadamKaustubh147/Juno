import uuid

from app.db.session import session_scope
from app.features.sessions import service
from app.features.sessions.models import MessageRole


def _create(client, headers) -> str:
    response = client.post("/sessions", headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _archive(session_id: str, *contents: str, role=MessageRole.USER) -> list[str]:
    with session_scope() as db:
        return [str(service.archive(db, uuid.UUID(session_id), role, c).id) for c in contents]


def test_a_new_session_starts_at_section_1(client, alice):
    response = client.post("/sessions", headers=alice)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "active"
    assert body["current_section"] == "Section 1"
    assert body["script_id"] == "cbt_intro_v1"
    assert body["ended_at"] is None
    assert body["last_at"] == body["created_at"]  # nothing said yet


def test_every_session_route_needs_a_token(client):
    sid = str(uuid.uuid4())

    assert client.post("/sessions").status_code == 401
    assert client.get("/sessions").status_code == 401
    assert client.get(f"/sessions/{sid}").status_code == 401
    assert client.get(f"/sessions/{sid}/messages").status_code == 401
    assert client.delete(f"/sessions/{sid}").status_code == 401


def test_list_is_most_recently_active_first_and_only_yours(client, alice, bob):
    first, second, third = (_create(client, alice) for _ in range(3))
    _create(client, bob)
    _archive(first, "hello")  # written after `third` was created, so `first` is now the freshest

    listed = client.get("/sessions", headers=alice).json()["sessions"]

    assert [s["id"] for s in listed] == [first, third, second]  # empty ones fall back to created_at
    assert len(client.get("/sessions", headers=bob).json()["sessions"]) == 1
    assert len(client.get("/sessions?limit=2", headers=alice).json()["sessions"]) == 2
    assert client.get("/sessions?limit=0", headers=alice).status_code == 422


def test_read_one_session(client, alice):
    sid = _create(client, alice)
    [message_id] = _archive(sid, "hi")

    body = client.get(f"/sessions/{sid}", headers=alice).json()

    assert body["id"] == sid
    assert body["last_at"] > body["created_at"]
    assert message_id  # the message exists; last_at moved because of it


def test_someone_elses_session_looks_like_a_missing_one(client, alice, bob):
    sid = _create(client, alice)
    missing = str(uuid.uuid4())

    for path in ("", "/messages"):
        theirs = client.get(f"/sessions/{sid}{path}", headers=bob)
        absent = client.get(f"/sessions/{missing}{path}", headers=bob)
        assert theirs.status_code == absent.status_code == 404
        assert theirs.json() == absent.json()
    assert client.delete(f"/sessions/{sid}", headers=bob).status_code == 404
    assert client.get(f"/sessions/{sid}", headers=alice).status_code == 200  # untouched


def test_a_malformed_id_is_a_422(client, alice):
    assert client.get("/sessions/not-a-uuid", headers=alice).status_code == 422


def test_messages_are_paged_newest_first_and_returned_chronologically(client, alice):
    sid = _create(client, alice)
    ids = _archive(sid, *(f"m{i}" for i in range(5)))

    page1 = client.get(f"/sessions/{sid}/messages?limit=2", headers=alice).json()
    assert [m["content"] for m in page1["messages"]] == ["m3", "m4"]
    assert page1["has_more"] is True

    page2 = client.get(f"/sessions/{sid}/messages?limit=2&before={page1['messages'][0]['id']}", headers=alice).json()
    assert [m["content"] for m in page2["messages"]] == ["m1", "m2"]
    assert page2["has_more"] is True

    page3 = client.get(f"/sessions/{sid}/messages?limit=2&before={page2['messages'][0]['id']}", headers=alice).json()
    assert [m["content"] for m in page3["messages"]] == ["m0"]
    assert page3["has_more"] is False
    assert ids[0] == page3["messages"][0]["id"]


def test_has_more_is_false_when_the_last_page_is_exactly_full(client, alice):
    sid = _create(client, alice)
    _archive(sid, "a", "b")

    page = client.get(f"/sessions/{sid}/messages?limit=2", headers=alice).json()

    assert len(page["messages"]) == 2
    assert page["has_more"] is False


def test_message_shape_and_an_empty_session(client, alice):
    sid = _create(client, alice)
    assert client.get(f"/sessions/{sid}/messages", headers=alice).json() == {"messages": [], "has_more": False}

    _archive(sid, "hi", role=MessageRole.ASSISTANT)
    [message] = client.get(f"/sessions/{sid}/messages", headers=alice).json()["messages"]

    assert set(message) == {"id", "role", "content", "created_at"}
    assert message["role"] == "assistant"


def test_a_cursor_from_another_session_is_rejected(client, alice):
    mine, other = _create(client, alice), _create(client, alice)
    [foreign] = _archive(other, "elsewhere")

    assert client.get(f"/sessions/{mine}/messages?before={foreign}", headers=alice).status_code == 404
    assert client.get(f"/sessions/{mine}/messages?before={uuid.uuid4()}", headers=alice).status_code == 404


def test_delete_removes_the_session_its_messages_and_the_checkpoint(client, alice, checkpointer):
    sid = _create(client, alice)
    keep = _create(client, alice)

    response = client.delete(f"/sessions/{sid}", headers=alice)

    assert response.status_code == 204 and response.content == b""
    assert client.get(f"/sessions/{sid}", headers=alice).status_code == 404
    assert [s["id"] for s in client.get("/sessions", headers=alice).json()["sessions"]] == [keep]
    assert checkpointer.deleted == [sid]


def test_a_failed_delete_does_not_touch_the_checkpoint(client, alice, bob, checkpointer):
    sid = _create(client, alice)

    client.delete(f"/sessions/{sid}", headers=bob)

    assert checkpointer.deleted == []
