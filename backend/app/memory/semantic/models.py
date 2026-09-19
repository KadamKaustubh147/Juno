import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import REAL, Computed, ForeignKey, Index, Text, Uuid
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

# Must match app/memory/semantic/embeddings.py's EMBEDDING_DIM -- swapping the model
# means a migration.
EMBEDDING_DIM = 384


class Memory(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "memories"
    __table_args__ = (
        Index("memories_user_id_idx", "user_id"),
        # L1 lexical retrieval (search_lexical).
        Index("memories_content_tsv_idx", "content_tsv", postgresql_using="gin"),
        # L2 dense retrieval (search_dense): cosine distance, matching the `<=>` queries.
        Index(
            "memories_embedding_hnsw_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    # 'user' | 'assistant' -- plain text, not an enum.
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    novelty: Mapped[float] = mapped_column(REAL)
    salience: Mapped[float] = mapped_column(REAL)
    prediction_error: Mapped[float] = mapped_column(REAL)
    score: Mapped[float] = mapped_column(REAL)
    content_tsv = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True)
    )
