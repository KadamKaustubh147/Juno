"""initial schema

Revision ID: 2ce8cec333ac
Revises:
Create Date: 2026-09-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy
from sqlalchemy.dialects import postgresql

revision: str = "2ce8cec333ac"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def _updated_at() -> sa.Column:
    return sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    # gen_random_uuid() is built into core Postgres since v13, no pgcrypto needed.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("CREATE TYPE session_status AS ENUM ('active', 'completed', 'abandoned')")
    op.execute("CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system')")

    op.create_table(
        "users",
        _pk(),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("users_email_idx", "users", ["email"])

    op.create_table(
        "refresh_tokens",
        _pk(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("revoked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("refresh_tokens_user_id_idx", "refresh_tokens", ["user_id"])
    op.create_index("refresh_tokens_family_id_idx", "refresh_tokens", ["family_id"])

    op.create_table(
        "therapy_sessions",
        _pk(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("script_id", sa.String(100), nullable=False),
        sa.Column("current_section", sa.String(100), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("active", "completed", "abandoned", name="session_status", create_type=False),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("therapy_sessions_user_id_idx", "therapy_sessions", ["user_id"])

    op.create_table(
        "messages",
        _pk(),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("user", "assistant", "system", name="message_role", create_type=False),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("section_at_time", sa.String(100), nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["therapy_sessions.id"], ondelete="CASCADE"),
    )
    op.create_index("messages_session_id_idx", "messages", ["session_id"])

    op.create_table(
        "section_transitions",
        _pk(),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("from_section", sa.String(100), nullable=True),
        sa.Column("to_section", sa.String(100), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["therapy_sessions.id"], ondelete="CASCADE"),
    )
    op.create_index("section_transitions_session_id_idx", "section_transitions", ["session_id"])

    op.create_table(
        "memories",
        _pk(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(384), nullable=False),
        sa.Column("novelty", sa.REAL(), nullable=False),
        sa.Column("salience", sa.REAL(), nullable=False),
        sa.Column("prediction_error", sa.REAL(), nullable=False),
        sa.Column("score", sa.REAL(), nullable=False),
        sa.Column(
            "content_tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', content)", persisted=True),
            nullable=True,
        ),
        _created_at(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("memories_user_id_idx", "memories", ["user_id"])
    op.create_index("memories_content_tsv_idx", "memories", ["content_tsv"], postgresql_using="gin")
    op.create_index(
        "memories_embedding_hnsw_idx",
        "memories",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_table("memories")
    op.drop_table("section_transitions")
    op.drop_table("messages")
    op.drop_table("therapy_sessions")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    op.execute("DROP TYPE message_role")
    op.execute("DROP TYPE session_status")
    # The vector extension is left in place on purpose: dropping it is a database-wide
    # change other objects may depend on.
