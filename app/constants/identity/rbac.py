"""Bounds on the role and permission vocabulary.

Roles and permissions arrive from the seed migration, so these bound what a seeded
row may contain and what a response may publish about it.
"""

ROLE_KEY_MAX = 64

ROLE_NAME_MAX = 80

PERMISSION_KEY_MAX = 64

PERMISSION_DESCRIPTION_MAX = 200
