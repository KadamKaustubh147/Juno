# AI service

```
AI service/
├── ai/            # LangChain + LangGraph logic (the chatbot graph)
│   └── chatbot.py
└── api/           # FastAPI layer that exposes the graph over HTTP
    └── server.py
```

## Setup

`.env` needs:

```
AICREDITS_API_KEY=...
DATABASE_URL=postgresql://postgres:postgres@localhost:5442/postgres
```

```sh
docker compose up -d   # starts Postgres (see docker-compose.yml)
uv sync
```

Postgres must be running before you start the app -- the checkpoint tables are
created automatically on first run (`checkpointer.setup()`), but the connection
itself is opened at import time.

## Short-term memory

Conversation state is checkpointed to Postgres per `thread_id`, so it survives
process restarts. Two things keep it from growing unbounded:

- **Token trimming** (`MAX_TOKENS`, `ai/chatbot.py`): every turn, only a
  token-capped window of the raw history is sent to the LLM. Doesn't touch
  what's persisted -- just a guard-rail against oversized single turns.
- **Rolling summary** (`SUMMARIZE_AFTER_TOKENS`): once the raw history's token
  count passes this (set below `MAX_TOKENS`, so it fires before trimming would
  start silently excluding old content), the `summarize` node folds older
  turns into a `summary` string and deletes them from state (`RemoveMessage`),
  keeping the persisted history itself bounded too.

## Run the CLI chatbot

```sh
uv run python -m ai.chatbot
```

## Run the API server

MLflow tracing must be running first -- despite the comment in `chatbot.py`,
`mlflow.set_experiment()` does NOT fail silently when there's no server; it
raises and crashes the app at import time:

```sh
uvx mlflow server
```

Then, in another terminal:

```sh
uv run uvicorn api.server:app --reload
# or: ./runserver.sh
```

Then:

```sh
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "message": "hi", "thread_id": "1"}'
```

## Tests

No pytest suite -- the two `test_*.py` files under `ai/memory/` are runnable inspection
scripts, not assertions:

```sh
uv run python -m ai.memory.test_encoding_gate   # no DB needed; prints gate scores for sample messages
uv run python -m ai.memory.test_true_memory      # needs Postgres + AICREDITS_API_KEY; drives the real graph
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
for the test user, then runs a few retrieval sanity queries against it (e.g. "What is the
student studying?") to confirm retrieval surfaces the right memories too. Safe to re-run:
`reset_test_data()` clears the previous run's rows for the same throwaway user id first.

## Running with the frontend

CORS is only opened up for `http://localhost:5173` / `http://127.0.0.1:5173`
(the Vite dev server) in `api/server.py`. A frontend on any other origin gets
silently blocked at the browser's CORS preflight (`OPTIONS /chat` -> 405) --
curl and Postman won't show this since they don't send preflights, so it only
surfaces when testing from an actual browser.

With Postgres, `mlflow server`, and this API all running, start the frontend
(see `frontend/Juno`'s own setup) and it just works against
`http://localhost:8000` by default.
