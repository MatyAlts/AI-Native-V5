"""integrity-attestation-service — registro externo auditable del CTR (ADR-021).

Recibe attestation requests del ctr-service (cuando un episodio se cierra),
firma con clave Ed25519 institucional, y appendea a `attestations-YYYY-MM-DD.jsonl`.

Este servicio es **infraestructura interna del piloto**: NO se expone al
api-gateway publico. Solo el ctr-service (autenticado por mTLS o IP allowlist)
puede emitir POST. La verificacion la hace un auditor externo con la pubkey
+ tool CLI `scripts/verify-attestations.py`.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from integrity_attestation_service.config import settings
from integrity_attestation_service.observability import setup_observability
from integrity_attestation_service.routes import attestations, health
from integrity_attestation_service.services.signing import load_keypair_with_failsafe

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_observability(app)

    # Carga de claves Ed25519 + failsafe contra deploy con dev key en produccion
    private_key, public_key, pubkey_id = load_keypair_with_failsafe(
        private_path=settings.attestation_private_key_path,
        public_path=settings.attestation_public_key_path,
        environment=settings.environment,
    )
    app.state.signing = {
        "private_key": private_key,
        "public_key": public_key,
        "pubkey_id": pubkey_id,
    }
    logger.info(
        "attestation_keys_loaded environment=%s pubkey_id=%s",
        settings.environment,
        pubkey_id,
    )
    yield


app = FastAPI(
    title="integrity-attestation-service",
    description="Registro externo auditable del CTR (ADR-021)",
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
app.include_router(attestations.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "integrity-attestation-service",
        "version": "0.1.0",
        "status": "operational",
        "adr": "ADR-021",
    }
