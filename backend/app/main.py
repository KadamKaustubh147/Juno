"""FastAPI application entrypoint.

Run with (from the "backend" directory):
    uvicorn app.main:app --reload

Then POST to http://localhost:8000/chat
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.features.chat.router import router as chat_router
from app.features.sessions.router import router as sessions_router

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

app.include_router(chat_router)
app.include_router(sessions_router)


@app.get("/health")
def health():
    return {"status": "ok"}
