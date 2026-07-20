# Build stage: install dependencies with uv
FROM python:3.12-slim AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN --mount=from=ghcr.io/astral-sh/uv:latest,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --no-install-project --no-dev

COPY . /app
WORKDIR /app
RUN --mount=from=ghcr.io/astral-sh/uv:latest,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --all-packages --no-dev

# Runtime stage: distroless python
FROM python:3.12-slim

COPY --from=builder /app /app
WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Script dispatcher: arranca server HTTP (CTR_MODE=server default) o worker
# (CTR_MODE=worker + CTR_WORKER_PARTITION=N). Robusto contra overrides de
# docker-compose (EasyPanel) que pisarian el `command:` del compose y
# dejarian al python ejecutandose desde /usr/bin/ sin el venv activo.
COPY --from=builder /app/apps/ctr-service/docker-entrypoint.sh /usr/local/bin/ctr-entrypoint
RUN chmod +x /usr/local/bin/ctr-entrypoint

ENTRYPOINT ["/usr/local/bin/ctr-entrypoint"]
