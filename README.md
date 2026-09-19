# Juno

An AI therapist chatbot: a LangGraph backend with Postgres-backed long-term memory
("True Memory") in `backend/`, and a React chat client in `frontend/`. They talk
over plain HTTP -- there's no shared build tooling between them, this is not a real
Turborepo despite the folder layout.

See `backend/README.md` for how the backend is structured, and
`CLAUDE.md` for repo-wide notes aimed at coding agents.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) (Python 3.12, pinned by `backend/.python-version`)
- Node.js + `npm` (or `pnpm`)
- A PostgreSQL database with the `pgvector` extension available -- a managed one such as
  Aiven works (no other extensions are needed)
- An API key for an OpenAI-compatible LLM endpoint (this repo currently points at
  `https://aicredits.in/v1`, model `openai/gpt-oss-120b` -- see `backend/app/orchestration/llm_client.py`)
- Optional: Docker, only for the `pgweb` DB browser in `backend/docker-compose.yml`

## 1. Backend

```sh
cd backend
```

Create `.env`:

```
AICREDITS_API_KEY=your_key_here
DATABASE_URL=postgresql://user:password@host:port/dbname?sslmode=require
```

Install deps, create the schema, and seed the interim dev user (there's no auth yet):

```sh
uv sync
uv run alembic upgrade head              # creates the tables and the pgvector extension
uv run python -m scripts.seed_dev_user   # the frontend's USER_ID is this user's fixed UUID
```

The database must be reachable when the app starts -- it opens its connections at import
time. Then start the API:

```sh
uv run uvicorn app.main:app --reload     # leave running
```

Verify: `curl http://localhost:8000/health` -> `{"status":"ok"}`.

## 2. Frontend

```sh
cd frontend
npm install     # or pnpm install
npm run dev     # or pnpm dev
```

Opens on `http://localhost:5173`, talks to `http://localhost:8000` by default
(`VITE_API_URL` env var to change it). If you change the frontend's origin/port, add it
to the CORS allowlist in `backend/app/main.py` or every request will be silently
blocked at the browser's preflight.

## 3. Try it

Open `http://localhost:5173` and send a message. To confirm persistence: note the
`?thread=<uuid>` the URL gets after your first message, then reload that exact URL --
the conversation should restore from Postgres.

## Optional: browse the database

```sh
cd backend && docker compose up -d pgweb   # http://localhost:8081, reads DATABASE_URL from .env
docker compose stop                        # when you're done
```

## Repo layout

- `backend/` -- Python backend (FastAPI + LangGraph + SQLAlchemy/Alembic + Postgres). See its
  own `README.md` for backend-only setup detail and the folder structure.
- `frontend/` -- React + TypeScript + Vite chat client.
