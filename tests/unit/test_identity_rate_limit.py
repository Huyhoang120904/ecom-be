"""Contract: rate limiting, including its failure mode.

The behaviour worth pinning is not "the limit fires" (that is arithmetic) but what
happens when Redis is down. Failing closed would turn a cache outage into a total
sign-in outage, so the degradation is deliberate and this test is what keeps it
deliberate rather than accidental.
"""

from __future__ import annotations

import pytest

from ecom_be.modules.identity.errors import RateLimited
from ecom_be.modules.identity.services import enforce_rate_limit

pytestmark = pytest.mark.anyio

KEY = "login:1.2.3.4"


class FakeRedis:
    """Enough of the Redis surface for the limiter, plus a failure switch."""

    def __init__(self, *, fail: bool = False) -> None:
        self.counts: dict[str, int] = {}
        self.expiries: dict[str, int] = {}
        self.fail = fail

    async def incr(self, key: str) -> int:
        if self.fail:
            raise ConnectionError("redis is down")
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        if self.fail:
            raise ConnectionError("redis is down")
        self.expiries[key] = seconds
        return True


async def test_attempts_up_to_the_limit_are_allowed():
    redis = FakeRedis()

    for _ in range(5):
        await enforce_rate_limit(redis, key=KEY, limit=5, window_seconds=900)


async def test_the_attempt_past_the_limit_is_refused():
    redis = FakeRedis()
    for _ in range(5):
        await enforce_rate_limit(redis, key=KEY, limit=5, window_seconds=900)

    with pytest.raises(RateLimited):
        await enforce_rate_limit(redis, key=KEY, limit=5, window_seconds=900)


async def test_the_window_is_set_once_on_the_first_attempt():
    """``expire`` on every increment would keep pushing the window forward."""

    redis = FakeRedis()

    await enforce_rate_limit(redis, key=KEY, limit=5, window_seconds=900)
    await enforce_rate_limit(redis, key=KEY, limit=5, window_seconds=900)

    assert redis.expiries == {KEY: 900}
    assert redis.counts[KEY] == 2


async def test_a_redis_failure_lets_the_request_through():
    """Failing closed would turn a cache outage into a sign-in outage."""

    redis = FakeRedis(fail=True)

    await enforce_rate_limit(redis, key=KEY, limit=1, window_seconds=900)


async def test_no_redis_client_means_no_limiting():
    await enforce_rate_limit(None, key=KEY, limit=1, window_seconds=900)


async def test_the_caller_address_is_part_of_the_key():
    """Two clients do not share one budget."""

    redis = FakeRedis()

    await enforce_rate_limit(redis, key="login:1.1.1.1", limit=1, window_seconds=900)
    await enforce_rate_limit(redis, key="login:2.2.2.2", limit=1, window_seconds=900)

    assert set(redis.counts) == {"login:1.1.1.1", "login:2.2.2.2"}
