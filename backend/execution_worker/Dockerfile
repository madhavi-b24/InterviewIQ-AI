# syntax=docker/dockerfile:1
#
# The sandbox executor image — module §4/§5. Deliberately built from this
# directory only (docker-compose.yml's `build.context` points here, not at
# `backend/`) so there is no way for the main application's source,
# .env, or anything else from `backend/app/` to end up inside it, even by
# accident. This image never receives application secrets at runtime
# either (see docker-compose.yml — no env_file, no secret env vars).

FROM python:3.12-slim

# Language toolchains for the three supported languages (module §6) —
# python3 is already in the base image; add a headless JDK and g++.
# --no-install-recommends keeps the image (and therefore the attack
# surface) smaller; apt lists are removed in the same layer so they never
# ship in the final image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        default-jdk-headless \
        g++ \
    && rm -rf /var/lib/apt/lists/*

# Non-root user — mirrors backend/Dockerfile's appuser pattern exactly.
# Nothing in this image ever runs as root, including the candidate code
# subprocess spawned by sandbox_runner.py (it inherits this user, it never
# elevates).
RUN useradd --create-home --uid 1000 sandboxrunner
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only this directory's own three files — no COPY of backend/app anywhere
# in this Dockerfile, by construction.
COPY app.py languages.py sandbox_runner.py ./
RUN chown -R sandboxrunner:sandboxrunner /app

USER sandboxrunner

EXPOSE 8100
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8100"]
