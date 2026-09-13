"""Contract: the shared column mixins.

Every persisted table carries a uuid primary key and, unless it is a join table or
a code-driven vocabulary, timestamps. Repeating those definitions per model is how
they drift, so the mixins are the single place those columns are declared.

The probe models are declared on a *local* declarative base rather than the
application's ``Base``: declaring tables on the shared metadata from a test would
make them visible to Alembic autogenerate and to the aggregation gate in
``test_migration_metadata.py``.
"""

from __future__ import annotations

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase

from ecom_be.infrastructure.db.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


def _datetime_type(table_name: str, column_name: str) -> DateTime:
    """Return the column's type, narrowed, so the timezone flag is readable."""

    column_type = ProbeBase.metadata.tables[table_name].c[column_name].type
    assert isinstance(column_type, DateTime), (
        f"{table_name}.{column_name} is not a DateTime"
    )
    return column_type


class ProbeBase(DeclarativeBase):
    """A throwaway base, so these tables never reach the application metadata."""


class ProbeUUID(UUIDPrimaryKeyMixin, ProbeBase):
    __tablename__ = "probe_uuid"


class ProbeStamps(UUIDPrimaryKeyMixin, TimestampMixin, ProbeBase):
    __tablename__ = "probe_stamps"


class ProbeSoft(UUIDPrimaryKeyMixin, SoftDeleteMixin, ProbeBase):
    __tablename__ = "probe_soft"


def test_uuid_primary_key_has_a_python_and_a_server_default():
    column = ProbeBase.metadata.tables["probe_uuid"].c.id

    assert column.primary_key, "the column must be the primary key"
    assert column.default is not None, (
        "without a Python default an ORM insert has no id"
    )
    assert column.server_default is not None, (
        "without a server default an insert from psql or a data migration fails on "
        "a not-null primary key"
    )


def test_created_at_and_updated_at_are_timezone_aware():
    assert _datetime_type("probe_stamps", "created_at").timezone, (
        "a naive timestamp silently loses the offset it was written with"
    )
    assert _datetime_type("probe_stamps", "updated_at").timezone
    table = ProbeBase.metadata.tables["probe_stamps"]
    assert table.c.created_at.nullable is False
    assert table.c.updated_at.nullable is False


def test_timestamps_have_server_defaults():
    table = ProbeBase.metadata.tables["probe_stamps"]

    assert table.c.created_at.server_default is not None
    assert table.c.updated_at.server_default is not None


def test_updated_at_advances_on_update():
    table = ProbeBase.metadata.tables["probe_stamps"]

    assert table.c.updated_at.onupdate is not None, (
        "without onupdate a modified row keeps its original updated_at"
    )


def test_deleted_at_is_nullable_so_null_can_mean_live():
    column = ProbeBase.metadata.tables["probe_soft"].c.deleted_at

    assert column.nullable is True
    assert column.default is None, "a default would make every new row look deleted"
    assert column.server_default is None


def test_the_mixins_are_composable_in_one_model():
    """A model can take all three, which is what most tables do."""

    class ProbeEverything(
        UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, ProbeBase
    ):
        __tablename__ = "probe_everything"

    table = ProbeBase.metadata.tables["probe_everything"]
    assert set(table.c.keys()) == {"id", "created_at", "updated_at", "deleted_at"}
