"""tutor-service: orquesta prompt + retrieval + LLM + CTR."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tutor_service.config import settings
from tutor_service.observability import setup_observability
from tutor_service.routes import episodes, health
from tutor_service.services.abandonment_worker import run_abandonment_worker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_observability(app)

    # ADR-025 (G10-A): worker de abandono por timeout. Arranca despues
    # del setup de observabilidad para que sus logs/traces queden capturados.
    worker_task: asyncio.Task[None] | None = None
    if settings.enable_abandonment_worker:
        tutor = episodes._get_tutor()
        worker_task = asyncio.create_task(
            run_abandonment_worker(
                sessions=tutor.sessions,
                tutor=tutor,
                idle_timeout_seconds=settings.episode_idle_timeout_seconds,
                check_interval_seconds=settings.abandonment_check_interval_seconds,
            ),
            name="tutor.abandonment_worker",
        )

    try:
        yield
    finally:
        if worker_task is not None:
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task


app = FastAPI(
    title="tutor-service",
    description="Tutor socrático con streaming SSE y emisión de eventos CTR",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(episodes.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "tutor-service", "version": "0.1.0", "status": "operational"}
