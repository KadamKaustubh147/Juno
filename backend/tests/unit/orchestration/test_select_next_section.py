import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.orchestration.nodes import select_next_section as module
from app.orchestration.nodes.select_next_section import select_next_section
from tests.unit.orchestration.fakes import FakeLLM

MESSAGES = [
    AIMessage(content="Would you like to explore your problem first, or learn a CBT exercise right away?"),
    HumanMessage(content="Let's do an exercise right away."),
]


def state(section):
    return {"messages": MESSAGES, "current_section": section}


def install(monkeypatch, *structured, replies=(), native=True):
    fake = FakeLLM(structured=structured, replies=replies, native=native)
    monkeypatch.setattr(module, "judge_llm", fake)
    return fake


def test_single_successor_skips_the_llm():
    # judge_llm is the ForbiddenLLM from conftest: a call would fail the test
    result = select_next_section(state("Section 1"))
    assert result == {
        "current_section": "Section 2",
        "thought": "single allowed transition",
        "transitions": [{"from": "Section 1", "to": "Section 2", "reasoning": "single allowed transition"}],
    }


@pytest.mark.parametrize("section, successor", [("Section 3", "Section 4"), ("Section 5", "Section 8"), ("Section 7", "Section 8")])
def test_every_single_successor_section_short_circuits(section, successor):
    assert select_next_section(state(section))["current_section"] == successor


def test_branching_section_asks_the_dispatcher(monkeypatch):
    fake = install(monkeypatch, {"reasoning": "wants an exercise", "next_section": "Section 4"})
    result = select_next_section(state("Section 2"))
    assert result["current_section"] == "Section 4"
    assert result["thought"] == "wants an exercise"
    assert result["transitions"] == [{"from": "Section 2", "to": "Section 4", "reasoning": "wants an exercise"}]
    prompt = fake.prompts[0]
    assert "- Section 3\n- Section 4" in prompt
    assert "Patient: Let's do an exercise right away." in prompt


def test_invalid_answer_is_retried_once_with_a_correction(monkeypatch):
    fake = install(
        monkeypatch,
        {"reasoning": "picked wrong", "next_section": "Section 8"},
        {"reasoning": "thought record", "next_section": " Section 5 "},
    )
    result = select_next_section(state("Section 4"))
    assert result["current_section"] == "Section 5"
    assert len(fake.prompts) == 2
    assert "'Section 8' is not one of the allowed options" in fake.prompts[1]


def test_two_invalid_answers_stay_in_the_current_section(monkeypatch):
    install(
        monkeypatch,
        {"reasoning": "a", "next_section": "Section 8"},
        {"reasoning": "b", "next_section": "Section 1"},
    )
    result = select_next_section(state("Section 4"))
    assert result["current_section"] == "Section 4"
    assert "staying in Section 4" in result["thought"]
    assert "'Section 1'" in result["thought"]
    assert result["transitions"] == [{"from": "Section 4", "to": "Section 4", "reasoning": result["thought"]}]


def test_unparseable_dispatch_stays_in_the_current_section(monkeypatch):
    install(monkeypatch, native=False, replies=["nope", "nope", "nope", "nope"])
    result = select_next_section(state("Section 2"))
    assert result["current_section"] == "Section 2"
    assert "staying in Section 2" in result["thought"]


def test_a_terminal_section_has_nothing_to_select():
    with pytest.raises(ValueError, match="Section 8"):
        select_next_section(state("Section 8"))
