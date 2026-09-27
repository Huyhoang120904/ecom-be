"""A category's attribute configuration.

The read route is what a client builds a product form from: it needs no knowledge of
what any category's attributes are.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.v1.catalog.common import (
    Caller,
    CatalogAdmin,
    Session,
    category_attribute_data,
)
from app.schemas.catalog import CategoryAttributeData, CategoryAttributeRequest
from app.schemas.common import BaseResponse
from app.services.attribute_service import CategoryAttributeService

read_router = APIRouter(prefix="/api/v1/catalog/categories", tags=["catalog"])
admin_router = APIRouter(
    prefix="/api/v1/admin/catalog/categories", tags=["catalog-admin"]
)


@read_router.get(
    "/{category_id}/attributes",
    response_model=BaseResponse[list[CategoryAttributeData]],
)
async def category_attributes(
    category_id: uuid.UUID, _: Caller, session: Session
) -> BaseResponse[list[CategoryAttributeData]]:
    rows = await CategoryAttributeService(session).configuration(category_id)
    return BaseResponse[list[CategoryAttributeData]](
        status_code=status.HTTP_200_OK,
        data=[category_attribute_data(*row) for row in rows],
    )


@admin_router.put(
    "/{category_id}/attributes/{attribute_id}",
    response_model=BaseResponse[CategoryAttributeData],
)
async def put_category_attribute(
    category_id: uuid.UUID,
    attribute_id: uuid.UUID,
    payload: CategoryAttributeRequest,
    _: CatalogAdmin,
    session: Session,
) -> BaseResponse[CategoryAttributeData]:
    config, attribute, options = await CategoryAttributeService(
        session
    ).put_configuration(
        category_id=category_id,
        attribute_id=attribute_id,
        values=payload.model_dump(),
    )
    return BaseResponse[CategoryAttributeData](
        status_code=status.HTTP_200_OK,
        data=category_attribute_data(config, attribute, options),
    )


@admin_router.delete(
    "/{category_id}/attributes/{attribute_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def detach_category_attribute(
    category_id: uuid.UUID, attribute_id: uuid.UUID, _: CatalogAdmin, session: Session
) -> None:
    await CategoryAttributeService(session).detach(
        category_id=category_id, attribute_id=attribute_id
    )
