"""Contract: identity request bounds and response envelopes.

The request assertions are about normalization and bounds, because those are the
rules the OpenAPI document promises to a generated client. The response assertions
are about what must *not* be exposed.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ecom_be.schemas.identity.request import (
    DeactivateRequest,
    DeleteShopRequest,
    LoginRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    ShopUpdateRequest,
    SwitchShopRequest,
)
from ecom_be.schemas.identity.response import (
    MeEnvelope,
    SessionEnvelope,
    ShopEnvelope,
)

VALID_PASSWORD = "a-perfectly-fine-password"


class TestRegisterRequest:
    def test_normalizes_every_field(self):
        request = RegisterRequest(
            email="  Seller@Example.COM ",
            password=VALID_PASSWORD,
            full_name="  Nguyễn Văn A  ",
            shop_name="  Cửa hàng Hoàng  ",
        )

        assert request.email == "seller@example.com"
        assert request.full_name == "Nguyễn Văn A"
        assert request.shop_name == "Cửa hàng Hoàng"
        assert request.password == VALID_PASSWORD

    def test_rejects_a_short_password(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="a@b.co",
                password="short",
                full_name="Name",
                shop_name="Good Shop",
            )

    def test_rejects_a_one_character_shop_name(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="a@b.co",
                password=VALID_PASSWORD,
                full_name="Name",
                shop_name="A",
            )

    def test_rejects_a_malformed_email(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="not-an-email",
                password=VALID_PASSWORD,
                full_name="Name",
                shop_name="Good Shop",
            )

    def test_rejects_a_whitespace_only_full_name(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="a@b.co",
                password=VALID_PASSWORD,
                full_name="   ",
                shop_name="Good Shop",
            )

    def test_rejects_a_password_over_the_byte_cap(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="a@b.co",
                password="\U0001f600" * 128,
                full_name="Name",
                shop_name="Good Shop",
            )


class TestLoginRequest:
    def test_accepts_a_short_password_so_the_failure_is_indistinguishable(self):
        """A length rule here would disclose the stored password's length."""

        request = LoginRequest(email="a@b.co", password="x")

        assert request.password == "x"

    def test_normalizes_the_email(self):
        assert LoginRequest(email=" A@B.CO ", password="x").email == "a@b.co"

    def test_rejects_an_empty_password(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="a@b.co", password="")


class TestProfileUpdateRequest:
    def test_an_omitted_key_is_absent_from_fields_set(self):
        request = ProfileUpdateRequest.model_validate({"bio": "Hi"})

        assert request.model_fields_set == {"bio"}
        assert request.full_name is None

    def test_an_explicit_null_is_present_in_fields_set(self):
        """The distinction the service needs to tell "leave it" from "clear it"."""

        request = ProfileUpdateRequest.model_validate({"job_title": None})

        assert "job_title" in request.model_fields_set
        assert request.job_title is None

    def test_normalizes_a_bio_and_collapses_blank_lines(self):
        request = ProfileUpdateRequest.model_validate({"bio": "one\n\n\n\ntwo"})

        assert request.bio == "one\n\ntwo"

    def test_rejects_an_over_long_bio(self):
        with pytest.raises(ValidationError):
            ProfileUpdateRequest.model_validate({"bio": "y" * 501})

    def test_rejects_a_phone_the_helper_rejects(self):
        with pytest.raises(ValidationError):
            ProfileUpdateRequest.model_validate({"phone": "12345"})

    def test_normalizes_a_phone(self):
        assert (
            ProfileUpdateRequest.model_validate({"phone": "+1 (312) 847-1928"}).phone
            == "+13128471928"
        )

    def test_rejects_a_cleared_full_name(self):
        with pytest.raises(ValidationError):
            ProfileUpdateRequest.model_validate({"full_name": None})

    def test_rejects_newlines_in_the_job_title(self):
        with pytest.raises(ValidationError):
            ProfileUpdateRequest.model_validate({"job_title": "two\nlines"})

    def test_an_empty_body_is_valid_and_changes_nothing(self):
        request = ProfileUpdateRequest.model_validate({})

        assert request.model_fields_set == set()


class TestShopUpdateRequest:
    def test_publishes_no_slug_field(self):
        """A rename must not silently rewrite a public URL."""

        assert "slug" not in ShopUpdateRequest.model_fields

    def test_requires_a_scheme_on_the_website(self):
        with pytest.raises(ValidationError):
            ShopUpdateRequest.model_validate({"website": "example.com"})

    @pytest.mark.parametrize("value", ["https://shop.example", "http://localhost:3000"])
    def test_accepts_an_absolute_website(self, value: str):
        assert ShopUpdateRequest.model_validate({"website": value}).website == value

    def test_a_blank_optional_field_becomes_absent(self):
        request = ShopUpdateRequest.model_validate(
            {"contact_email": "", "contact_phone": "  ", "website": ""}
        )

        assert request.contact_email is None
        assert request.contact_phone is None
        assert request.website is None

    def test_rejects_a_one_character_name(self):
        with pytest.raises(ValidationError):
            ShopUpdateRequest.model_validate({"name": "A"})


class TestSmallRequests:
    def test_deactivate_requires_a_password(self):
        with pytest.raises(ValidationError):
            DeactivateRequest.model_validate({})

    def test_switch_shop_requires_a_uuid(self):
        with pytest.raises(ValidationError):
            SwitchShopRequest.model_validate({"shop_id": "not-a-uuid"})

    def test_switch_shop_accepts_a_uuid(self):
        value = "11111111-1111-4111-8111-111111111111"

        assert (
            str(SwitchShopRequest.model_validate({"shop_id": value}).shop_id) == value
        )

    def test_delete_shop_requires_the_name(self):
        with pytest.raises(ValidationError):
            DeleteShopRequest.model_validate({})


class TestResponseEnvelopes:
    @pytest.mark.parametrize("envelope", [SessionEnvelope, MeEnvelope, ShopEnvelope])
    def test_wraps_its_payload_in_a_data_field(self, envelope):
        assert "data" in envelope.model_json_schema()["properties"]

    def test_the_session_body_carries_no_refresh_token(self):
        """The refresh token travels only as an httpOnly cookie."""

        properties = SessionEnvelope.model_json_schema()["$defs"]["SessionData"][
            "properties"
        ]

        assert "refresh_token" not in properties
        assert "access_token" in properties

    def test_no_response_exposes_a_media_object_key(self):
        """The client receives a derived URL, never the storage layout."""

        serialized = str(SessionEnvelope.model_json_schema())

        assert "avatar_key" not in serialized
        assert "background_key" not in serialized
        assert "avatar_url" in serialized
        assert "background_url" in serialized

    def test_no_response_exposes_a_password_hash(self):
        assert "password_hash" not in str(SessionEnvelope.model_json_schema())
