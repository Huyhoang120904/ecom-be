"""Shared dependencies and response mappers for the catalog routers.

``CatalogAdmin`` is the temporary write guard: a permission inside a shop, standing in
for a platform-admin check. See the ``catalog manage permission`` migration and the
plan's *Next phase* for why it exists and how it is to be replaced.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_application_db_session,
    get_current_principal,
    require_permissions,
)
from app.api.principal import Principal
from app.constants.catalog import CATALOG_MANAGE, AttributeDataType
from app.models.catalog import Attribute, AttributeOption, Brand, CategoryAttribute
from app.schemas.catalog import (
    AttributeData,
    BrandData,
    CategoryAttributeData,
    OptionData,
)

# Any authenticated caller: a seller needs the catalog to build a product form.
Caller = Annotated[Principal, Depends(get_current_principal)]

# The catalog is written only by a holder of ``catalog:manage``.
CatalogAdmin = Annotated[Principal, Depends(require_permissions(CATALOG_MANAGE))]

Session = Annotated[AsyncSession, Depends(get_application_db_session)]


def option_data(option: AttributeOption) -> OptionData:
    return OptionData(id=option.id, value=option.value, sort_order=option.sort_order)


def brand_data(brand: Brand) -> BrandData:
    return BrandData(id=brand.id, name=brand.name, slug=brand.slug)


def attribute_data(
    attribute: Attribute, options: list[AttributeOption]
) -> AttributeData:
    return AttributeData(
        id=attribute.id,
        key=attribute.key,
        name=attribute.name,
        data_type=AttributeDataType(attribute.data_type),
        options=[option_data(option) for option in options],
    )


def category_attribute_data(
    config: CategoryAttribute, attribute: Attribute, options: list[AttributeOption]
) -> CategoryAttributeData:
    return CategoryAttributeData(
        id=attribute.id,
        key=attribute.key,
        name=attribute.name,
        type=AttributeDataType(attribute.data_type),
        required=config.required,
        filterable=config.filterable,
        searchable=config.searchable,
        is_variation=config.is_variation,
        position=config.position,
        options=[option_data(option) for option in options],
    )
