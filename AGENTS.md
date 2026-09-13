# ecom-be contributor guidance

- Target Python 3.11.x and manage dependencies with `uv`.
- Keep application code under `src/ecom_be` and tests under `tests`.
- Run `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`,
  and `uv run mypy src` before committing.
- Never commit `.env`, credentials, or other secrets; update `.env.example` with
  safe local placeholders when configuration changes.
- Keep changes scoped to the requested task and avoid adding business behavior
  without a corresponding test.
