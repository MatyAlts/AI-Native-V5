"""ctr-service: persistencia del CTR criptográfico.

F3: expone API HTTP para publish/read/verify + workers particionados
que consumen del bus y persisten eventos con cadena SHA-256.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ctr_service.config import settings
from ctr_service.observability import setup_observability
from ctr_service.routes import events, health


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_observability(app)
    yield


app = FastAPI(
    title="ctr-service",
    description="Cuaderno de Trabajo Reflexivo — persistencia criptográfica",
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
app.include_router(events.router)
# ADR-031 (D.4): alias publicos del CTR bajo `/api/v1/audit/episodes/...`
# expuestos al frontend web-admin via api-gateway ROUTE_MAP.
app.include_router(events.audit_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "ctr-service",
        "version": "0.1.0",
        "status": "operational",
    }
