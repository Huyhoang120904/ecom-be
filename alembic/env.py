"""Alembic environment for the settings-driven async engine.

The migration URL comes from the validated application settings, so the same
``DATABASE_URL`` drives the application and its migrations. Only the shared
declarative ``Base.metadata`` is imported: this scaffold has no persisted
business entity yet, and ``alembic upgrade head`` is expected to succeed with an
empty migration history.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from ecom_be.core.config import get_settings
from ecom_be.infrastructure.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The single source of truth for both runtime and migration connections.
config.set_main_option("sqlalchemy.url", str(get_settings().database_url))

# Import only the shared declarative base. Business modules add their models by
# importing them so they register on this same metadata object.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode against a URL, without a DBAPI."""

    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode over the async engine."""

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
