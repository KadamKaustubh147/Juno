# Backend architecture

## Layout

```
AI service/
├── ai/
│   ├── chatbot.py          # the LangGraph conversation graph
│   └── memory/              # long-term memory subsystem ("True Memory")
│       ├── embeddings.py
│       ├── store.py
│       ├── retrieval.py
│       ├── encoding_gate.py
│       ├── salience.py
│       └── markers.py
├── api/
│   └── server.py            # FastAPI HTTP layer
└── initdb/                  # Postgres schema, auto-applied on fresh volume
```

## The core idea

Every chat turn flows through a LangGraph **state machine**, not a single LLM call:

```
START → retrieve_memories → chatbot → ingest_memory → (summarize?) → END
```

Each node reads/writes a shared `State` dict (`messages`, `summary`, `memory_context`).

## What each node does and why

### 1. `retrieve_memories` — pull relevant long-term facts

Before the LLM sees anything, this node takes the user's latest message and searches
**past** conversations (across sessions, not just this thread) for relevant facts about
this specific user. Formats them into `memory_context`, which gets injected as a system
message. This is what lets the bot "remember" things from weeks-old conversations, not
just the current thread.

### 2. `chatbot` — the actual LLM turn

- Builds a system message from `memory_context` (long-term facts) + `summary` (this
  conversation's own compressed history).
- Trims the message list to `MAX_TOKENS` (8000) using `trim_messages` — a safety net
  against oversized prompts, doesn't touch what's persisted.
- Calls the LLM (`ChatOpenAI`, model `openai/gpt-oss-120b`, served via
  `https://aicredits.in/v1`).
- Streamed back to the client via LangGraph's `stream_mode="messages"`.

### 3. `ingest_memory` — decide what's worth remembering

Runs the **encoding gate** (see below) over both the user's message and the bot's own
reply. Whatever clears the gate gets embedded and written to the `memories` table for
future `retrieve_memories` calls to find.

### 4. `summarize` (conditional) — keep the raw history bounded

Once the persisted history exceeds `SUMMARIZE_AFTER_TOKENS` (6000, deliberately below
`MAX_TOKENS`), this folds older messages into a running `summary` string via one more LLM
call, then deletes those raw messages from state (`RemoveMessage`). Keeps both the prompt
and the Postgres checkpoint from growing forever.

## Persistence — three separate stores, different jobs

| Store | What | Written by | Read by |
|---|---|---|---|
| **LangGraph checkpoint** (`PostgresSaver`) | Full graph state per `thread_id` | the graph itself, every turn | the graph, to resume a thread |
| **`messages` table** | Every message, verbatim, forever | `api/server.py`'s `archive()` | `GET /messages` (scrollback UI) — never read by the LLM |
| **`memories` table** | Only gate-approved excerpts + embeddings + scores | `ingest_memory` → `insert_memory()` | `retrieve_memories`, next time this user says something relevant |

## The "True Memory" encoding gate

Storing every message is the same as storing nothing (retrieval drowns in noise).
`encoding_gate.py` scores each candidate message on three signals and only stores it if
it clears a threshold:

- **novelty** — gzip-compression trick: append the message to existing memories and see
  how much the compressed size grows. Restating something already known compresses away
  to near-nothing (low novelty); genuinely new information doesn't compress against
  anything (high novelty). Chosen over embedding distance because embeddings rate "ok" as
  maximally distant from everything, which is backwards.
- **salience** — "is this worth remembering at all?" Short messages (≤50 chars) go
  through a rule-based classifier (question vs. commitment vs. noise); longer ones
  through a small logistic regression over hand-built text features (`l3_weights.json`).
- **prediction error** — embeds the message next to its nearest existing memory and
  checks whether it contradicts it (e.g. "I switched to sertraline" vs. stored "takes
  fluoxetine" — barely novel in wording, but a real contradiction).

Two overrides sit on top: a **salience floor** blocks storage no matter how
novel/surprising (stops noise), and a **contradiction bypass** (`markers.py`, regex for
phrases like "actually", "no longer", "switched from") always force-stores corrections
regardless of score, because getting a correction wrong is worse than over-storing.

## Retrieval — fusing two search strategies

`retrieval.py` combines:

- **L1 lexical** (`search_lexical`, pg_search/BM25) — exact word matches, catches
  specific terms (drug names, proper nouns) that embeddings blur.
- **L2 dense** (`search_dense`, pgvector cosine on 384-dim `all-MiniLM-L6-v2` embeddings
  via `fastembed`/ONNX) — catches paraphrases.

Merged via **Reciprocal Rank Fusion** (`RRF_K=60`): `score = Σ 1/(k + rank)` across both
ranked lists, so items both searches agree on rank higher than either alone.

## API layer (`api/server.py`)

Thin FastAPI wrapper — three endpoints:

- `POST /chat` — streams the reply as plain text (filtered to only the `chatbot` node's
  output, so the internal `summarize` LLM call never leaks), archives both sides to
  `messages`.
- `GET /messages` — cursor-paginated scrollback for the frontend.
- `GET /health`.

`CORSMiddleware` allows the Vite dev origins (`localhost:5173`/`127.0.0.1:5173`) — without
it the browser blocks every request at the preflight (`OPTIONS /chat` → 405), which curl
and Postman won't reveal since they don't send preflights.

## Key external dependencies and why

| Library | Purpose |
|---|---|
| `langgraph` / `langchain` | the conversation state machine + LLM abstraction |
| `langchain-openai` | talks to the OpenAI-compatible endpoint (aicredits.in) |
| `langgraph-checkpoint-postgres` | persists graph state to Postgres per thread |
| `fastembed` | runs the embedding model via ONNX (no torch, ~90MB vs ~800MB) |
| `psycopg[binary,pool]` | Postgres driver + connection pooling (two separate pools: one in `chatbot.py` for the checkpointer, one in `store.py` for the memory layer, kept independent so memory works standalone) |
| `paradedb/paradedb` (Docker image) | Postgres + `pgvector` (dense search) + `pg_search`/BM25 (lexical search) compiled in |
| `mlflow` | traces LLM calls — currently a hard startup dependency, not optional despite the code comment |
| `fastapi` | HTTP layer |
