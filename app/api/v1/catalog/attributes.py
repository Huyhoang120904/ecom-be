"""Attributes and their options: read for any caller, writes for a catalog manager."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.v1.catalog.common import (
    Caller,
    CatalogAdmin,
    Session,
    attribute_data,
    option_data,
)
from app.schemas.catalog import (
    AttributeCreateRequest,
    AttributeData,
    AttributeUpdateRequest,
    OptionCreateRequest,
    OptionData,
    OptionUpdateRequest,
)
from app.schemas.common import BaseResponse
from app.services.attribute_service import AttributeService

read_router = APIRouter(prefix="/api/v1/catalog/attributes", tags=["catalog"])
admin_router = APIRouter(
    prefix="/api/v1/admin/catalog/attributes", tags=["catalog-admin"]
)


@read_router.get("/{attribute_id}", response_model=BaseResponse[AttributeData])
async def get_attribute(
    attribute_id: uuid.UUID, _: Caller, session: Session
) -> BaseResponse[AttributeData]:
    attribute, options = await AttributeService(session).attribute_with_options(
        attribute_id
    )
    return BaseResponse[AttributeData](
        status_code=status.HTTP_200_OK, data=attribute_data(attribute, options)
    )


@admin_router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=BaseResponse[AttributeData]
)
async def create_attribute(
    payload: AttributeCreateRequest, _: CatalogAdmin, session: Session
) -> BaseResponse[AttributeData]:
    attribute = await AttributeService(session).create_attribute(
        key=payload.key, name=payload.name, data_type=payload.data_type
    )
    return BaseResponse[AttributeData](
        status_code=status.HTTP_201_CREATED, data=attribute_data(attribute, [])
    )


@admin_router.patch("/{attribute_id}", response_model=BaseResponse[AttributeData])
async def rename_attribute(
    attribute_id: uuid.UUID,
    payload: AttributeUpdateRequest,
    _: CatalogAdmin,
    session: Session,
) -> BaseResponse[AttributeData]:
    service = AttributeService(session)
    await service.rename_attribute(attribute_id=attribute_id, name=payload.name)
    attribute, options = await service.attribute_with_options(attribute_id)
    return BaseResponse[AttributeData](
        status_code=status.HTTP_200_OK, data=attribute_data(attribute, options)
    )


@admin_router.delete("/{attribute_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attribute(
    attribute_id: uuid.UUID, _: CatalogAdmin, session: Session
) -> None:
    await AttributeService(session).delete_attribute(attribute_id)


@admin_router.post(
    "/{attribute_id}/options",
    status_code=status.HTTP_201_CREATED,
    response_model=BaseResponse[OptionData],
)
async def create_option(
    attribute_id: uuid.UUID,
    payload: OptionCreateRequest,
    _: CatalogAdmin,
    session: Session,
) -> BaseResponse[OptionData]:
    option = await AttributeService(session).create_option(
        attribute_id=attribute_id, value=payload.value, sort_order=payload.sort_order
    )
    return BaseResponse[OptionData](
        status_code=status.HTTP_201_CREATED, data=option_data(option)
    )


@admin_router.patch(
    "/{attribute_id}/options/{option_id}", response_model=BaseResponse[OptionData]
)
async def update_option(
    attribute_id: uuid.UUID,
    option_id: uuid.UUID,
    payload: OptionUpdateRequest,
    _: CatalogAdmin,
    session: Session,
) -> BaseResponse[OptionData]:
    changes: dict[str, object] = {
        field: getattr(payload, field)
        for field in ("value", "sort_order")
        if getattr(payload, field) is not None
    }
    option = await AttributeService(session).update_option(
        attribute_id=attribute_id, option_id=option_id, changes=changes
    )
    return BaseResponse[OptionData](
        status_code=status.HTTP_200_OK, data=option_data(option)
    )


@admin_router.delete(
    "/{attribute_id}/options/{option_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_option(
    attribute_id: uuid.UUID, option_id: uuid.UUID, _: CatalogAdmin, session: Session
) -> None:
    await AttributeService(session).delete_option(
        attribute_id=attribute_id, option_id=option_id
    )
