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

# Runtime stage
FROM python:3.12-slim

COPY --from=builder /app /app
WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Sin migraciones en el arranque: este servicio NO tiene base propia (el estado
# de las ejecuciones vive en Redis y el resultado se persiste via CTR). Si
# alguna vez la tuviera, la migracion NO va acá con tolerancia a error — el
# patron de "arrancar igual si la migracion falla" convierte un despliegue roto
# en uno aparentemente exitoso (tarea 2.5 de la change).
ENTRYPOINT ["/app/.venv/bin/python", "-m", "uvicorn", "execution_service.main:app", "--host", "0.0.0.0", "--port", "8013"]
