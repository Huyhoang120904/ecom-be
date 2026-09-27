"""Bounds on the role and permission vocabulary.

Roles and permissions arrive from the seed migration, so these bound what a seeded
row may contain and what a response may publish about it.
"""

ROLE_KEY_MAX = 64

ROLE_NAME_MAX = 80

PERMISSION_KEY_MAX = 64

PERMISSION_DESCRIPTION_MAX = 200

# The one platform role that carries oversight. A platform membership with any other
# role is not an administrator, which is why the login and principal paths resolve
# ``find_platform_membership`` by this key rather than accepting any ``shop_id IS NULL``
# membership.
SYS_ADMIN_ROLE_KEY = "sys_admin"
