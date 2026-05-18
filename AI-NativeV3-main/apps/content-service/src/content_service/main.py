"""content-service: ingesta de materiales + RAG retrieval."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from content_service.config import settings
from content_service.observability import setup_observability
from content_service.routes import health, materiales, retrieve


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_observability(app)
    yield


app = FastAPI(
    title="content-service",
    description="Ingesta de materiales y retrieval RAG para el tutor",
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
app.include_router(materiales.router)
app.include_router(retrieve.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "content-service",
        "version": "0.1.0",
        "status": "operational",
    }
