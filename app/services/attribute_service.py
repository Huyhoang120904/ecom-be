"""Use cases for attributes and their options, and for a category's configuration.

``key`` and ``data_type`` never change after creation, so there is no update path for
them. "In use" means a product value or a variant option references the attribute or
option, soft-deleted products included (see the plan's *Catalog invariants*); it is
decided by an existence query, not by catching a foreign-key error, so the client gets
a specific ``409``.
"""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.catalog import AttributeDataType
from app.errors.catalog import (
    AttributeAttached,
    AttributeDetachLocked,
    AttributeExists,
    AttributeInUse,
    AttributeNotFound,
    CategoryAttributeNotFound,
    CategoryNotFound,
    OptionExists,
    OptionInUse,
    OptionNotFound,
    OptionsRequireSelect,
    VariationFlagLocked,
    VariationRequiresSelect,
)
from app.models.catalog import Attribute, AttributeOption, CategoryAttribute
from app.repositories import (
    attribute_option_repository,
    attribute_repository,
    category_attribute_repository,
    category_repository,
)


class AttributeService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- attributes --------------------------------------------------------------

    async def get_attribute(self, attribute_id: uuid.UUID) -> Attribute:
        attribute = await attribute_repository.get_attribute(
            self._session, attribute_id
        )
        if attribute is None:
            raise AttributeNotFound
        return attribute

    async def attribute_with_options(
        self, attribute_id: uuid.UUID
    ) -> tuple[Attribute, list[AttributeOption]]:
        attribute = await self.get_attribute(attribute_id)
        options = await attribute_option_repository.list_options(
            self._session, attribute_id
        )
        return attribute, options

    async def create_attribute(
        self, *, key: str, name: str, data_type: AttributeDataType
    ) -> Attribute:
        try:
            async with self._session.begin_nested():
                attribute = await attribute_repository.create_attribute(
                    self._session, key=key, name=name, data_type=data_type.value
                )
        except IntegrityError as error:
            raise AttributeExists from error
        await self._session.commit()
        return attribute

    async def rename_attribute(
        self, *, attribute_id: uuid.UUID, name: str
    ) -> Attribute:
        attribute = await self.get_attribute(attribute_id)
        await attribute_repository.rename_attribute(self._session, attribute, name)
        await self._session.commit()
        return attribute

    async def delete_attribute(self, attribute_id: uuid.UUID) -> None:
        await self.get_attribute(attribute_id)
        if await attribute_repository.attribute_is_attached(
            self._session, attribute_id
        ):
            raise AttributeAttached
        if await attribute_repository.attribute_in_use(self._session, attribute_id):
            raise AttributeInUse
        await attribute_repository.delete_attribute(self._session, attribute_id)
        await self._session.commit()

    # -- options -----------------------------------------------------------------

    async def create_option(
        self, *, attribute_id: uuid.UUID, value: str, sort_order: int | None
    ) -> AttributeOption:
        attribute = await self.get_attribute(attribute_id)
        if attribute.data_type != AttributeDataType.SELECT:
            raise OptionsRequireSelect
        if sort_order is None:
            existing = await attribute_option_repository.list_options(
                self._session, attribute_id
            )
            sort_order = len(existing)
        try:
            async with self._session.begin_nested():
                option = await attribute_option_repository.create_option(
                    self._session,
                    attribute_id=attribute_id,
                    value=value,
                    sort_order=sort_order,
                )
        except IntegrityError as error:
            raise OptionExists from error
        await self._session.commit()
        return option

    async def update_option(
        self,
        *,
        attribute_id: uuid.UUID,
        option_id: uuid.UUID,
        changes: dict[str, object],
    ) -> AttributeOption:
        option = await attribute_option_repository.get_option(
            self._session, attribute_id, option_id
        )
        if option is None:
            raise OptionNotFound
        try:
            async with self._session.begin_nested():
                await attribute_option_repository.update_option(
                    self._session, option, changes
                )
        except IntegrityError as error:
            raise OptionExists from error
        await self._session.commit()
        return option

    async def delete_option(
        self, *, attribute_id: uuid.UUID, option_id: uuid.UUID
    ) -> None:
        option = await attribute_option_repository.get_option(
            self._session, attribute_id, option_id
        )
        if option is None:
            raise OptionNotFound
        if await attribute_option_repository.option_in_use(self._session, option_id):
            raise OptionInUse
        await attribute_option_repository.delete_option(self._session, option_id)
        await self._session.commit()


class CategoryAttributeService:
    """Which attributes a category asks for, and the flags on each."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def configuration(
        self, category_id: uuid.UUID
    ) -> list[tuple[CategoryAttribute, Attribute, list[AttributeOption]]]:
        """A category's attributes with their options: what a form is built from."""

        if await category_repository.get_category(self._session, category_id) is None:
            raise CategoryNotFound
        rows = await category_attribute_repository.list_for_category(
            self._session, category_id
        )
        options = await attribute_option_repository.list_options_for_attributes(
            self._session, {attribute.id for _, attribute in rows}
        )
        return [
            (config, attribute, options.get(attribute.id, []))
            for config, attribute in rows
        ]

    async def put_configuration(
        self,
        *,
        category_id: uuid.UUID,
        attribute_id: uuid.UUID,
        values: dict[str, object],
    ) -> tuple[CategoryAttribute, Attribute, list[AttributeOption]]:
        """Attach the attribute or replace its flags. Idempotent."""

        if await category_repository.get_category(self._session, category_id) is None:
            raise CategoryNotFound
        attribute = await attribute_repository.get_attribute(
            self._session, attribute_id
        )
        if attribute is None:
            raise AttributeNotFound

        wants_variation = bool(values["is_variation"])
        if wants_variation and attribute.data_type != AttributeDataType.SELECT:
            raise VariationRequiresSelect

        existing = await category_attribute_repository.get_config(
            self._session, category_id, attribute_id
        )
        if (
            existing is not None
            and existing.is_variation != wants_variation
            and await category_attribute_repository.used_in_category(
                self._session, category_id, attribute_id
            )
        ):
            raise VariationFlagLocked

        config = await category_attribute_repository.upsert_config(
            self._session,
            category_id=category_id,
            attribute_id=attribute_id,
            values=values,
        )
        options = await attribute_option_repository.list_options(
            self._session, attribute_id
        )
        await self._session.commit()
        return config, attribute, options

    async def detach(self, *, category_id: uuid.UUID, attribute_id: uuid.UUID) -> None:
        if await category_repository.get_category(self._session, category_id) is None:
            raise CategoryNotFound
        config = await category_attribute_repository.get_config(
            self._session, category_id, attribute_id
        )
        if config is None:
            raise CategoryAttributeNotFound
        if await category_attribute_repository.used_in_category(
            self._session, category_id, attribute_id
        ):
            raise AttributeDetachLocked
        await category_attribute_repository.delete_config(
            self._session, category_id, attribute_id
        )
        await self._session.commit()
