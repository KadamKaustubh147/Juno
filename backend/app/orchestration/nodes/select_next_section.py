"""Node: pick the next scripted-content section to run.

Only reached when assess_completion found the current section complete and the session isn't
over. The model's choice is checked against TRANSITIONS: it can pick among the script's legal
successors, never invent a jump.
"""

import logging

from pydantic import BaseModel

from app.orchestration.llm_client import StructuredOutputError, format_transcript, invoke_structured, judge_llm, render_prompt
from app.orchestration.script_loader import TRANSITIONS, section_text
from app.orchestration.state import State

logger = logging.getLogger(__name__)


class Dispatch(BaseModel):
    reasoning: str
    next_section: str


def select_next_section(state: State) -> dict:
    current = state["current_section"]
    allowed = TRANSITIONS[current]

    if not allowed:
        # route_after_assessment sends terminal sections to END, so this is a wiring bug.
        raise ValueError(f"{current!r} has no successor to select")

    if len(allowed) == 1:
        chosen, reasoning = allowed[0], "single allowed transition"
    else:
        chosen, reasoning = _dispatch(state, current, allowed)

    return {
        "current_section": chosen,
        "thought": reasoning,
        "transitions": [{"from": current, "to": chosen, "reasoning": reasoning}],
    }


def _dispatch(state: State, current: str, allowed: list[str]) -> tuple[str, str]:
    """Ask the model which of `allowed` to go to; (choice, reasoning). Stays in `current` if it can't answer validly."""
    prompt = render_prompt(
        "dispatch_prompt.txt",
        section_name=current,
        section_text=section_text(current),
        options="\n".join(f"- {name}" for name in allowed),
        transcript=format_transcript(state["messages"]),
    )

    problem = ""
    for _ in range(2):  # the first try, plus one retry
        attempt = prompt
        if problem:
            # Temperature 0 would just repeat the same wrong answer, so say what was wrong.
            attempt += f"\n\n{problem} Choose exactly one of the options listed above, spelled exactly as written."
        try:
            dispatch = invoke_structured(judge_llm, Dispatch, attempt)
        except StructuredOutputError as exc:
            problem = f"Your previous reply could not be used ({exc})."
            continue

        answer = dispatch.next_section.strip()
        if answer in allowed:
            return answer, dispatch.reasoning
        problem = f"Your previous answer {answer!r} is not one of the allowed options."

    logger.warning("dispatch from %s gave no valid choice (%s); staying put", current, problem)
    return current, f"could not choose a valid next section ({problem}); staying in {current}"
