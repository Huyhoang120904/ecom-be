"""Use cases for the category tree.

The tree's two structural rules are the ones a product depends on: it never contains a
cycle, and a category that holds products is a leaf. Both are enforced here, and the
second is made race-free by locking the parent row (see ``category_repository``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.catalog import CATEGORY_MAX_DEPTH
from app.errors.catalog import (
    CategoryCycle,
    CategoryHasChildren,
    CategoryHasProducts,
    CategoryNotFound,
    CategoryTooDeep,
)
from app.models.catalog import Category
from app.repositories import category_repository
from app.schemas.catalog import CategoryTreeNode
from app.utils.catalog import ancestors_contain


@dataclass(frozen=True, slots=True)
class CategoryView:
    category: Category
    is_leaf: bool


class CategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- reads -------------------------------------------------------------------

    async def get_category(self, category_id: uuid.UUID) -> CategoryView:
        category = await category_repository.get_category(self._session, category_id)
        if category is None:
            raise CategoryNotFound
        is_leaf = not await category_repository.has_children(self._session, category_id)
        return CategoryView(category, is_leaf)

    async def tree(self) -> list[CategoryTreeNode]:
        """The whole tree, nested, built from one query."""

        categories = await category_repository.list_categories(self._session)
        children: dict[uuid.UUID | None, list[Category]] = {}
        for category in categories:
            children.setdefault(category.parent_id, []).append(category)

        def build(category: Category) -> CategoryTreeNode:
            kids = children.get(category.id, [])
            return CategoryTreeNode(
                id=category.id,
                name=category.name,
                slug=category.slug,
                position=category.position,
                is_leaf=not kids,
                children=[build(kid) for kid in kids],
            )

        return [build(root) for root in children.get(None, [])]

    # -- writes ------------------------------------------------------------------

    async def create_category(
        self, *, name: str, parent_id: uuid.UUID | None, position: int
    ) -> CategoryView:
        if parent_id is not None:
            await self._check_can_hold_child(parent_id, added_height=0)
        category = await category_repository.create_category(
            self._session, name=name, parent_id=parent_id, position=position
        )
        await self._session.commit()
        return CategoryView(category, True)

    async def update_category(
        self,
        *,
        category_id: uuid.UUID,
        changes: dict[str, object],
        reparent: bool,
    ) -> CategoryView:
        """Rename, reposition, or move a category.

        ``reparent`` says the request named ``parent_id`` (possibly as ``None``, which
        moves the category to the root), because "absent" and "null" mean different
        things.
        """

        category = await category_repository.get_category(
            self._session, category_id, lock="update"
        )
        if category is None:
            raise CategoryNotFound

        if reparent:
            new_parent = changes.get("parent_id")
            if new_parent is not None:
                assert isinstance(new_parent, uuid.UUID)
                await self._check_can_move_under(category, new_parent)
        await category_repository.update_category(self._session, category, changes)
        is_leaf = not await category_repository.has_children(self._session, category_id)
        await self._session.commit()
        return CategoryView(category, is_leaf)

    async def delete_category(self, category_id: uuid.UUID) -> None:
        category = await category_repository.get_category(
            self._session, category_id, lock="update"
        )
        if category is None:
            raise CategoryNotFound
        if await category_repository.has_children(self._session, category_id):
            raise CategoryHasChildren
        if await category_repository.has_products(self._session, category_id):
            raise CategoryHasProducts
        await category_repository.delete_category(self._session, category_id)
        await self._session.commit()

    # -- rules -------------------------------------------------------------------

    async def _check_can_hold_child(
        self, parent_id: uuid.UUID, *, added_height: int
    ) -> list[uuid.UUID]:
        """Lock the parent and check it may take a child; returns its ancestor chain.

        The lock is what serialises this against a product being created in the same
        category (which takes ``FOR SHARE``), so the parent cannot gain a child and a
        product at the same moment.
        """

        parent = await category_repository.get_category(
            self._session, parent_id, lock="update"
        )
        if parent is None:
            raise CategoryNotFound
        if await category_repository.has_products(self._session, parent_id):
            raise CategoryHasProducts
        chain = await category_repository.ancestor_chain(self._session, parent_id)
        # ``chain`` includes the parent itself, so its length is the parent's depth.
        if len(chain) + 1 + added_height > CATEGORY_MAX_DEPTH:
            raise CategoryTooDeep
        return chain

    async def _check_can_move_under(
        self, category: Category, new_parent_id: uuid.UUID
    ) -> None:
        height = await category_repository.subtree_height(self._session, category.id)
        chain = await self._check_can_hold_child(new_parent_id, added_height=height)
        if ancestors_contain(chain, category.id):
            raise CategoryCycle
