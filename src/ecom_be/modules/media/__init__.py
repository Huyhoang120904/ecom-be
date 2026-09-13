"""Media module: image validation, normalization, storage, and serving.

This module deliberately has no ``models.py`` and no ``repository.py``, following the
precedent ``modules/health/`` already sets: a module with no persisted entity omits
those files rather than inventing an empty shape. An image's *reference* lives on the
entity that owns it (``users.avatar_key``, ``shops.background_key``); this module
owns the bytes.
"""
