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
GROQ_API_KEY=...
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
