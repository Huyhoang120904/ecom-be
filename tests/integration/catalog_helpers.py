"""Helpers shared by the product-side API tests.

The tests build on the *seeded* sample catalog (``ao-thun``, ``laptop``, ``dien-thoai``)
rather than recreating it, so they double as proof that the seed is usable. Anything a
test needs that is not in the seed it creates through the admin API.
"""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass, field
from typing import Any

from httpx import AsyncClient, Response
from PIL import Image
from sqlalchemy import text

PRODUCTS = "/api/v1/products"


@dataclass
class Seed:
    """Ids of the seeded catalog, looked up by slug / key / value."""

    categories: dict[str, str] = field(default_factory=dict)
    attributes: dict[str, str] = field(default_factory=dict)
    options: dict[tuple[str, str], str] = field(default_factory=dict)
    brands: dict[str, str] = field(default_factory=dict)

    def option(self, attribute: str, value: str) -> dict[str, str]:
        """A ``{attribute_id, option_id}`` pair for a variant's ``options`` list."""

        return {
            "attribute_id": self.attributes[attribute],
            "option_id": self.options[(attribute, value)],
        }

    def select(self, attribute: str, value: str) -> dict[str, str]:
        """An attribute-value entry for a SELECT attribute."""

        return {
            "attribute_id": self.attributes[attribute],
            "option_id": self.options[(attribute, value)],
        }


async def load_seed(db_session) -> Seed:  # type: ignore[no-untyped-def]
    seed = Seed()
    for slug, ident in await db_session.execute(
        text("SELECT slug, id FROM categories")
    ):
        seed.categories[slug] = str(ident)
    for key, ident in await db_session.execute(text("SELECT key, id FROM attributes")):
        seed.attributes[key] = str(ident)
    rows = await db_session.execute(
        text(
            "SELECT a.key, o.value, o.id FROM attribute_options o "
            "JOIN attributes a ON a.id = o.attribute_id"
        )
    )
    for key, value, ident in rows:
        seed.options[(key, value)] = str(ident)
    for slug, ident in await db_session.execute(text("SELECT slug, id FROM brands")):
        seed.brands[slug] = str(ident)
    return seed


async def create_product(
    client: AsyncClient,
    headers: dict[str, str],
    category_id: str,
    name: str = "Áo Polo Nike",
    **extra: Any,
) -> dict[str, Any]:
    response = await client.post(
        PRODUCTS,
        json={"category_id": category_id, "name": name, **extra},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]  # type: ignore[no-any-return]


async def add_variant(
    client: AsyncClient,
    headers: dict[str, str],
    product_id: str,
    sku_code: str,
    price: int = 300000,
    options: list[dict[str, str]] | None = None,
    **extra: Any,
) -> Response:
    return await client.post(
        f"{PRODUCTS}/{product_id}/variants",
        json={
            "sku_code": sku_code,
            "price": price,
            "options": options or [],
            **extra,
        },
        headers=headers,
    )


async def make_variant(
    client: AsyncClient,
    headers: dict[str, str],
    product_id: str,
    sku_code: str,
    price: int = 300000,
    options: list[dict[str, str]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    response = await add_variant(
        client, headers, product_id, sku_code, price, options, **extra
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]  # type: ignore[no-any-return]


def make_png(width: int = 200, height: int = 100, color: str = "red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


async def upload_image(
    client: AsyncClient,
    headers: dict[str, str],
    product_id: str,
    *,
    data: bytes | None = None,
    variant_id: str | None = None,
    content_type: str = "image/png",
) -> Response:
    form = {"variant_id": variant_id} if variant_id is not None else {}
    return await client.post(
        f"{PRODUCTS}/{product_id}/images",
        files={"file": ("photo.png", data or make_png(), content_type)},
        data=form,
        headers=headers,
    )


async def polo(
    client: AsyncClient,
    headers: dict[str, str],
    seed: Seed,
    *,
    publish: bool = False,
) -> dict[str, Any]:
    """A T-shirt with its six Color x Size variants, optionally published."""

    product = await create_product(client, headers, seed.categories["ao-thun"])
    for color in ("Black", "White"):
        for size in ("S", "M", "L"):
            price = 320000 if size == "L" else 300000
            await make_variant(
                client,
                headers,
                product["id"],
                f"POLO-{color.upper()}-{size}",
                price,
                [seed.option("color", color), seed.option("size", size)],
                stock=10,
            )
    if publish:
        response = await client.post(
            f"{PRODUCTS}/{product['id']}/publish", headers=headers
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]  # type: ignore[no-any-return]
    return product


def new_id() -> str:
    return str(uuid.uuid4())
