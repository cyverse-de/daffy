set shell := ["bash", "-uc"]

# Install all dependencies (including dev) into the project venv.
install:
    uv sync

# Lint with ruff.
lint:
    uv run ruff check .

# Auto-format with ruff.
fmt:
    uv run ruff format .

# Type-check with pyright.
typecheck:
    uv run pyright

# Run the test suite.
test:
    uv run pytest

# Lint, type-check, and test.
check: lint typecheck test

# Build the daffy process-wrapper image.
build-daffy-image tag="daffy:latest":
    docker build --network host -f Dockerfile.daffy -t {{tag}} .

# Build the Scrooge aggregator image.
build-scrooge-image tag="scrooge:latest":
    docker build --network host -f Dockerfile.scrooge -t {{tag}} .
