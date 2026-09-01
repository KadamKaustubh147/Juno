# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

This is not a real Turborepo (the root `README.md` is unmodified boilerplate and there's no
`turbo.json`) — it's two independent projects living side by side:

- `AI service/` — Python backend: a LangGraph chatbot ("AI Therapist Chatbot") with a
  Postgres-backed long-term memory system, exposed over FastAPI.
- `frontend/Juno/` — React + TypeScript + Vite chat client.

They communicate over plain HTTP (`VITE_API_URL`, default `http://localhost:8000`); there's no
shared build tooling between them. Treat them as separate projects and `cd` into the relevant one.

## AI service

### Setup & running

```sh
cd "AI service"
docker compose up -d          # starts Postgres (ParadeDB image w/ pgvector + pg_search)
uv sync                       # installs deps (requires Python 3.12, see .python-version)
```

Requires a `.env` with:
```
GROQ_API_KEY=...
DATABASE_URL=postgresql://postgres:postgres@localhost:5442/postgres
```

Postgres must be up before the app starts — the connection pool opens at import time.
Checkpoint tables are created automatically (`checkpointer.setup()`); the `messages` and
`memories` tables come from `initdb/` (only runs on a fresh volume — apply by hand with
`docker compose exec postgres psql -U postgres -f /docker-entrypoint-initdb.d/<file>.sql`
against an existing volume).

Run the CLI chatbot:
```sh
uv run python -m ai.chatbot
```

Run the API server:
```sh
uv run uvicorn api.server:app --reload   # or ./runserver.sh
```

Tracing: `chatbot.py` points `mlflow` at `http://localhost:5000` and autologs. Despite the
comment in the code, `mlflow.set_experiment()` does NOT fail silently when no server is
running — it raises and crashes the app at import time. `uvx mlflow server` is effectively
required, not optional, until that's fixed.

CORS: `api/server.py` allows `http://localhost:5173` and `http://127.0.0.1:5173` (the Vite
dev server) via `CORSMiddleware`. Add any other frontend origin there too, or the browser
will block every request at the preflight (`OPTIONS`) — this fails silently from curl/Postman
since they don't send preflights, so it only shows up when testing from an actual browser.

### Tests

No pytest suite — the two `test_*.py` files under `ai/memory/` are runnable inspection
scripts, not assertions:

```sh
uv run python -m ai.memory.test_encoding_gate   # no DB needed; prints gate scores for sample messages
uv run python -m ai.memory.test_true_memory      # needs Postgres + GROQ_API_KEY; drives the real graph
```

### Architecture

**Chat graph** (`ai/chatbot.py`): a LangGraph `StateGraph` —
`START → retrieve_memories → chatbot → ingest_memory → (summarize?) → END`, checkpointed to
Postgres per `thread_id` via `PostgresSaver` so conversations survive restarts.

- `retrieve_memories` — pulls this user's relevant long-term memories into `memory_context`
  before the LLM call.
- `chatbot` — the actual LLM turn (Groq, model set by `MODEL_NAME`). Builds a system message
  from `memory_context` + running `summary`, trims the sent history to `MAX_TOKENS` (doesn't
  touch what's persisted).
- `ingest_memory` — runs the encoding gate over both the user's message and the assistant's
  reply, storing whatever it admits.
- `summarize` (conditional, fires past `SUMMARIZE_AFTER_TOKENS`) — folds older turns into a
  `summary` string and deletes them from persisted state via `RemoveMessage`, keeping both the
  prompt and the checkpoint bounded. `SUMMARIZE_AFTER_TOKENS` is set below `MAX_TOKENS` on
  purpose, so summarization fires before `trim_messages` would start silently dropping content.

Both `ingest_memory` and `summarize` run synchronously in-graph (see TODOs in `chatbot.py`) —
every request pays their cost before the response can close; not yet moved to a background task.

**Long-term memory** (`ai/memory/`, ported from a separate "TrueMemory" project):

- `embeddings.py` — shared `fastembed` (ONNX) `all-MiniLM-L6-v2` model, 384-dim. That
  dimension is baked into the `memories.embedding` column type — swapping models needs a migration.
- `store.py` — owns its own connection pool (separate from `chatbot.py`'s) so the memory layer
  works standalone. `search_lexical` (pg_search/BM25, L1) and `search_dense` (pgvector cosine, L2)
  are the two raw retrieval paths; `insert_memory` writes a row plus the `EncodingDecision` that
  justified storing it.
- `retrieval.py` — `retrieve()` fuses L1 + L2 via Reciprocal Rank Fusion (`RRF_K = 60`) into the
  ranking used for prompt context.
- `encoding_gate.py` — decides what's worth storing: a weighted blend of `novelty` (gzip-based
  compression delta against existing memories, not embedding distance — see module docstring for
  why), `salience` (`salience.py`), and `prediction_error` (embedding-based contradiction check),
  with a salience floor that blocks storage regardless of score and a contradiction bypass
  (`markers.py`) that always stores corrections. Threshold and weights are module constants at
  the top of the file.
- `salience.py` — hybrid scorer: short messages (`<= 50` chars) go through a rule-based speech-act
  classifier; longer ones through a logistic regression over hand-built text features, weights
  loaded from `l3_weights.json`.

**API** (`api/server.py`): thin FastAPI wrapper around `graph` from `ai/chatbot.py`.

- `POST /chat` — streams the assistant's reply as plain text (`stream_mode="messages"`, filtered
  to chunks from the `"chatbot"` node so `summarize`'s internal LLM call never leaks to the
  client). Every user message and the full assembled reply are also archived verbatim to the
  `messages` table (`initdb/02-messages.sql`) — this table is scrollback only, never read back
  by the graph itself, distinct from the LangGraph checkpoint.
- `GET /messages` — cursor-paginated scrollback (`before` = smallest id the client already has,
  newest page first, reversed to chronological order before returning).

## Frontend (`frontend/Juno/`)

React 19 + TypeScript + Vite, Tailwind v4 via `@tailwindcss/vite`. React Compiler is enabled
(babel plugin), which affects dev/build performance per the Vite template README.

```sh
cd frontend/Juno
pnpm install
pnpm dev        # vite dev server
pnpm build      # tsc -b && vite build
pnpm lint       # eslint .
pnpm preview
```

`src/api.ts` is the entire API client: `fetchMessages` (scrollback) and `streamChat` (POSTs to
`/chat`, reads the streamed body via a `ReadableStream` reader, token-by-token callback). Points
at `VITE_API_URL` env var, default `http://localhost:8000`.
