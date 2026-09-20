"""The whole graph, end to end, on MemorySaver with fake LLMs.

Imports graph_builder, never graph.py/checkpointer.py: those connect to Postgres at import time.
No user_id is passed in the config, so the real retrieve_memories/ingest_memory nodes run but
no-op -- the memory layer (and its database) is never touched.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver

from app.orchestration.graph_builder import build_graph
from app.orchestration.nodes import assess_completion, generate_response, select_next_section
from tests.unit.orchestration.fakes import FakeLLM

CONFIG = {"configurable": {"thread_id": "walk"}}


def verdict(complete: bool, why: str = "r") -> dict:
    return {"reasoning": why, "section_complete": complete}


@pytest.fixture
def session(monkeypatch):
    """(graph, assessor, dispatcher, chatbot) wired to fakes that answer the scripted walk."""
    assessor = FakeLLM(structured=[
        verdict(False, "name not given yet"),        # turn 2, Section 1
        verdict(True, "no more questions"),          # turn 3, Section 1 -> 2 (single successor)
        verdict(True, "problem shared"),             # turn 4, Section 2 -> dispatcher
        verdict(True, "exercise picked"),            # turn 5, Section 4 -> dispatcher
        verdict(True, "exercise done"),              # turn 6, Section 5 -> 8 (single successor)
        verdict(True, "patient said goodbye"),       # turn 7, Section 8 -> session done
    ])
    dispatcher = FakeLLM(structured=[
        {"reasoning": "wants an exercise", "next_section": "Section 4"},
        {"reasoning": "chose the thought record", "next_section": "Section 5"},
    ])
    chatbot = FakeLLM(replies=[f"therapist reply {n}" for n in range(1, 7)])

    monkeypatch.setattr(assess_completion, "judge_llm", assessor)
    monkeypatch.setattr(select_next_section, "judge_llm", dispatcher)
    monkeypatch.setattr(generate_response, "llm", chatbot)
    return build_graph(MemorySaver()), assessor, dispatcher, chatbot


def say(graph, text):
    graph.invoke({"messages": [HumanMessage(content=text)]}, CONFIG)
    return graph.get_state(CONFIG).values


def system_prompt(chatbot, call):
    sent = chatbot.prompts[call]
    assert isinstance(sent[0], SystemMessage)
    return sent[0].content


def test_the_response_node_keeps_its_name(session):
    graph, *_ = session
    assert "chatbot" in graph.get_graph().nodes  # the chat service filters the token stream on it


def test_walk_through_the_script_to_the_end(session):
    graph, assessor, dispatcher, chatbot = session

    # Turn 1: no therapist reply yet, so nothing to assess -- straight to the welcome.
    values = say(graph, "Hello")
    assert values["current_section"] == "Section 1"
    assert assessor.prompts == []
    assert "Task 1a: Welcome the patient warmly" in system_prompt(chatbot, 0)

    # Turn 2: assessed, not complete -- stays in Section 1.
    values = say(graph, "Call me Sam.")
    assert values["current_section"] == "Section 1"
    assert values["section_complete"] is False
    assert values["transitions"] == []

    # Turn 3: complete, one successor -> Section 2, no dispatcher call, and the reply opens it.
    values = say(graph, "No, no more questions.")
    assert values["current_section"] == "Section 2"
    assert dispatcher.prompts == []
    assert "Task 2a:" in system_prompt(chatbot, 2)
    assert generate_response.NEW_SECTION_NOTE in system_prompt(chatbot, 2)

    # Turn 4: Section 2 branches; the dispatcher picks Section 4.
    values = say(graph, "I'd like to learn a CBT exercise right away.")
    assert values["current_section"] == "Section 4"
    assert len(dispatcher.prompts) == 1

    # Turn 5: Section 4 branches three ways; the dispatcher picks Section 5.
    values = say(graph, "The thought record, please.")
    assert values["current_section"] == "Section 5"
    assert len(dispatcher.prompts) == 2

    # Turn 6: Section 5 -> Section 8 (single successor).
    values = say(graph, "That went well, thank you.")
    assert values["current_section"] == "Section 8"
    assert len(dispatcher.prompts) == 2
    assert "Task 8a:" in system_prompt(chatbot, 5)

    assert [(t["from"], t["to"]) for t in values["transitions"]] == [
        ("Section 1", "Section 2"),
        ("Section 2", "Section 4"),
        ("Section 4", "Section 5"),
        ("Section 5", "Section 8"),
    ]

    # Turn 7: the patient says goodbye -> session done. The graph ends with no therapist reply.
    replies_before = len(chatbot.prompts)
    values = say(graph, "Goodbye, take care!")
    assert values["session_done"] is True
    assert values["current_section"] == "Section 8"
    assert len(chatbot.prompts) == replies_before
    assert isinstance(values["messages"][-1], HumanMessage)

    # Turn 8: the session stays ended -- no LLM calls at all, still no reply.
    assessor_calls, chatbot_calls = len(assessor.prompts), len(chatbot.prompts)
    values = say(graph, "Oh, one more thing?")
    assert values["session_done"] is True
    assert (len(assessor.prompts), len(chatbot.prompts)) == (assessor_calls, chatbot_calls)
    assert isinstance(values["messages"][-1], HumanMessage)

    # Every scripted LLM answer was consumed exactly once.
    assert assessor.structured == [] and dispatcher.structured == [] and chatbot.replies == []


def test_only_the_chatbot_node_produces_therapist_messages(session):
    graph, *_ = session
    say(graph, "Hello")
    say(graph, "Call me Sam.")
    ai = [m for m in graph.get_state(CONFIG).values["messages"] if isinstance(m, AIMessage)]
    assert [m.content for m in ai] == ["therapist reply 1", "therapist reply 2"]
