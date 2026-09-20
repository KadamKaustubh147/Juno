"""The therapy script (script.json) and the legal moves between its sections.

script.json only describes transitions in prose ("proceed with Section 5"), so the
rules are encoded here as data -- `select_next_section` validates the model's choice
against TRANSITIONS rather than trusting it.
"""

import json
from functools import lru_cache
from pathlib import Path

SCRIPT_PATH = Path(__file__).parent / "script.json"

FIRST_SECTION = "Section 1"

# section -> sections it may move to. Empty list = terminal (the session ends there).
TRANSITIONS: dict[str, list[str]] = {
    "Section 1": ["Section 2"],
    "Section 2": ["Section 3", "Section 4"],
    "Section 3": ["Section 4"],
    "Section 4": ["Section 5", "Section 6", "Section 7"],
    "Section 5": ["Section 8"],
    "Section 6": ["Section 8"],
    "Section 7": ["Section 8"],
    "Section 8": [],
}


@lru_cache(maxsize=1)
def load_script() -> dict[str, dict[str, str]]:
    """{"Section 1": {"Task 1a": "...", ...}, ...}, parsed once and validated against TRANSITIONS."""
    # strict=False: the file has raw newlines inside its strings, which strict JSON rejects.
    script = json.loads(SCRIPT_PATH.read_text(encoding="utf-8"), strict=False)
    _validate(script)
    return script


def _validate(script: dict) -> None:
    if FIRST_SECTION not in script:
        raise ValueError(f"FIRST_SECTION {FIRST_SECTION!r} is not in {SCRIPT_PATH.name}")

    for section, targets in TRANSITIONS.items():
        if section not in script:
            raise ValueError(f"TRANSITIONS has {section!r}, which is not in {SCRIPT_PATH.name}")
        for target in targets:
            if target not in script:
                raise ValueError(f"TRANSITIONS sends {section!r} to {target!r}, which is not in {SCRIPT_PATH.name}")

    # The reverse direction: a section with no TRANSITIONS entry would only fail later, as a
    # KeyError in the middle of a conversation.
    missing = [section for section in script if section not in TRANSITIONS]
    if missing:
        raise ValueError(f"{SCRIPT_PATH.name} has sections with no TRANSITIONS entry: {missing}")


def section_text(name: str) -> str:
    """All of a section's tasks as prompt text, one 'Task 1a: ...' block per task."""
    tasks = load_script()[name]
    return "".join(f"{task}: {text}\n" for task, text in tasks.items())
