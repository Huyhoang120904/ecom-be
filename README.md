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

`.env` holds **only** the five keys `.env.example` lists. `Settings` requires
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
| Type-check | `uv run mypy src` |
| Run the whole suite | `uv run pytest -q` |
| Run one test file | `uv run pytest -q tests/unit/test_config.py` |
| Verify the lockfile | `uv lock --check` |
| Apply migrations | `uv run alembic upgrade head` |
| Show the current revision | `uv run alembic current` |
| Create a migration | `uv run alembic revision --autogenerate -m "add order table"` |
| Start the dev server | `uv run uvicorn ecom_be.main:app --reload --port 8000` |

Formatting, linting, and type-check rules live in `pyproject.toml`
(`[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]`) and are the same
rules CI runs. `uv run pytest -q` passes without any Docker service running.

## Database migrations

Alembic reads the database URL from the validated application settings, so the
application and its migrations always use the same `DATABASE_URL`; no
connection string is stored in `alembic.ini`. The async engine is created with
`async_engine_from_config` (NullPool), so `uv run alembic upgrade head` runs the
real async driver.

Autogenerate compares the live database against a single named aggregation
point:

```
src/ecom_be/infrastructure/db/models.py
```

That module imports the shared declarative `Base` and every module's ORM
models, and exports the resulting `metadata` object, which is what
`alembic/env.py` assigns to `target_metadata`. A model class that is not
imported there is invisible to autogenerate.

The scaffold has an empty migration history on purpose: the health module has
no ORM business model, and inventing a table just to make the history look
populated would be fake data. Adding the first persisted module means:

1. Write `modules/<module_name>/models.py`, declaring the model on
   `ecom_be.infrastructure.db.base.Base`.
2. Import that model class in `src/ecom_be/infrastructure/db/models.py` and add
   its name to that file's `__all__`.
3. `uv run alembic revision --autogenerate -m "<change>"`, then
   `uv run alembic upgrade head`.

`tests/unit/test_migration_metadata.py` fails if a module ships a `models.py`
that the aggregation point does not import, so this step cannot be forgotten
silently.

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

| Endpoint | Purpose |
| --- | --- |
| `GET /health/live` | I/O-free liveness; answers as long as the process is up |
| `GET /health/ready` | Readiness; probes PostgreSQL and Redis, `200` when both are `ok`, `503` with `{"status": "not_ready"}` otherwise |
| `GET /api/v1/openapi.json` | Generated OpenAPI document |

Errors are returned as `{"error": "<stable_code>", "message": "<safe text>"}`.
Internal exception details never reach a client, and logs are JSON with
credentials redacted before any handler sees them.

## Module template

Every feature module lives under `src/ecom_be/modules/<module_name>/` and has
exactly these files:

```
src/ecom_be/modules/<module_name>/
├── __init__.py         # one-line module docstring
├── models.py           # SQLAlchemy ORM models on the shared Base
├── schemas/
│   ├── __init__.py
│   ├── request.py      # incoming payload models
│   └── response.py     # outgoing payload models
├── utils.py            # pure helpers: no I/O, no framework imports
├── repository.py       # all database operations for this module
├── services.py         # use cases; orchestrates repositories and clients
└── router.py           # HTTP routes; calls services through dependencies
```

`models.py` may be omitted while a module has no persisted entity — the health
module is the example — but the other files are part of the template and a new
module that needs persistence adds `models.py`, not a new schema strategy.

### Layer rules

- **Routes never perform persistence.** `router.py` declares the HTTP
  contract, resolves dependencies, and delegates. No SQLAlchemy session is
  touched and no query is built in a route.
- **Services own use cases.** `services.py` holds the business decision — which
  repository calls happen, in what order, and what the outcome means. It is
  async and takes its collaborators through its constructor, so it can be
  tested with fakes and without a database.
- **Repositories own database operations.** `repository.py` is the only place
  that executes statements or builds queries against the session. It takes a
  session (or a factory) in its constructor and never commits on its own.
- **`utils.py` stays pure.** Deterministic helpers only: no I/O, no session, no
  `httpx`/`redis` client, no request object.
- **All I/O is async.** Database access uses `AsyncSession`, Redis uses
  `redis.asyncio`, and outbound HTTP uses an async client. A synchronous driver
  call inside a coroutine blocks the event loop and is treated as a defect.
- **Schemas are transport types.** `schemas/request.py` and
  `schemas/response.py` define the API boundary; ORM models stay out of
  responses and are mapped explicitly.

### Wiring a new module

1. Create the directory and files above.
2. Register the routes in `src/ecom_be/api/router.py` with
   `api_router.include_router(<module>.router)`; that file only composes
   modules and adds no behavior of its own.
3. Reuse the request-scoped session from `ecom_be.infrastructure.db.session` and
   the lifecycle-owned Redis client from `app.state`; do not create clients per
   request.
4. If the module persists data, add `models.py`, import the model class in
   `src/ecom_be/infrastructure/db/models.py` (the Alembic metadata aggregation
   point), and generate a migration.
5. Add unit tests under `tests/unit/` and API tests under
   `tests/integration/`.

## Continuous integration

`.github/workflows/ci.yml` runs three jobs on GitHub Actions:

- `quality` — `ruff format --check .`, `ruff check .`, `mypy src`, `uv lock --check`
- `tests` — `uv run pytest -q`, with no external services started
- `readiness` — starts PostgreSQL 16 and Redis 7 service containers, applies
  `alembic upgrade head`, boots the app, polls `/health/ready` until it is
  healthy, and verifies `/health/live` plus the OpenAPI document lists
  `/health/live` and `/health/ready`

The `readiness` job is the only job that starts datastores, which keeps the
committed test suite runnable on a machine with no Docker.

## Contributing

See `AGENTS.md` for the short list of contributor rules. Never commit `.env`,
credentials, connection strings, or generated caches; add a migration for any
schema change; and run the four gates plus `uv lock --check` before pushing.
