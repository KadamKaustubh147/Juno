"""FastAPI application entrypoint.

Run with (from the "backend" directory):
    uvicorn app.main:app --reload

Then POST /auth/register, POST /sessions, and POST /chat (the reply streams back as
Server-Sent Events) -- or browse the interactive docs at http://localhost:8000/docs
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.exceptions import register_exception_handlers
from app.features.auth.router import router as auth_router
from app.features.chat.router import router as chat_router
from app.features.sessions.router import router as sessions_router
from app.features.users.router import router as users_router

# uvicorn only configures its own loggers, so without this the app's INFO logs (the per-node
# timings in graph_builder) are dropped and only WARNING and above reach the console.
logging.basicConfig(level=logging.WARNING, format="%(levelname)s:     %(name)s: %(message)s")
logging.getLogger("app").setLevel(logging.INFO)

app = FastAPI(title="AI Therapist Chatbot")

# The frontend (Vite dev server) runs on a different origin, so without this the
# browser blocks every request at the CORS preflight (OPTIONS) before it even
# reaches this app -- streaming, memory, everything looks "broken" from the
# frontend even though the API itself works fine (curl doesn't send preflights).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(sessions_router)
app.include_router(chat_router)


@app.get("/health")
def health():
    return {"status": "ok"}
