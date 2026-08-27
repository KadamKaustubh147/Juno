"""The encoding gate -- decides which messages are worth storing as memories.

Ported from TrueMemory's `truememory/ingest/encoding_gate.py`.

Storing every message is the same as storing nothing: retrieval drowns. The
gate scores each candidate on three signals and keeps only what clears a
threshold.

    score = (0.25*novelty + 0.20*salience + 0.30*prediction_error) / 0.75
    store if score >= 0.30

The three signals answer different questions, which is why all three are
needed -- in TrueMemory's own evaluation they're only weakly correlated:

- **novelty**  -- "do we already know this?" Compares the message against
  what's stored using gzip: text that compresses well against existing
  memories is redundant. Compression beats embedding distance here, because
  embeddings rate "ok" as very distant from everything (it's semantically
  unlike any real memory) while rating a genuine update as very close to the
  fact it updates -- exactly backwards. TrueMemory measured AUC 0.788 for
  compression vs 0.484 for cosine.
- **salience** -- "is this worth remembering at all?" (see salience.py)
- **prediction error** -- "does this contradict what we know?" Embeds the
  message paired with its nearest memory and checks whether that pair reads
  differently from the memory paired with itself.

Two overrides sit on top of the score:

- **salience floor** -- below 0.10 salience, nothing gets stored no matter
  how novel or surprising. Stops off-topic noise from scoring high on
  novelty (novel *is* what noise looks like) and sneaking through.
- **contradiction bypass** -- corrections ("actually, it was my sister")
  are always stored. Getting a correction wrong means confidently
  remembering something false, which is worse than storing too much.

The neuroscience names in the paper (hippocampal novelty detection, amygdala
modulation, predictive coding) describe what each signal is *inspired by*.
None of this is a model of the brain.
"""

import gzip
from dataclasses import dataclass

import numpy as np

from ai.memory.embeddings import embed_many
from ai.memory.markers import has_update_markers
from ai.memory.salience import NOISE_EXACT_SHORT, encoding_salience

# How much each signal counts. They don't sum to 1, so the weighted sum is
# divided by their total to bring the final score back into [0, 1].
W_NOVELTY = 0.25
W_SALIENCE = 0.20
W_PREDICTION_ERROR = 0.30
_WEIGHT_TOTAL = W_NOVELTY + W_SALIENCE + W_PREDICTION_ERROR

THRESHOLD = 0.30
SALIENCE_FLOOR = 0.10

# Below this cosine similarity the nearest memory is about something else
# entirely, so "does this contradict it?" isn't a meaningful question.
_PE_MIN_SIMILARITY = 0.2


@dataclass
class EncodingDecision:
    """Why the gate decided what it decided. Everything is 0-1."""

    should_encode: bool
    score: float
    novelty: float           # 0 = we already know this, 1 = completely new
    salience: float          # 0 = noise, 1 = important personal information
    prediction_error: float  # 0 = expected, 1 = contradicts what we know
    reason: str


def _is_contradiction(text: str) -> bool:
    """True if the message looks like it's correcting something."""
    lower = text.lower().strip()

    # "it was not my mother but my sister"
    if " not " in lower and " but " in lower:
        return True

    return has_update_markers(text)


def compute_novelty(text: str, memories: list[str]) -> float:
    """How much new information this message adds, 0-1.

        (gzip(memories + text) - gzip(memories)) / gzip(text)

    gzip works by replacing repeated byte sequences with references to their
    earlier occurrence. So if `text` restates something already in `memories`,
    appending it barely grows the compressed output -- the numerator stays
    small and novelty is low. If it says something genuinely new, there's
    nothing to back-reference and it costs close to its own compressed size,
    giving a ratio near 1.
    """
    if not memories:
        return 1.0  # nothing stored yet, so everything is new

    memory_text = " ".join(m for m in memories if m)
    if not memory_text.strip():
        return 1.0

    text_bytes = text.encode("utf-8")
    memory_bytes = memory_text.encode("utf-8")

    compressed_text = len(gzip.compress(text_bytes, compresslevel=6))
    compressed_memory = len(gzip.compress(memory_bytes, compresslevel=6))
    compressed_both = len(gzip.compress(memory_bytes + b" " + text_bytes, compresslevel=6))

    # Very short messages ("ok") compress to almost nothing, which makes the
    # denominator tiny and the ratio meaningless. Call them not novel.
    if compressed_text < 10:
        return 0.05

    cost = (compressed_both - compressed_memory) / compressed_text

    return max(0.05, min(1.0, cost))


def compute_prediction_error(text: str, nearest_memory: str) -> float:
    """How much this message contradicts the memory closest to it, 0-1.

    Embed "text [SEP] memory" and "memory [SEP] memory" and compare them. The
    second is what the pair would look like if the message simply restated
    the memory; the further the real pair sits from that, the more the
    message is saying something *different* about the same subject.

    Note this is different from novelty: "I switched to sertraline" is barely
    novel if we already stored "patient takes fluoxetine" (similar words,
    compresses well) but has high prediction error, because it contradicts it.
    """
    if not text or not nearest_memory:
        return 0.0

    # Noise is never a contradiction, and short fragments carry too little
    # signal for the embedding comparison to mean anything.
    if text.lower().strip().rstrip("!?.… ") in NOISE_EXACT_SHORT:
        return 0.0
    if len(text.strip()) < 3:
        return 0.0

    embeddings = embed_many([
        text,
        nearest_memory,
        text + " [SEP] " + nearest_memory,
        nearest_memory + " [SEP] " + nearest_memory,
    ])

    def cosine(a, b) -> float | None:
        norm_a = float(np.linalg.norm(a))
        norm_b = float(np.linalg.norm(b))
        if norm_a < 1e-10 or norm_b < 1e-10:
            return None
        return float(np.dot(a, b)) / (norm_a * norm_b)

    # Unrelated topics can't contradict each other.
    similarity = cosine(embeddings[0], embeddings[1])
    if similarity is None or similarity < _PE_MIN_SIMILARITY:
        return 0.0

    pair_similarity = cosine(embeddings[2], embeddings[3])
    if pair_similarity is None:
        return 0.0

    return max(0.0, min(1.0, 1.0 - pair_similarity))


def _explain(decision: str, score: float, novelty: float, salience: float,
             prediction_error: float) -> str:
    """A one-line, human-readable summary of the scores."""
    notes = []

    if novelty > 0.7:
        notes.append("novel")
    elif novelty < 0.2:
        notes.append("familiar")

    if salience > 0.6:
        notes.append("high salience")
    elif salience < 0.3:
        notes.append("low salience")

    if prediction_error > 0.6:
        notes.append("contradicts existing memory")
    elif prediction_error > 0.3:
        notes.append("moderately surprising")

    return (
        f"{decision} score={score:.2f} "
        f"(n={novelty:.2f}, s={salience:.2f}, p={prediction_error:.2f})"
        + (f" -- {', '.join(notes)}" if notes else "")
    )


def evaluate(text: str, memories: list[str]) -> EncodingDecision:
    """Decide whether `text` is worth storing.

    `memories` is the existing memories most similar to `text`, most similar
    first -- i.e. what retrieval already returned. The gate doesn't search;
    the caller passes results in.
    """
    novelty = compute_novelty(text, memories)
    salience = encoding_salience(text)
    prediction_error = compute_prediction_error(text, memories[0] if memories else "")

    raw = (
        novelty * W_NOVELTY
        + salience * W_SALIENCE
        + prediction_error * W_PREDICTION_ERROR
    )
    score = max(0.0, min(1.0, raw / _WEIGHT_TOTAL))

    if _is_contradiction(text):
        should_encode = True
        reason = _explain("ENCODE(correction)", score, novelty, salience, prediction_error)
    elif salience < SALIENCE_FLOOR:
        should_encode = False
        reason = _explain("SKIP(below salience floor)", score, novelty, salience, prediction_error)
    else:
        should_encode = score >= THRESHOLD
        reason = _explain("ENCODE" if should_encode else "SKIP", score, novelty, salience, prediction_error)

    return EncodingDecision(
        should_encode=should_encode,
        score=round(score, 3),
        novelty=round(novelty, 3),
        salience=round(salience, 3),
        prediction_error=round(prediction_error, 3),
        reason=reason,
    )
