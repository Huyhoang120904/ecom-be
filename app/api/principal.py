"""Who is asking, and which shop they are asking for.

Deliberately framework-free, and therefore in the identity module rather than in
``api/deps.py``: the layer contract forbids a service from importing FastAPI, and
a service needs to type its own parameters. ``api/deps.py`` imports this file;
nothing imports ``api/deps.py`` except routers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Principal:
    """A resolved caller.

    ``active_shop_id`` is a *request*, not a grant. Resolving a principal already
    proved a live membership for that shop, which is why a stale ``sid`` claim
    cannot reach another shop's data.
    """

    user_id: str
    active_shop_id: str
    email: str
    roles: tuple[str, ...]
    permissions: frozenset[str]
    shop_is_active: bool

    def has(self, *keys: str) -> bool:
        """Return whether this principal holds every permission key."""

        return all(key in self.permissions for key in keys)

    def has_any(self, *keys: str) -> bool:
        """Return whether this principal holds at least one permission key."""

        return any(key in self.permissions for key in keys)

    def has_role(self, key: str) -> bool:
        """Return whether this principal holds this role in the active shop."""

        return key in self.roles

    def has_any_role(self, *keys: str) -> bool:
        """Return whether this principal holds at least one of these roles."""

        return any(key in self.roles for key in keys)
