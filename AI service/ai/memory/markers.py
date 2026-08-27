"""Correction / update marker vocabulary.

Ported from TrueMemory's `truememory/ingest/markers.py`.

If a patient says "actually I'm not seeing that therapist anymore" or
"correction: it was my sister, not my mother", that message *corrects*
something we already stored. Corrections are the most important thing a
memory system can get right, so the encoding gate bypasses its usual
scoring for them -- they're always stored (see `encoding_gate.py`).

This module is just the "does this look like a correction?" test.
"""

import re

# Words/phrases that signal a correction or a fact update.
UPDATE_MARKERS = (
    "actually",
    "correction:",
    "correction -",
    "no longer",
    "not anymore",
    "changed to",
    "changed from",
    "switched to",
    "switched from",
    "moved to",
    "used to be",
    "used to",
    "instead of",
    "wrong about",
    "was wrong",
    "is wrong",
    "not true",
    "isn't true",
    "that's incorrect",
    "that is incorrect",
    "updated",
    "replaced",
    "formerly",
    "previously",
)


def _compile_markers():
    """Turn UPDATE_MARKERS into regexes, plus a few structural patterns.

    Word-boundary anchored (`\\b`) so "actually" matches but "actualization"
    doesn't. Markers ending in punctuation ("correction:") only get a
    boundary on the left, since `\\b` doesn't sit before a ":".
    """
    patterns = []

    for marker in UPDATE_MARKERS:
        if marker[-1].isalnum():
            patterns.append(re.compile(rf"\b{re.escape(marker)}\b", re.IGNORECASE))
        else:
            patterns.append(re.compile(rf"\b{re.escape(marker)}", re.IGNORECASE))

    # Change patterns that no plain word/phrase can express.
    patterns += [
        # "now is/uses/prefers/lives/works/takes/runs/has ..."
        re.compile(r"\bnow\s+(?:is|uses?|prefers?|lives?|works?|takes?|runs?|has)\b", re.IGNORECASE),
        # "was ... now ..."
        re.compile(r"\bwas\b.*\bnow\b", re.IGNORECASE),
        # a number changing: "5mg to 10mg", "6.5% -> 6.25%"
        re.compile(r"\d[\d.]*[%a-zA-Z]*\s*(?:to|->|-->|=>|→)\s*\d[\d.]*", re.IGNORECASE),
        # a date changing: "since 2024", "as of March"
        re.compile(r"\b(?:since|as\s+of|starting|effective)\s+\w+", re.IGNORECASE),
    ]

    return patterns


UPDATE_MARKER_PATTERNS = _compile_markers()


def has_update_markers(content: str) -> bool:
    """True if the text contains correction/update language."""
    return any(pattern.search(content) for pattern in UPDATE_MARKER_PATTERNS)
