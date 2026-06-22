FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# Put the venv's console scripts on PATH so the binaries run directly (no uv sync at
# container start).
ENV PATH="/app/.venv/bin:$PATH"

# Scrooge persists here by default; mount a volume at /data to keep logs across restarts.
ENV SCROOGE_STORAGE_DIR=/data/scrooge \
    SCROOGE_DB=/data/scrooge.duckdb
EXPOSE 9494

# One image runs both binaries; choose the command at run time, e.g.:
#   docker run <image> daffy  --service my-svc -- my-server --port 8080
#   docker run <image> scrooge --quack-port 9494 --token my-shared-token
