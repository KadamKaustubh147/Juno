"""Run some example messages through the encoding gate and print the scores.

Testing/inspection script -- a quick way to see what the gate keeps and what
it throws away, without a database or a running chatbot.

Run (from the "AI service" directory):
    uv run python -m ai.memory.test_encoding_gate

The first run downloads the embedding model (~90MB), so it takes a minute.
"""

from ai.memory.encoding_gate import evaluate

# Pretend these are already stored for this patient.
EXISTING_MEMORIES = [
    "Patient takes fluoxetine 20mg daily for anxiety.",
    "Patient works as a software engineer and finds their job stressful.",
    "Patient's mother passed away in March.",
]

# (message, what we expect the gate to do and why)
CANDIDATES = [
    ("ok", "noise -- should be skipped by the salience floor"),
    ("lol yeah", "noise -- should be skipped"),
    ("How are you feeling about that?", "a question, asks rather than tells"),
    ("Patient takes fluoxetine 20mg daily for anxiety.",
     "exact restatement of a stored memory -- novelty should be near zero"),
    ("I switched from fluoxetine to sertraline last week.",
     "contradicts a stored memory -- correction bypass should force ENCODE"),
    ("I got promoted at work yesterday.", "new, salient, self-announcement"),
    ("I have been sleeping badly for about three weeks and I think it is making the anxiety worse.",
     "new, long, clinically relevant"),
]


if __name__ == "__main__":
    print("Stored memories:")
    for m in EXISTING_MEMORIES:
        print(f"  - {m}")
    print()

    for text, note in CANDIDATES:
        decision = evaluate(text, EXISTING_MEMORIES)
        print(f"{text}")
        print(f"  {decision.reason}")
        print(f"  ({note})")
        print()
