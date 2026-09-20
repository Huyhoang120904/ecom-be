"""Shared column mixins for ORM models.

Every persisted table in this project carries a uuid primary key and, unless it is
a join table or a code-driven vocabulary, creation and modification timestamps.
Repeating those column definitions per model is how they drift apart, so they are
declared once here and composed into each model.

Which tables take which mixin is a per-table decision and is recorded in
``docs/superpowers/specs/2026-09-13-identity-rbac-tenancy-design.md`` under
*Shared mixins*.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, declarative_mixin, mapped_column


@declarative_mixin
class UUIDPrimaryKeyMixin:
    """A uuid primary key with a Python default and a server default.

    The server default is not redundant. Without it, an insert that does not go
    through the ORM -- a data migration, a ``psql`` session, a future admin script
    -- fails on a not-null primary key instead of generating an id.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )


@declarative_mixin
class TimestampMixin:
    """Timezone-aware creation and modification timestamps.

    Both are timezone-aware on purpose: a naive ``timestamp`` silently discards
    the offset it was written with, which turns an audit trail into a guess.

    ``updated_at`` is ORM-managed through ``onupdate``. That means a hand-written
    ``UPDATE`` in ``psql`` or inside a migration will not touch it, which is worth
    knowing before trusting the column.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


@declarative_mixin
class SoftDeleteMixin:
    """Retirement without destruction: NULL means live, a timestamp means retired.

    Reads filter on ``deleted_at IS NULL``. A unique key that should be reusable
    after retirement gets a partial unique index on the same predicate rather than
    a plain constraint, so a retired row does not hold the key forever.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
