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

Layered, not module-packaged: each feature contributes one file per layer it
needs, and a change's layer is decided by what the change does.

```
src/ecom_be/
├── main.py                     # app factory, lifespan, middleware wiring
├── config/settings.py          # the validated settings object
├── core/                       # cross-cutting: errors.py, logging.py
├── infrastructure/             # external systems
│   ├── db/base.py              # the single declarative Base
│   ├── db/mixins.py            # id and timestamp column mixins
│   ├── db/session.py           # async engine + request-scoped session factory
│   ├── db/urls.py              # configparser-safe DSN escaping for Alembic
│   ├── cache/redis.py          # async Redis client factory
│   ├── security/passwords.py   # Argon2 hashing and verification
│   └── storage/local.py        # StorageBackend protocol + local adapter
├── models/                     # ORM models, one module per feature
│   └── __init__.py             # imports every model; the Alembic target_metadata
├── schemas/                    # transport shapes (common.py envelope, one file per feature)
├── repositories/               # database operations, one module per feature
├── services/                   # use cases, one module per feature
├── errors/                     # domain errors, one module per feature
├── constants/                  # contract bounds, one module per feature
├── utils/                      # pure helpers, one module per feature
└── api/                        # HTTP transport
    ├── deps.py                 # shared dependencies, guards, health probes
    ├── principal.py            # the framework-free resolved caller
    ├── media_urls.py           # stored object key -> URL
    └── v1/                     # one router module per feature
```

`main.py` owns the lifespan: it creates the Redis client once and disposes the
engine once, with a nested `try/finally` so a Redis close failure still disposes
the database engine. Repositories and routes never create their own clients.

## Feature layers

A feature is a name that appears in whichever layers it needs. `identity` is the
reference: `models/identity.py`, `repositories/identity.py`,
`services/identity.py`, `errors/identity.py`, `constants/identity.py`,
`utils/identity.py`, `schemas/identity.py`, and
`api/v1/identity/`. The paths are literal — a feature never invents another
shape. Layers a feature has nothing for are simply absent (`media` and `health`
persist nothing, so they have no model, repository, or constants).

### Layer rules

- **Routes do not perform persistence.** A router in `api/v1/` defines the HTTP
  contract, resolves dependencies, and calls a service. It never opens a query,
  builds a statement, or calls `commit()`. HTTP-only concerns (the refresh
  cookie, response mappers) stay in that router package's `common.py`.
- **Services own use cases.** A service decides what happens: which repository
  calls run, in what order, and what the result means. Collaborators arrive
  through the constructor so services are testable without a database.
- **Repositories own database operations.** `repositories/<feature>.py` is the
  only layer that executes statements. It receives a session and never commits
  implicitly — one request-scoped session is yielded per request with no implicit
  commit, so a use case decides transaction boundaries explicitly.
- **`utils/<feature>.py` is pure.** Deterministic helpers with no I/O, no
  session, no client, and no request object.
- **All I/O is async.** `AsyncSession` for PostgreSQL, `redis.asyncio` for
  Redis, an async HTTP client for outbound calls. Blocking the event loop from a
  coroutine is a defect, not a style preference.
- **Schemas define the API boundary.** ORM models are never returned directly;
  `schemas/<feature>.py` models are the contract and are what
  `/api/v1/openapi.json` publishes.

### Adding a feature

1. Add the layer files the feature needs, named for the feature, in each layer
   directory above.
2. Register the router from `src/ecom_be/api/v1/__init__.py`; that file only
   composes routers.
3. Take the request-scoped session and the lifecycle-owned Redis client from
   application state; do not build per-request clients.
4. For persisted data: write `models/<feature>.py` on the shared `Base`, then
   import the model class in `src/ecom_be/models/__init__.py` — the single
   aggregation point `alembic/env.py` uses as `target_metadata` — and add its
   name to that file's `__all__`. Then
   `uv run alembic revision --autogenerate -m "..."` and
   `uv run alembic upgrade head`. A model not imported there is invisible to
   autogenerate; `tests/unit/test_migration_metadata.py` fails if a model module
   is missing from that view.
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
