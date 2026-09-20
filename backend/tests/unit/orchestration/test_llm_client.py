import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from app.orchestration.llm_client import (
    StructuredOutputError,
    format_transcript,
    invoke_structured,
    render_prompt,
)
from tests.unit.orchestration.fakes import FakeLLM

PLACEHOLDERS = {
    "assessment_prompt.txt": {"section_name", "section_text", "summary", "transcript"},
    "dispatch_prompt.txt": {"section_name", "section_text", "options", "transcript"},
    "response_prompt.txt": {"section_name", "section_text"},
    "system_prompt.txt": set(),
}


class Verdict(BaseModel):
    reasoning: str
    ok: bool


GOOD = '{"reasoning": "fine", "ok": true}'


@pytest.mark.parametrize("name, variables", PLACEHOLDERS.items())
def test_each_prompt_renders_with_exactly_its_documented_placeholders(name, variables):
    rendered = render_prompt(name, **{v: f"<{v}>" for v in variables})
    for v in variables:
        assert f"<{v}>" in rendered
    assert "$" not in rendered


def test_render_prompt_raises_on_a_missing_variable():
    with pytest.raises(KeyError, match="transcript"):
        render_prompt("assessment_prompt.txt", section_name="Section 1", section_text="t", summary="s")


def test_render_prompt_leaves_dollar_signs_in_values_alone():
    rendered = render_prompt("dispatch_prompt.txt", section_name="S", section_text="t", options="o", transcript="Patient: I owe $500 and $name")
    assert "I owe $500 and $name" in rendered


def test_render_prompt_keeps_json_braces():
    assert '{"reasoning"' in render_prompt("assessment_prompt.txt", section_name="S", section_text="t", summary="s", transcript="x")


def test_format_transcript_labels_roles_skips_others_and_keeps_the_last_n():
    messages = [SystemMessage(content="sys")] + [
        m for i in range(10) for m in (HumanMessage(content=f"h{i}"), AIMessage(content=f"a{i}"))
    ]
    lines = format_transcript(messages, limit=4).splitlines()
    assert lines == ["Patient: h8", "Therapist: a8", "Patient: h9", "Therapist: a9"]
    everything = format_transcript(messages).splitlines()  # no limit by default
    assert len(everything) == 20
    assert everything[0] == "Patient: h0"


def test_invoke_structured_uses_native_output_when_available():
    fake = FakeLLM(structured=[{"reasoning": "r", "ok": True}])
    assert invoke_structured(fake, Verdict, "p") == Verdict(reasoning="r", ok=True)
    assert fake.prompts == ["p"]


def test_invoke_structured_falls_back_to_prompted_json_when_native_raises():
    fake = FakeLLM(native=False, replies=[f"Sure!\n```json\n{GOOD}\n```"])
    assert invoke_structured(fake, Verdict, "p") == Verdict(reasoning="fine", ok=True)
    assert fake.prompts[0].startswith("p\n\nReply with ONLY a JSON object")


def test_invoke_structured_falls_back_when_native_call_errors():
    fake = FakeLLM(structured=[RuntimeError("400 response_format unsupported")], replies=[GOOD])
    assert invoke_structured(fake, Verdict, "p").ok is True


def test_invoke_structured_retries_once_and_says_what_was_wrong():
    fake = FakeLLM(native=False, replies=["not json at all", GOOD])
    assert invoke_structured(fake, Verdict, "p").ok is True
    assert len(fake.prompts) == 2
    assert "could not be used" in fake.prompts[1]


def test_invoke_structured_raises_after_the_retry_fails_too():
    fake = FakeLLM(native=False, replies=['{"reasoning": "missing ok"}', "{}"])
    with pytest.raises(StructuredOutputError):
        invoke_structured(fake, Verdict, "p")
    assert len(fake.prompts) == 2
