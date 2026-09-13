# ecom-be contributor guidance

## Ground rules

- Target Python 3.11.x and manage dependencies with `uv`. Do not add a second
  dependency manager or hand-edit `uv.lock`.
- Keep application code under `app` and tests under `tests`.
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
app/
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
├── schemas/                    # transport shapes (common.py BaseResponse, one module per flow)
├── repositories/               # database operations, one module per owning model
├── services/                   # use cases, one module per service
├── errors/                     # domain errors, one module per feature
├── constants/                  # contract bounds, grouped by the subject they bound
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
reference: `models/identity.py`, `repositories/{user,shop,role,membership,refresh_token}_repository.py`,
`services/{identity,auth,account,shop,session}_service.py`, `errors/identity.py`,
`constants/identity/{account,shop,rbac,media}.py`, `utils/identity.py`,
`schemas/identity/{common,auth,profile,shop}.py`, and
`api/v1/identity/`. The names are literal — a feature never invents another
shape. Layers a feature has nothing for are simply absent (`media` and `health`
persist nothing, so they have no model, no repository, and no constants), and a
feature that outgrows one module splits per owning model in `repositories/`, per
use-case seam in `services/`, per flow in `schemas/`, or per subject in
`constants/`.

Schema module names follow the router's flow names, so `schemas/identity/shop.py`
belongs to the flow `api/v1/identity/shops.py` serves. Constants are grouped by the
subject they bound instead, because a bound is not a flow: `EMAIL_MAX` governs both
registration and a shop's contact address, and the role and permission bounds belong
to no flow at all.

Both packages re-export their contents from `__init__.py` with an explicit
`__all__` (`no_implicit_reexport` makes an unlisted re-export a type error), so a
caller writes `from app.schemas.identity import MeData` and never needs to know
which flow module a model lives in.

### The response envelope

`schemas/common.py` declares the one `BaseResponse`, and every route applies it
directly as `response_model=BaseResponse[YourData]`. It carries `status_code`
(echoing the HTTP status the route returned), `message`, and `data`. Do not add a
per-endpoint envelope subclass: that convention existed only to keep the generic's
type-variable name out of the published schema names, and it cost a class per
endpoint plus a parallel naming convention in the frontend's generated types.
`tests/unit/test_openapi_envelope.py` holds the document to this and pins the
envelope's own fields.

Errors are not enveloped: they keep `{"error", "message"}` from `core/errors.py`.

### Layer rules

- **Routes do not perform persistence.** A router in `api/v1/` defines the HTTP
  contract, resolves dependencies, and calls a service. It never opens a query,
  builds a statement, or calls `commit()`. HTTP-only concerns (the refresh
  cookie, response mappers) stay in that router package's `common.py`.
- **Services own use cases.** A service decides what happens: which repository
  calls run, in what order, and what the result means. Collaborators arrive
  through the constructor so services are testable without a database. When a
  feature's use cases span several aggregates, split them per seam
  (`services/{auth,account,shop}_service.py`) and keep the composite
  (`IdentityService` in `services/identity_service.py`) as the single entry point,
  so routers and tests are not rewritten when a seam moves.
- **Repositories own database operations, one module per owning model.**
  `repositories/<model>_repository.py` is the only layer that executes statements
  against that table, so a table's SQL has exactly one home. It receives a session
  and never commits implicitly — one request-scoped session is yielded per request
  with no implicit commit, so a use case decides transaction boundaries
  explicitly, and a use case that writes four tables still commits once.
- **`utils/<feature>.py` is pure.** Deterministic helpers with no I/O, no
  session, no client, and no request object.
- **All I/O is async.** `AsyncSession` for PostgreSQL, `redis.asyncio` for
  Redis, an async HTTP client for outbound calls. Blocking the event loop from a
  coroutine is a defect, not a style preference.
- **Schemas define the API boundary.** ORM models are never returned directly;
  `schemas/<feature>.py` models are the contract and are what
  `/api/v1/openapi.json` publishes. Every route response is
  `BaseResponse[<payload>]`, never a bare payload and never a new envelope class.

### Adding a feature

1. Add the layer files the feature needs, named for the feature, in each layer
   directory above — one repository module per owning model.
2. Register the router from `app/api/v1/__init__.py`; that file only
   composes routers.
3. Take the request-scoped session and the lifecycle-owned Redis client from
   application state; do not build per-request clients.
4. For persisted data: write `models/<feature>.py` on the shared `Base`, then
   import the model class in `app/models/__init__.py` — the single
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
