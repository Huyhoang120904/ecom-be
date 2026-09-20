"""Contract: the pure identity helpers.

Everything here is pure, so these tests need no database, no Redis, and no request.
That is the reason the helpers live in their own file rather than inside the
services that use them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.config.settings import get_settings
from app.constants.identity import (
    PASSWORD_MAX,
    PASSWORD_MAX_BYTES,
    PHONE_MAX_INPUT,
    SLUG_MAX,
)
from app.utils import identity as utils


class TestNormalizeEmail:
    def test_strips_and_lowercases(self):
        assert utils.normalize_email("  Seller@Example.COM  ") == "seller@example.com"

    @pytest.mark.parametrize(
        "raw",
        [
            "a b@example.com",
            "no-at-sign",
            "@example.com",
            "a@b",
            "a@.com",
            "a" * 250 + "@example.com",
            "",
        ],
    )
    def test_rejects_malformed_addresses(self, raw: str):
        with pytest.raises(ValueError):
            utils.normalize_email(raw)

    def test_accepts_an_address_at_the_maximum_length(self):
        local = "a" * (254 - len("@example.com"))
        assert len(utils.normalize_email(f"{local}@example.com")) == 254

    def test_rejects_one_character_over_the_maximum(self):
        local = "a" * (255 - len("@example.com"))
        with pytest.raises(ValueError):
            utils.normalize_email(f"{local}@example.com")

    def test_subdomains_and_plus_addressing_are_accepted(self):
        assert (
            utils.normalize_email("Seller+lamps@shop.example.co.uk")
            == "seller+lamps@shop.example.co.uk"
        )


class TestNormalizeName:
    def test_strips_surrounding_whitespace(self):
        assert utils.normalize_name("  Nguyễn  ", field="full_name") == "Nguyễn"

    def test_composed_and_decomposed_forms_agree(self):
        """NFC folding means two spellings of one name compare equal.

        Without it, ``Nguyễn`` typed with a combining circumflex and ``Nguyễn``
        typed as a precomposed character are different strings, and a duplicate
        check or a search would treat one person as two.
        """

        decomposed = "Nguye\u0302\u0303n"
        precomposed = "Nguyễn"

        assert decomposed != precomposed, "the two forms really are different strings"
        assert utils.normalize_name(
            decomposed, field="full_name"
        ) == utils.normalize_name(precomposed, field="full_name")

    def test_rejects_a_whitespace_only_value(self):
        with pytest.raises(ValueError):
            utils.normalize_name("   ", field="full_name")

    def test_bounds_full_name(self):
        assert len(utils.normalize_name("x" * 120, field="full_name")) == 120
        with pytest.raises(ValueError):
            utils.normalize_name("x" * 121, field="full_name")

    def test_bounds_shop_name_at_both_ends(self):
        assert utils.normalize_name("ab", field="shop_name") == "ab"
        with pytest.raises(ValueError):
            utils.normalize_name("a", field="shop_name")

    @pytest.mark.parametrize("bad", ["bad\x00name", "bad\x1fname", "bad\x7fname"])
    def test_rejects_control_characters(self, bad: str):
        with pytest.raises(ValueError):
            utils.normalize_name(bad, field="full_name")

    @pytest.mark.parametrize("bad", ["two\nlines", "two\rlines"])
    def test_rejects_newlines_in_a_single_line_field(self, bad: str):
        with pytest.raises(ValueError):
            utils.normalize_name(bad, field="full_name")

    def test_a_name_may_be_absent_when_the_field_is_optional(self):
        assert utils.normalize_name("", field="job_title") == ""


class TestNormalizeMultiline:
    def test_collapses_run_on_blank_lines(self):
        assert (
            utils.normalize_multiline("line one\n\n\n\nline two", field="bio")
            == "line one\n\nline two"
        )

    def test_keeps_a_single_blank_line(self):
        assert (
            utils.normalize_multiline("first\n\nsecond", field="bio")
            == "first\n\nsecond"
        )

    def test_allows_empty(self):
        assert utils.normalize_multiline("", field="bio") == ""

    def test_rejects_control_characters_but_not_newlines(self):
        assert utils.normalize_multiline("ok\nfine", field="bio") == "ok\nfine"
        with pytest.raises(ValueError):
            utils.normalize_multiline("bad\x00value", field="bio")

    def test_bounds_bio_after_normalization(self):
        assert len(utils.normalize_multiline("y" * 500, field="bio")) == 500
        with pytest.raises(ValueError):
            utils.normalize_multiline("y" * 501, field="bio")


class TestNormalizePhone:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("+1 (312) 847-1928", "+13128471928"),
            ("090 123 4567", "0901234567"),
            ("+84-90-123-4567", "+84901234567"),
            ("(555) 010 9999", "5550109999"),
        ],
    )
    def test_folds_punctuation_and_keeps_an_optional_plus(self, raw, expected):
        assert utils.normalize_phone(raw, field="phone") == expected

    @pytest.mark.parametrize(
        "raw", ["12345", "+1234567890123456", "not-a-phone", "++1234567"]
    )
    def test_rejects_values_outside_the_grammar(self, raw: str):
        with pytest.raises(ValueError):
            utils.normalize_phone(raw, field="phone")

    @pytest.mark.parametrize("blank", ["", "   ", "\t"])
    def test_blank_becomes_absent_rather_than_invalid(self, blank: str):
        assert utils.normalize_phone(blank, field="phone") is None

    def test_rejects_an_input_far_beyond_the_raw_bound(self):
        with pytest.raises(ValueError):
            utils.normalize_phone("1" * (PHONE_MAX_INPUT + 1), field="phone")


class TestSlugify:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Cửa hàng Hoàng", "cua-hang-hoang"),
            ("  --Weird   Name!!  ", "weird-name"),
            ("Huyhoang120904", "huyhoang120904"),
            ("Lamps & Shades", "lamps-shades"),
            ("Ünïcôdé Shöp", "unicode-shop"),
            ("Bàn phở", "ban-pho"),
        ],
    )
    def test_ascii_folds_and_collapses_punctuation(self, name, expected):
        assert utils.slugify(name) == expected

    @pytest.mark.parametrize("empty", ["", "!!!", "   ", "---", "日本語"])
    def test_falls_back_when_nothing_survives(self, empty: str):
        assert utils.slugify(empty) == "shop"

    def test_bounds_length_and_leaves_room_for_a_suffix(self):
        slug = utils.slugify("a" * 400)
        assert len(slug) <= 72
        assert len(utils.slug_with_suffix(slug, 2)) <= SLUG_MAX

    def test_a_collision_suffix_stays_inside_the_column_bound(self):
        base = utils.slugify("a" * 400)
        for suffix in (2, 9, 10, 99, 100, 9999):
            assert len(utils.slug_with_suffix(base, suffix)) <= SLUG_MAX
            assert utils.slug_with_suffix(base, suffix).endswith(f"-{suffix}")

    def test_a_trailing_hyphen_is_trimmed_before_the_suffix(self):
        assert utils.slug_with_suffix("shop-", 2) == "shop-2"
        assert utils.slug_with_suffix("shop", 2) == "shop-2"


class TestValidatePassword:
    def test_accepts_a_password_at_the_minimum(self):
        utils.validate_password("a" * 12)

    def test_rejects_a_password_one_below_the_minimum(self):
        with pytest.raises(ValueError):
            utils.validate_password("a" * 11)

    def test_accepts_a_password_at_the_character_maximum(self):
        utils.validate_password("a" * PASSWORD_MAX)

    def test_rejects_a_password_over_the_character_maximum(self):
        with pytest.raises(ValueError):
            utils.validate_password("a" * (PASSWORD_MAX + 1))

    def test_rejects_whitespace_only(self):
        with pytest.raises(ValueError):
            utils.validate_password(" " * 20)

    def test_the_byte_cap_is_independent_of_the_character_cap(self):
        """A 4-byte character inside the character cap can still exceed the byte cap.

        With ``PASSWORD_MAX`` at 128, a password must be at least 3 bytes per
        character to trip this: 128 characters of a 4-byte emoji is 512 bytes.
        """

        password = "\U0001f600" * PASSWORD_MAX
        assert len(password) == PASSWORD_MAX, "inside the character cap"
        assert len(password.encode("utf-8")) > PASSWORD_MAX_BYTES, (
            "outside the byte cap"
        )

        with pytest.raises(ValueError):
            utils.validate_password(password)

    def test_a_multibyte_password_inside_both_caps_is_accepted(self):
        password = "é" * 12
        assert len(password.encode("utf-8")) == 24
        utils.validate_password(password)


class TestAccessTokens:
    def test_round_trips_with_the_expected_claims(self):
        settings = get_settings()
        user_id, shop_id = utils.new_id(), utils.new_id()

        token = utils.issue_access_token(
            settings, user_id=user_id, active_shop_id=shop_id
        )
        claims = utils.decode_access_token(settings, token)

        assert claims["sub"] == user_id
        assert claims["sid"] == shop_id
        assert claims["type"] == "access"
        assert claims["iss"] == "ecom-be"
        assert isinstance(claims["jti"], str) and claims["jti"]

    def test_carries_no_authority_beyond_identity(self):
        """The token says who and which shop, never what they may do."""

        settings = get_settings()
        token = utils.issue_access_token(
            settings, user_id=utils.new_id(), active_shop_id=utils.new_id()
        )
        claims = utils.decode_access_token(settings, token)

        assert "permissions" not in claims
        assert "roles" not in claims

    def test_rejects_an_expired_token(self):
        settings = get_settings()
        expired = utils.issue_access_token(
            settings,
            user_id=utils.new_id(),
            active_shop_id=utils.new_id(),
            now=datetime.now(UTC) - timedelta(hours=2),
        )
        with pytest.raises(utils.InvalidAccessToken):
            utils.decode_access_token(settings, expired)

    def test_rejects_a_token_from_another_issuer(self):
        settings = get_settings()
        foreign = utils.issue_access_token(
            settings,
            user_id=utils.new_id(),
            active_shop_id=utils.new_id(),
            issuer="someone-else",
        )
        with pytest.raises(utils.InvalidAccessToken):
            utils.decode_access_token(settings, foreign)

    def test_rejects_a_token_of_the_wrong_type(self):
        """A refresh value must never be usable as a bearer token."""

        settings = get_settings()
        wrong_type = utils.issue_access_token(
            settings,
            user_id=utils.new_id(),
            active_shop_id=utils.new_id(),
            token_type="refresh",
        )
        with pytest.raises(utils.InvalidAccessToken):
            utils.decode_access_token(settings, wrong_type)

    @pytest.mark.parametrize("bad", ["not.a.jwt", "", "a.b.c", "Bearer x"])
    def test_rejects_a_malformed_token(self, bad: str):
        with pytest.raises(utils.InvalidAccessToken):
            utils.decode_access_token(get_settings(), bad)

    def test_rejects_a_token_signed_with_another_secret(self):
        settings = get_settings()
        other = settings.model_copy(update={"jwt_secret": "x" * 32})
        foreign = utils.issue_access_token(
            other, user_id=utils.new_id(), active_shop_id=utils.new_id()
        )
        with pytest.raises(utils.InvalidAccessToken):
            utils.decode_access_token(settings, foreign)


class TestRefreshTokens:
    def test_tokens_are_unique_and_a_digest_is_returned(self):
        first, first_hash = utils.new_refresh_token()
        second, second_hash = utils.new_refresh_token()

        assert first != second
        assert first_hash != second_hash
        assert len(first_hash) == 64

    def test_the_raw_token_is_absent_from_what_is_stored(self):
        token, digest = utils.new_refresh_token()

        assert token not in digest
        assert utils.hash_refresh_token(token) == digest

    def test_the_digest_is_stable_for_the_same_token(self):
        token, digest = utils.new_refresh_token()

        assert utils.hash_refresh_token(token) == utils.hash_refresh_token(token)
        assert digest == utils.hash_refresh_token(token)
