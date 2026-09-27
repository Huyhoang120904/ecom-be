"""Pure helpers for the catalog and product layers.

Deterministic, no I/O, no session: everything here can be tested with plain values.
The publish rule lives here (``published_gaps``) so the one function that decides "may
this product be active" is shared by ``publish`` and by every mutation of an active
product, and cannot drift between them.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.constants.catalog import (
    CATALOG_SLUG_BASE_MAX,
    CATALOG_SLUG_FALLBACK,
    CATALOG_SLUG_MAX,
    VALUE_NUMBER_ABS_MAX,
    VALUE_TEXT_MAX,
    AttributeDataType,
    VariantStatus,
)

_NON_SLUG = re.compile(r"[^a-z0-9]+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def normalize_text(
    value: str, *, field_name: str, minimum: int, maximum: int, multiline: bool = False
) -> str:
    """NFC-fold and strip a text field, then bound it.

    Control characters are rejected (a newline is allowed only when ``multiline``), for
    the same reason identity rejects them in a name: text that reaches a renderer must
    not carry layout.
    """

    normalized = unicodedata.normalize("NFC", value).strip()
    body = normalized.replace("\n", "").replace("\r", "") if multiline else normalized
    if _CONTROL.search(body):
        raise ValueError(f"{field_name} contains control characters")
    if not multiline and ("\n" in normalized or "\r" in normalized):
        raise ValueError(f"{field_name} must be a single line")
    if not minimum <= len(normalized) <= maximum:
        raise ValueError(f"{field_name} length is out of range")
    return normalized


def slugify(value: str) -> str:
    """A URL-safe slug: NFKD, ascii fold, lowercase, hyphen-separated."""

    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii").lower()
    slug = _NON_SLUG.sub("-", ascii_only).strip("-")
    if not slug:
        return CATALOG_SLUG_FALLBACK
    return slug[:CATALOG_SLUG_BASE_MAX].strip("-") or CATALOG_SLUG_FALLBACK


def slug_with_suffix(base: str, suffix: int) -> str:
    """Append a numeric collision suffix, staying inside the column bound."""

    text = str(suffix)
    trimmed = base[: CATALOG_SLUG_MAX - len(text) - 1].strip("-")
    return f"{trimmed or CATALOG_SLUG_FALLBACK}-{text}"


def option_key(pairs: Iterable[tuple[uuid.UUID, uuid.UUID]]) -> str:
    """The canonical text of a variant's option combination.

    ``attribute_id:option_id`` pairs sorted by attribute and joined with ``|``; the
    empty string for a variant with no options. Order-independent by construction, so
    two requests listing the same options in a different order produce the same key,
    and a partial unique index over ``(product_id, option_key)`` can be the arbiter of
    "this combination already exists".
    """

    return "|".join(
        f"{attribute}:{option}" for attribute, option in sorted(pairs, key=_pair_order)
    )


def _pair_order(pair: tuple[uuid.UUID, uuid.UUID]) -> tuple[str, str]:
    return (str(pair[0]), str(pair[1]))


@dataclass(frozen=True, slots=True)
class AttributeValueInput:
    """One attribute value as a client sent it, before it is type-checked."""

    attribute_id: uuid.UUID
    option_id: uuid.UUID | None = None
    value_text: str | None = None
    value_number: Decimal | None = None


def check_value_matches_type(
    data_type: str, value: AttributeValueInput, *, valid_option_ids: set[uuid.UUID]
) -> str | None:
    """Return why ``value`` is wrong for ``data_type``, or ``None`` when it is fine.

    Exactly one value field is set and it is the one the type asks for. A ``SELECT``
    option must be one of the attribute's own options. The reason is a fixed token for
    logging and tests; it is never returned to a client.
    """

    given = [
        name
        for name, present in (
            ("option_id", value.option_id is not None),
            ("value_text", value.value_text is not None),
            ("value_number", value.value_number is not None),
        )
        if present
    ]
    expected = {
        AttributeDataType.SELECT: "option_id",
        AttributeDataType.TEXT: "value_text",
        AttributeDataType.NUMBER: "value_number",
    }.get(AttributeDataType(data_type))
    if given != [expected]:
        return "wrong_value_field"
    if value.option_id is not None and value.option_id not in valid_option_ids:
        return "option_not_of_attribute"
    if value.value_text is not None and not (
        value.value_text.strip() and len(value.value_text) <= VALUE_TEXT_MAX
    ):
        return "text_out_of_range"
    if value.value_number is not None:
        try:
            magnitude = abs(Decimal(value.value_number))
        except InvalidOperation:
            return "number_invalid"
        if not magnitude.is_finite() or magnitude > VALUE_NUMBER_ABS_MAX:
            return "number_out_of_range"
    return None


def ancestors_contain(chain: Iterable[uuid.UUID], candidate: uuid.UUID) -> bool:
    """Whether ``candidate`` appears in ``chain`` (a node's ancestors, nearest first).

    A category may not be moved under itself or any descendant. Walking up from the
    *proposed parent*: if the category being moved is in that chain, the move would
    close a loop.
    """

    return any(node == candidate for node in chain)


def reorder(
    ids: Sequence[uuid.UUID], moving: uuid.UUID, target: int
) -> list[uuid.UUID]:
    """Move ``moving`` to index ``target`` in ``ids``, keeping the others in order.

    The result is a permutation of ``ids``; positions are then ``0..n-1`` again. Raises
    ``ValueError`` when ``moving`` is absent or ``target`` is outside ``[0, n-1]``.
    """

    if moving not in ids or not 0 <= target < len(ids):
        raise ValueError("position out of range")
    remaining = [item for item in ids if item != moving]
    remaining.insert(target, moving)
    return remaining


@dataclass(frozen=True, slots=True)
class CategoryAttributeRule:
    """One row of a category's attribute configuration, as the publish rule needs it."""

    attribute_id: uuid.UUID
    name: str
    required: bool
    is_variation: bool


@dataclass(frozen=True, slots=True)
class VariantShape:
    """A live variant reduced to what the publish rule looks at."""

    status: str
    attribute_ids: frozenset[uuid.UUID]


@dataclass(frozen=True, slots=True)
class Gaps:
    """What stops a product from being active; empty means it may be."""

    missing: list[dict[str, str]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.missing and not self.reasons


def published_gaps(
    *,
    rules: Sequence[CategoryAttributeRule],
    value_attribute_ids: set[uuid.UUID],
    variants: Sequence[VariantShape],
) -> Gaps:
    """Everything an active product must satisfy that it currently does not.

    1. Every ``required`` attribute that is *not* a variation has a product value.
    2. Every ``required`` variation attribute is an option of **every** live variant
       (an inactive variant counts: it can be switched back on).
    3. At least one live variant is ``active``.
    4. All live variants use the same set of variation attributes.

    Returned as data, not raised, so callers can report exactly what is missing.
    """

    missing: list[dict[str, str]] = []
    reasons: list[str] = []

    for rule in rules:
        if not rule.required:
            continue
        if not rule.is_variation:
            if rule.attribute_id not in value_attribute_ids:
                missing.append(
                    {
                        "attribute_id": str(rule.attribute_id),
                        "name": rule.name,
                        "where": "product",
                    }
                )
        elif any(
            rule.attribute_id not in variant.attribute_ids for variant in variants
        ):
            missing.append(
                {
                    "attribute_id": str(rule.attribute_id),
                    "name": rule.name,
                    "where": "variants",
                }
            )

    if not any(variant.status == VariantStatus.ACTIVE for variant in variants):
        reasons.append("no_active_variant")
    if len({variant.attribute_ids for variant in variants}) > 1:
        reasons.append("inconsistent_variation_attributes")

    return Gaps(missing=missing, reasons=reasons)


def variation_sets_consistent(
    existing: Sequence[frozenset[uuid.UUID]], candidate: frozenset[uuid.UUID]
) -> bool:
    """Whether a new variant's attribute set matches the live variants' shared set."""

    return all(shape == candidate for shape in existing)


def attribute_values_by_id(
    values: Sequence[AttributeValueInput],
) -> Mapping[uuid.UUID, AttributeValueInput]:
    """Index values by attribute, assuming the caller has rejected duplicates."""

    return {value.attribute_id: value for value in values}
