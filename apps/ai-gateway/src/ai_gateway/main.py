"""ai-gateway: routing unificado a LLMs con budget + caché."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_gateway.config import settings
from ai_gateway.observability import setup_observability
from ai_gateway.routes import byok, complete, health


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_observability(app)
    yield


app = FastAPI(
    title="ai-gateway",
    description="Gateway unificado de invocaciones a LLMs con budget y caché",
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
app.include_router(complete.router)
app.include_router(byok.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "ai-gateway", "version": "0.1.0", "status": "operational"}
