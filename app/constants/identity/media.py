"""Bounds on stored objects and the URLs derived from them.

``MEDIA_KEY_MAX`` bounds a storage key, ``UPLOAD_FIELD_NAME`` is the multipart part
name both image uploads use, and ``URL_MAX`` bounds the derived URL a response
publishes for an object -- it sits here rather than with the shop or account bounds
because the URLs that needed a ceiling are the media ones.
"""

MEDIA_KEY_MAX = 128

URL_MAX = 500

# Multipart part name for both image uploads.
UPLOAD_FIELD_NAME = "file"
