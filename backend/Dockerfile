# syntax=docker/dockerfile:1

# --- Builder: resolve and install dependencies with uv into a venv ---
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, so this layer only invalidates when pyproject.toml/uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev

# --- Runtime: slim image, no build toolchain, non-root user ---
FROM python:3.12-slim AS runtime

RUN useradd --create-home --uid 1000 appuser
WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/app /app/app
COPY --from=builder --chown=appuser:appuser /app/alembic /app/alembic
COPY --from=builder --chown=appuser:appuser /app/alembic.ini /app/alembic.ini

# RESUME_STORAGE_LOCAL_DIR (default ./data/resumes, Module 3) resolves
# under /app — WORKDIR created /app as root, and only the COPYs above were
# chowned to appuser, so appuser can't mkdir directly under /app at
# runtime. Pre-create it here, owned by appuser, so LocalResumeStorage's
# runtime mkdir(exist_ok=True) is a no-op instead of a PermissionError.
RUN mkdir -p /app/data/resumes && chown -R appuser:appuser /app/data

ENV PATH="/app/.venv/bin:$PATH"
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
