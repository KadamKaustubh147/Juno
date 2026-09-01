# Juno

An AI therapist chatbot: a LangGraph backend with Postgres-backed long-term memory
("True Memory") in `AI service/`, and a React chat client in `frontend/Juno/`. They talk
over plain HTTP -- there's no shared build tooling between them, this is not a real
Turborepo despite the folder layout.

See `AI service/ARCHITECTURE.md` for how the backend is structured, and
`CLAUDE.md` for repo-wide notes aimed at coding agents.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) (Python 3.12, pinned by `AI service/.python-version`)
- Node.js + `npm` (or `pnpm`)
- An API key for an OpenAI-compatible LLM endpoint (this repo currently points at
  `https://aicredits.in/v1`, model `openai/gpt-oss-120b` -- see `AI service/ai/chatbot.py`)

## 1. Database

```sh
cd "AI service"
docker compose up -d
```

Starts Postgres (`paradedb/paradedb`, port `5442`) with `pgvector` and `pg_search`
compiled in. On a fresh volume, `initdb/` auto-creates everything: the extensions, the
`messages` archive table, and the `memories` table. On an existing volume, apply the
`initdb/*.sql` files by hand -- see `AI service/README.md`.

## 2. Backend

```sh
cd "AI service"
```

Create `.env`:

```
AICREDITS_API_KEY=your_key_here
DATABASE_URL=postgresql://postgres:postgres@localhost:5442/postgres
```

Install deps and start MLflow (required -- the app crashes on startup without it,
see `AI service/README.md`), then the API, in separate terminals:

```sh
uv sync
uvx mlflow server                          # terminal 1, leave running
uv run uvicorn api.server:app --reload     # terminal 2, leave running
```

Verify: `curl http://localhost:8000/health` -> `{"status":"ok"}`.

## 3. Frontend

```sh
cd frontend/Juno
npm install     # or pnpm install
npm run dev     # or pnpm dev
```

Opens on `http://localhost:5173`, talks to `http://localhost:8000` by default
(`VITE_API_URL` env var to change it). If you change the frontend's origin/port, add it
to the CORS allowlist in `AI service/api/server.py` or every request will be silently
blocked at the browser's preflight.

## 4. Try it

Open `http://localhost:5173` and send a message. To confirm persistence: note the
`?thread=<uuid>` the URL gets after your first message, then reload that exact URL --
the conversation should restore from Postgres.

## Shutting down

```sh
# Ctrl+C the frontend, backend, and mlflow terminals
cd "AI service" && docker compose stop   # or `down` to remove the container (data persists in the volume)
```

## Repo layout

- `AI service/` -- Python backend (FastAPI + LangGraph + Postgres). See its own
  `README.md` for backend-only setup detail, and `ARCHITECTURE.md` for how the pieces
  fit together.
- `frontend/Juno/` -- React + TypeScript + Vite chat client.
