"""Tests del wizard IA de ejercicios (`POST /api/v1/ejercicios/generate`).

ADR-047 + ADR-048. Foco: el manejo del pool de conexiones (P-9 / A2.4).

Invoca `generate_ejercicio` directamente (unit-style). El handler ya NO recibe
`db` por parámetro: abre una sesión DB CORTA para resolver la materia y la
cierra ANTES de las llamadas al LLM (que pueden tardar hasta 3×90s). Sin eso,
una conexión del pool (~8) queda retenida toda la generación y bajo concurrencia
se agota el pool.

Mock approach: patch `AIGatewayClient` + `GovernanceClient` a nivel de
`ai_clients`, `_retrieve_rag_context` (para no pegar al content-service) y
`tenant_session` (para ceder un mock de AsyncSession y trackear apertura).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from academic_service.auth.dependencies import User
from academic_service.config import settings
from academic_service.routes.ejercicios import (
    EjercicioGenerateRequest,
    generate_ejercicio,
)
from academic_service.routes.tareas_practicas import RagContext
from academic_service.services.ai_clients import CompleteResult, PromptConfig
from fastapi import HTTPException


def _user() -> User:
    return User(
        id=uuid4(),
        tenant_id=uuid4(),
        email="docente@utn.edu.ar",
        roles=frozenset({"docente"}),
        realm="utn",
    )


def _mock_db_returning(materia: object | None) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = materia
    db.execute = AsyncMock(return_value=result)
    return db


def _patch_tenant_session(db: object, tracker: dict | None = None):
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


def _patch_rag(rag: RagContext | None = None):
    """RAG deshabilitado por default: sin contexto, 0 chunks, hash None."""
    return patch(
        "academic_service.routes.tareas_practicas._retrieve_rag_context",
        new=AsyncMock(return_value=rag or RagContext(context="", n_chunks=0, chunks_hash=None)),
    )


def _good_request() -> EjercicioGenerateRequest:
    return EjercicioGenerateRequest(
        materia_id=uuid4(),
        descripcion_nl="Ejercicio de listas en Python para principiantes.",
        unidad_tematica="Estructuras de datos",
        dificultad="basica",
    )


def _good_prompt() -> PromptConfig:
    return PromptConfig(
        name="ejercicio_generator",
        version="v1.0.0",
        content="Sos un asistente que genera ejercicios en JSON.",
        hash="a" * 64,
    )


def _good_complete_result(content: str) -> CompleteResult:
    return CompleteResult(
        content=content,
        model="google/gemini-2.0-flash",
        provider="google",
        feature="ejercicio_generator",
        input_tokens=90,
        output_tokens=300,
        cost_usd=0.001,
        cache_hit=False,
    )


_GOOD_BORRADOR = (
    '{"titulo": "Sumar lista", "enunciado": "Sumar los numeros de una lista.",'
    ' "dificultad": "intermedia", "unidad_tematica": "otra"}'
)


async def test_materia_inexistente_devuelve_400() -> None:
    user = _user()
    db = _mock_db_returning(None)
    req = _good_request()

    with _patch_tenant_session(db), pytest.raises(HTTPException) as exc_info:
        await generate_ejercicio(req=req, user=user)

    assert exc_info.value.status_code == 400


async def test_happy_path_devuelve_borrador_con_overrides() -> None:
    user = _user()
    db = _mock_db_returning(MagicMock())
    req = _good_request()

    fake_governance = MagicMock()
    fake_governance.get_prompt = AsyncMock(return_value=_good_prompt())
    fake_ai = MagicMock()
    fake_ai.complete = AsyncMock(return_value=_good_complete_result(_GOOD_BORRADOR))

    with (
        _patch_tenant_session(db),
        _patch_rag(),
        patch(
            "academic_service.services.ai_clients.GovernanceClient",
            return_value=fake_governance,
        ),
        patch(
            "academic_service.services.ai_clients.AIGatewayClient",
            return_value=fake_ai,
        ),
    ):
        resp = await generate_ejercicio(req=req, user=user)

    # El handler sobreescribe unidad_tematica/dificultad con las del request y
    # marca created_via_ai (no confía esos campos al LLM).
    assert resp.borrador["unidad_tematica"] == "Estructuras de datos"
    assert resp.borrador["dificultad"] == "basica"
    assert resp.borrador["created_via_ai"] is True
    assert resp.provider_used == "google"
    assert resp.tokens_input == 90

    call = fake_ai.complete.await_args
    assert call.kwargs["feature"] == "ejercicio_generator"
    assert call.kwargs["materia_id"] == req.materia_id


async def test_sesion_db_cerrada_durante_llamada_llm() -> None:
    """P-9 / A2.4: la sesión DB debe estar CERRADA cuando se pega al LLM."""
    user = _user()
    db = _mock_db_returning(MagicMock())
    req = _good_request()
    tracker: dict = {"open": False}
    seen_open_during_llm: list[bool] = []

    async def _capture(**kwargs):
        seen_open_during_llm.append(tracker["open"])
        return _good_complete_result(_GOOD_BORRADOR)

    fake_governance = MagicMock()
    fake_governance.get_prompt = AsyncMock(return_value=_good_prompt())
    fake_ai = MagicMock()
    fake_ai.complete = AsyncMock(side_effect=_capture)

    with (
        _patch_tenant_session(db, tracker),
        _patch_rag(),
        patch(
            "academic_service.services.ai_clients.GovernanceClient",
            return_value=fake_governance,
        ),
        patch(
            "academic_service.services.ai_clients.AIGatewayClient",
            return_value=fake_ai,
        ),
    ):
        await generate_ejercicio(req=req, user=user)

    assert seen_open_during_llm == [False], (
        "la sesión DB seguía abierta durante la llamada al LLM (regresión P-9)"
    )


# ── Truncamiento por techo de tokens de salida ───────────────────────
#
# Incidente 2026-07-27 en prod: el wizard devolvía 502 con
# "LLM devolvió JSON inválido", que apuntaba al prompt. El JSON estaba bien
# formado — venía CORTADO a mitad de string porque el modelo agotaba el
# `max_tokens` (8192, ~28.700 chars). El log mostraba los 3 intentos fallando
# en el mismo punto (~26.5k-29.2k chars): determinista, reintentar no servía.


def _truncated_complete_result(output_tokens: int) -> CompleteResult:
    """Respuesta cortada a mitad de string, con el presupuesto agotado."""
    return CompleteResult(
        content='{"titulo": "Sistema de Control de Inventario", "enunciado_md": "Una ferrete',
        model="google/gemini-2.5-flash-lite",
        provider="google",
        feature="ejercicio_generator",
        input_tokens=90,
        output_tokens=output_tokens,
        cost_usd=0.01,
        cache_hit=False,
    )


def _run_generate_with(fake_ai):
    """Arma el contexto de patches comun y devuelve la corutina del handler."""
    fake_governance = MagicMock()
    fake_governance.get_prompt = AsyncMock(return_value=_good_prompt())
    return (
        _patch_tenant_session(_mock_db_returning(MagicMock())),
        _patch_rag(),
        patch(
            "academic_service.services.ai_clients.GovernanceClient",
            return_value=fake_governance,
        ),
        patch(
            "academic_service.services.ai_clients.AIGatewayClient",
            return_value=fake_ai,
        ),
    )


async def test_respuesta_truncada_falla_en_un_solo_intento() -> None:
    """Truncamiento = determinista: NO se reintenta (no quema 3 llamadas al LLM)."""
    cap = settings.ejercicio_generator_max_tokens
    fake_ai = MagicMock()
    fake_ai.complete = AsyncMock(return_value=_truncated_complete_result(cap))

    patches = _run_generate_with(fake_ai)
    with patches[0], patches[1], patches[2], patches[3], pytest.raises(HTTPException) as exc_info:
        await generate_ejercicio(req=_good_request(), user=_user())

    assert exc_info.value.status_code == 502
    assert fake_ai.complete.await_count == 1, (
        "el truncamiento se detecta al primer intento: reintentar falla igual"
    )
    # El mensaje tiene que apuntar al techo de tokens, NO al prompt.
    detail = exc_info.value.detail
    assert "limite de tokens" in detail
    assert str(cap) in detail


async def test_json_invalido_sin_truncar_si_reintenta() -> None:
    """Control: JSON malformado con presupuesto de sobra SI agota los 3 intentos."""
    fake_ai = MagicMock()
    # output_tokens muy por debajo del cap => no es truncamiento, es basura.
    fake_ai.complete = AsyncMock(return_value=_truncated_complete_result(42))

    patches = _run_generate_with(fake_ai)
    with patches[0], patches[1], patches[2], patches[3], pytest.raises(HTTPException) as exc_info:
        await generate_ejercicio(req=_good_request(), user=_user())

    assert exc_info.value.status_code == 502
    assert fake_ai.complete.await_count == 3, "sin truncamiento el retry sigue vivo"


async def test_rag_no_semantico_deja_rastro_en_el_log(caplog) -> None:
    """Incidente 2026-07-27: dos prompts distintos → el mismo ejercicio.

    El `chunks_used_hash` venía idéntico y no había forma de distinguir un
    índice con vectores mock (ranking = ruido determinista, mismos chunks para
    cualquier query) de "hay menos material que top_k". Ahora queda en el log.
    """
    fake_ai = MagicMock()
    fake_ai.complete = AsyncMock(return_value=_good_complete_result(_GOOD_BORRADOR))
    rag_mock = RagContext(
        context="material",
        n_chunks=5,
        chunks_hash="324de3bd",
        is_semantic=False,
        embedder_model="mock-deterministic",
        chunk_names=("apunte-u1.pdf",),
    )

    fake_governance = MagicMock()
    fake_governance.get_prompt = AsyncMock(return_value=_good_prompt())

    with (
        _patch_tenant_session(_mock_db_returning(MagicMock())),
        _patch_rag(rag_mock),
        patch(
            "academic_service.services.ai_clients.GovernanceClient",
            return_value=fake_governance,
        ),
        patch(
            "academic_service.services.ai_clients.AIGatewayClient",
            return_value=fake_ai,
        ),
        caplog.at_level("WARNING"),
    ):
        await generate_ejercicio(req=_good_request(), user=_user())

    assert "rag_no_semantico_en_generacion" in caplog.text
    assert "mock-deterministic" in caplog.text


async def test_rag_semantico_no_ensucia_el_log(caplog) -> None:
    """Control: con retrieval real no se emite el warning."""
    fake_ai = MagicMock()
    fake_ai.complete = AsyncMock(return_value=_good_complete_result(_GOOD_BORRADOR))
    rag_mock = RagContext(
        context="material",
        n_chunks=5,
        chunks_hash="abc123",
        is_semantic=True,
        embedder_model="gemini-embedding-001",
    )

    fake_governance = MagicMock()
    fake_governance.get_prompt = AsyncMock(return_value=_good_prompt())

    with (
        _patch_tenant_session(_mock_db_returning(MagicMock())),
        _patch_rag(rag_mock),
        patch(
            "academic_service.services.ai_clients.GovernanceClient",
            return_value=fake_governance,
        ),
        patch(
            "academic_service.services.ai_clients.AIGatewayClient",
            return_value=fake_ai,
        ),
        caplog.at_level("WARNING"),
    ):
        await generate_ejercicio(req=_good_request(), user=_user())

    assert "rag_no_semantico_en_generacion" not in caplog.text


async def test_max_tokens_sale_de_settings_y_no_esta_hardcodeado() -> None:
    """Anti-regresión: el 8192 hardcodeado fue la causa raíz del incidente."""
    fake_ai = MagicMock()
    fake_ai.complete = AsyncMock(return_value=_good_complete_result(_GOOD_BORRADOR))

    patches = _run_generate_with(fake_ai)
    with patches[0], patches[1], patches[2], patches[3]:
        await generate_ejercicio(req=_good_request(), user=_user())

    assert (
        fake_ai.complete.await_args.kwargs["max_tokens"] == settings.ejercicio_generator_max_tokens
    )
