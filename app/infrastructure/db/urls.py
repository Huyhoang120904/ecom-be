"""Hand database URLs to Alembic's configparser-backed config without mangling them.

``alembic/config.py`` routes every value through ``configparser``, which treats
``%`` as the start of an interpolation token. A percent sign that is meaningful
to the DSN -- a URL-encoded credential such as ``p%40ss`` standing for ``p@ss``
-- therefore raises ``ValueError: invalid interpolation syntax`` and
``alembic upgrade head`` fails with an error naming neither the password nor the
offending character. Escaping each ``%`` as ``%%`` transmits the URL verbatim;
``Config.get_main_option`` interpolates it back to the original DSN on read.
"""


def escape_for_configparser(value: str) -> str:
    """Double every ``%`` so configparser leaves the value untouched.

    The escaping is a transport detail of ``alembic.ini`` handling, not part of
    the URL: pass the raw value and read it back with ``get_main_option``, which
    un-escapes it to exactly what was passed in.
    """
    return value.replace("%", "%%")
