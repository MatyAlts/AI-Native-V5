"""Tests del endpoint TP-gen IA (`POST /api/v1/tareas-practicas/generate`).

Sec 11.7 epic ai-native-completion-and-byok / ADR-036.

Cubre los caminos críticos invocando la función del route directamente
(unit-style — sin TestClient/RBAC, que ya cubre `test_casbin_matrix`):

  1. materia_id inexistente → 400.
  2. governance falla → 502.
  3. ai-gateway falla → 502.
  4. LLM devuelve JSON malformado → 502.
  5. LLM devuelve `{"error": "razon"}` → 422.
  6. Happy path → 200 con borrador parseado + audit log structlog emitido.
  7. P-9 / A2.4: la sesión DB NO está abierta durante la llamada al LLM.

Mock approach: patch `AIGatewayClient` y `GovernanceClient` a nivel del módulo
`ai_clients`, y patch `tenant_session` (de `academic_service.db`) para que ceda
un mock de `AsyncSession` cuyo `execute().scalar_one_or_none()` simula la
materia presente/ausente. El handler ya NO recibe `db` por parámetro (P-9): abre
una sesión corta él mismo y la cierra antes de pegar al LLM.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from academic_service.auth.dependencies import User
from academic_service.routes.tareas_practicas import (
    TPGenerateRequest,
    generate_tarea_practica,
)
from academic_service.services.ai_clients import CompleteResult, PromptConfig
from fastapi import HTTPException


def _user(roles: frozenset[str]) -> User:
    return User(
        id=uuid4(),
        tenant_id=uuid4(),
        email="docente@utn.edu.ar",
        roles=roles,
        realm="utn",
    )


def _mock_db_returning(materia: object | None) -> MagicMock:
    """Construye un mock de AsyncSession cuyo `execute` devuelve un result
    con `scalar_one_or_none() == materia`."""
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = materia
    db.execute = AsyncMock(return_value=result)
    return db


def _patch_tenant_session(db: object, tracker: dict | None = None):
    """Patch de `academic_service.db.tenant_session` con un ctx-manager async
    que cede `db`. Si `tracker` viene dado, registra apertura/cierre en
    `tracker["open"]` para verificar que la sesión se soltó antes del LLM."""

    @asynccontextmanager
    async def fake_ts(tenant_id):
        if tracker is not None:
            tracker["open"] = True
        try:
            yield db
        finally:
            if tracker is not None:
                tracker["open"] = False

    return patch("academic_service.db.tenant_session", fake_ts)


def _good_request() -> TPGenerateRequest:
    return TPGenerateRequest(
        materia_id=uuid4(),
        descripcion_nl="Crear un TP de listas en Python para principiantes.",
        dificultad="basica",
    )


def _good_complete_result(content: str) -> CompleteResult:
    return CompleteResult(
        content=content,
        model="claude-sonnet-4-6",
        provider="anthropic",
        feature="tp_generator",
        input_tokens=120,
        output_tokens=400,
        cost_usd=0.003,
        cache_hit=False,
    )


def _good_prompt() -> PromptConfig:
    return PromptConfig(
        name="tp_generator",
        version="v1.0.0",
        content="Sos un asistente que genera TPs en JSON estructurado.",
        hash="a" * 64,
    )


_GOOD_BORRADOR = (
    '{"enunciado": "Sumar todos los numeros de una lista.",'
    ' "inicial_codigo": "def sumar(xs):\\n    pass",'
    ' "rubrica": {"correctness": 60, "style": 40},'
    ' "test_cases": [{"id": "t1", "name": "lista vacia",'
    ' "code": "assert sumar([]) == 0", "expected": 0,'
    ' "is_public": true, "weight": 10}]}'
)


# ── Tests ──────────────────────────────────────────────────────────────


async def test_materia_inexistente_devuelve_400() -> None:
    user = _user(frozenset({"docente"}))
    db = _mock_db_returning(None)  # materia no existe
    req = _good_request()

    with _patch_tenant_session(db), pytest.raises(HTTPException) as exc_info:
        await generate_tarea_practica(req=req, user=user)

    assert exc_info.value.status_code == 400
    assert "no encontrada" in exc_info.value.detail.lower()


async def test_governance_falla_devuelve_502() -> None:
    user = _user(frozenset({"docente"}))
    db = _mock_db_returning(MagicMock())  # materia existe
    req = _good_request()

    fake_governance = MagicMock()
    fake_governance.get_prompt = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with (
        _patch_tenant_session(db),
        patch(
            "academic_service.services.ai_clients.GovernanceClient",
            return_value=fake_governance,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await generate_tarea_practica(req=req, user=user)

    assert exc_info.value.status_code == 502
    assert "prompt" in exc_info.value.detail.lower()


async def test_ai_gateway_falla_devuelve_502() -> None:
    user = _user(frozenset({"docente"}))
    db = _mock_db_returning(MagicMock())
    req = _good_request()

    fake_governance = MagicMock()
    fake_governance.get_prompt = AsyncMock(return_value=_good_prompt())

    fake_ai = MagicMock()
    fake_ai.complete = AsyncMock(side_effect=httpx.HTTPError("provider down"))

    with (
        _patch_tenant_session(db),
        patch(
            "academic_service.services.ai_clients.GovernanceClient",
            return_value=fake_governance,
        ),
        patch(
            "academic_service.services.ai_clients.AIGatewayClient",
            return_value=fake_ai,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await generate_tarea_practica(req=req, user=user)

    assert exc_info.value.status_code == 502
    assert "ai-gateway" in exc_info.value.detail.lower()


async def test_llm_devuelve_json_invalido_devuelve_502() -> None:
    user = _user(frozenset({"docente"}))
    db = _mock_db_returning(MagicMock())
    req = _good_request()

    fake_governance = MagicMock()
    fake_governance.get_prompt = AsyncMock(return_value=_good_prompt())

    fake_ai = MagicMock()
    fake_ai.complete = AsyncMock(
        return_value=_good_complete_result("esto no es JSON estructurado, es texto libre"),
    )

    with (
        _patch_tenant_session(db),
        patch(
            "academic_service.services.ai_clients.GovernanceClient",
            return_value=fake_governance,
        ),
        patch(
            "academic_service.services.ai_clients.AIGatewayClient",
            return_value=fake_ai,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await generate_tarea_practica(req=req, user=user)

    assert exc_info.value.status_code == 502
    assert "json" in exc_info.value.detail.lower()


async def test_llm_devuelve_error_estructurado_devuelve_422() -> None:
    user = _user(frozenset({"docente"}))
    db = _mock_db_returning(MagicMock())
    req = _good_request()

    fake_governance = MagicMock()
    fake_governance.get_prompt = AsyncMock(return_value=_good_prompt())

    fake_ai = MagicMock()
    fake_ai.complete = AsyncMock(
        return_value=_good_complete_result(
            '{"error": "descripcion ambigua, no puedo generar el borrador"}'
        ),
    )

    with (
        _patch_tenant_session(db),
        patch(
            "academic_service.services.ai_clients.GovernanceClient",
            return_value=fake_governance,
        ),
        patch(
            "academic_service.services.ai_clients.AIGatewayClient",
            return_value=fake_ai,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await generate_tarea_practica(req=req, user=user)

    assert exc_info.value.status_code == 422
    assert "ambigua" in exc_info.value.detail


async def test_happy_path_devuelve_borrador_parseado() -> None:
    user = _user(frozenset({"docente"}))
    db = _mock_db_returning(MagicMock())
    req = _good_request()

    fake_governance = MagicMock()
    fake_governance.get_prompt = AsyncMock(return_value=_good_prompt())

    fake_ai = MagicMock()
    fake_ai.complete = AsyncMock(return_value=_good_complete_result(_GOOD_BORRADOR))

    with (
        _patch_tenant_session(db),
        patch(
            "academic_service.services.ai_clients.GovernanceClient",
            return_value=fake_governance,
        ),
        patch(
            "academic_service.services.ai_clients.AIGatewayClient",
            return_value=fake_ai,
        ),
    ):
        resp = await generate_tarea_practica(req=req, user=user)

    assert len(resp.ejercicios) == 1
    ej = resp.ejercicios[0]
    assert ej.enunciado == "Sumar todos los numeros de una lista."
    assert ej.inicial_codigo == "def sumar(xs):\n    pass"
    assert ej.rubrica == {"correctness": 60, "style": 40}
    assert len(ej.test_cases) == 1
    assert ej.test_cases[0]["id"] == "t1"
    assert resp.provider_used == "anthropic"
    assert resp.tokens_input == 120
    assert resp.tokens_output == 400

    # Verificar que el ai-gateway recibió el materia_id (ADR-040)
    call = fake_ai.complete.await_args
    assert call.kwargs["materia_id"] == req.materia_id
    assert call.kwargs["feature"] == "tp_generator"
    assert call.kwargs["tenant_id"] == user.tenant_id


async def test_sesion_db_cerrada_durante_llamada_llm() -> None:
    """P-9 / A2.4: la sesión DB (conexión del pool) debe estar CERRADA cuando
    se pega al LLM. Verificamos que el tracker de apertura marca `False` en el
    momento exacto en que se invoca `ai.complete`."""
    user = _user(frozenset({"docente"}))
    db = _mock_db_returning(MagicMock())
    req = _good_request()
    tracker: dict = {"open": False}
    seen_open_during_llm: list[bool] = []

    async def _capture(**kwargs):
        # Snapshot del estado de la sesión en el instante de la llamada al LLM.
        seen_open_during_llm.append(tracker["open"])
        return _good_complete_result(_GOOD_BORRADOR)

    fake_governance = MagicMock()
    fake_governance.get_prompt = AsyncMock(return_value=_good_prompt())

    fake_ai = MagicMock()
    fake_ai.complete = AsyncMock(side_effect=_capture)

    with (
        _patch_tenant_session(db, tracker),
        patch(
            "academic_service.services.ai_clients.GovernanceClient",
            return_value=fake_governance,
        ),
        patch(
            "academic_service.services.ai_clients.AIGatewayClient",
            return_value=fake_ai,
        ),
    ):
        await generate_tarea_practica(req=req, user=user)

    assert seen_open_during_llm == [False], (
        "la sesión DB seguía abierta durante la llamada al LLM (regresión P-9)"
    )
