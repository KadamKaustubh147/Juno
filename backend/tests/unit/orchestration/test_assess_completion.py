from langchain_core.messages import AIMessage, HumanMessage

from app.orchestration.nodes import assess_completion as module
from app.orchestration.nodes.assess_completion import assess_completion
from tests.unit.orchestration.fakes import FakeLLM

MID_CONVERSATION = [
    HumanMessage(content="Hello"),
    AIMessage(content="Hi, I'm Juno, an AI therapist. What should I call you?"),
    HumanMessage(content="Call me Sam. No more questions."),
]


def install(monkeypatch, *structured):
    fake = FakeLLM(structured=structured)
    monkeypatch.setattr(module, "judge_llm", fake)
    return fake


def test_first_turn_skips_the_llm_and_returns_the_baseline():
    # judge_llm is the ForbiddenLLM from conftest: a call would fail the test
    result = assess_completion({"messages": [HumanMessage(content="Hello")]})
    assert result == {"current_section": "Section 1", "section_complete": False, "session_done": False, "thought": ""}


def test_keeps_the_section_from_state(monkeypatch):
    install(monkeypatch, {"reasoning": "not yet", "section_complete": False})
    result = assess_completion({"messages": MID_CONVERSATION, "current_section": "Section 4"})
    assert result["current_section"] == "Section 4"


def test_complete_section_with_a_successor(monkeypatch):
    install(monkeypatch, {"reasoning": "patient has no more questions", "section_complete": True})
    result = assess_completion({"messages": MID_CONVERSATION, "current_section": "Section 1"})
    assert result["section_complete"] is True
    assert result["session_done"] is False
    assert result["thought"] == "patient has no more questions"


def test_incomplete_section(monkeypatch):
    install(monkeypatch, {"reasoning": "name not asked yet", "section_complete": False})
    result = assess_completion({"messages": MID_CONVERSATION})
    assert (result["section_complete"], result["session_done"]) == (False, False)
    assert result["thought"] == "name not asked yet"


def test_completing_the_terminal_section_ends_the_session(monkeypatch):
    install(monkeypatch, {"reasoning": "patient said goodbye", "section_complete": True})
    result = assess_completion({"messages": MID_CONVERSATION, "current_section": "Section 8"})
    assert result["section_complete"] is True
    assert result["session_done"] is True


def test_an_unfinished_terminal_section_does_not_end_the_session(monkeypatch):
    install(monkeypatch, {"reasoning": "still has a question", "section_complete": False})
    result = assess_completion({"messages": MID_CONVERSATION, "current_section": "Section 8"})
    assert result["session_done"] is False


def test_session_done_is_sticky_and_costs_no_llm_call():
    state = {"messages": MID_CONVERSATION, "current_section": "Section 8", "session_done": True}
    result = assess_completion(state)
    assert result["session_done"] is True
    assert result["section_complete"] is False
    assert result["current_section"] == "Section 8"


def test_stale_flags_from_the_previous_turn_are_reset(monkeypatch):
    install(monkeypatch, {"reasoning": "not yet", "section_complete": False})
    state = {"messages": MID_CONVERSATION, "section_complete": True, "thought": "old"}
    result = assess_completion(state)
    assert result["section_complete"] is False
    assert result["thought"] == "not yet"


def test_unusable_verdict_is_treated_as_incomplete(monkeypatch):
    # native output errors, and the prompted-JSON fallback returns garbage twice
    monkeypatch.setattr(module, "judge_llm", FakeLLM(structured=[RuntimeError("400")], replies=["garbage", "garbage"]))
    result = assess_completion({"messages": MID_CONVERSATION, "current_section": "Section 8"})
    assert (result["section_complete"], result["session_done"]) == (False, False)
    assert "assessment failed" in result["thought"]


def test_a_long_section_keeps_its_opening_visible_to_the_assessor(monkeypatch):
    """Regression: with a 12-message window, Task 1a's welcome scrolled out and the assessor
    concluded it never happened, so a long Section 1 could never be judged complete."""
    welcome = "Hello! I'm Juno, an AI therapist here to support you."
    history = [HumanMessage(content="Hi"), AIMessage(content=welcome)]
    for n in range(20):
        history += [HumanMessage(content=f"patient {n}"), AIMessage(content=f"therapist {n}")]
    history.append(HumanMessage(content="Sam"))

    fake = install(monkeypatch, {"reasoning": "r", "section_complete": False})
    assess_completion({"messages": history, "current_section": "Section 1"})
    assert f"Therapist: {welcome}" in fake.prompts[0]
    assert "Patient: Hi\n" in fake.prompts[0]


def test_prompt_carries_section_summary_and_transcript(monkeypatch):
    fake = install(monkeypatch, {"reasoning": "r", "section_complete": False})
    assess_completion({"messages": MID_CONVERSATION, "summary": "Patient is a student.", "current_section": "Section 1"})
    prompt = fake.prompts[0]
    assert "Task 1a: Welcome the patient warmly" in prompt
    assert "Patient is a student." in prompt
    assert "Patient: Call me Sam. No more questions." in prompt
    assert "Therapist: Hi, I'm Juno" in prompt
