"""Identity, RBAC, and shop tenancy models.

The partial unique indexes and the ``CHECK`` constraints are the parts that carry
real meaning, and they are written explicitly here rather than left to
autogenerate, which does not invent a ``CHECK`` at all.

Which table takes which mixin is a deliberate choice, documented per class.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.constants.identity import (
    BIO_MAX,
    EMAIL_MAX,
    FULL_NAME_MAX,
    JOB_TITLE_MAX,
    MEDIA_KEY_MAX,
    PHONE_MAX_INPUT,
    SHOP_DESCRIPTION_MAX,
    SHOP_NAME_MAX,
    SHOP_WEBSITE_MAX,
)
from app.infrastructure.db.base import Base
from app.infrastructure.db.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
ROLE_KEY_PATTERN = r"^[a-z][a-z0-9_]*$"
PERMISSION_KEY_PATTERN = r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$"


class User(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """An account, with its profile.

    There is no ``is_active`` column. "Can this account sign in" is
    ``deleted_at IS NULL AND deactivated_at IS NULL``: one fact with two causes,
    each recorded when it happened. A boolean alongside the two timestamps would be
    a third source of truth for the same question.

    Email uniqueness is partial on ``deleted_at IS NULL``, so retiring an account
    releases its address while deactivating one does not: a deactivated seller may
    return, and nobody else may claim their address in the meantime.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"char_length(email) <= {EMAIL_MAX}", name="users_email_len"),
        CheckConstraint("email = lower(email)", name="users_email_lower"),
        CheckConstraint(
            f"char_length(btrim(full_name)) between 1 and {FULL_NAME_MAX}",
            name="users_full_name_ck",
        ),
        CheckConstraint(
            f"bio is null or char_length(bio) <= {BIO_MAX}", name="users_bio_ck"
        ),
        CheckConstraint(
            f"phone is null or char_length(phone) <= {PHONE_MAX_INPUT}",
            name="users_phone_ck",
        ),
        CheckConstraint(
            f"job_title is null or char_length(job_title) <= {JOB_TITLE_MAX}",
            name="users_job_title_ck",
        ),
        CheckConstraint(
            f"avatar_key is null or char_length(avatar_key) <= {MEDIA_KEY_MAX}",
            name="users_avatar_key_ck",
        ),
        Index(
            "users_email_live",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(FULL_NAME_MAX), nullable=False)
    bio: Mapped[str | None] = mapped_column(String(BIO_MAX), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(PHONE_MAX_INPUT), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(JOB_TITLE_MAX), nullable=True)
    avatar_key: Mapped[str | None] = mapped_column(String(MEDIA_KEY_MAX), nullable=True)
    avatar_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def is_live(self) -> bool:
        """Whether this account may sign in."""

        return self.deleted_at is None and self.deactivated_at is None


class Shop(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A seller's workspace.

    Both ``is_active`` and ``deleted_at`` exist here, unlike on ``users``, because
    they have different authors: ``deleted_at`` is the seller deleting their own
    shop, while ``is_active`` is an operator suspending one. A shop is usable only
    when both are clear.

    ``slug`` is generated once from the name and never changes on rename. A shop's
    public URL is not something a settings form should silently rewrite.
    """

    __tablename__ = "shops"
    __table_args__ = (
        CheckConstraint(
            f"char_length(btrim(name)) between 2 and {SHOP_NAME_MAX}",
            name="shops_name_ck",
        ),
        CheckConstraint(f"slug ~ '{SLUG_PATTERN}'", name="shops_slug_ck"),
        CheckConstraint(
            f"char_length(slug) between 1 and {SHOP_NAME_MAX}", name="shops_slug_len"
        ),
        CheckConstraint(
            "description is null or "
            f"char_length(description) <= {SHOP_DESCRIPTION_MAX}",
            name="shops_description_ck",
        ),
        CheckConstraint(
            f"contact_email is null or char_length(contact_email) <= {EMAIL_MAX}",
            name="shops_contact_email_ck",
        ),
        CheckConstraint(
            f"contact_phone is null or char_length(contact_phone) <= {PHONE_MAX_INPUT}",
            name="shops_contact_phone_ck",
        ),
        CheckConstraint(
            f"website is null or (char_length(website) <= {SHOP_WEBSITE_MAX} "
            "and website ~* '^https?://')",
            name="shops_website_ck",
        ),
        CheckConstraint(
            f"background_key is null or char_length(background_key) <= {MEDIA_KEY_MAX}",
            name="shops_background_key_ck",
        ),
        Index(
            "shops_slug_live",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(SHOP_NAME_MAX), nullable=False)
    slug: Mapped[str] = mapped_column(String(SHOP_NAME_MAX), nullable=False)
    description: Mapped[str | None] = mapped_column(
        String(SHOP_DESCRIPTION_MAX), nullable=True
    )
    contact_email: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(
        String(PHONE_MAX_INPUT), nullable=True
    )
    website: Mapped[str | None] = mapped_column(String(SHOP_WEBSITE_MAX), nullable=True)
    background_key: Mapped[str | None] = mapped_column(
        String(MEDIA_KEY_MAX), nullable=True
    )
    background_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class Role(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A named permission set, either a system role or a shop's own.

    ``shop_id IS NULL`` means a system role. Uniqueness has to be two *partial*
    indexes rather than constraints, because Postgres treats ``NULL`` as distinct in
    a plain ``UNIQUE``, so a plain unique on ``key`` would happily accept two
    ``owner`` system roles.

    The soft-delete ``CHECK`` closes a subtle trap: the partial unique index still
    holds a soft-deleted system role's key, so that role could never be recreated.
    The constraint makes the unrecoverable state unrepresentable instead of merely
    discouraged.
    """

    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint(f"key ~ '{ROLE_KEY_PATTERN}'", name="roles_key_ck"),
        CheckConstraint(
            "char_length(key) between 2 and 64",
            name="roles_key_len",
        ),
        CheckConstraint("char_length(btrim(name)) >= 1", name="roles_name_ck"),
        CheckConstraint(
            "deleted_at IS NULL OR shop_id IS NOT NULL",
            name="roles_system_role_not_deleted",
        ),
        Index(
            "roles_system_key_uniq",
            "key",
            unique=True,
            postgresql_where=text("shop_id IS NULL"),
        ),
        Index(
            "roles_shop_key_uniq",
            "shop_id",
            "key",
            unique=True,
            postgresql_where=text("shop_id IS NOT NULL"),
        ),
    )

    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    shop_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=True,
    )


class Permission(UUIDPrimaryKeyMixin, Base):
    """A code-driven capability.

    No timestamps and no soft delete: a row here is a fact about the software, owned
    by seed data, and nothing about a seller. ``updated_at`` would never move.
    """

    __tablename__ = "permissions"
    __table_args__ = (
        CheckConstraint(f"key ~ '{PERMISSION_KEY_PATTERN}'", name="permissions_key_ck"),
        CheckConstraint(
            "char_length(key) between 3 and 64", name="permissions_key_len"
        ),
        CheckConstraint(
            "char_length(description) between 1 and 200", name="permissions_desc_ck"
        ),
    )

    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A user's role in one shop: the join that replaces a role column on ``User``.

    A user belongs to many shops, so this is the only shape that can express "owner
    here, viewer there".
    """

    __tablename__ = "memberships"
    __table_args__ = (
        Index(
            "memberships_user_shop_live",
            "user_id",
            "shop_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
    )


class RolePermission(Base):
    """The role-to-permission join.

    A composite primary key and no lifecycle: there is nothing to update and nothing
    to soft delete.
    """

    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    """One issued refresh token, stored only as a digest.

    Session state, not business data: revocation is a state (``revoked_at``), not a
    deletion, and a soft delete here would be a second way to say the same thing.
    Only ``created_at`` is kept, because nothing updates this row except revocation.

    The raw token is never stored, so a database read cannot produce a usable
    session.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("refresh_tokens_user_idx", "user_id"),
        Index("refresh_tokens_family_idx", "family_id"),
        Index("refresh_tokens_expires_idx", "expires_at"),
        UniqueConstraint("token_hash", name="refresh_tokens_hash_uniq"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    active_shop_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
