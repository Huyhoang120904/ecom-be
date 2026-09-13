"""Contract: Argon2id hashing and timing-equalised verification.

Two properties matter beyond "the right password verifies":

* The same password must hash differently every time. Argon2 salts internally, so
  a shared digest would mean the salt is not being used.
* Verifying against an unknown account must cost about as much as verifying
  against a known one, or login response time discloses which emails are
  registered. ``verify_dummy`` exists for that, and these tests are what keep it
  honest.
"""

from __future__ import annotations

import time

from ecom_be.infrastructure.security.passwords import (
    DUMMY_DIGEST,
    hash_password,
    verify_dummy,
    verify_password,
)

PASSWORD = "correct horse battery staple"


def test_a_hash_verifies_its_own_password():
    digest = hash_password(PASSWORD)

    assert verify_password(digest, PASSWORD) is True


def test_a_hash_rejects_the_wrong_password():
    digest = hash_password(PASSWORD)

    assert verify_password(digest, "Correct horse battery staple") is False
    assert verify_password(digest, PASSWORD + " ") is False


def test_the_digest_identifies_argon2id():
    """The algorithm is part of the contract: a silent downgrade must be visible."""

    assert hash_password(PASSWORD).startswith("$argon2id$")


def test_hashing_the_same_password_twice_gives_different_digests():
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_a_malformed_digest_is_rejected_rather_than_raising():
    """A corrupt row must fail closed, not crash the login endpoint."""

    assert verify_password("not-a-digest", PASSWORD) is False
    assert verify_password("", PASSWORD) is False
    assert verify_password("$argon2id$truncated", PASSWORD) is False


def test_the_dummy_digest_is_a_real_argon2id_hash():
    assert DUMMY_DIGEST.startswith("$argon2id$")


def test_verify_dummy_never_raises_and_never_matches():
    verify_dummy()
    assert verify_password(DUMMY_DIGEST, "never-matches") is False


def test_dummy_verification_costs_comparable_time_to_a_real_one():
    """This is the point of ``verify_dummy``: an unknown account is not faster.

    The bound is deliberately loose (a quarter of the real cost) because a shared
    CI machine is noisy. A tighter bound would flake; a missing dummy would fail
    this by an order of magnitude.
    """

    digest = hash_password("baseline-password")
    verify_password(digest, "baseline-password")

    start = time.perf_counter()
    verify_password(digest, "wrong-password")
    real_elapsed = time.perf_counter() - start

    start = time.perf_counter()
    verify_dummy()
    dummy_elapsed = time.perf_counter() - start

    assert dummy_elapsed > real_elapsed * 0.25, (
        f"dummy verification was {dummy_elapsed:.6f}s against a real "
        f"{real_elapsed:.6f}s; an unknown account would be measurably faster"
    )
