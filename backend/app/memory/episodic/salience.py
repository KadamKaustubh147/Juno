"""Salience scoring -- "is this message worth remembering?"

Ported from TrueMemory's `truememory/salience.py` (the L3 scorer) and
`truememory/ingest/encoding_salience.py` (variant D, the one their encoding
gate actually calls).

The scorer is a hybrid, split on message length:

- **<= 50 chars** -> `_speech_act_score`: a rule-based scorer that classifies
  the message by what it *does* (noise / question / commitment / correction),
  not by how long it is. Length-based scoring rates "I got the job" as noise
  purely because it's short, which is exactly backwards.
- **> 50 chars** -> `compute_message_salience`: a logistic regression over 13
  hand-built text features, with weights trained on LoCoMo (see
  l3_weights.json). Length dominates there (weight 8.54), which is fine once
  you're past the short-message regime.

TrueMemory implements five variants (A-E); only D is wired into their gate,
so only D is ported here. Their legacy hand-tuned additive scorer is also
dropped -- it's a fallback for when the weights file is missing, and we ship
the weights file.
"""

import json
import re
from math import exp, log
from pathlib import Path

# ---------------------------------------------------------------------------
# Word lists and patterns
# ---------------------------------------------------------------------------

# Filler messages that carry no information worth storing.
_NOISE_EXACT = frozenset({
    "ok", "okay", "k", "kk",
    "yes", "yeah", "yep", "yup", "ya", "yea",
    "no", "nah", "nope",
    "lol", "lmao", "lmfao", "haha", "hahaha", "heh",
    "omg", "omfg", "wtf",
    "nice", "cool", "dope", "sick", "lit", "fire",
    "thanks", "thx", "ty", "thank you",
    "got it", "gotcha",
    "sounds good", "sounds great",
    "bet", "word",
    "sure", "for sure",
    "same", "mood",
    "idk", "idc",
    "np", "no problem",
    "gn", "goodnight", "good night",
    "gm", "good morning",
    "brb", "ttyl",
})

# Same idea as _NOISE_EXACT but extended -- this is the list the short-message
# scorer uses, and it adds reactions to *someone else's* news ("that's great",
# "congrats"). Those look positive and emotional but say nothing about the
# speaker, so they're noise for memory purposes.
NOISE_EXACT_SHORT = frozenset({
    "ok", "okay", "k", "kk", "yes", "yeah", "yep", "yup", "ya", "yea",
    "no", "nah", "nope", "lol", "lmao", "lmfao", "haha", "hahaha", "heh",
    "omg", "omfg", "wtf", "nice", "cool", "dope", "sick", "lit", "fire",
    "thanks", "thx", "ty", "thank you", "got it", "gotcha",
    "sounds good", "sounds great", "bet", "word", "sure", "for sure",
    "same", "mood", "idk", "idc", "np", "no problem",
    "gn", "goodnight", "good night", "gm", "good morning", "brb", "ttyl",
    "damn", "dude", "bro", "ugh", "wow", "yikes", "ooh", "oof",
    "true", "facts", "right", "exactly", "totally", "absolutely",
    "lmao dead", "im dead", "crying", "screaming",
    "that's great", "thats great", "that's awesome", "thats awesome",
    "that's amazing", "thats amazing", "that's crazy", "thats crazy",
    "that's insane", "thats insane", "that's wild", "thats wild",
    "that's so cool", "thats so cool",
    "congratulations", "congrats", "happy for you", "so happy for you",
    "proud of you", "so proud of you", "good for you",
    "no way", "are you serious", "oh my god", "oh my gosh",
    "i can't believe it", "i cant believe it", "shut up",
    "that's wonderful", "thats wonderful", "that's fantastic",
    "love that", "love it", "so cool", "so sick",
    "good luck", "you got this", "go for it", "let's go", "lets go",
    "aww", "aw", "yay", "woohoo", "woo",
})

_HIGH_AROUSAL = frozenset({
    "amazing", "incredible", "devastating", "heartbreaking",
    "thrilled", "furious", "terrified", "ecstatic", "crushed",
    "panic", "emergency", "urgent", "critical", "breakthrough",
    "milestone", "promoted", "fired", "pregnant", "engaged",
    "diagnosed", "accident", "passed away", "died",
})

_LIFE_EVENTS = frozenset({
    "got married", "got engaged", "having a baby", "got promoted",
    "got fired", "broke up", "moved to", "graduated", "launched",
    "raised funding", "demo day", "ipo", "acquisition",
})

# Verbs that mark a state change ("I switched therapists").
_UPDATE_VERBS = frozenset({
    "switched", "changed", "moved", "quit", "started", "enrolled",
    "promoted", "graduated", "launched", "resigned", "transferred",
    "hired", "fired", "accepted", "declined", "submitted",
})

# Phrases where the speaker commits to / announces something about themselves.
_COMMITMENT_PATTERNS = frozenset({
    "said yes", "said no", "i'm in", "we're in", "i quit", "i did it",
    "i got it", "i got in", "i made it", "i passed", "i failed",
    "we're pregnant", "i'm pregnant", "she's pregnant",
    "i'm engaged", "we're engaged", "i'm married", "we're married",
    "i enrolled", "i applied", "i submitted", "i accepted",
    "i declined", "i resigned", "i'm leaving", "i'm moving",
    "it's booked", "it's done", "it's official", "it's over",
    "i had a baby", "had a baby", "having a baby",
    "seeing someone", "broke up", "breaking up",
    "got the job", "got the offer", "got accepted", "got rejected",
    "got promoted", "got fired", "got hired", "got laid off",
    "gave my notice", "two weeks notice", "gave notice",
    "passed away", "passed on",
})

_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?%?")
_MONEY_PATTERN = re.compile(r"\$[\d,]+(?:\.\d{2})?")
_DATE_PATTERN = re.compile(
    r"\b(?:january|february|march|april|may|june|july|august|"
    r"september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"\s+\d{1,2}",
    re.IGNORECASE,
)
_CAPS_WORDS_RE = re.compile(r"\b[A-Z]{3,}\b")
_BULLET_RE = re.compile(r"^[-*•]\s", re.MULTILINE)

# Emoji ranges, matched one character at a time (for the emoji-density feature).
_EMOJI_RE = re.compile(
    r"[\U0001F600-\U0001F64F"
    r"\U0001F300-\U0001F5FF"
    r"\U0001F680-\U0001F6FF"
    r"\U0001F1E0-\U0001F1FF"
    r"\U00002702-\U000027B0"
    r"\U000024C2-\U0001F251"
    r"\U0001f900-\U0001f9FF"
    r"\U0001fa00-\U0001fa6f"
    r"\U0001fa70-\U0001faff]",
    re.UNICODE,
)

# Same "the speaker did something" idea as _COMMITMENT_PATTERNS, but as one
# regex so it catches conjugations the fixed phrase list would miss.
_COMMITMENT_RE = re.compile(
    r"\b(?:"
    r"i\s+(?:got|did|made|found|built|started|quit|left|joined|enrolled|"
    r"accepted|submitted|finished|completed|signed|bought|sold|moved|"
    r"said|told|asked|proposed|created|launched|shipped|published|"
    r"passed|graduated|earned|won|lost|broke|fixed)"
    r"|i'm\s+(?:pregnant|engaged|leaving|moving|starting|quitting|"
    r"going\s+to|seeing\s+someone|having\s+a)"
    r"|we're\s+(?:pregnant|engaged|moving|having|getting|doing)"
    r"|i\s+have\s+(?:a\s+baby|cancer|diabetes|a\s+new)"
    r"|she\s+(?:promoted|said\s+yes|agreed|accepted)"
    r"|he\s+(?:proposed|said\s+yes|agreed|accepted)"
    r"|it's\s+(?:booked|official|confirmed|done|over|happening)"
    r"|i\s+gave\s+(?:my\s+(?:two\s+weeks|notice))"
    r"|(?:all|both)\s+(?:three|four|five)?\s*(?:apps?|applications?)\s+submitted"
    r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# The trained logistic regression (long messages)
# ---------------------------------------------------------------------------

_WEIGHTS_PATH = Path(__file__).parent / "l3_weights.json"

with open(_WEIGHTS_PATH, encoding="utf-8") as f:
    _data = json.load(f)
    L3_WEIGHTS = tuple(_data["weights"])
    L3_BIAS = float(_data["bias"])

assert len(L3_WEIGHTS) == 13, f"Expected 13 weights, got {len(L3_WEIGHTS)}"


def _extract_features(content: str) -> tuple[float, ...]:
    """The 13 features the trained model expects, in weight-file order.

    Every feature is squashed into roughly [0, 1] (log-scaled or capped) so no
    single one can dominate just by being on a bigger numeric scale.
    """
    text = content.strip()
    text_lower = text.lower().strip("!?.… ")

    f_noise = 1.0 if text_lower in _NOISE_EXACT else 0.0

    if text:
        emoji_chars = sum(1 for _ in _EMOJI_RE.finditer(text))
        f_emoji = min(1.0, emoji_chars / max(1, len(text)))
    else:
        f_emoji = 0.0

    f_length = log(1 + len(text)) / 7.0
    f_num = log(1 + len(_NUMBER_PATTERN.findall(text))) / 3.0
    f_money = min(1.0, len(_MONEY_PATTERN.findall(text)) / 2.0)
    f_date = min(1.0, len(_DATE_PATTERN.findall(text)) / 2.0)

    # f_mod flags high-signal sources (OCR, bank statements, calendar entries).
    # Everything we score is chat, so it's always 0 -- and its trained weight
    # is 0.0 anyway. Kept so the vector still lines up with the weight file.
    f_mod = 0.0

    f_nl = 1.0 if ("\n" in text and len(text) > 50) else 0.0
    f_bul = 1.0 if _BULLET_RE.search(text) else 0.0
    f_excl = min(1.0, text.count("!") / 3.0)
    f_caps = min(1.0, len(_CAPS_WORDS_RE.findall(text)) / 5.0)
    f_arou = min(1.0, sum(1 for w in _HIGH_AROUSAL if w in text_lower) / 3.0)
    f_life = min(1.0, sum(1 for e in _LIFE_EVENTS if e in text_lower) / 2.0)

    return (
        f_noise, f_emoji, f_length, f_num, f_money, f_date,
        f_mod, f_nl, f_bul, f_excl, f_caps, f_arou, f_life,
    )


def compute_message_salience(content: str) -> float:
    """Score a message 0-1 with the trained model. Used for long messages."""
    if not content or not content.strip():
        return 0.0

    features = _extract_features(content)
    logit = sum(w * f for w, f in zip(L3_WEIGHTS, features)) + L3_BIAS

    # Sigmoid: turns the unbounded logit into a 0-1 probability.
    return 1.0 / (1.0 + exp(-logit))


# ---------------------------------------------------------------------------
# The speech-act scorer (short messages)
# ---------------------------------------------------------------------------

def _speech_act_score(content: str) -> float:
    """Score a short message by what it *does*, not how long it is.

    Order matters: the checks run most-specific first, and the first one that
    matches wins.
    """
    lower = content.lower().strip()

    if lower in NOISE_EXACT_SHORT:
        return 0.02

    # A question asks for information rather than supplying it.
    if content.strip().endswith("?") or lower.startswith((
        "what ", "how ", "why ", "where ", "when ", "who ", "which ",
        "do you", "are you", "is it", "can you", "could you",
    )):
        return 0.2

    # "I got the job" -- the speaker announcing something about themselves.
    if _COMMITMENT_RE.search(lower):
        return 0.8
    if any(p in lower for p in _COMMITMENT_PATTERNS):
        return 0.7

    # A correction or state change.
    if (
        re.search(r"\b(?:no longer|not anymore|instead|correction)\b", lower)
        or any(v in lower for v in _UPDATE_VERBS)
        or ("actually" in lower and re.search(r"\bnot\b", lower))
    ):
        return 0.6

    if re.match(r"^(?:hey|hi|hello|yo|sup|what's up|howdy)", lower):
        return 0.05
    if re.match(r"^(?:haha|lol|lmao|omg|wow|damn|ugh|yikes)", lower):
        return 0.08

    # Nothing matched: fall back to "does it have enough words to say anything".
    words = re.findall(r"[a-zA-Z]+", content)
    return 0.5 if len(words) >= 5 else 0.25


# ---------------------------------------------------------------------------
# The hybrid the gate actually calls
# ---------------------------------------------------------------------------

def encoding_salience(content: str) -> float:
    """Score how worth-remembering a message is, 0-1."""
    if not content or not content.strip():
        return 0.0

    if len(content.strip()) <= 50:
        return _speech_act_score(content)

    return compute_message_salience(content)
