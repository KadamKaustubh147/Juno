
"""The chat model, wired to OpenRouter (an OpenAI-compatible endpoint), plus the prompt and
structured-output helpers the script-driven nodes share."""

import json
import logging
from pathlib import Path
from typing import TypeVar

from langchain_core.messages import AIMessage, HumanMessage
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.config import OPENROUTER_API_KEY

logger = logging.getLogger(__name__)

# Per MLflow's own tracing quickstart: point at a running `mlflow server`, set an
# experiment to group traces under, then autolog. Start the server yourself first:
#   uvx mlflow server
# import mlflow
# import mlflow.langchain
# mlflow.set_tracking_uri("http://localhost:5000")
# mlflow.set_experiment("ai-therapist-chatbot")
# mlflow.langchain.autolog()

MODEL_NAME = "openai/gpt-oss-120b"

# Without these the OpenAI SDK's defaults apply: a 600s (10 minute) timeout and 2 retries, so a
# stalled request from the provider hangs the whole turn for 10+ minutes before anything fails.
# The timeout is per read (httpx), so a reply that keeps streaming tokens is not cut off; it only
# fires when nothing arrives for this long. One retry covers a transient blip without tripling the wait.
LLM_TIMEOUT_SECONDS = 60
LLM_MAX_RETRIES = 1

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# OpenRouter routes a model across several providers by default. Pin gpt-oss-120b to Crusoe's bf16
# endpoint: `only` restricts routing to that endpoint, and `allow_fallbacks: False` returns the
# upstream error instead of silently moving to another provider when Crusoe is unavailable.
# Sent as extra request-body fields (`extra_body`), since the OpenAI client has no such parameter.
OPENROUTER_PROVIDER = {"only": ["crusoe/bf16"], "allow_fallbacks": False}

llm = ChatOpenAI(
    model=MODEL_NAME,
    base_url=OPENROUTER_BASE_URL,
    api_key=OPENROUTER_API_KEY,
    extra_body={"provider": OPENROUTER_PROVIDER},
    timeout=LLM_TIMEOUT_SECONDS,
    max_retries=LLM_MAX_RETRIES,
)

# For the assessor/dispatcher, which classify rather than converse: same model and endpoint,
# but temperature 0 so the same transcript gets the same verdict. A second client instead of
# `llm.bind(temperature=0)` because a binding is lost when `with_structured_output` wraps the model.
judge_llm = ChatOpenAI(
    model=MODEL_NAME,
    base_url=OPENROUTER_BASE_URL,
    api_key=OPENROUTER_API_KEY,
    extra_body={"provider": OPENROUTER_PROVIDER},
    temperature=0,
    timeout=LLM_TIMEOUT_SECONDS,
    max_retries=LLM_MAX_RETRIES,
)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# One shared environment (it caches the compiled templates). The settings matter:
#   StrictUndefined   a variable the caller didn't pass raises UndefinedError instead of quietly
#                     rendering blank into a prompt. Optional blocks take an explicit empty value.
#   autoescape=False  these are plain-text prompts for an LLM, not HTML. Escaping would turn a
#                     patient's "&" or "'" into "&amp;" / "&#39;" before the model sees it.
#   trim_blocks / lstrip_blocks
#                     a {% if %} / {% for %} tag on its own line leaves no blank line behind.
#   keep_trailing_newline
#                     don't drop the file's final newline.
_prompts = Environment(
    loader=FileSystemLoader(PROMPTS_DIR),
    undefined=StrictUndefined,
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


def render_prompt(name: str, /, **ctx: object) -> str:
    """Render prompts/<name> (a Jinja2 template, extension included) with `ctx`.

    Only files in prompts/ are ever loaded, by a name the code chooses. Values in `ctx` (a patient's
    message, say) are inserted as-is and never parsed as template syntax, so a patient typing
    "{{ ... }}" or "{% ... %}" just gets those characters in the prompt.
    """
    return _prompts.get_template(name).render(**ctx)


def format_transcript(messages: list, limit: int | None = None) -> str:
    """Human/AI messages as "Patient: ..." / "Therapist: ..." lines -- all of them, or the last `limit`.

    Goes into the prompt as plain text, not as chat roles -- the assessor and dispatcher are
    judging the conversation, not taking part in it. The default is the whole persisted history
    on purpose: `summarize` already bounds it (about SUMMARIZE_AFTER_TOKENS, folding older turns
    into `summary`), and a window narrower than that hides early tasks -- a section's welcome
    scrolling out of view makes the assessor conclude it never happened, so it can never finish.
    """
    turns = [m for m in messages if isinstance(m, (HumanMessage, AIMessage))]
    if limit:
        turns = turns[-limit:]
    return "\n".join(f"{'Patient' if isinstance(m, HumanMessage) else 'Therapist'}: {m.text}" for m in turns)


T = TypeVar("T", bound=BaseModel)


class StructuredOutputError(ValueError):
    """The model never produced a reply that parses into the requested schema."""


def invoke_structured(model, schema: type[T], prompt: str) -> T:
    """Get an instance of `schema` out of `model`.

    Tries the endpoint's native structured output first. If that raises (not every model behind
    an OpenAI-compatible gateway supports it), falls back to asking for JSON in the prompt and
    parsing the reply, with one retry that tells the model what was wrong with its first try.
    Raises StructuredOutputError if neither works; transport errors (auth, timeouts) are not
    treated as parse failures, so they surface from the fallback call unchanged.
    """
    try:
        result = model.with_structured_output(schema).invoke(prompt)
        if isinstance(result, schema):
            return result
        logger.warning("native structured output returned %r, not %s; falling back", type(result), schema.__name__)
    except Exception as exc:
        logger.warning("native structured output failed (%s: %s); falling back to prompted JSON", type(exc).__name__, exc)

    json_prompt = (
        f"{prompt}\n\nReply with ONLY a JSON object matching this schema -- no prose, no code fences:\n"
        f"{json.dumps(schema.model_json_schema())}"
    )
    error = None
    for _ in range(2):
        attempt = json_prompt
        if error:
            attempt += f"\n\nYour previous reply could not be used ({error}). Reply again with ONLY the JSON object."
        reply = model.invoke(attempt).text
        try:
            return _parse_json_reply(schema, reply)
        except ValueError as exc:  # json.JSONDecodeError and pydantic.ValidationError are both ValueErrors
            error = str(exc).splitlines()[0]
    raise StructuredOutputError(f"no valid {schema.__name__} after retry: {error}")


def _parse_json_reply(schema: type[T], text: str) -> T:
    # First "{" to last "}" tolerates a code fence or a sentence of preamble around the object.
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in the reply")
    return schema.model_validate(json.loads(text[start : end + 1], strict=False))
