import os

import pytest

# app.config reads these at import time. Real values (from .env) win; these only keep a checkout
# without a .env importable. Nothing here connects to a database or an LLM.
os.environ.setdefault("DATABASE_URL", "postgresql://user:password@127.0.0.1:1/unused")
os.environ.setdefault("OPENROUTER_API_KEY", "unused")

from app.orchestration.nodes import assess_completion, generate_response, select_next_section  # noqa: E402
from tests.unit.orchestration.fakes import ForbiddenLLM  # noqa: E402


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    """Every node module starts each test wired to an LLM that raises. Tests install their own fakes."""
    monkeypatch.setattr(assess_completion, "judge_llm", ForbiddenLLM())
    monkeypatch.setattr(select_next_section, "judge_llm", ForbiddenLLM())
    monkeypatch.setattr(generate_response, "llm", ForbiddenLLM())
