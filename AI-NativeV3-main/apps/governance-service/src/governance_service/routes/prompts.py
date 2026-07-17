"""Endpoints del governance-service.

GET  /api/v1/active_configs            → manifest global
GET  /api/v1/prompts/{name}/{version}  → contenido + hash del prompt
POST /api/v1/prompts/{name}/{version}/verify → recomputa hash vs declarado
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from governance_service.auth import require_gateway_auth
from governance_service.config import settings
from governance_service.services.prompt_loader import PromptLoader

# Auth a nivel router (A0.4): todos los endpoints de prompts/configs exigen
# procedencia probada cuando `require_gateway_signature` está ON. Con el flag
# OFF (default) el dependency es no-op y no rompe al tutor-service. `/health`
# vive en otro router y queda abierto (probes de k8s).
router = APIRouter(
    prefix="/api/v1",
    tags=["governance"],
    dependencies=[Depends(require_gateway_auth)],
)


@lru_cache(maxsize=1)
def get_loader() -> PromptLoader:
    return PromptLoader(Path(settings.prompts_repo_path))


class PromptOut(BaseModel):
    name: str
    version: str
    content: str
    hash: str
    path: str


class VerifyResult(BaseModel):
    name: str
    version: str
    valid: bool
    computed_hash: str
    message: str


@router.get("/active_configs")
async def active_configs() -> dict:
    return get_loader().active_configs()


@router.get("/prompts/{name}/{version}", response_model=PromptOut)
async def get_prompt(name: str, version: str) -> PromptOut:
    try:
        cfg = get_loader().load(name, version)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        # Hash mismatch → el servicio no puede operar con esto
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prompt integrity compromised: {e}",
        )
    return PromptOut(
        name=cfg.name,
        version=cfg.version,
        content=cfg.content,
        hash=cfg.hash,
        path=cfg.path,
    )


@router.post("/prompts/{name}/{version}/verify", response_model=VerifyResult)
async def verify_prompt(name: str, version: str) -> VerifyResult:
    try:
        cfg = get_loader().load(name, version)
        return VerifyResult(
            name=name,
            version=version,
            valid=True,
            computed_hash=cfg.hash,
            message="Hash verificado correctamente",
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        return VerifyResult(
            name=name,
            version=version,
            valid=False,
            computed_hash="",
            message=str(e),
        )
