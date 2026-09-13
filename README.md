# ecom-be

Async FastAPI backend for the ecommerce application.

## Requirements

- Python 3.11.x
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync
cp .env.example .env
```

The example environment file contains local development values only. Keep real
credentials in an untracked `.env` file or in the deployment environment.

## Checks

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```
