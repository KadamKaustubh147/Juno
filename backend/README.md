# Juno backend

```
backend/
├── app/
│   ├── main.py            # FastAPI app: CORS, router wiring, /health
│   ├── config.py          # env settings (DATABASE_URL, AICREDITS_API_KEY)
│   ├── core/db.py         # psycopg pool for the LangGraph checkpointer only
│   ├── db/                # SQLAlchemy Base/mixins, engine + session, Alembic migrations/
│   ├── features/
│   │   ├── chat/          # POST /chat (streams the graph's reply)
│   │   └── sessions/      # GET /sessions, GET /messages + the `messages` archive
│   ├── orchestration/     # LangGraph: graph, state, nodes/, edges, checkpointer, llm_client
│   └── memory/            # long-term memory (encoding gate, retrieval, pgvector store)
├── scripts/               # seed/CLI/inspection scripts (not app code)
└── alembic.ini            # migrations config (DB URL comes from DATABASE_URL)
```

Each feature keeps its SQLAlchemy models in its own `models.py` (`features/users`,
`features/auth`, `features/sessions`); the `memories` model is `app/memory/semantic/models.py`.

(`auth/` and `users/` have models only so far; their routers/services, `features/scripts/`, `memory/graph/` etc. are empty placeholders.)

## Setup

`.env` needs:

```
AICREDITS_API_KEY=...
DATABASE_URL=postgresql://user:password@host:port/dbname?sslmode=require   # e.g. Aiven Postgres
```

`postgres://` and `postgresql://` URIs both work: SQLAlchemy is pointed at the psycopg3
driver automatically (`app/config.py`). The `vector` extension is created by the first
migration.

```sh
uv sync
uv run alembic upgrade head                 # creates the schema
uv run python -m scripts.seed_dev_user      # interim dev user (no auth yet)
```

Migrations: `uv run alembic revision --autogenerate -m "..."` after changing a model,
then review the file (vector / generated-column / HNSW parts often need hand edits).
The LangGraph checkpoint tables are created by `checkpointer.setup()`, not by Alembic;
`migrations/env.py` tells autogenerate to ignore them.

The database must be reachable before you start the app -- the checkpoint tables are
created automatically on first run (`checkpointer.setup()`), but the connection
itself is opened at import time.

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

Then (the dev user must be seeded, and `thread_id` is any new UUID -- it becomes the
session id on the first message):

```sh
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "00000000-0000-4000-8000-000000000001", "message": "hi", "thread_id": "'"$(uuidgen)"'"}'
```

## Tests

No pytest suite -- the two `test_*.py` files under `scripts/` are runnable inspection
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
so `retrieve_memories` -> `chatbot` -> `ingest_memory` all run exactly as they would in
production, including one genuine LLM call per message. Since the assistant's replies
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
