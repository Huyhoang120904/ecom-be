"""Rate limiting for the endpoints that disclose something by being tried.

Not identity-specific and not transport-specific, so it sits beside the feature
services rather than inside one.

The policy is explicitly fail-open: a cache outage must not become a sign-in outage.
Refusing an attempt past the limit is the only thing this raises for.
"""

from __future__ import annotations

import logging
from typing import Protocol

from ecom_be.errors.identity import RateLimited

# Rate-limit windows. Registration is the tightest because it is the endpoint that
# discloses whether an address is taken.
REGISTER_LIMIT = 5
REGISTER_WINDOW_SECONDS = 3600
LOGIN_LIMIT = 10
LOGIN_WINDOW_SECONDS = 900
UPLOAD_LIMIT = 30
UPLOAD_WINDOW_SECONDS = 3600

logger = logging.getLogger(__name__)


class RateLimitStore(Protocol):
    """The two Redis commands the limiter needs.

    Narrowing the dependency to what is used is what lets the failure path be tested
    with a small fake instead of a real server, and it keeps the limiter from
    acquiring a reason to reach for anything else.
    """

    async def incr(self, key: str) -> int: ...

    async def expire(self, key: str, seconds: int) -> bool: ...


async def enforce_rate_limit(
    client: RateLimitStore | None,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    """Refuse an attempt past the limit. A Redis failure lets it through.

    Failing closed would turn a cache outage into a total sign-in outage, which is a
    worse outcome than a temporarily unthrottled login. The event is logged so the
    degradation is visible rather than silent.
    """

    if client is None:
        return
    try:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, window_seconds)
        if count > limit:
            raise RateLimited
    except RateLimited:
        raise
    except Exception:  # noqa: BLE001 - a cache outage must not deny sign-in
        logger.warning("Rate limit check failed for %s; allowing the request", key)
