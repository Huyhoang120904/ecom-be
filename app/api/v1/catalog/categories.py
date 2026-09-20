"""Categories: the tree for any caller, writes for a catalog manager."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.v1.catalog.common import Caller, CatalogAdmin, Session
from app.schemas.catalog import (
    CategoryCreateRequest,
    CategoryData,
    CategoryTreeNode,
    CategoryUpdateRequest,
)
from app.schemas.common import BaseResponse
from app.services.category_service import CategoryService, CategoryView

read_router = APIRouter(prefix="/api/v1/catalog/categories", tags=["catalog"])
admin_router = APIRouter(
    prefix="/api/v1/admin/catalog/categories", tags=["catalog-admin"]
)


def _data(view: CategoryView) -> CategoryData:
    category = view.category
    return CategoryData(
        id=category.id,
        parent_id=category.parent_id,
        name=category.name,
        slug=category.slug,
        position=category.position,
        is_leaf=view.is_leaf,
    )


@read_router.get("", response_model=BaseResponse[list[CategoryTreeNode]])
async def category_tree(
    _: Caller, session: Session
) -> BaseResponse[list[CategoryTreeNode]]:
    return BaseResponse[list[CategoryTreeNode]](
        status_code=status.HTTP_200_OK, data=await CategoryService(session).tree()
    )


@read_router.get("/{category_id}", response_model=BaseResponse[CategoryData])
async def get_category(
    category_id: uuid.UUID, _: Caller, session: Session
) -> BaseResponse[CategoryData]:
    view = await CategoryService(session).get_category(category_id)
    return BaseResponse[CategoryData](status_code=status.HTTP_200_OK, data=_data(view))


@admin_router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=BaseResponse[CategoryData]
)
async def create_category(
    payload: CategoryCreateRequest, _: CatalogAdmin, session: Session
) -> BaseResponse[CategoryData]:
    view = await CategoryService(session).create_category(
        name=payload.name, parent_id=payload.parent_id, position=payload.position
    )
    return BaseResponse[CategoryData](
        status_code=status.HTTP_201_CREATED, data=_data(view)
    )


@admin_router.patch("/{category_id}", response_model=BaseResponse[CategoryData])
async def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdateRequest,
    _: CatalogAdmin,
    session: Session,
) -> BaseResponse[CategoryData]:
    sent = payload.model_fields_set
    changes: dict[str, object] = {
        field: getattr(payload, field)
        for field in ("name", "position")
        if field in sent and getattr(payload, field) is not None
    }
    reparent = "parent_id" in sent
    if reparent:
        changes["parent_id"] = payload.parent_id
    view = await CategoryService(session).update_category(
        category_id=category_id, changes=changes, reparent=reparent
    )
    return BaseResponse[CategoryData](status_code=status.HTTP_200_OK, data=_data(view))


@admin_router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: uuid.UUID, _: CatalogAdmin, session: Session
) -> None:
    await CategoryService(session).delete_category(category_id)
