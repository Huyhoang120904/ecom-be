"""Permission keys the catalog and product surfaces are guarded by.

``products:read`` and ``products:write`` were seeded with the identity vocabulary.
``catalog:manage`` is a temporary, shop-scoped stand-in for a platform-admin check;
see the ``catalog manage permission`` migration for why and for the plan to replace it.
"""

CATALOG_MANAGE = "catalog:manage"

PRODUCTS_READ = "products:read"

PRODUCTS_WRITE = "products:write"
