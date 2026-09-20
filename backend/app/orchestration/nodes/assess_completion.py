"""Node: assess whether the current scripted section is complete.

Runs at the start of every turn (after retrieve_memories). Its verdict decides the route
(see `route_after_assessment` in edges.py): end the session, move to the next section, or
carry on with the current one.
"""

import logging

from langchain_core.messages import AIMessage
from pydantic import BaseModel

from app.orchestration.llm_client import StructuredOutputError, format_transcript, invoke_structured, judge_llm, render_prompt
from app.orchestration.script_loader import FIRST_SECTION, TRANSITIONS, section_text
from app.orchestration.state import State

logger = logging.getLogger(__name__)


class Assessment(BaseModel):
    reasoning: str  # first, so the model reasons before it commits to the verdict
    section_complete: bool


def assess_completion(state: State) -> dict:
    section = state.get("current_section") or FIRST_SECTION

    # Baseline: stay put. Re-derived every turn, so a stale section_complete or thought from
    # the previous turn's checkpoint can never leak into this turn's routing.
    result = {"current_section": section, "section_complete": False, "session_done": False, "thought": ""}

    # session_done is the one flag that isn't reset: once the terminal section has finished,
    # the session is over, and any later message to the thread ends the graph without a reply
    # (and without an LLM call).
    if state.get("session_done"):
        return {**result, "session_done": True, "thought": "session already ended"}

    # No therapist reply yet = the conversation is only just starting. Nothing has been said
    # that could have completed a task, so there's nothing to assess.
    if not any(isinstance(m, AIMessage) for m in state["messages"]):
        return result

    prompt = render_prompt(
        "assessment_prompt.j2",
        section_name=section,
        section_text=section_text(section),
        summary=state.get("summary", ""),  # the template shows "(none yet)" when empty
        transcript=format_transcript(state["messages"]),
    )

    try:
        assessment = invoke_structured(judge_llm, Assessment, prompt)
    except StructuredOutputError as exc:
        # Unusable verdict: the safe reading is "not complete", so the conversation carries on
        # in the current section rather than a flaky classifier ending or skipping it.
        logger.warning("assessment failed in %s, treating the section as incomplete: %s", section, exc)
        return {**result, "thought": f"assessment failed, section treated as incomplete: {exc}"}

    return {
        **result,
        "section_complete": assessment.section_complete,
        # Finishing a section with no successor finishes the session.
        "session_done": assessment.section_complete and not TRANSITIONS[section],
        "thought": assessment.reasoning,
    }
