# syntax=docker/dockerfile:1
# Container image for the ecom-be application.
#
# Build and run it with the local dependencies from compose.yaml, or point
# DATABASE_URL and REDIS_URL at the services reachable from the container.
# Both are read from the environment at runtime; no credential, and no
# connection string, is baked into or documented literally in this image.
#
#   docker build -t ecom-be .
#   docker run --rm -p 8000:8000 --network host \
#     -e DATABASE_URL=... -e REDIS_URL=... ecom-be
#
# The runtime environment supplies its own configuration.

FROM python:3.11-slim-bookworm AS builder

# uv is the only dependency manager this project uses.
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /build

# Install dependencies first so the layer is cached while only source changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=README.md,target=README.md \
    uv sync --locked --no-dev --no-install-project

COPY uv.lock pyproject.toml README.md ./
COPY app ./app

# Install the project itself, non-editable, from the locked environment.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


FROM python:3.11-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN useradd --create-home --uid 1001 --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Migration assets, so the image can apply its own schema in a deploy step.
# Settings validation requires the full configuration, so pass both URLs:
#   docker run --rm --network host \
#     -e DATABASE_URL=... -e REDIS_URL=... ecom-be alembic upgrade head
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

USER app

EXPOSE 8000

# The liveness endpoint performs no I/O, so it is a safe container health probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3).read()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
