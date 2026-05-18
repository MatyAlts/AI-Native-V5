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
    uv sync --no-dev

# Runtime stage: distroless python
FROM gcr.io/distroless/python3-debian12:nonroot

COPY --from=builder --chown=nonroot:nonroot /app /app
WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8009

ENTRYPOINT ["/app/.venv/bin/python", "-m", "uvicorn", "content_service.main:app", "--host", "0.0.0.0", "--port", "8009"]
