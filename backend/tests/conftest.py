import os

# app.config reads these at import time. Real values (from .env) win; these only keep a checkout
# without a .env importable. Nothing in the suite connects to a database or an LLM.
os.environ.setdefault("DATABASE_URL", "postgresql://user:password@127.0.0.1:1/unused")
os.environ.setdefault("AICREDITS_API_KEY", "unused")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret")
