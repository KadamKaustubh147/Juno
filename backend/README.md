# Juno backend

```
backend/
├── app/
│   ├── main.py            # FastAPI app: CORS, router wiring, /health
│   ├── config.py          # env settings (DATABASE_URL, AICREDITS_API_KEY, JWT_SECRET)
│   ├── core/              # auth/ (jwt, password hashing), security.py (bearer-token dependency),
│   │                      #   exceptions.py, db.py (psycopg pool for the LangGraph checkpointer only)
│   ├── db/                # SQLAlchemy Base/mixins, engine + session, Alembic migrations/
│   ├── features/
│   │   ├── auth/          # POST /auth/register, /auth/login
│   │   ├── users/         # GET/PATCH /users/me
│   │   ├── sessions/      # POST/GET/DELETE /sessions..., GET /sessions/{id}/messages + the `messages` archive
│   │   └── chat/          # POST /chat (streams the graph's reply as Server-Sent Events)
│   ├── orchestration/     # LangGraph: graph_builder (structure), graph (+ Postgres checkpointer), state,
│   │                      #   nodes/, edges, llm_client, script.json + script_loader, prompts/*.txt
│   └── memory/            # long-term memory (episodic/: encoding gate, retrieval, pgvector store)
├── tests/unit/orchestration/  # pytest suite for the scripted-session flow (no DB, no network)
├── tests/unit/api/            # HTTP API tests (in-memory SQLite, fake/real-on-MemorySaver graph)
├── scripts/               # seed/CLI/inspection scripts (not app code)
└── alembic.ini            # migrations config (DB URL comes from DATABASE_URL)
```

Each feature keeps its SQLAlchemy models in its own `models.py` (`features/users`,
`features/auth`, `features/sessions`); the `memories` model is `app/memory/episodic/models.py`.

(`features/scripts/`, `memory/graph/` etc. are empty placeholders. `features/auth` still carries the `RefreshToken`
model and `core/auth/refresh_tokens.py` is a placeholder: there are no refresh tokens, access tokens never expire.)

## Setup

`.env` needs:

```
AICREDITS_API_KEY=...
DATABASE_URL=postgresql://user:password@host:port/dbname?sslmode=require   # e.g. Aiven Postgres
JWT_SECRET=...                                                              # signs access tokens; keep it long and random
```

`postgres://` and `postgresql://` URIs both work: SQLAlchemy is pointed at the psycopg3
driver automatically (`app/config.py`). The `vector` extension is created by the first
migration.

```sh
uv sync
uv run alembic upgrade head                 # creates the schema
uv run python -m scripts.seed_dev_user      # optional: the dev user the CLI/memory scripts use
```

Migrations: `uv run alembic revision --autogenerate -m "..."` after changing a model,
then review the file (vector / generated-column / HNSW parts often need hand edits).
The LangGraph checkpoint tables are created by `checkpointer.setup()`, not by Alembic;
`migrations/env.py` tells autogenerate to ignore them.

The database must be reachable before you start the app -- the checkpoint tables are
created automatically on first run (`checkpointer.setup()`), but the connection
itself is opened at import time.

## Scripted sessions

The therapist follows a scripted CBT session (Script-Based Dialog Policy Planning,
[arXiv:2412.15242](https://arxiv.org/abs/2412.15242)). `orchestration/script.json` holds eight
sections of tasks; the graph works out where the patient is in it and steers the reply accordingly:

```
START -> retrieve_memories -> assess_completion -+- session_done ------> END
                                                 +- section_complete --> select_next_section -> chatbot
                                                 `- otherwise --------> chatbot
chatbot -> ingest_memory -> (summarize) -> END
```

- **`assess_completion`** asks an LLM, conservatively, whether every task in the current section is
  done (including conditions like "patient confirmed" or "no more questions"). On the very first turn
  there's nothing to assess, so it skips the LLM and stays in Section 1.
- **`select_next_section`** moves on. Where a section has one legal successor it just takes it; in
  Sections 2 and 4, which branch, a second LLM call chooses, and the choice is checked against the
  allowed transitions (`script_loader.TRANSITIONS`) -- an invalid answer is retried once, then the
  session stays put.
- **`chatbot`** builds its system message from `prompts/system_prompt.txt` and
  `prompts/response_prompt.txt` (the current section's full text), plus retrieved memories and the
  running summary. It never mentions sections or tasks to the patient.

Transitions: 1 -> 2; 2 -> 3 or 4; 3 -> 4; 4 -> 5, 6 or 7; 5, 6, 7 -> 8; 8 ends the session. The script
states these only as prose, so they're encoded in `script_loader.py` and checked against the prose by a
test. `script.json` is **not strict JSON** (raw newlines inside strings) -- it's loaded with
`json.loads(text, strict=False)`, so don't reformat it.

Prompts are plain `.txt` files filled by `render_prompt()` (`string.Template`): use `$name` /
`${name}` placeholders, write a literal dollar sign as `$$`, and a missing variable raises rather than
rendering blank. The assessor and dispatcher use `judge_llm` (temperature 0) and get structured output
through `invoke_structured()`, which uses the endpoint's native structured output and falls back to
prompting for JSON.

**Ending a session.** When the final section is complete, `session_done` is set and stays set: the
graph then ends every turn without calling an LLM or producing a reply. The chat service doesn't
handle this yet -- it streams an empty response and doesn't tell the frontend the session is over. It also
doesn't write the graph's `current_section` back to `therapy_sessions`, which still holds the interim
`"intro"` value from `app/shared/constants.py`.

Every turn after the first costs one extra LLM call (the assessor) before the reply starts streaming.

## Short-term memory

Conversation state is checkpointed to Postgres per `thread_id`, so it survives
process restarts. Two things keep it from growing unbounded:

- **Token trimming** (`MAX_TOKENS`, `app/orchestration/nodes/generate_response.py`): every turn, only a
  token-capped window of the raw history is sent to the LLM. Doesn't touch
  what's persisted -- just a guard-rail against oversized single turns.
- **Rolling summary** (`SUMMARIZE_AFTER_TOKENS`): once the raw history's token
  count passes this (set below `MAX_TOKENS`, so it fires before trimming would
  start silently excluding old content), the `summarize` node folds older
  turns into a `summary` string and deletes them from state (`RemoveMessage`),
  keeping the persisted history itself bounded too.

## Run the CLI chatbot

```sh
uv run python -m scripts.chat_cli
```

## Run the API server

MLflow tracing is not required: the tracing block in `app/orchestration/llm_client.py`
is commented out and nothing imports `mlflow`. (If you uncomment it, `mlflow.set_experiment()`
raises at import time unless `uvx mlflow server` is running.)

```sh
uv run uvicorn app.main:app --reload
# or: ./runserver.sh
```

Then register, start a session, and chat (`-N` keeps curl from buffering the stream):

```sh
BASE=http://localhost:8000
TOKEN=$(curl -s -X POST $BASE/auth/register -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "at least 8 chars"}' | jq -r .access_token)
SESSION=$(curl -s -X POST $BASE/sessions -H "Authorization: Bearer $TOKEN" | jq -r .id)
curl -N -X POST $BASE/chat -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"thread_id": "'"$SESSION"'", "message": "hi"}'
```

### Endpoints

Everything except `/auth/*` and `/health` needs `Authorization: Bearer <token>`. Tokens never expire
(no refresh tokens); deactivate the user (`users.is_active`) or rotate `JWT_SECRET` to cut one off.

| Method + path | |
|---|---|
| `POST /auth/register` | `{email, password (8+), full_name?}` -> `{access_token, token_type, user}` |
| `POST /auth/login` | `{email, password}` -> same shape |
| `GET /users/me`, `PATCH /users/me` | profile; PATCH takes `{full_name}` |
| `POST /sessions` | start a session at Section 1 -> `{id, status, current_section, ...}` |
| `GET /sessions` | your sessions, most recently active first (`?limit=`) |
| `GET /sessions/{id}` | one session: status, current section, `ended_at`, `last_at` |
| `GET /sessions/{id}/messages` | scrollback, newest page first (`?before=<message id>&limit=`) |
| `DELETE /sessions/{id}` | delete the session, its messages and its saved graph state |
| `POST /chat` | `{thread_id, message}` -> the reply as Server-Sent Events |
| `GET /health` | |

Someone else's session id answers 404, same as one that doesn't exist.

### Streaming (`POST /chat`)

The response is `text/event-stream`; each event is `event: <name>` + one line of `data: <json>`:

| event | data | |
|---|---|---|
| `start` | `{user_message_id}` | your message is saved; the reply is on its way |
| `section` | `{from, to}` | the session moved to a new script section |
| `token` | `{text}` | a chunk of the reply (zero or more) |
| `done` | `{message_id, current_section, session_done}` | reply complete and saved; `message_id` is null if there was no reply |
| `error` | `{detail}` | the turn failed after streaming began |

Errors before streaming starts (401, 404, 422) are ordinary JSON responses. `EventSource` can't POST or send
an `Authorization` header, so clients read the body with `fetch` and parse the frames themselves
(`frontend/src/api.ts`). If the client disconnects, whatever reply text was sent is still archived.

## Tests

The scripted-session flow has a pytest suite in `tests/unit/orchestration/`, and the HTTP API has one in
`tests/unit/api/` (in-memory SQLite, plus the real graph on `MemorySaver`). Neither needs a database or
network -- every LLM is replaced by a fake, and any test that forgets to install one fails instead of
calling the real model:

```sh
uv run pytest tests
```

Tests import `app.orchestration.graph_builder`, not `graph.py`, because `graph.py` (via
`checkpointer.py`) connects to Postgres at import time. The full-graph test walks
Section 1 -> 2 -> 4 -> 5 -> 8 -> done on an in-memory checkpointer.

Separately, the two `test_*.py` files under `scripts/` are runnable inspection
scripts, not assertions:

```sh
uv run python -m scripts.test_encoding_gate   # no DB needed; prints gate scores for sample messages
uv run python -m scripts.test_true_memory      # needs the migrated DB + AICREDITS_API_KEY; drives the real graph
```

`test_encoding_gate.py` runs a handful of hand-picked example messages (noise, an exact
restatement, a worded correction, a new salient fact, ...) straight through
`encoding_gate.evaluate()` and prints the score breakdown for each -- no database or LLM
call needed, just a quick way to see what the gate keeps vs. throws away.

`test_true_memory.py` is the real integration test: it plays a scripted 18-message mock
conversation through the *actual* compiled graph (`graph.invoke`, not a reimplementation),
so `retrieve_memories` -> `assess_completion` -> `chatbot` -> `ingest_memory` all run exactly as they
would in production, including genuine LLM calls (the assessor, from the second message on, and the
reply) per message. Since the assistant's replies
aren't scripted, it can't predict ahead of time which assistant turns will get stored --
so after the conversation runs, it prints everything that actually ended up in `memories`
for the test user (a throwaway `users` row it creates itself), then runs a few retrieval sanity queries against it (e.g. "What is the
student studying?") to confirm retrieval surfaces the right memories too. Safe to re-run:
`reset_test_data()` clears the previous run's rows for the same throwaway user id first.

## Running with the frontend

CORS is only opened up for `http://localhost:5173` / `http://127.0.0.1:5173`
(the Vite dev server) in `app/main.py`. A frontend on any other origin gets
silently blocked at the browser's CORS preflight (`OPTIONS /chat` -> 405) --
curl and Postman won't show this since they don't send preflights, so it only
surfaces when testing from an actual browser.

With the database migrated and this API running, start the frontend
(see `../frontend`) and it just works against
`http://localhost:8000` by default.
