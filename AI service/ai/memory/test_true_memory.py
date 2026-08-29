"""Run a mock student's messages through the full True Memory pipeline for real.

Drives the actual compiled graph from chatbot.py rather than reimplementing its
retrieve_memories/chatbot/ingest_memory logic here -- so retrieval, the real
Groq LLM call, and the encoding gate all run exactly as they would in
production, on both message roles. The assistant's replies are genuine Groq
output, not scripted text: the "does the gate correctly handle assistant
messages too" question gets tested against what the bot actually says, not
against text we assumed it would say.

That also means the exact assistant text -- and therefore whether any given
assistant turn gets encoded -- isn't fully predictable ahead of time. After the
conversation runs, this prints everything actually stored in `memories` for
this user, for both roles, so you can see what the gate really did rather than
compare against a scripted expectation for the assistant side.

Requires:
- Postgres running (docker compose up -d) with the `memories` table already
  created (see Helpful notes/postgres/)
- GROQ_API_KEY set -- this makes one real Groq API call per message

Run (from the "AI service" directory):
    uv run python -m ai.memory.test_true_memory
"""

from ai.chatbot import graph
from ai.memory.retrieval import retrieve
from ai.memory.store import get_pool

# Throwaway ids, distinct from anything real, so this is safe to re-run.
TEST_USER_ID = "test-student-mock-1"
TEST_THREAD_ID = "test-student-mock-thread-1"

# Three fake sessions with a burnt-out college student. Notes mark what each
# USER message is meant to demonstrate on the gate -- there's no equivalent
# list for assistant messages, since we don't write those; Groq does.
MOCK_MESSAGES = [
    # --- Session 1: establishing facts ---
    ("Hey, I guess I'm here because I've been feeling really burnt out with school lately.",
     "opening message -- store is empty, novelty should be maxed out"),
    ("I'm a junior majoring in computer science and this semester has just been brutal.",
     "salient fact -- should encode"),
    ("I'm taking five classes plus a part-time job at the campus library.",
     "salient fact -- should encode"),
    ("lol yeah",
     "noise -- should be skipped by the salience floor"),
    ("My roommate moved out last month and it's been way harder to focus without someone else around.",
     "life event -- should encode"),
    ("I work at the library on weekends and it's honestly the only calm part of my week.",
     "salient, establishes the job fact later sessions will build on"),
    ("ok",
     "noise -- should be skipped"),

    # --- Session 2: a restatement, a marker-bypassed correction, more new facts ---
    ("I'm a junior majoring in computer science and this semester has just been brutal.",
     "exact restatement of an existing memory -- novelty should be near zero, expect SKIP"),
    ("Actually, I switched my major from computer science to data science last week.",
     "contains an update marker ('switched') -- correction bypass should force ENCODE"),
    ("thanks",
     "noise -- should be skipped"),
    ("I've been sleeping better since I started leaving my phone outside my room.",
     "new, moderately salient -- likely encode"),
    ("My best friend and I had a huge fight about a group project and we're barely speaking now.",
     "new, salient, emotionally charged -- should encode"),

    # --- Session 3: a contradiction with NO marker words -- tests prediction error
    #     on its own, not the keyword bypass ---
    ("I don't work at the library anymore, I'm tutoring freshman calc instead now.",
     "contradicts the earlier library-job memory, but phrased so no marker "
     "matches ('no longer' / 'not anymore' aren't literally present) -- this "
     "is the real test of whether prediction error catches it unaided"),
    ("yeah",
     "noise -- should be skipped"),
    ("I've been having panic moments again before exams, worse than last semester.",
     "new, salient, relevant to the burnout thread -- should encode"),
    ("sounds good",
     "noise -- should be skipped"),
    ("I've been having trouble falling asleep for the past three weeks, my mind just races "
     "about assignments, and I think it's tied to picking up more tutoring hours plus "
     "everything that happened with my best friend over that group project.",
     "new, long, ties several earlier threads together -- should encode"),
]

# Queries to run against whatever got stored, to sanity-check retrieval end to end.
TEST_QUERIES = [
    "What is the student studying?",
    "How is the part-time job going?",
    "Tell me about the student's sleep problems.",
    "What's going on with the student's friendships?",
]


def reset_test_data():
    """Delete any memories left over from a previous run of this script."""
    with get_pool().connection() as conn:
        conn.execute("DELETE FROM memories WHERE user_id = %s", (TEST_USER_ID,))


def send_turn(text: str) -> str:
    """Send one user message through the real graph; return the assistant's reply.

    retrieve_memories, chatbot, and ingest_memory all run as they would for a
    real request -- this isn't a simulation of the pipeline, it IS the pipeline.
    """
    config = {"configurable": {"thread_id": TEST_THREAD_ID, "user_id": TEST_USER_ID}}
    result = graph.invoke({"messages": [{"role": "user", "content": text}]}, config=config)
    return result["messages"][-1].content


def print_stored_memories() -> None:
    """Show what actually ended up in `memories` for this user, both roles."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT role, content, score FROM memories WHERE user_id = %s ORDER BY created_at",
            (TEST_USER_ID,),
        ).fetchall()

    if not rows:
        print("  (nothing stored)")
        return

    for row in rows:
        print(f"  [{row['role']:>9}] score={row['score']:.2f}  {row['content']}")


if __name__ == "__main__":
    print(f"Resetting test data for user_id={TEST_USER_ID!r}...\n")
    reset_test_data()

    print("=== Running the mock conversation through the real graph ===\n")
    for text, note in MOCK_MESSAGES:
        reply = send_turn(text)
        print(f"user: {text}")
        print(f"  ({note})")
        print(f"assistant: {reply}\n")

    print("=== What the gate actually stored (both roles) ===\n")
    print_stored_memories()
    print()

    print("=== Retrieval ===\n")
    for query in TEST_QUERIES:
        print(f"Query: {query}")
        hits = retrieve(TEST_USER_ID, query, limit=5)
        if not hits:
            print("  (no memories retrieved)")
        for hit in hits:
            print(f"  [{hit['rrf_score']:.4f}] {hit['content']}")
        print()
