# ecom-be contributor guidance

## Ground rules

- Target Python 3.11.x and manage dependencies with `uv`. Do not add a second
  dependency manager or hand-edit `uv.lock`.
- Keep application code under `src/ecom_be` and tests under `tests`.
- Never commit `.env`, credentials, connection strings, or secret values —
  including passwords embedded in examples, tests, or docs. `.env.example`
  holds replaceable placeholders only.
- Keep changes scoped to the requested task and avoid adding business behavior
  without a corresponding test.
- Run the quality gates before committing:

  ```bash
  uv run ruff format --check .
  uv run ruff check .
  uv run mypy src
  uv run pytest -q
  uv lock --check
  ```

## Architecture

```
src/ecom_be/
├── main.py                     # app factory, lifespan, middleware wiring
├── api/                        # cross-module HTTP wiring
│   ├── deps.py                 # shared dependencies and health probes
│   └── router.py               # composes module routers; adds no behavior
├── core/                       # config, error handlers, structured logging
├── infrastructure/             # external systems
│   ├── db/base.py              # the single declarative Base
│   ├── db/models.py            # imports module models; Alembic target_metadata
│   ├── db/session.py           # async engine + request-scoped session factory
│   └── cache/redis.py          # async Redis client factory
└── modules/                    # feature modules
    └── health/                 # the reference module
```

`main.py` owns the lifespan: it creates the Redis client once and disposes the
engine once, with a nested `try/finally` so a Redis close failure still disposes
the database engine. Repositories and routes never create their own clients.

## Module template

Every module is exactly this shape:

```
modules/<module_name>/
├── __init__.py         # one-line module docstring
├── models.py           # SQLAlchemy ORM models registered on the shared Base
├── schemas/
│   ├── __init__.py
│   ├── request.py      # request payload schemas
│   └── response.py     # response payload schemas
├── utils.py            # pure helpers: no I/O, no framework imports
├── repository.py       # all database operations for this module
├── services.py         # use cases; orchestrates repositories and clients
└── router.py           # HTTP routes; delegates to services
```

`models.py` is the one optional file, and only while a module has no persisted
entity — `modules/health/` is that case. A module that persists anything adds
`models.py`; it does not invent another persistence shape.

### Layer rules

- **Routes do not perform persistence.** `router.py` defines the HTTP contract,
  resolves dependencies, and calls a service. It never opens a query, builds a
  statement, or calls `commit()`.
- **Services own use cases.** `services.py` decides what happens: which
  repository calls run, in what order, and what the result means. Collaborators
  arrive through the constructor so services are testable without a database.
- **Repositories own database operations.** `repository.py` is the only layer
  that executes statements. It receives a session and never commits implicitly —
  one request-scoped session is yielded per request with no implicit commit, so
  a use case decides transaction boundaries explicitly.
- **`utils.py` is pure.** Deterministic helpers with no I/O, no session, no
  client, and no request object.
- **All I/O is async.** `AsyncSession` for PostgreSQL, `redis.asyncio` for
  Redis, an async HTTP client for outbound calls. Blocking the event loop from a
  coroutine is a defect, not a style preference.
- **Schemas define the API boundary.** ORM models are never returned directly;
  `schemas/response.py` models are the contract and are what `/api/v1/openapi.json`
  publishes.

### Adding a module

1. Create the template files above.
2. Register the router from `src/ecom_be/api/router.py`; that file only
   composes modules.
3. Take the request-scoped session and the lifecycle-owned Redis client from
   application state; do not build per-request clients.
4. For persisted data: write `models.py` on the shared `Base`, then import the
   model class in `src/ecom_be/infrastructure/db/models.py` — the single
   aggregation point `alembic/env.py` uses as `target_metadata` — and add its
   name to that file's `__all__`. Then
   `uv run alembic revision --autogenerate -m "..."` and
   `uv run alembic upgrade head`. A model not imported there is invisible to
   autogenerate; `tests/unit/test_migration_metadata.py` fails if a module's
   `models.py` is missing from that view.
5. Add unit tests in `tests/unit/` and API tests in `tests/integration/`.

## Local services and migrations

- `compose.yaml` starts local PostgreSQL 16 and Redis 7 with health checks and
  named volumes. Its credentials are disposable development values with env-var
  overrides — never production credentials, never reused elsewhere.
- **Two env surfaces, never mixed.** `.env` is parsed by `Settings`, which
  forbids unknown keys; it holds only `APP_NAME`, `ENVIRONMENT`, `DATABASE_URL`,
  `REDIS_URL`, and `CORS_ORIGINS`. Compose variables (`POSTGRES_DB`,
  `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`, `REDIS_PORT`) belong in
  `compose.env`, documented by the tracked `compose.env.example`, and are passed
  with `docker compose --env-file compose.env`. A compose key written into
  `.env` makes the application fail to start with a `ValidationError`.
- The committed test suite must pass with no Docker service running. Tests that
  need live PostgreSQL or Redis belong in the CI `readiness` job.
- Alembic takes its URL from the validated settings (`DATABASE_URL`); no
  connection string belongs in `alembic.ini`.
- The scaffold's migration history is empty by design because no business entity
  exists yet. Do not add a placeholder table to make it look populated.

## Contract changes

`/api/v1/openapi.json` is the contract frontends generate from. Any change to a
response model or route is a contract change: regenerate the clients, call it
out in the commit message, and update `README.md` when the endpoint table
changes.

## Error and logging conventions

- Client-facing errors keep the stable `{"error": "<code>", "message": "<text>"}`
  shape. Add new codes to the maps in `core/errors.py` rather than one-off
  responses.
- Never return a raw exception message to a client.
- Log through the configured JSON logging; it redacts credentials before any
  handler sees a record. Do not bypass it with `print()` or a private handler.
