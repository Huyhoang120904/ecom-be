# ecom-be

Async FastAPI backend for the ecommerce application. Every I/O path — HTTP,
PostgreSQL, Redis — is asynchronous, and the scaffold ships with a validated
settings object, liveness/readiness endpoints, a generated OpenAPI contract,
Alembic migrations, local service definitions, and a container image.

## Requirements

- Python 3.11.x
- [uv](https://docs.astral.sh/uv/) (the only supported dependency manager)
- Docker with the Compose plugin (local PostgreSQL and Redis only)
- `gh` (optional), for reading the pushed GitHub state

## Install

```bash
uv sync
cp .env.example .env
```

`uv sync` installs the locked runtime and development dependencies into
`.venv`. Edit `.env` and replace both URL placeholders with your own local
service URLs: use the async driver `postgresql+asyncpg`, host `localhost`, and
the published ports `55432` (PostgreSQL) and `56379` (Redis) that
`compose.yaml` defaults to. Build the URLs from those parts rather than
committing a ready-made connection string.

`.env` holds **only** the keys `.env.example` lists (see
[Configuration](#configuration)). `Settings` requires
`DATABASE_URL` and `REDIS_URL` and rejects unknown keys, so a stale `.env` fails
fast at import time instead of at the first query. Compose variables such as
`POSTGRES_PORT` belong in `compose.env`, never in `.env` — see
[Two environment surfaces](#two-environment-surfaces).

`CORS_ORIGINS` is a JSON array of explicit origins; a `*` entry is refused
because the policy allows credentials.

`.env` is untracked. `.env.example` is credential-free by design — it holds
replaceable placeholders, and no connection string or real credential is ever
committed.

## Local services

`compose.yaml` starts **only** the local datastores, so the committed test suite
runs without Docker:

```bash
docker compose up -d --wait        # PostgreSQL 16 and Redis 7, both health-checked
docker compose ps                  # expect (healthy) for both
docker compose down                # leaves the named volumes intact
```

The credentials in `compose.yaml` (`app` / `app`) are disposable
local-development values with env-var overrides. They are deliberately obvious,
they are not production credentials, and they must never be reused outside a
throwaway developer machine. Host ports default to `55432` and `56379` so they
do not collide with another project already using `5432`/`6379`. Data lives in
the named volumes `postgres-data` and `redis-data`.

### Two environment surfaces

An application setting and a Compose variable are different things, and they
live in different files:

| File | Read by | Keys |
| --- | --- | --- |
| `.env` (untracked) | `Settings` via `env_file` | `APP_NAME`, `ENVIRONMENT`, `DATABASE_URL`, `REDIS_URL`, `CORS_ORIGINS` |
| `compose.env` (untracked) | `docker compose --env-file` | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`, `REDIS_PORT` |

`Settings` rejects unknown keys, so a compose variable written into `.env`
makes the application fail to start with
`ValidationError: postgres_port Extra inputs are not permitted` — an error that
looks unrelated to Compose. Never put a compose variable in `.env`.

To override the compose values, copy the tracked example and pass it explicitly:

```bash
cp compose.env.example compose.env
docker compose --env-file compose.env up -d --wait
```

Omitting `--env-file` is fine: with no `compose.env`, `compose.yaml` falls back
to its own defaults, and `--env-file` is what keeps the overrides out of the
application's `.env`. `compose.env.example` documents the same five keys.

The application container is defined separately in `Dockerfile`:

```bash
docker build -t ecom-be .
docker run --rm -p 8000:8000 --network host \
  -e DATABASE_URL="<your async PostgreSQL URL>" \
  -e REDIS_URL="<your Redis URL>" \
  ecom-be
```

Use the same URLs as `.env`; do not hardcode a connection string.

`docker compose up` does not build or start the application: local dependency
startup and application startup stay independent.

## Commands

| Task | Command |
| --- | --- |
| Install/refresh dependencies | `uv sync` |
| Format code | `uv run ruff format .` |
| Check formatting (CI gate) | `uv run ruff format --check .` |
| Lint | `uv run ruff check .` |
| Lint and auto-fix | `uv run ruff check --fix .` |
| Type-check | `uv run mypy src alembic` |
| Run the whole suite | `uv run pytest -q` |
| Run one test file | `uv run pytest -q tests/unit/test_config.py` |
| Run the database suite | `uv run pytest -q -m db` (needs `docker compose up -d --wait`) |
| Verify the lockfile | `uv lock --check` |
| Apply migrations | `uv run alembic upgrade head` |
| Show the current revision | `uv run alembic current` |
| Create a migration | `uv run alembic revision --autogenerate -m "add order table"` |
| Start the dev server | `uv run uvicorn ecom_be.main:app --reload --port 8000` |

Formatting, linting, and type-check rules live in `pyproject.toml`
(`[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]`) and are the same
rules CI runs.

### Two test runs

`uv run pytest -q` passes with no Docker service running. Tests that assert real
PostgreSQL behaviour — `citext`, the partial unique indexes, the `CHECK`
constraints — are marked `db`, and `addopts` excludes them by default so that
stays true. Run them explicitly against the compose database:

```bash
docker compose up -d --wait
uv run alembic upgrade head
uv run pytest -q -m db
```

Writing those assertions against SQLite would prove nothing: SQLite has no
`citext`, no partial-index semantics worth trusting, and no `gen_random_uuid`.


## Database migrations

Alembic reads the database URL from the validated application settings, so the
application and its migrations always use the same `DATABASE_URL`; no
connection string is stored in `alembic.ini`. The async engine is created with
`async_engine_from_config` (NullPool), so `uv run alembic upgrade head` runs the
real async driver.

Autogenerate compares the live database against a single named aggregation
point:

```
src/ecom_be/models/__init__.py
```

That module imports the shared declarative `Base` and every model module, and
exports the resulting `metadata` object, which is what `alembic/env.py` assigns
to `target_metadata`. A model class that is not imported there is invisible to
autogenerate.

The scaffold ships two revisions: an identity schema (accounts, shops, roles,
permissions, memberships, refresh tokens) and a seed that installs the permission
vocabulary and the three system roles. Adding a persisted feature means:

1. Write `src/ecom_be/models/<feature>.py`, declaring the model on
   `ecom_be.infrastructure.db.base.Base` and taking the mixins from
   `ecom_be.infrastructure.db.mixins` for the id and timestamp columns.
2. Import that model class in `src/ecom_be/models/__init__.py` and add its name
   to that file's `__all__`.
3. `uv run alembic revision --autogenerate -m "<change>"`, then **review the
   file by hand**, then `uv run alembic upgrade head`.

Autogenerate does emit `CHECK` constraints, which is convenient and easy to
assume wrongly in either direction — it does *not* emit `CREATE EXTENSION`, and
it cannot infer a partial index predicate you did not express in the model. The
identity revision therefore carries a hand-added `CREATE EXTENSION IF NOT EXISTS
citext` and hand-reviewed constraints.

`tests/unit/test_migration_metadata.py` fails if a model module in
`ecom_be/models/` is not imported by the aggregation view, so this step cannot
be forgotten silently.

`alembic/versions/` is tracked through a `.gitkeep` so revisions have a home.

## API contract

The OpenAPI document is served at `/api/v1/openapi.json` and is the single
source of truth for clients. Frontends generate their types from it:

```bash
uv run uvicorn ecom_be.main:app --host 127.0.0.1 --port 8000 &
curl --fail http://127.0.0.1:8000/api/v1/openapi.json -o openapi.json
```

Never hand-write a client type the schema already describes; regenerate instead.
Any change that alters a response model is a contract change and should be
called out in the commit message.

## Endpoints

Health is public so a probe needs no credential. The two media `GET`s are public
because an avatar and a shop background are shareable-by-intent images. Every
other route requires a bearer token.

| Endpoint | Auth | Purpose |
| --- | --- | --- |
| `GET /health/live` | public | I/O-free liveness; answers as long as the process is up |
| `GET /health/ready` | public | Readiness; probes PostgreSQL and Redis, `200` when both are `ok`, `503` with the same envelope otherwise |
| `GET /api/v1/openapi.json` | public | Generated OpenAPI document |
| `POST /api/v1/auth/register` | public | Create an account and its first shop, then sign in |
| `POST /api/v1/auth/login` | public | Start a session |
| `POST /api/v1/auth/refresh` | cookie | Rotate the refresh cookie and issue a new access token |
| `POST /api/v1/auth/logout` | cookie | End the session. Always `204` |
| `POST /api/v1/auth/switch-shop` | bearer | Move the session to another shop the caller belongs to |
| `GET /api/v1/auth/me` | bearer | The caller, their memberships, the active shop, effective permissions |
| `PATCH /api/v1/auth/me` | bearer | Update the caller's own profile; omitted keys are left alone |
| `POST /api/v1/auth/me/avatar` | bearer | Replace the avatar (`multipart/form-data`) |
| `DELETE /api/v1/auth/me/avatar` | bearer | Remove the avatar. Idempotent |
| `POST /api/v1/auth/deactivate` | bearer | Retire the account, confirmed by password. One-way |
| `PATCH /api/v1/shops/active` | `shop:update` | Update the active shop's profile |
| `POST /api/v1/shops/active/background` | `shop:update` | Replace the shop background |
| `DELETE /api/v1/shops/active/background` | `shop:update` | Remove the shop background. Idempotent |
| `DELETE /api/v1/shops/active` | `shop:update` | Retire the shop, confirmed by its exact name |
| `GET /api/v1/media/avatar/{user_id}.webp` | public | Serve an avatar |
| `GET /api/v1/media/shop-background/{shop_id}.webp` | public | Serve a shop background |

Every `2xx` response with a body is wrapped: `{"data": {...}}`. Errors are never
wrapped, and keep the `{"error": "<stable_code>", "message": "<safe text>"}`
shape. Internal exception details never reach a client, and logs are JSON with
credentials redacted before any handler sees them.

Two mechanical gates hold the contract to that: a string property with no
`maxLength` and a `2xx` body that is not a `BaseResponse` subclass both fail the
suite.

## Media

An avatar is normalized to a 512 x 512 WebP and a shop background to 1600 x 900,
centre-cropped, with the EXIF block dropped. Dropping EXIF is not cosmetic: a
phone photo carries GPS coordinates, and serving a seller's home location from a
public endpoint is a privacy leak.

Objects are keyed by a content digest, so a byte-identical re-upload is a no-op
rather than a duplicate, and the URL is versioned by that digest so a replaced
image is never served from a cache.

Storage is a local directory (`MEDIA_ROOT`, default `.media/`, gitignored) behind
the `StorageBackend` protocol in `src/ecom_be/infrastructure/storage/local.py`.
That protocol is the single swap point for object storage. **Mount `MEDIA_ROOT`
as a volume**: a local directory inside a container does not survive a redeploy.

| Setting | Default | Meaning |
| --- | --- | --- |
| `MEDIA_ROOT` | `.media` | Where objects are written |
| `MEDIA_BASE_URL` | empty | The origin used in returned URLs. Empty means "use the request's own origin" |
| `MAX_UPLOAD_BYTES` | `2097152` (2 MiB) | The upload cap, enforced before any decode |

## Configuration

`.env` holds exactly these keys; `Settings` rejects anything else.

| Key | Required | Default | Meaning |
| --- | --- | --- | --- |
| `APP_NAME` | no | `ecom-be` | Reported by `/health/live` |
| `ENVIRONMENT` | no | `development` | `development` relaxes the refresh cookie's `Secure` flag |
| `DATABASE_URL` | yes | — | Async PostgreSQL DSN (`postgresql+asyncpg`) |
| `REDIS_URL` | yes | — | Redis DSN |
| `CORS_ORIGINS` | no | `()` | JSON array of explicit origins; `*` is refused |
| `JWT_SECRET` | yes | — | Access-token signing secret, at least 32 characters |
| `ACCESS_TOKEN_TTL_SECONDS` | no | `900` | Access-token lifetime |
| `REFRESH_TOKEN_TTL_SECONDS` | no | `2592000` | Refresh-token lifetime (30 days) |

## Project layout

The application is layered, not module-packaged: every feature contributes one
file to each layer, and the layer a change belongs in is decided by what it does
rather than by which feature it serves.

```
src/ecom_be/
├── main.py                     # app factory, lifespan, middleware wiring
├── config/settings.py          # the validated settings object
├── core/                       # cross-cutting concerns: errors.py, logging.py
├── infrastructure/             # external systems
│   ├── db/base.py              # the single declarative Base
│   ├── db/mixins.py            # id and timestamp column mixins
│   ├── db/session.py           # async engine + request-scoped session factory
│   ├── db/urls.py              # configparser-safe DSN escaping for Alembic
│   ├── cache/redis.py          # async Redis client factory
│   ├── security/passwords.py   # Argon2 hashing and verification
│   └── storage/local.py        # the StorageBackend protocol and its local adapter
├── models/                     # ORM models, one module per feature
│   ├── __init__.py             # imports every model; the Alembic target_metadata
│   └── identity.py             # users, shops, roles, permissions, memberships, tokens
├── schemas/                    # pydantic transport shapes, one module per feature
│   ├── common.py               # the BaseResponse envelope
│   ├── identity.py             # request and response models
│   └── health.py
├── repositories/               # database operations, one module per owning model
│   ├── user.py                 # statements against users
│   ├── shop.py                 # statements against shops
│   ├── role.py                 # roles and permissions (read-only lookups)
│   ├── membership.py           # memberships + the permission resolution
│   └── refresh_token.py        # refresh token lifecycle
├── services/                   # use cases
│   ├── identity/               # one module per seam, composed by IdentityService
│   │   ├── __init__.py         # the composite facade
│   │   ├── auth.py             # register, login, refresh, logout, switch-shop
│   │   ├── account.py          # the caller's own profile, avatar, deactivation
│   │   ├── shop.py             # the active shop's profile and retirement
│   │   └── session.py          # the Session result and issue_session
│   ├── rate_limit.py           # cross-feature Redis limiter
│   ├── media.py
│   └── health.py
├── errors/                     # domain errors, one module per feature
│   ├── identity.py
│   └── media.py
├── constants/                  # contract bounds, one module per feature
│   └── identity.py
├── utils/                      # pure helpers, one module per feature
│   ├── identity.py
│   ├── media.py
│   └── health.py
└── api/                        # HTTP transport
    ├── deps.py                 # shared dependencies, guards, and health probes
    ├── principal.py            # the framework-free resolved caller
    ├── media_urls.py           # stored object key -> URL
    └── v1/
        ├── __init__.py         # composes the feature routers; adds no behavior
        ├── health.py
        ├── media.py
        └── identity/           # one module per resource area
            ├── __init__.py     # assembles `router` and `shops_router`
            ├── common.py       # shared response mappers and the refresh cookie
            ├── auth.py         # register, login, refresh, logout, switch-shop
            ├── profile.py      # /auth/me read, update, and deactivation
            ├── media_uploads.py# the caller's avatar
            └── shops.py        # the active shop's profile and background
```

A layer file exists only when the feature has something to put in it, and a layer
that outgrows one file becomes a package of them: `services/identity/` is split by
use-case seam, and `repositories/` is one module per owning model. `media` and
`health` persist nothing, so they contribute no model, no repository, and no
constants.

### Layer rules

- **Routes never perform persistence.** A router in `api/v1/` declares the HTTP
  contract, resolves dependencies, and delegates. No SQLAlchemy session is
  touched and no query is built in a route.
- **Services own use cases.** A `services/<feature>.py` holds the business
  decision — which repository calls happen, in what order, and what the outcome
  means. It is async and takes its collaborators through its constructor, so it
  can be tested with fakes and without a database. A feature whose use cases span
  several aggregates grows a `services/<feature>/` package with one module per
  seam plus a composite facade that keeps a single entry point.
- **Repositories own database operations.** `repositories/<model>.py` is the only
  place that executes statements or builds queries against the session, one module
  per owning model rather than per feature, so a table's statements have exactly
  one home. Repositories take a session and never commit on their own; the
  transaction boundary belongs to the service.
- **`utils/<feature>.py` stays pure.** Deterministic helpers only: no I/O, no
  session, no `httpx`/`redis` client, no request object.
- **All I/O is async.** Database access uses `AsyncSession`, Redis uses
  `redis.asyncio`, and outbound HTTP uses an async client. A synchronous driver
  call inside a coroutine blocks the event loop and is treated as a defect.
- **Schemas are transport types.** A `schemas/<feature>.py` defines the API
  boundary; ORM models stay out of responses and are mapped explicitly.

### Wiring a new feature

1. Add the layer files the feature needs: `models/<feature>.py`,
   `repositories/<model>.py` (one per owning model), `services/<feature>.py`,
   `errors/<feature>.py`, `constants/<feature>.py`, `utils/<feature>.py`,
   `schemas/<feature>.py`, and a router under `api/v1/`.
2. Register the router in `src/ecom_be/api/v1/__init__.py` with
   `api_router.include_router(...)`; that file only composes routers and adds no
   behavior of its own.
3. Reuse the request-scoped session from `ecom_be.infrastructure.db.session` and
   the lifecycle-owned Redis client from `app.state`; do not create clients per
   request.
4. If the feature persists data, add `models/<feature>.py`, import the model
   class in `src/ecom_be/models/__init__.py` (the Alembic metadata aggregation
   point), and generate a migration.
5. Add unit tests under `tests/unit/` and API tests under `tests/integration/`.

## Continuous integration

`.github/workflows/ci.yml` runs three jobs on GitHub Actions:

- `quality` — `ruff format --check .`, `ruff check .`, `mypy src alembic`, `uv lock --check`
- `tests` — `uv run pytest -q`, with no external services started (the `db`-marked
  tests are deselected by `addopts`, so this job needs no database)
- `readiness` — starts PostgreSQL 16 and Redis 7 service containers, applies
  `alembic upgrade head`, boots the app, polls `/health/ready` until it is
  healthy, and verifies `/health/live` plus the OpenAPI document

The `readiness` job is the only job that starts datastores, which keeps the
committed test suite runnable on a machine with no Docker. It is also where
`uv run pytest -q -m db` belongs: the `db` suite needs the same migrated database
this job already builds.

## Contributing

See `AGENTS.md` for the short list of contributor rules. Never commit `.env`,
credentials, connection strings, or generated caches; add a migration for any
schema change; and run the four gates plus `uv lock --check` before pushing.
