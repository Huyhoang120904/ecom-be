"""Alembic environment for the settings-driven async engine.

The migration URL comes from the validated application settings, so the same
``DATABASE_URL`` drives the application and its migrations.

``target_metadata`` is the aggregation view ``app.models``, which imports
every ORM model module so they register on the shared declarative ``Base``. That
import is what makes ``alembic revision --autogenerate`` see a new feature's
tables.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.config.settings import get_settings
from app.infrastructure.db.urls import escape_for_configparser
from app.models import metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The single source of truth for both runtime and migration connections.
# `set_main_option` stores the value through configparser, where `%` opens an
# interpolation token, so escape it: a URL-encoded credential such as `p%40ss`
# would otherwise raise `ValueError: invalid interpolation syntax` and abort the
# migration. `get_main_option` interpolates the escape back to this exact DSN.
config.set_main_option(
    "sqlalchemy.url",
    escape_for_configparser(str(get_settings().database_url)),
)

# The named metadata view: it imports the shared declarative Base and every
# module's ORM models, so autogenerate compares against all of them. Add new
# models to `app.models`, not here.
target_metadata = metadata


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
