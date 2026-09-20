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
    """A resolved caller across storefront, cms, or admin.

    ``active_shop_id`` is a *request*, not a grant. Resolving a principal already
    proved a live membership for that shop, which is why a stale ``sid`` claim
    cannot reach another shop's data.
    """

    user_id: str
    email: str
    audience: str = "cms"
    active_shop_id: str | None = None
    roles: tuple[str, ...] = ()
    permissions: frozenset[str] = frozenset()
    shop_is_active: bool | None = None
    is_platform_admin: bool = False

    def has(self, *keys: str) -> bool:
        """Return whether this principal holds every permission key."""
        if self.is_platform_admin:
            return True
        return all(key in self.permissions for key in keys)

    def has_any(self, *keys: str) -> bool:
        """Return whether this principal holds at least one permission key."""
        if self.is_platform_admin:
            return True
        return any(key in self.permissions for key in keys)

    def has_role(self, key: str) -> bool:
        """Return whether this principal holds this role in the active shop."""
        return key in self.roles

    def has_any_role(self, *keys: str) -> bool:
        """Return whether this principal holds at least one of these roles."""
        return any(key in self.roles for key in keys)
