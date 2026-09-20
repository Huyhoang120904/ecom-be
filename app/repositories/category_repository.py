"""Every statement the catalog layer runs against ``categories``.

The two lock modes exist for one invariant: a product may only sit in a leaf. Adding a
child locks the parent row ``FOR UPDATE``; creating a product locks its category row
``FOR SHARE``. The two therefore serialise, and "has children" and "has products" can
never both become true.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, exists, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Category
from app.models.product import Product
from app.utils.catalog import slug_with_suffix, slugify


async def get_category(
    session: AsyncSession, category_id: uuid.UUID, *, lock: str | None = None
) -> Category | None:
    """Fetch a category; ``lock`` is ``"update"`` (exclusive) or ``"share"``."""

    statement = select(Category).where(Category.id == category_id)
    if lock == "update":
        statement = statement.with_for_update()
    elif lock == "share":
        statement = statement.with_for_update(read=True)
    return (await session.scalars(statement)).first()


async def list_categories(session: AsyncSession) -> list[Category]:
    statement = select(Category).order_by(Category.position, Category.name)
    return list((await session.scalars(statement)).all())


async def create_category(
    session: AsyncSession, *, name: str, parent_id: uuid.UUID | None, position: int
) -> Category:
    base = slugify(name)
    candidate = base
    suffix = 1
    while (
        await session.scalar(select(Category.id).where(Category.slug == candidate))
    ) is not None:
        suffix += 1
        candidate = slug_with_suffix(base, suffix)

    category = Category(
        name=name, slug=candidate, parent_id=parent_id, position=position
    )
    session.add(category)
    await session.flush()
    return category


async def update_category(
    session: AsyncSession, category: Category, changes: dict[str, object]
) -> Category:
    """Apply changes. ``slug`` is never among them."""

    for field, value in changes.items():
        setattr(category, field, value)
    await session.flush()
    return category


async def delete_category(session: AsyncSession, category_id: uuid.UUID) -> None:
    await session.execute(delete(Category).where(Category.id == category_id))


async def has_children(session: AsyncSession, category_id: uuid.UUID) -> bool:
    return bool(
        await session.scalar(select(exists().where(Category.parent_id == category_id)))
    )


async def has_products(session: AsyncSession, category_id: uuid.UUID) -> bool:
    """Any product row, soft deleted included: the foreign key sees them too."""

    return bool(
        await session.scalar(select(exists().where(Product.category_id == category_id)))
    )


async def ancestor_chain(
    session: AsyncSession, category_id: uuid.UUID
) -> list[uuid.UUID]:
    """The category itself, then its parent, and so on up to the root."""

    chain = (
        select(Category.id, Category.parent_id, literal(0).label("depth"))
        .where(Category.id == category_id)
        .cte("chain", recursive=True)
    )
    chain = chain.union_all(
        select(Category.id, Category.parent_id, chain.c.depth + 1).join(
            chain, Category.id == chain.c.parent_id
        )
    )
    rows = await session.execute(select(chain.c.id).order_by(chain.c.depth))
    return [row[0] for row in rows]


async def subtree_height(session: AsyncSession, category_id: uuid.UUID) -> int:
    """How many levels lie below a category (0 for a leaf)."""

    tree = (
        select(Category.id, literal(0).label("depth"))
        .where(Category.id == category_id)
        .cte("tree", recursive=True)
    )
    tree = tree.union_all(
        select(Category.id, tree.c.depth + 1).join(
            tree, Category.parent_id == tree.c.id
        )
    )
    height = await session.scalar(select(func.max(tree.c.depth)))
    return int(height or 0)
