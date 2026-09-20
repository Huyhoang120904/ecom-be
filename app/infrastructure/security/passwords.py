"""Argon2id password hashing.

The parameters are the library defaults, which track current guidance. Do not
hand-tune them: Argon2 stores its parameters inside the digest, so changing them
does not invalidate existing hashes, but it does change the cost of every future
login and every future verification. A change here is a deliberate performance and
security decision, not a tweak.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

# Verified against on every login for an unknown account, so that response time
# does not disclose whether an email address is registered. Computed at import
# rather than hardcoded, because a hardcoded digest would silently stop matching
# the hasher's parameters if they ever change.
DUMMY_DIGEST = _hasher.hash("dummy-password-for-timing-equalisation")


def hash_password(password: str) -> str:
    """Return an Argon2id digest for the password.

    The digest embeds the salt and the parameters, so two calls with the same
    password produce different strings and both verify.
    """

    return _hasher.hash(password)


def verify_password(digest: str, password: str) -> bool:
    """Return whether the password matches the digest.

    Never raises: a malformed or truncated digest is a failed verification, not a
    500. A row corrupted in the database must fail closed and let the caller return
    the same generic response it returns for a wrong password.
    """

    try:
        return _hasher.verify(digest, password)
    except (VerificationError, VerifyMismatchError, InvalidHashError):
        return False


def verify_dummy() -> None:
    """Burn one verification against a digest nothing can match.

    Called on the login path when no account matches the submitted email, so an
    unknown address costs the same as a known one.
    """

    verify_password(DUMMY_DIGEST, "never-matches")
