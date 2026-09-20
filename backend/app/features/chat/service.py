"""One chat turn: archive the user's message, run the graph, stream the reply as Server-Sent Events.

Events (`event: <name>` + `data: <json>`), in order:

    start    {"user_message_id"}                                  the message was saved; the reply is coming
    section  {"from", "to"}                                       the session moved to a new script section
    token    {"text"}                                             a chunk of the reply (zero or more)
    done     {"message_id", "current_section", "session_done"}    the reply is complete and saved
    error    {"detail"}                                           the turn failed after streaming began

`message_id` is null when there was no reply (the session had already ended). Failures that
happen before streaming starts (bad token, unknown session, empty message) are ordinary HTTP errors.
"""

import json
import logging
import uuid
from collections.abc import Iterator

from app.db.session import session_scope
from app.features.chat.schemas import ChatRequest
from app.features.sessions import service as sessions_service
from app.features.sessions.models import MessageRole
from app.orchestration.graph import graph

logger = logging.getLogger(__name__)


def start_chat(user_id: uuid.UUID, request: ChatRequest) -> uuid.UUID:
    """Check the session belongs to this user and archive their message; returns that message's id.

    Runs before the response starts streaming, so an unknown session comes back as a proper
    404 instead of a broken stream.
    """
    with session_scope() as db:
        sessions_service.get_owned(db, request.thread_id, user_id)
        message = sessions_service.archive(db, request.thread_id, MessageRole.USER, request.message)
        return message.id


def stream_reply(user_id: uuid.UUID, request: ChatRequest, user_message_id: uuid.UUID) -> Iterator[str]:
    config = {
        "configurable": {"thread_id": str(request.thread_id), "user_id": str(user_id)}
    }
    reply: list[str] = []
    settled: dict | None = None

    try:
        yield _sse("start", {"user_message_id": str(user_message_id)})

        # Two stream modes, so each item is a (mode, data) pair. "messages" carries the tokens as the
        # LLM produces them, from *any* node that calls it -- including the assessor, the dispatcher
        # and `summarize` -- so we keep only chunks from the "chatbot" node. "updates" is one dict per
        # finished node; it's how we learn a section change the moment it's decided.
        for mode, data in graph.stream(
            {"messages": [{"role": "user", "content": request.message}]},
            config=config,
            stream_mode=["messages", "updates"],
        ):
            if mode == "messages":
                chunk, metadata = data
                if metadata.get("langgraph_node") == "chatbot" and isinstance(chunk.content, str) and chunk.content:
                    reply.append(chunk.content)
                    yield _sse("token", {"text": chunk.content})
            elif mode == "updates":
                for change in _section_changes(data):
                    yield _sse("section", change)

        settled = _settle(request, config, reply)
        yield _sse("done", settled)
    except Exception:
        logger.exception("chat turn failed for session %s", request.thread_id)
        yield _sse("error", {"detail": "something went wrong generating the reply"})
    finally:
        # Also runs on client disconnect (GeneratorExit) and after a mid-stream crash, so the
        # archive keeps whatever reply text actually made it out. Skipped when the normal path
        # already settled.
        if settled is None:
            try:
                _settle(request, config, reply)
            except Exception:
                logger.exception("could not save the partial reply for session %s", request.thread_id)


def _section_changes(update: dict) -> Iterator[dict]:
    """The section moves in one "updates" item ({node_name: what_it_returned}); a no-move dispatch (from == to) isn't one."""
    for node_result in update.values():
        if not isinstance(node_result, dict):
            continue
        for transition in node_result.get("transitions", []):
            if transition["from"] != transition["to"]:
                yield {"from": transition["from"], "to": transition["to"]}


def _settle(request: ChatRequest, config: dict, reply: list[str]) -> dict:
    """Save the reply and the session's progress in one transaction; returns the `done` payload.

    Progress is read back from the checkpoint rather than tracked while streaming, so it's
    right even for a turn that was cut short. One transaction, so a failure leaves nothing
    half-saved and calling this again is safe.
    """
    state = graph.get_state(config).values
    session_done = bool(state.get("session_done"))

    with session_scope() as db:
        # No current_section in the checkpoint means the graph died before its first node finished.
        current_section = sessions_service.record_progress(
            db, request.thread_id, state.get("current_section"), state.get("transitions", []), session_done
        )
        text = "".join(reply)
        message = (
            sessions_service.archive(
                db, request.thread_id, MessageRole.ASSISTANT, text, section=current_section
            )
            if text
            else None
        )

    return {
        "message_id": str(message.id) if message else None,
        "current_section": current_section,
        "session_done": session_done,
    }


def _sse(event: str, data: dict) -> str:
    # json.dumps escapes newlines, so `data` is always exactly one line.
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
