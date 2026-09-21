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
uv run python -m scripts.seed_dev_user     # optional: the dev user the CLI/memory scripts use (it can't log in)
```

Requires a `.env` with:
```
OPENROUTER_API_KEY=...
DATABASE_URL=postgresql://user:password@host:port/dbname?sslmode=require
JWT_SECRET=...   # signs access tokens; only the server needs it (core/auth/jwt.py refuses to import without it)
```

The database is a managed Postgres (Aiven) that only needs the `pgvector` extension; there is
no local database container. `postgres://` and `postgresql://` URIs both work — `app/config.py`
derives `SQLALCHEMY_DATABASE_URL` (`postgresql+psycopg://…`) from `DATABASE_URL`. Both env vars
are read at import time, so `alembic` needs `OPENROUTER_API_KEY` set too.

The database must be reachable before the app starts: importing `app.core.db` opens a psycopg
pool and `app/orchestration/checkpointer.py` calls `checkpointer.setup()` at import time, so
even importing `app.main` (or `app.orchestration.graph`) fails without a live database.
`app/orchestration/graph_builder.py` (`build_graph(checkpointer)`) has no such dependency, which is
why the tests import it instead.

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

`tests/unit/orchestration/` is a pytest suite for the scripted-session flow: the script loader, prompt
rendering, the structured-output helper, routing, both SBDPP nodes, the response node, and a full-graph
walk (Section 1 → 2 → 4 → 5 → 8 → done) on `MemorySaver`. It needs no database and no network:
`conftest.py` sets dummy env vars if there's no `.env`, and swaps every LLM in the node modules for one
that raises, so a test can't spend credits by accident — tests install `FakeLLM`s (`fakes.py`) instead.
pytest is a dev dependency (`[dependency-groups].dev`), installed by `uv sync`.

```sh
uv run pytest tests
```

Tests must import `app.orchestration.graph_builder`, never `graph.py` or `checkpointer.py` (Postgres at
import time). With no `user_id` in the config, `retrieve_memories`/`ingest_memory` return early, so the
real memory nodes can run in a test without touching the memory layer.

The `test_*.py` files under `scripts/` are not part of that suite — they're runnable inspection
scripts, not assertions:

```sh
uv run python -m scripts.test_encoding_gate   # no DB needed; prints gate scores for sample messages
uv run python -m scripts.test_true_memory     # needs the migrated DB + OPENROUTER_API_KEY; drives the real graph
uv run python -m scripts.query <user_id> "<query>"   # ad-hoc retrieve() against stored memories
```

### Architecture

Code lives in `backend/app/`; each feature keeps its own `router`/`schemas`/`service`/`models`.
Several files in the target structure (`auth/`, `users/` routers and services, `features/scripts/`,
`memory/graph/`, `memory/working_memory.py`) are empty placeholders with only a docstring.

**Chat graph**: a LangGraph `StateGraph` that runs a scripted CBT session — Script-Based Dialog
Policy Planning (SBDPP, arXiv:2412.15242). The structure is `build_graph(checkpointer)` in
`graph_builder.py`; `graph.py` just attaches the Postgres `PostgresSaver` (per `thread_id`, so
conversations survive restarts) and exports `graph`. State is in `state.py`, routing in `edges.py`,
the LLM client and prompt/structured-output helpers in `llm_client.py`, the script in `script.json` +
`script_loader.py`.

```
START → retrieve_memories → assess_completion ─┬─ session_done ─────→ END
                                               ├─ section_complete → select_next_section → chatbot
                                               └─ otherwise ───────→ chatbot
chatbot → ingest_memory → (summarize?) → END
```

**The script** (`script.json`, loaded by `script_loader.load_script()`): "Section 1".."Section 8",
each a dict of "Task 1a".. → instruction text. It is *not* strict JSON (raw newlines inside strings),
so it's loaded with `strict=False` — don't "fix" or reformat the file. The script only states
transitions as prose ("proceed with Section 5"), so `script_loader.TRANSITIONS` encodes them as data
(1→2; 2→3|4; 3→4; 4→5|6|7; 5,6,7→8; 8 is terminal). A test compares the table to the prose, and
`load_script()` validates it against the script's keys. `FIRST_SECTION` is `"Section 1"`.

- `retrieve_memories` (`nodes/memory_hook.py`) — pulls this user's relevant long-term memories
  into `memory_context` before the LLM call. Runs before `assess_completion`; the SBDPP nodes never
  call the memory layer themselves.
- `assess_completion` (`nodes/assess_completion.py`) — every turn: an LLM judges (conservatively)
  whether *all* tasks of `current_section` are done, including conditions like "patient confirmed" or
  "no more questions". It re-derives `section_complete`/`session_done`/`thought` from scratch each
  turn; only `current_section` (and `session_done`, see below) carries over from the checkpoint.
  No therapist reply yet (first turn) → no LLM call, stay in Section 1. An unparseable verdict is
  treated as "not complete". Completing a section with no successor (Section 8) sets `session_done`.
- `select_next_section` (`nodes/select_next_section.py`) — one allowed successor → take it, no LLM.
  Otherwise (Sections 2 and 4) a dispatcher LLM picks; the answer is validated against
  `TRANSITIONS[current]`, retried once with a correction, then it stays in the current section and
  says so in the reasoning. Appends a `{"from","to","reasoning"}` entry to `transitions`.
- `chatbot` (`nodes/generate_response.py`, registered under the name `"chatbot"` — the chat
  service filters the token stream on that name, which is also what keeps the assessor's and
  dispatcher's LLM output from reaching the client) — the actual LLM turn (model set by
  `MODEL_NAME` in `llm_client.py`). Builds the system message from `prompts/system_prompt.txt` +
  `prompts/response_prompt.txt` (the *current section's* full text) + `memory_context` + running
  `summary`; on the turn a section change actually happened it also appends a "you have just entered
  this part, open it naturally" sentence (added in Python, not templated). Trims the sent history to
  `MAX_TOKENS` (doesn't touch what's persisted).
- `ingest_memory` (`nodes/memory_hook.py`) — runs the encoding gate over both the user's message
  and the assistant's reply, storing whatever it admits.
- `summarize` (`nodes/summarize.py`, conditional, fires past `SUMMARIZE_AFTER_TOKENS` in
  `edges.py`) — folds older turns into a `summary` string and deletes them from persisted state
  via `RemoveMessage`, keeping both the prompt and the checkpoint bounded. It's set below
  `MAX_TOKENS` on purpose, so summarization fires before `trim_messages` would start silently
  dropping content.

Both `ingest_memory` and `summarize` run synchronously in-graph (see the TODOs) — every request
pays their cost before the response can close; not yet moved to a background task. Likewise every
turn after the first now pays one non-streamed assessor LLM call *before* the reply's first token
(plus a dispatcher call on turns that leave a branching section).

**Ending a session**: `session_done` is sticky — once the terminal section completes, every later
turn skips the LLM, routes to `END`, and produces no reply (no `chatbot` chunks, nothing for
`ingest_memory`/`summarize` to run on). `retrieve_memories` still runs first on those turns. The chat
service reads `session_done` back from the checkpoint after every turn, marks the session `completed`
(`ended_at`), and reports it in the `done` event; a finished session's turns stream `start` then `done`
with `message_id: null` and archive no reply.

**Prompts and LLM helpers** (`prompts/*.txt`, `llm_client.py`):
- `prompts/` holds plain-text prompts — `system_prompt`, `response_prompt`, `assessment_prompt`,
  `dispatch_prompt` (no Jinja, no new dependency). `render_prompt(name, **ctx)` reads
  `prompts/<name>` (extension included) and fills `$name`/`${name}` with `string.Template.substitute`,
  so a missing variable raises `KeyError` instead of rendering blank. A literal dollar sign in a prompt
  file must be written `$$`; JSON braces need no escaping; substituted *values* are never re-scanned.
- `llm` is the streaming chat model. `judge_llm` is a second client, same model, `temperature=0`,
  for the assessor and dispatcher (a `.bind(temperature=0)` would be lost by `with_structured_output`).
  Both go through OpenRouter (`OPENROUTER_API_KEY`), pinned to the Crusoe `crusoe/bf16` endpoint via
  `extra_body={"provider": {"only": [...], "allow_fallbacks": False}}` (`OPENROUTER_PROVIDER`): if Crusoe
  is down the turn errors rather than routing elsewhere. Both also have a 60s timeout and 1 retry
  (the OpenAI SDK default is a 600s timeout).
- `invoke_structured(model, schema, prompt)` tries native structured output first and falls back to
  prompting for JSON and parsing it into the Pydantic model, with one retry that says what was wrong;
  it raises `StructuredOutputError` if neither works. Native structured output (`json_schema`,
  `function_calling`, `json_mode`) worked on `openai/gpt-oss-120b` via AICredits (probed 2026-09-20; not yet
  re-probed on OpenRouter/Crusoe), so the fallback normally never runs. Nodes take the model as an argument from their own module-level
  name (`judge_llm`), which is what tests patch.
- `format_transcript` renders *all* persisted human/AI messages as `Patient:`/`Therapist:` lines for
  the assessor and dispatcher; they get it as prompt text, not as chat roles. There is deliberately no
  window: `summarize` already bounds the raw history (≈`SUMMARIZE_AFTER_TOKENS`, ~6k tokens), and a
  narrower cap (it used to be the last 12) hid early tasks — Task 1a's welcome scrolled out of view, so
  the assessor concluded it never happened and Section 1 could never complete
  (`test_a_long_section_keeps_its_opening_visible_to_the_assessor`). Once `summarize` has pruned
  the history, only the last 2 raw messages plus `summary` remain; the assessor's prompt includes the
  summary, the dispatcher's does not.

**Database access**: sync SQLAlchemy 2.0 over psycopg3. `app/db/base.py` has `Base` and the shared
column mixins (uuid PK, `created_at`, `updated_at`); `app/db/session.py` has the engine and
`session_scope()` (commit/rollback/close). Routers get a session via `Depends(get_db)`
(`app/dependencies.py`); graph nodes and the streaming reply use `session_scope()` directly,
because a request-scoped session doesn't outlive a `StreamingResponse`. The one exception is
`app/core/db.py`: a separate raw psycopg pool used only by the LangGraph checkpointer, which
can't run on SQLAlchemy. Together they can hold ~30 connections — mind the managed plan's
`max_connections`.

**Schema**: `users`, `refresh_tokens` (`features/auth/models.py`), `therapy_sessions`, `messages`,
`section_transitions` (`features/sessions/models.py`), `memories` (`memory/episodic/models.py`).
All ids are UUIDs. `therapy_sessions.script_id`/`current_section` are NOT NULL but no scripts
feature exists, so `POST /sessions` (`sessions.service.create_session`) sets `script_id` to
`DEFAULT_SCRIPT_ID` (`app/shared/constants.py`, `"cbt_intro_v1"`) and `current_section` to `FIRST_SECTION`.
The LangGraph checkpoint stays the source of truth for the section and `transitions`; after every chat turn
`chat.service._settle` copies them onto the row via `sessions.service.record_progress` (`current_section`,
new `section_transitions` rows — the checkpoint's list only grows, so it inserts the tail past the rows
already there — and `status`/`ended_at` when the session finishes). `refresh_tokens` exists as a model but
nothing uses it: there are no refresh tokens.

**Long-term memory** (`app/memory/episodic/`): all of it is code ported from a separate "TrueMemory"
project, which is an episodic memory (it stores what was said, per user). It lives flat in
`episodic/`; the other `app/memory/` entries (`graph/`, `working_memory.py`) are placeholders.
`episodic/store.py` is also a docstring-only placeholder, not part of the working code below.

- `embeddings.py` — shared `fastembed` (ONNX) `all-MiniLM-L6-v2` model, 384-dim. That
  dimension is baked into the `memories.embedding` column type (`Vector(384)`) — swapping models
  needs a migration.
- `models.py` — the `Memory` ORM model (the `memories` table).
- `vector_store.py` — the ORM read/write path for `memories`. `search_lexical` (L1) is
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

**API** (`app/main.py`, routers in `app/features/*/router.py`). `thread_id`, session and message
ids are UUIDs; bad ones get a 422. Not-found/auth errors are `AppError`s (`app/core/exceptions.py`)
mapped to 401/404/409. Every route except `/auth/*` and `/health` requires `Authorization: Bearer <jwt>`
(`CurrentUserId` in `app/core/security.py`); nothing takes a `user_id` from the client. Someone else's
session is a 404, indistinguishable from a missing one.

- `POST /auth/register`, `POST /auth/login` — `{access_token, token_type, user}`. Passwords are argon2
  (`core/auth/password.py`); emails are stored lowercased; login doesn't format-validate the email (the
  seeded `dev@juno.local` fails `EmailStr`). The JWT is HS256 with `sub` = user id and **no `exp`**:
  tokens never expire and there are no refresh tokens. `get_current_user_id` re-checks `users.is_active`
  on every request, which is the kill switch (the other is rotating `JWT_SECRET`). It uses its own short
  `session_scope()` rather than `get_db`, so a streaming `/chat` doesn't hold a pooled connection open.
- `GET`/`PATCH /users/me`.
- `POST /sessions` (server-side creation, returns the `id` to chat to), `GET /sessions` (`?limit=`, includes
  sessions with no messages yet), `GET /sessions/{id}`, `DELETE /sessions/{id}` (row + cascaded messages, then
  `checkpointer.delete_thread`), `GET /sessions/{id}/messages` (cursor-paginated scrollback: `before` = the id
  of the oldest message the client has; ordered by `(created_at, id)`, newest page first, reversed to
  chronological order; `has_more` is exact).
- `POST /chat` `{thread_id, message}` — checks ownership and archives the user's message (all before
  streaming starts, so failures are real HTTP errors), then streams **Server-Sent Events** (see the
  docstring of `features/chat/service.py` for the event list: `start`, `section`, `token`, `done`,
  `error`). It runs `graph.stream(..., stream_mode=["messages", "updates"])`: `messages` items filtered to
  the `"chatbot"` node become `token` events (so the assessor's, dispatcher's and `summarize`'s LLM output
  never leaks); `updates` items carrying a `transitions` entry become `section` events. Afterwards
  `_settle` reads the checkpoint (`graph.get_state`), saves the reply and the session's progress in one
  transaction, and sends `done`. The same `_settle` runs from `finally` when the client disconnects or the
  graph crashes, so the partial reply is archived (an empty reply is not). A mid-stream failure is an
  `error` event with a generic message, not an HTTP error. The `messages` table is scrollback only, never
  read back by the graph — distinct from the LangGraph checkpoint. Mutating routes call `db.commit()`
  before returning because `get_db`'s own commit only runs after the response has been sent.
- `GET /health`.

`tests/unit/api/` covers all of it on in-memory SQLite (`conftest.py` stubs `app.orchestration.graph` and
`.checkpointer` in `sys.modules`, since those connect to Postgres at import) with a fake graph, plus
`test_chat_real_graph.py` running the real graph on `MemorySaver` to pin the stream shapes the service
depends on.

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

**Screens.** There is no router: `src/Root.tsx` picks one of three screens from two pieces of state
(signed in? which auth screen is open?). Signed out shows `pages/LandingPage.tsx`; its buttons open
`AuthScreen.tsx` in login or register mode; signed in shows `pages/ChatPage.tsx`. Logout drops back to
the landing page. A restored session renders straight from the stored token, without waiting for the
server -- only a 401 (see below) signs the user out, so a network error or an unreachable backend doesn't.

**API client.** `src/api.ts` is the entire client and the only file that knows the backend contract: auth
(`login`, `register`, `fetchMe`), sessions (`createSession`, `fetchSessions`, `fetchMessages`) and
`streamChat`, which POSTs `/chat` and parses the Server-Sent Events itself (`EventSource` can't POST or
send headers) into `onStart`/`onToken`/`onDone`/`onError` callbacks. The bearer token lives in
localStorage (`juno_token`); nothing sends a user id, the server reads it from the token. A 401 on a
request that carried a token clears it and calls the handler `Root` registers with
`setUnauthorizedHandler`, which shows the login screen. Base URL is `VITE_API_URL`, default
`http://localhost:8000`.

**Layout** (`src/`): `components/` (shared `Button`, `Logo`), `pages/` (one per screen, they only compose),
`features/chat/` (`hooks/useChat.ts` -- messages, scrollback paging, the streamed reply, sessions created
lazily on the first send; `hooks/useSessions.ts`; `components/` for sidebar, header, message list,
bubble, composer) and `features/auth/useMe.ts`. The open session lives in `?thread=<id>` so a refresh
restores it. Optimistic messages carry a temporary `local-…` id until `onStart`/`onDone` report the real
ones; `useChat` never sends a `local-` id as a scrollback cursor. When a turn's `done` reports
`session_done`, or a session opens with `status: "completed"`, the composer is replaced by a notice.

**Palette and type.** The colors are the tokens in `src/index.css` (`cream`, `sage`, `ink`, `muted`,
`line`); use them rather than adding new colors. `font-serif` is Fraunces (Google Fonts link in
`index.html`), used for headlines and the assistant's messages.
