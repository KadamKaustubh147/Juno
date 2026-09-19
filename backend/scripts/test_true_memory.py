"""Run a mock student's messages through the full True Memory pipeline for real.

Drives the actual compiled graph from app/orchestration/graph.py rather than reimplementing its
retrieve_memories/chatbot/ingest_memory logic here -- so retrieval, the real
LLM call, and the encoding gate all run exactly as they would in
production, on both message roles. The assistant's replies are genuine LLM
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
- AICREDITS_API_KEY set -- this makes one real LLM API call per message

Run (from the "backend" directory):
    uv run python -m scripts.test_true_memory

Output shape:
The whole thing prints as Markdown (headers, tables, blockquotes) so stdout can
be piped straight into a .md file and read as a document, not a log -- see
scripts/test_true_memory.md for a captured run. Sessions and turns are kept
visually distinct (User vs Juno), and the final Retrieval section renders each
query's fused hits as a ranked table, since that's the part worth showing
someone who wants to see True Memory actually working end to end.
"""

from app.orchestration.graph import graph
from app.memory.retriever import retrieve
from app.memory.semantic.vector_store import get_pool

# Throwaway ids, distinct from anything real, so this is safe to re-run.
TEST_USER_ID = "test-student-mock-1"
TEST_THREAD_ID = "test-student-mock-thread-1"

# Three fake sessions with a burnt-out college student, grouped so the printed
# output can visually separate them. Notes mark what each USER message is meant
# to demonstrate on the gate -- there's no equivalent list for assistant
# messages, since we don't write those; the LLM does.
MOCK_SESSIONS = [
    ("Session 1 -- establishing facts", [
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
    ]),
    ("Session 2 -- a restatement, a marker-bypassed correction, more new facts", [
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
    ]),
    ("Session 3 -- a contradiction with no marker words (tests prediction error alone)", [
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
    ]),
]

# Queries to run against whatever got stored, to sanity-check retrieval end to end.
TEST_QUERIES = [
    "What is the student studying?",
    "How is the part-time job going?",
    "Tell me about the student's sleep problems.",
    "What's going on with the student's friendships?",
]


def _md_escape(text: str) -> str:
    """Escape the one character that would break a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ")


def _blockquote(text: str) -> str:
    """Render arbitrary text as a Markdown blockquote, one '> ' per line.

    The LLM's replies are themselves Markdown (headers, tables, lists) -- printed
    raw they'd compete with this script's own ## / ### section headers for the
    document's heading hierarchy. Quoting demotes them to "quoted content" so a
    reader (and any Markdown outline/TOC) can't mistake Juno's "## Next steps" for
    an actual section of this trace.
    """
    lines = text.splitlines() or [""]
    return "\n".join(f"> {line}" if line else ">" for line in lines)


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
    """Show what actually ended up in `memories` for this user, both roles, as a table."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT role, content, score FROM memories WHERE user_id = %s ORDER BY created_at",
            (TEST_USER_ID,),
        ).fetchall()

    if not rows:
        print("_(nothing stored)_\n")
        return

    print("| Role | Gate score | Memory content |")
    print("|------|-----------|-----------------|")
    for row in rows:
        print(f"| {row['role']} | {row['score']:.2f} | {_md_escape(row['content'])} |")
    print()


def print_retrieval_hits(query: str) -> None:
    """Run one retrieval query and print its fused hits as a ranked Markdown table.

    role="user" matches what retrieve_memories actually asks for in production
    (app/orchestration/nodes/memory_hook.py) -- prompt context should be grounded in what the patient
    said, not the bot's own stored replies.
    """
    print(f"### Query: \"{query}\"\n")
    hits = retrieve(TEST_USER_ID, query, limit=5, role="user")
    if not hits:
        print("_(no memories retrieved)_\n")
        return

    print("| Rank | RRF score | Retrieved memory |")
    print("|------|-----------|-------------------|")
    for rank, hit in enumerate(hits, start=1):
        print(f"| {rank} | {hit['rrf_score']:.4f} | {_md_escape(hit['content'])} |")
    print()


if __name__ == "__main__":
    print("# True Memory -- Full Pipeline Trace\n")
    print(
        "Drives the real LangGraph pipeline end to end for one mock student: every "
        "turn below runs through the actual `retrieve_memories -> chatbot -> "
        "ingest_memory` graph from `app/orchestration/graph.py`, not a simulation of it. The "
        "assistant's replies are genuine LLM output, so exact wording (and therefore "
        "what the encoding gate does with it) varies run to run.\n"
    )
    print(f"Resetting test data for `user_id={TEST_USER_ID!r}`...\n")
    reset_test_data()

    print("## Conversation\n")
    print(
        "Each turn shows the user's message (with a note on what it's meant to "
        "demonstrate on the encoding gate), followed by Juno's real reply.\n"
    )
    for session_title, turns in MOCK_SESSIONS:
        print(f"### {session_title}\n")
        for text, note in turns:
            reply = send_turn(text)
            print("> 🙋 **User**")
            print(f"> {text}")
            print(">")
            print(f"> _{note}_\n")
            print("> 🧠 **Juno**")
            print(_blockquote(reply))
            print()
        print("---\n")

    print("## What the gate actually stored\n")
    print(
        "Both roles run through the same encoding gate -- something Juno itself "
        "noticed out loud is as worth remembering as something the student said.\n"
    )
    print_stored_memories()

    print("## Retrieval\n")
    print(
        "Each query below is fused from two independent rankings -- full-text "
        "lexical search (L1) and pgvector cosine similarity (L2) -- via Reciprocal Rank "
        "Fusion (`RRF_K=60`, see `app/memory/retriever.py`). The RRF score is "
        "`sum(1 / (60 + rank))` across whichever list(s) a memory appeared in, so a "
        "memory both searches agree on outranks one that only tops a single list. "
        "This is the same `retrieve()` call `retrieve_memories` makes on every real "
        "chat turn -- these queries just make the result visible.\n"
    )
    for query in TEST_QUERIES:
        print_retrieval_hits(query)

    # ponytail: interactive retrieval check, ctrl-c/empty line to quit
    print("## Try your own queries\n")
    print("_(interactive -- only meaningful when run in a terminal, not piped to a file; empty line to quit)_\n")
    while True:
        try:
            query = input("\nquery> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not query:
            break
        print_retrieval_hits(query)
