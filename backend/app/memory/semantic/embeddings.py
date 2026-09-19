"""The embedding model, loaded once and reused.

all-MiniLM-L6-v2: 384 dimensions, ~90MB. Quality is okayish -- it's a tiny
model and a bigger one would retrieve better -- but it runs on CPU in
milliseconds and needs no API key, which is the right trade for now. The 384
has to match the VECTOR(384) column in the memories table, so swapping models
later means a migration.

Served through fastembed rather than the sentence-transformers library: same
model, but fastembed runs it via ONNX so it doesn't drag in torch (~800MB).

The model file is downloaded on first use and cached under ~/.cache, so the
first call is slow and every call after is not.
"""

import numpy as np
from fastembed import TextEmbedding

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

_model = None


def get_model() -> TextEmbedding:
    """Return the shared model, loading it on first call.

    Loaded lazily rather than at import time so importing this module (or
    anything that imports it) doesn't pay the model load when it's never
    actually going to embed anything.
    """
    global _model
    if _model is None:
        _model = TextEmbedding(model_name=MODEL_NAME)
    return _model


def embed_many(texts: list[str]) -> list[np.ndarray]:
    """Embed several strings at once.

    fastembed's .embed() hands back a generator rather than an array, so this
    drains it into a list -- callers get plain vectors and don't have to know
    which embedding backend is underneath.
    """
    return list(get_model().embed(texts))


def embed(text: str) -> list[float]:
    """Embed one string into a 384-dim vector (as a plain list, for pgvector)."""
    return embed_many([text])[0].tolist()
