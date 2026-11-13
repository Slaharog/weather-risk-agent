# One long-lived service: API, chat page and (later) the alert scheduler in one process.
# Base: official Python 3.12 slim image; uv binary copied from its official image (pinned).
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.3 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Dependencies first, in their own layer, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Then the project itself (code, hub config, committed seed snapshot).
COPY . .
RUN uv sync --locked --no-dev

# Railway sets PORT; the CLI reads it. DATA_DIR (refreshed data, later SQLite) is set to the
# volume's mount path as a Railway variable, so it is not baked into the image.
CMD ["python", "-m", "weather_risk", "serve", "--host", "0.0.0.0"]
