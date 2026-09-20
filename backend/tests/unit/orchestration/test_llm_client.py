import pytest
from jinja2 import UndefinedError, meta
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from app.orchestration.llm_client import (
    _prompts,
    StructuredOutputError,
    format_transcript,
    invoke_structured,
    render_prompt,
)
from tests.unit.orchestration.fakes import FakeLLM

# Every variable each template uses. Optional blocks (entered_new_section, memory_context, summary)
# are still required by StrictUndefined: callers pass them empty.
PLACEHOLDERS = {
    "assessment_prompt.j2": {"section_name", "section_text", "summary", "transcript"},
    "dispatch_prompt.j2": {"section_name", "section_text", "options", "transcript"},
    "response_prompt.j2": {"section_name", "section_text", "entered_new_section", "memory_context", "summary"},
    "system_prompt.j2": set(),
}


class Verdict(BaseModel):
    reasoning: str
    ok: bool


GOOD = '{"reasoning": "fine", "ok": true}'


def test_there_is_a_template_for_every_documented_prompt_and_no_others():
    assert set(_prompts.list_templates()) == set(PLACEHOLDERS)


@pytest.mark.parametrize("name, variables", PLACEHOLDERS.items())
def test_each_template_uses_exactly_its_documented_variables(name, variables):
    source = _prompts.loader.get_source(_prompts, name)[0]
    assert meta.find_undeclared_variables(_prompts.parse(source)) == variables


def test_render_prompt_raises_on_a_missing_variable():
    with pytest.raises(UndefinedError, match="transcript"):
        render_prompt("assessment_prompt.j2", section_name="Section 1", section_text="t", summary="s")


HOSTILE = "I owe $500 and $name. {{ 7 * 7 }} {% if x %}boom{% endif %} {# c #} <b>Tom & 'Jerry'</b>"


def test_values_are_inserted_verbatim_never_parsed_or_escaped():
    rendered = render_prompt("dispatch_prompt.j2", section_name="S", section_text="t", options=["o"], transcript=f"Patient: {HOSTILE}")
    assert f"Patient: {HOSTILE}" in rendered  # no template syntax evaluated, no HTML escaping


def test_prompts_keep_their_literal_json_braces():
    rendered = render_prompt("assessment_prompt.j2", section_name="S", section_text="t", summary="s", transcript="x")
    assert '{"reasoning"' in rendered
    assert "{{" not in rendered and "{%" not in rendered


def test_assessment_shows_a_placeholder_for_an_empty_summary():
    empty = render_prompt("assessment_prompt.j2", section_name="S", section_text="t", summary="", transcript="x")
    assert "(none yet)" in empty
    filled = render_prompt("assessment_prompt.j2", section_name="S", section_text="t", summary="Talked about sleep.", transcript="x")
    assert "Talked about sleep." in filled and "(none yet)" not in filled


def test_dispatch_options_render_as_a_bulleted_list_with_no_stray_blank_lines():
    rendered = render_prompt("dispatch_prompt.j2", section_name="S", section_text="t\n", options=["Section 3", "Section 4"], transcript="x")
    assert "The allowed next sections are:\n- Section 3\n- Section 4\n\nThe conversation" in rendered


def test_response_prompt_blocks_appear_only_when_their_variable_is_set():
    base = dict(section_name="Section 2", section_text="Task 2a: hi\n", entered_new_section=False, memory_context="", summary="")
    plain = render_prompt("response_prompt.j2", **base)
    assert "Task 2a: hi" in plain
    assert "just entered" not in plain and "remember about this patient" not in plain and "Summary of" not in plain
    assert not plain.endswith("\n\n")  # blocks that don't apply leave no blank lines behind

    full = render_prompt("response_prompt.j2", **{**base, "entered_new_section": True, "memory_context": "- I work nights", "summary": "Talked."})
    assert "just entered" in full
    assert "Relevant things you remember about this patient:\n- I work nights\n" in full
    assert "Summary of the conversation so far:\nTalked.\n" in full
    assert full.index("just entered") < full.index("I work nights") < full.index("Talked.")


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
