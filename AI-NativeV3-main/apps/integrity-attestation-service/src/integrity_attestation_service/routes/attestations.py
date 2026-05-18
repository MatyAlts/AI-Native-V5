"""Endpoints del integrity-attestation-service (ADR-021).

POST /api/v1/attestations         — recibe del ctr-service (interno)
GET  /api/v1/attestations/pubkey  — pubkey activa en formato PEM (publico)
GET  /api/v1/attestations/{date}  — JSONL del dia YYYY-MM-DD (publico, para auditores)

Auth: el POST NO usa JWT/Casbin — es servicio-a-servicio. En produccion del
piloto se restringe por IP allowlist a nivel red. Los GETs son publicos por
diseno: la informacion de las attestations (hashes + firmas) es lo que
buscamos que sea verificable por terceros.
"""

from __future__ import annotations

import logging
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from integrity_attestation_service.config import settings
from integrity_attestation_service.services.journal import (
    Attestation,
    append_attestation,
    now_utc_z,
    raw_jsonl_for_date,
)
from integrity_attestation_service.services.signing import (
    SCHEMA_VERSION,
    compute_canonical_buffer,
    sign_buffer,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/attestations", tags=["attestations"])

_DATE_STR_LEN = 10  # "YYYY-MM-DD"


# ── Request / Response models ─────────────────────────────────────────


class AttestationRequest(BaseModel):
    """Payload del ctr-service al cerrar un episodio."""

    episode_id: UUID
    tenant_id: UUID
    final_chain_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    total_events: int = Field(ge=1)
    ts_episode_closed: str = Field(description="ISO-8601 UTC con sufijo Z")


# ── Helpers para acceder al estado del servicio ───────────────────────


def _signing_state(request: Request) -> tuple[Ed25519PrivateKey, Ed25519PublicKey, str]:
    """Recupera (priv, pub, pubkey_id) inyectados por lifespan en `app.state`."""
    state = getattr(request.app.state, "signing", None)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Signing keys not loaded. Verify ATTESTATION_PRIVATE_KEY_PATH.",
        )
    return state["private_key"], state["public_key"], state["pubkey_id"]


# ── POST: emitir attestation ──────────────────────────────────────────


@router.post("", response_model=Attestation, status_code=status.HTTP_201_CREATED)
async def create_attestation(
    req: AttestationRequest,
    request: Request,
) -> Attestation:
    """Firma + appendea al JSONL del dia. Idempotencia gestionada por el caller
    (ctr-service usa `event_uuid` como dedup key del bus Redis).

    Validacion del `ts_episode_closed` se delega a `compute_canonical_buffer`
    — debe terminar en `Z`.
    """
    private_key, _, pubkey_id = _signing_state(request)

    try:
        canonical = compute_canonical_buffer(
            episode_id=req.episode_id,
            tenant_id=req.tenant_id,
            final_chain_hash=req.final_chain_hash,
            total_events=req.total_events,
            ts_episode_closed=req.ts_episode_closed,
            schema_version=SCHEMA_VERSION,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    signature = sign_buffer(private_key, canonical)
    attestation = Attestation(
        episode_id=str(req.episode_id),
        tenant_id=str(req.tenant_id),
        final_chain_hash=req.final_chain_hash,
        total_events=req.total_events,
        ts_episode_closed=req.ts_episode_closed,
        ts_attested=now_utc_z(),
        signer_pubkey_id=pubkey_id,
        signature=signature,
        schema_version=SCHEMA_VERSION,
    )

    path = append_attestation(settings.attestation_log_dir, attestation)
    logger.info(
        "attestation_signed episode_id=%s tenant_id=%s pubkey_id=%s journal=%s",
        attestation.episode_id,
        attestation.tenant_id,
        pubkey_id,
        path.name,
    )
    return attestation


# ── GET: pubkey activa ────────────────────────────────────────────────


@router.get("/pubkey", response_class=PlainTextResponse)
async def get_pubkey(request: Request) -> PlainTextResponse:
    """Devuelve la pubkey activa en formato PEM. Publica por diseno —
    auditores la usan para verificar firmas con `verify-attestations.py`."""
    _, public_key, pubkey_id = _signing_state(request)
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return PlainTextResponse(
        content=pem.decode("utf-8"),
        headers={"X-Signer-Pubkey-Id": pubkey_id},
    )


# ── GET: JSONL del dia ────────────────────────────────────────────────


@router.get("/{day}")
async def get_attestations_for_date(day: str) -> Response:
    """Devuelve el JSONL crudo del dia `YYYY-MM-DD`. 404 si no existe.

    Sirve los bytes EXACTOS escritos al disco — los auditores procesan
    bit-exact lo que el verificador externo va a parsear.
    """
    # Validacion de formato YYYY-MM-DD para evitar path traversal
    if len(day) != _DATE_STR_LEN or day[4] != "-" or day[7] != "-":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="day must be in YYYY-MM-DD format",
        )
    try:
        for part, length in [(day[:4], 4), (day[5:7], 2), (day[8:10], 2)]:
            int(part)
            if len(part) != length:
                raise ValueError
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="day must be in YYYY-MM-DD format with numeric parts",
        ) from e

    raw = raw_jsonl_for_date(settings.attestation_log_dir, day)
    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No attestations for {day}",
        )
    # Content-Type application/x-ndjson es el estandar para JSONL
    return Response(content=raw, media_type="application/x-ndjson")
