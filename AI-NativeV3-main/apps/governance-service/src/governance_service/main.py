"""governance-service: prompts versionados con verificación de hash."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from governance_service.config import settings
from governance_service.observability import setup_observability
from governance_service.routes import health, prompts


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_observability(app)
    yield


app = FastAPI(
    title="governance-service",
    description="Custodia de prompts versionados con verificación criptográfica",
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
app.include_router(prompts.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "governance-service", "version": "0.1.0", "status": "operational"}
