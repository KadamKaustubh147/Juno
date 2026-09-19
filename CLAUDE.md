# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

This is not a real Turborepo (there's no `turbo.json`) — it's two independent projects living
side by side:

- `backend/` — Python backend: a LangGraph chatbot ("AI Therapist Chatbot") with a
  Postgres-backed long-term memory system, exposed over FastAPI, on SQLAlchemy + Alembic.
- `frontend/` — React + TypeScript + Vite chat client.

They communicate over plain HTTP (`VITE_API_URL`, default `http://localhost:8000`); there's no
shared build tooling between them. Treat them as separate projects and `cd` into the relevant one.

## Backend

### Setup & running

```sh
cd backend
uv sync                                    # installs deps (requires Python 3.12, see .python-version)
uv run alembic upgrade head                # creates the schema (and the pgvector extension)
uv run python -m scripts.seed_dev_user     # interim dev user -- there is no auth yet
```

Requires a `.env` with:
```
AICREDITS_API_KEY=...
DATABASE_URL=postgresql://user:password@host:port/dbname?sslmode=require
```

The database is a managed Postgres (Aiven) that only needs the `pgvector` extension; there is
no local database container. `postgres://` and `postgresql://` URIs both work — `app/config.py`
derives `SQLALCHEMY_DATABASE_URL` (`postgresql+psycopg://…`) from `DATABASE_URL`. Both env vars
are read at import time, so `alembic` needs `AICREDITS_API_KEY` set too.

The database must be reachable before the app starts: importing `app.core.db` opens a psycopg
pool and `app/orchestration/checkpointer.py` calls `checkpointer.setup()` at import time, so
even importing `app.main` (or `app.orchestration.graph`) fails without a live database.

Run the API server:
```sh
uv run uvicorn app.main:app --reload   # or ./runserver.sh
```

Run the CLI chatbot (needs the seeded dev user):
```sh
uv run python -m scripts.chat_cli
```

CORS: `app/main.py` allows `http://localhost:5173` and `http://127.0.0.1:5173` (the Vite
dev server) via `CORSMiddleware`. Add any other frontend origin there too, or the browser
will block every request at the preflight (`OPTIONS`) — this fails silently from curl/Postman
since they don't send preflights, so it only shows up when testing from an actual browser.

MLflow is not needed: the tracing block in `app/orchestration/llm_client.py` is commented out
and nothing imports `mlflow` (it's still listed in `pyproject.toml`, along with `flask` and
`pandas`, which are also unused).

### Migrations

Alembic lives in `app/db/migrations/` (`alembic.ini` at the backend root; the URL comes from
`app/config.py`, not the ini). Add models to `env.py`'s import list so autogenerate sees them.
`uv run alembic check` reports drift between the models and the DB. Autogenerate handles the
`vector` column, the generated `tsvector` column and the HNSW index poorly — review and hand-edit
the revision. The LangGraph checkpoint tables (`checkpoints`, `checkpoint_*`) are created by
`checkpointer.setup()`, not Alembic; `env.py` tells autogenerate to ignore them.

### Tests

No pytest suite — the `test_*.py` files under `scripts/` are runnable inspection scripts, not
assertions:

```sh
uv run python -m scripts.test_encoding_gate   # no DB needed; prints gate scores for sample messages
uv run python -m scripts.test_true_memory     # needs the migrated DB + AICREDITS_API_KEY; drives the real graph
uv run python -m scripts.query <user_id> "<query>"   # ad-hoc retrieve() against stored memories
```

### Architecture

Code lives in `backend/app/`; each feature keeps its own `router`/`schemas`/`service`/`models`.
Many files in the target structure (`auth/`, `users/` routers and services, `features/scripts/`,
`memory/graph/`, `memory/working_memory.py`, `orchestration/nodes/assess_completion.py` and
`select_next_section.py`, the `.j2` prompts) are empty placeholders with only a docstring.

**Chat graph** (`app/orchestration/graph.py`): a LangGraph `StateGraph` —
`START → retrieve_memories → chatbot → ingest_memory → (summarize?) → END`, checkpointed to
Postgres per `thread_id` via `PostgresSaver` so conversations survive restarts. State is in
`state.py`, routing in `edges.py`, the LLM client in `llm_client.py`, the checkpointer in
`checkpointer.py`.

- `retrieve_memories` (`nodes/memory_hook.py`) — pulls this user's relevant long-term memories
  into `memory_context` before the LLM call.
- `chatbot` (`nodes/generate_response.py`, registered under the name `"chatbot"` — the chat
  service filters the token stream on that name) — the actual LLM turn (model set by
  `MODEL_NAME` in `llm_client.py`). Builds a system message from `memory_context` + running
  `summary`, trims the sent history to `MAX_TOKENS` (doesn't touch what's persisted).
- `ingest_memory` (`nodes/memory_hook.py`) — runs the encoding gate over both the user's message
  and the assistant's reply, storing whatever it admits.
- `summarize` (`nodes/summarize.py`, conditional, fires past `SUMMARIZE_AFTER_TOKENS` in
  `edges.py`) — folds older turns into a `summary` string and deletes them from persisted state
  via `RemoveMessage`, keeping both the prompt and the checkpoint bounded. It's set below
  `MAX_TOKENS` on purpose, so summarization fires before `trim_messages` would start silently
  dropping content.

Both `ingest_memory` and `summarize` run synchronously in-graph (see the TODOs) — every request
pays their cost before the response can close; not yet moved to a background task.

**Database access**: sync SQLAlchemy 2.0 over psycopg3. `app/db/base.py` has `Base` and the shared
column mixins (uuid PK, `created_at`, `updated_at`); `app/db/session.py` has the engine and
`session_scope()` (commit/rollback/close). Routers get a session via `Depends(get_db)`
(`app/dependencies.py`); graph nodes and the streaming reply use `session_scope()` directly,
because a request-scoped session doesn't outlive a `StreamingResponse`. The one exception is
`app/core/db.py`: a separate raw psycopg pool used only by the LangGraph checkpointer, which
can't run on SQLAlchemy. Together they can hold ~30 connections — mind the managed plan's
`max_connections`.

**Schema**: `users`, `refresh_tokens` (`features/auth/models.py`), `therapy_sessions`, `messages`,
`section_transitions` (`features/sessions/models.py`), `memories` (`memory/semantic/models.py`).
All ids are UUIDs. `therapy_sessions.script_id`/`current_section` are NOT NULL but no scripts
feature exists, so `ensure_session` fills them from `app/shared/constants.py` when a thread's
first message creates the row.

**Long-term memory** (`app/memory/`, ported from a separate "TrueMemory" project):

- `semantic/embeddings.py` — shared `fastembed` (ONNX) `all-MiniLM-L6-v2` model, 384-dim. That
  dimension is baked into the `memories.embedding` column type (`Vector(384)`) — swapping models
  needs a migration.
- `semantic/vector_store.py` — the ORM read/write path for `memories`. `search_lexical` (L1) is
  core Postgres full-text search: `plainto_tsquery` with `&` swapped for `|` (any-term match, like
  the old ParadeDB `match()`), ranked by `ts_rank_cd` over the generated `content_tsv` column
  (GIN index). It is not BM25 — pg_search isn't installable on managed Postgres. `search_dense`
  (L2) is pgvector cosine distance (HNSW, `vector_cosine_ops`). `insert_memory` writes a row plus
  the `EncodingDecision` that justified storing it. `user_id` is a string at this module's
  boundary and converted to a UUID inside.
- `retriever.py` — `retrieve()` fuses L1 + L2 via Reciprocal Rank Fusion (`RRF_K = 60`) in Python
  into the ranking used for prompt context.
- `encoding_gate.py` — decides what's worth storing: a weighted blend of `novelty` (gzip-based
  compression delta against existing memories, not embedding distance — see module docstring for
  why), `salience` (`salience.py`), and `prediction_error` (embedding-based contradiction check),
  with a salience floor that blocks storage regardless of score and a contradiction bypass
  (`markers.py`) that always stores corrections. Threshold and weights are module constants at
  the top of the file.
- `salience.py` — hybrid scorer: short messages (`<= 50` chars) go through a rule-based speech-act
  classifier; longer ones through a logistic regression over hand-built text features, weights
  loaded from `l3_weights.json`.
- `writer.py` — thin re-export of `evaluate`/`insert_memory`; the actual decide-and-store loop is
  still the `ingest_memory` node.

**API** (`app/main.py`, routers in `app/features/*/router.py`). `user_id`, `thread_id`, and message
ids are all UUIDs; bad ones get a 422. Not-found/forbidden errors are `AppError`s
(`app/core/exceptions.py`) mapped to 404/403.

- `POST /chat` — validates the user and creates the session if new, archives the user's message
  (all before streaming starts, so failures are real HTTP errors), then streams the assistant's
  reply as plain text (`stream_mode="messages"`, filtered to chunks from the `"chatbot"` node so
  `summarize`'s internal LLM call never leaks to the client) and archives the assembled reply
  verbatim. `thread_id` (client-generated) becomes `therapy_sessions.id`. The `messages` table is
  scrollback only, never read back by the graph — distinct from the LangGraph checkpoint.
- `GET /sessions` — a user's threads, most recently active first.
- `GET /messages` — cursor-paginated scrollback (`before` = the id of the oldest message the client
  has; ordered by `(created_at, id)`, newest page first, reversed to chronological order).
- `GET /health`.

There's no auth: the frontend sends a hard-coded `USER_ID`, which must be the seeded dev user
(`scripts/seed_dev_user.py`, fixed UUID `00000000-0000-4000-8000-000000000001`).

## Frontend (`frontend/`)

React 19 + TypeScript + Vite, Tailwind v4 via `@tailwindcss/vite`. React Compiler is enabled
(babel plugin), which affects dev/build performance per the Vite template README.

```sh
cd frontend
pnpm install
pnpm dev        # vite dev server
pnpm build      # tsc -b && vite build
pnpm lint       # eslint .
pnpm preview
```

`src/api.ts` is the entire API client: `fetchSessions`, `fetchMessages` (scrollback) and
`streamChat` (POSTs to `/chat`, reads the streamed body via a `ReadableStream` reader,
token-by-token callback). Points at `VITE_API_URL` env var, default `http://localhost:8000`.
`ChatMsg.id` is typed `number` but the server now returns UUID strings (optimistic local messages
use numeric ids), so it works at runtime with a stale type.
