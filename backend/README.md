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
│   ├── orchestration/     # LangGraph: graph_builder (structure), graph (+ Postgres checkpointer), state,
│   │                      #   nodes/, edges, llm_client, script.json + script_loader, prompts/*.txt
│   └── memory/            # long-term memory (episodic/: encoding gate, retrieval, pgvector store)
├── tests/unit/orchestration/  # pytest suite for the scripted-session flow (no DB, no network)
├── scripts/               # seed/CLI/inspection scripts (not app code)
└── alembic.ini            # migrations config (DB URL comes from DATABASE_URL)
```

Each feature keeps its SQLAlchemy models in its own `models.py` (`features/users`,
`features/auth`, `features/sessions`); the `memories` model is `app/memory/episodic/models.py`.

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

Then (the dev user must be seeded, and `thread_id` is any new UUID -- it becomes the
session id on the first message):

```sh
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "00000000-0000-4000-8000-000000000001", "message": "hi", "thread_id": "'"$(uuidgen)"'"}'
```

## Tests

The scripted-session flow has a pytest suite in `tests/unit/orchestration/`. It needs no database
and no network -- every LLM is replaced by a fake, and any test that forgets to install one fails
instead of calling the real model:

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
