from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.orchestration.nodes import generate_response as module
from app.orchestration.nodes.generate_response import NEW_SECTION_NOTE, generate_response
from tests.unit.orchestration.fakes import FakeLLM

MESSAGES = [HumanMessage(content="Hello"), AIMessage(content="Hi!"), HumanMessage(content="I'm Sam.")]


def system_prompt_for(monkeypatch, **state):
    fake = FakeLLM(replies=["reply"])
    monkeypatch.setattr(module, "llm", fake)
    result = generate_response({"messages": MESSAGES, **state})
    sent = fake.prompts[0]
    assert isinstance(sent[0], SystemMessage)
    assert result["messages"][0].content == "reply"
    return sent[0].content, sent[1:]


def test_system_message_holds_persona_and_the_current_section(monkeypatch):
    system, history = system_prompt_for(monkeypatch, current_section="Section 2")
    assert "You are Juno" in system
    assert "Task 2a: Ask the patient how they are doing today" in system
    assert "Task 1a" not in system
    assert history == MESSAGES


def test_defaults_to_the_first_section(monkeypatch):
    system, _ = system_prompt_for(monkeypatch)
    assert "Task 1a: Welcome the patient warmly" in system


def test_memory_context_and_summary_are_still_injected(monkeypatch):
    system, _ = system_prompt_for(monkeypatch, memory_context="- I work nights", summary="Talked about sleep.")
    assert "Relevant things you remember about this patient:\n- I work nights" in system
    assert "Summary of the conversation so far:\nTalked about sleep." in system
    assert system.index("I work nights") < system.index("Talked about sleep.")


def test_no_memory_or_summary_blocks_when_empty(monkeypatch):
    system, _ = system_prompt_for(monkeypatch, memory_context="", summary="")
    assert "Relevant things you remember" not in system
    assert "Summary of the conversation" not in system


def test_new_section_note_only_on_the_turn_of_a_real_move(monkeypatch):
    moved = {"section_complete": True, "current_section": "Section 2", "transitions": [{"from": "Section 1", "to": "Section 2", "reasoning": "r"}]}
    system, _ = system_prompt_for(monkeypatch, **moved)
    assert NEW_SECTION_NOTE in system

    # an older transition still in the history, but nothing completed this turn
    system, _ = system_prompt_for(monkeypatch, **{**moved, "section_complete": False})
    assert NEW_SECTION_NOTE not in system

    # the dispatcher failed to choose and stayed put (from == to): not a move
    stayed = {"section_complete": True, "current_section": "Section 4", "transitions": [{"from": "Section 4", "to": "Section 4", "reasoning": "r"}]}
    system, _ = system_prompt_for(monkeypatch, **stayed)
    assert NEW_SECTION_NOTE not in system
