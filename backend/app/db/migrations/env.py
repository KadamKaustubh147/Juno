from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import SQLALCHEMY_DATABASE_URL
from app.db.base import Base

# Importing the models is what registers their tables on Base.metadata.
import app.features.auth.models  # noqa: F401
import app.features.sessions.models  # noqa: F401
import app.features.users.models  # noqa: F401
import app.memory.episodic.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Tables owned by LangGraph's PostgresSaver (created by checkpointer.setup(), not by us).
# Autogenerate must not see them as "unknown tables to drop".
LANGGRAPH_TABLES = {"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"}


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and reflected and name in LANGGRAPH_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=SQLALCHEMY_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Built directly rather than via config.set_main_option: a URL with a percent-encoded
    # password would be mangled by configparser interpolation.
    connectable = create_engine(SQLALCHEMY_DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
