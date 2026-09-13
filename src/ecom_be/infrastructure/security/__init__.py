"""Security primitives over external libraries.

Nothing here knows about a business concept. These are the same class of thing as
the Redis client factory and the session factory: thin, well-tested wrappers that
keep a third-party API from spreading through the codebase.
"""
