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

# Build the container image (runs both daffy and scrooge; pick the command at run time).
build-image tag="daffy:latest":
    docker build --network host -t {{tag}} .
