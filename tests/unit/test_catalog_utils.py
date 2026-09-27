"""Contract: the pure catalog helpers.

No database and no framework: these are the rules the services lean on, so they are
tested with plain values, including the ones a service would be slow to reach.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.constants.catalog import AttributeDataType, VariantStatus
from app.utils.catalog import (
    AttributeValueInput,
    CategoryAttributeRule,
    VariantShape,
    ancestors_contain,
    check_value_matches_type,
    normalize_text,
    option_key,
    published_gaps,
    reorder,
    slug_with_suffix,
    slugify,
)


def ids(count: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(count)]


class TestText:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("Áo thun", "ao-thun"),
            ("  Hello   World!! ", "hello-world"),
            ("###", "item"),
        ],
    )
    def test_slugify(self, value, expected):
        assert slugify(value) == expected

    def test_a_suffixed_slug_stays_inside_the_column(self):
        assert len(slug_with_suffix("a" * 200, 12345)) <= 120

    def test_normalize_text_folds_and_strips(self):
        assert normalize_text(" Café ", field_name="n", minimum=1, maximum=20) == "Café"

    @pytest.mark.parametrize("bad", ["a\nb", "a\x00b", ""])
    def test_normalize_text_rejects_control_characters_and_empties(self, bad):
        with pytest.raises(ValueError):
            normalize_text(bad, field_name="n", minimum=1, maximum=20)

    def test_a_newline_is_allowed_only_when_multiline(self):
        assert (
            normalize_text(
                "a\nb", field_name="n", minimum=1, maximum=20, multiline=True
            )
            == "a\nb"
        )


class TestOptionKey:
    def test_it_does_not_depend_on_the_order_of_options(self):
        (a1, o1), (a2, o2) = zip(ids(2), ids(2), strict=True)

        assert option_key([(a1, o1), (a2, o2)]) == option_key([(a2, o2), (a1, o1)])

    def test_different_combinations_have_different_keys(self):
        a, o1, o2 = ids(3)

        assert option_key([(a, o1)]) != option_key([(a, o2)])

    def test_no_options_is_the_empty_key(self):
        assert option_key([]) == ""

    def test_a_key_fits_its_column_at_the_option_limit(self):
        from app.constants.catalog import OPTION_KEY_MAX, VARIANT_OPTIONS_MAX

        pairs = [(uuid.uuid4(), uuid.uuid4()) for _ in range(VARIANT_OPTIONS_MAX)]

        assert len(option_key(pairs)) <= OPTION_KEY_MAX


class TestValueTypes:
    def check(self, data_type, valid=frozenset(), **fields):
        value = AttributeValueInput(attribute_id=uuid.uuid4(), **fields)
        return check_value_matches_type(data_type, value, valid_option_ids=set(valid))

    def test_a_select_takes_one_of_its_own_options(self):
        option = uuid.uuid4()

        assert self.check(AttributeDataType.SELECT, {option}, option_id=option) is None
        assert (
            self.check(AttributeDataType.SELECT, {option}, option_id=uuid.uuid4())
            == "option_not_of_attribute"
        )

    def test_each_type_asks_for_its_own_field(self):
        assert self.check(AttributeDataType.TEXT, value_text="M4") is None
        assert (
            self.check(AttributeDataType.NUMBER, value_number=Decimal("14.2")) is None
        )
        assert self.check(AttributeDataType.TEXT, value_number=Decimal(1)) == (
            "wrong_value_field"
        )
        assert self.check(AttributeDataType.NUMBER, value_text="14") == (
            "wrong_value_field"
        )

    def test_more_than_one_field_or_none_is_wrong(self):
        option = uuid.uuid4()

        assert self.check(AttributeDataType.TEXT) == "wrong_value_field"
        assert (
            self.check(
                AttributeDataType.SELECT, {option}, option_id=option, value_text="x"
            )
            == "wrong_value_field"
        )

    @pytest.mark.parametrize("bad", ["", "   "])
    def test_blank_text_is_rejected(self, bad):
        assert self.check(AttributeDataType.TEXT, value_text=bad) == "text_out_of_range"

    @pytest.mark.parametrize(
        "bad", [Decimal("NaN"), Decimal("Infinity"), Decimal(10**15)]
    )
    def test_non_finite_or_huge_numbers_are_rejected(self, bad):
        assert self.check(AttributeDataType.NUMBER, value_number=bad) is not None


class TestTree:
    def test_a_chain_containing_the_candidate_is_a_cycle(self):
        a, b, c = ids(3)

        assert ancestors_contain([c, b, a], a) is True
        assert ancestors_contain([c, b], a) is False

    def test_reorder_moves_one_item_and_keeps_the_rest_in_order(self):
        a, b, c, d = ids(4)

        assert reorder([a, b, c, d], c, 0) == [c, a, b, d]
        assert reorder([a, b, c, d], a, 3) == [b, c, d, a]
        assert reorder([a, b, c, d], b, 1) == [a, b, c, d]

    @pytest.mark.parametrize("target", [-1, 4])
    def test_reorder_rejects_a_position_outside_the_range(self, target):
        a, b, c, d = ids(4)

        with pytest.raises(ValueError):
            reorder([a, b, c, d], a, target)

    def test_reorder_rejects_an_unknown_item(self):
        a, b = ids(2)

        with pytest.raises(ValueError):
            reorder([a], b, 0)


class TestPublishedGaps:
    color, size, material, cpu = ids(4)

    def rules(self, **overrides):
        base = {
            "color": (True, True),
            "size": (True, True),
            "material": (False, False),
            "cpu": (True, False),
        }
        base.update(overrides)
        attr = {
            "color": self.color,
            "size": self.size,
            "material": self.material,
            "cpu": self.cpu,
        }
        return [
            CategoryAttributeRule(attr[name], name.title(), required, variation)
            for name, (required, variation) in base.items()
        ]

    def variant(self, *attribute_ids, status=VariantStatus.ACTIVE):
        return VariantShape(status=status, attribute_ids=frozenset(attribute_ids))

    def gaps(self, *, values, variants, rules=None):
        return published_gaps(
            rules=rules if rules is not None else self.rules(),
            value_attribute_ids=set(values),
            variants=variants,
        )

    def test_a_complete_product_has_no_gaps(self):
        result = self.gaps(
            values={self.cpu},
            variants=[self.variant(self.color, self.size)],
        )

        assert result.is_empty()

    def test_a_missing_required_product_attribute_is_named_with_where(self):
        result = self.gaps(values=set(), variants=[self.variant(self.color, self.size)])

        assert result.missing == [
            {"attribute_id": str(self.cpu), "name": "Cpu", "where": "product"}
        ]

    def test_a_required_variation_is_satisfied_by_variants_not_by_product_values(self):
        # Color is a required variation. Giving it as a product value does not count.
        result = self.gaps(
            values={self.cpu, self.color},
            variants=[self.variant(self.size)],
        )

        assert [m["name"] for m in result.missing] == ["Color"]
        assert result.missing[0]["where"] == "variants"

    def test_every_live_variant_must_carry_a_required_variation(self):
        result = self.gaps(
            values={self.cpu},
            variants=[
                self.variant(self.color, self.size),
                self.variant(self.size, status=VariantStatus.INACTIVE),
            ],
        )

        assert [m["name"] for m in result.missing] == ["Color"]
        assert "inconsistent_variation_attributes" in result.reasons

    def test_no_variant_or_no_active_variant_is_a_reason(self):
        assert "no_active_variant" in self.gaps(values={self.cpu}, variants=[]).reasons
        assert (
            "no_active_variant"
            in self.gaps(
                values={self.cpu},
                variants=[
                    self.variant(self.color, self.size, status=VariantStatus.INACTIVE)
                ],
            ).reasons
        )

    def test_variants_using_different_variation_sets_are_inconsistent(self):
        rules = self.rules(color=(False, True), size=(False, True))

        result = self.gaps(
            values={self.cpu},
            rules=rules,
            variants=[self.variant(self.color), self.variant(self.size)],
        )

        assert result.reasons == ["inconsistent_variation_attributes"]

    def test_an_optional_attribute_never_blocks(self):
        result = self.gaps(
            values={self.cpu}, variants=[self.variant(self.color, self.size)]
        )

        assert self.material not in {m["attribute_id"] for m in result.missing}

    def test_a_product_without_variations_needs_one_optionless_variant(self):
        rules = [CategoryAttributeRule(self.cpu, "Cpu", True, False)]

        result = self.gaps(values={self.cpu}, rules=rules, variants=[self.variant()])

        assert result.is_empty()
