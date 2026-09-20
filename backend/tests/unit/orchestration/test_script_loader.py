import re

import pytest

from app.orchestration import script_loader
from app.orchestration.script_loader import FIRST_SECTION, TRANSITIONS, load_script, section_text


def test_script_parses_despite_raw_newlines():
    script = load_script()
    assert list(script) == [f"Section {n}" for n in range(1, 9)]
    assert "Task 3a" in script["Section 3"]
    assert "\n- Can you further describe the main issue" in script["Section 3"]["Task 3a"]


def test_transitions_and_script_agree_on_sections():
    script = load_script()
    assert set(TRANSITIONS) == set(script)
    assert FIRST_SECTION in script
    for targets in TRANSITIONS.values():
        assert set(targets) <= set(script)


def test_transitions_match_the_prose_in_the_script():
    """script.json only states transitions as prose ("proceed with Section 5"); TRANSITIONS must say the same."""
    for section, tasks in load_script().items():
        prose = "\n".join(tasks.values())
        mentioned = {m.title() for m in re.findall(r"proceed with (section \d)", prose, re.IGNORECASE)}
        assert mentioned == set(TRANSITIONS[section]), section


def test_terminal_section_is_only_section_8():
    assert [s for s, targets in TRANSITIONS.items() if not targets] == ["Section 8"]


def test_section_text_lists_every_task_in_order():
    text = section_text("Section 1")
    assert text.startswith("Task 1a: Welcome the patient warmly")
    assert text.index("Task 1a:") < text.index("Task 1b:") < text.index("Task 1c:")
    assert text.endswith("\n")


def test_section_text_unknown_section():
    with pytest.raises(KeyError):
        section_text("Section 99")


def test_validation_rejects_a_target_missing_from_the_script(monkeypatch):
    monkeypatch.setitem(TRANSITIONS, "Section 1", ["Section 99"])
    with pytest.raises(ValueError, match="Section 99"):
        script_loader._validate(load_script())


def test_validation_rejects_a_transitions_key_missing_from_the_script(monkeypatch):
    monkeypatch.setitem(TRANSITIONS, "Section 99", [])
    with pytest.raises(ValueError, match="Section 99"):
        script_loader._validate(load_script())


def test_validation_rejects_a_script_section_with_no_transitions_entry(monkeypatch):
    monkeypatch.delitem(TRANSITIONS, "Section 8")
    with pytest.raises(ValueError, match="Section 8"):
        script_loader._validate(load_script())
