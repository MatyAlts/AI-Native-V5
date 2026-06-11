"""Tests del HANDLER `POST /api/v1/classify_episode/{episode_id}`.

Estos tests complementan `test_persist_classification_idempotent.py` (que cubre
la funcion de servicio) verificando que el HTTP layer respeta el contrato de
idempotencia documentado en CLAUDE.md / backlog QA 2026-05-07:

> POST /classify_episode/{id} no es idempotente: re-POST devuelve 500 con
> duplicate-key, deberia responder no-op con la classification existente.

Contrato verificado:
  - Test A: episodio nuevo (sin classification previa) -> 201 CREATED.
  - Test B: re-POST con MISMO classifier_config_hash -> 200 OK con la
    classification existente (idempotente, NO se viola UniqueConstraint).
  - Test C: re-POST con classifier_config_hash DISTINTO (simula bump
    LABELER_VERSION o profile cambiado) -> 201 CREATED con nueva fila;
    la vieja queda con `is_current=false` (append-only ADR-010).
  - Test D: race condition con IntegrityError -> 200 OK con la fila ganadora
    (recovery via rollback + re-SELECT, no se filtra el 500 al cliente).

Estrategia: mockeamos `tenant_session` (con un AsyncSession fake) y la HTTP
roundtrip al ctr-service via patch de `_fetch_episode_from_ctr`. El handler
corre tal cual contra esos doubles — la logica de SELECT-then-decide es
DB-agnostica y testeable a nivel route.
"""

from __future__ import annotations

import contextlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from classifier_service.main import app
from classifier_service.models import Classification
from classifier_service.services.pipeline import compute_classifier_config_hash
from classifier_service.services.tree import DEFAULT_REFERENCE_PROFILE
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

# ── Constantes del seed (replican el contrato del api-gateway) ───────────

DOCENTE_USER_ID = UUID("11111111-1111-1111-1111-111111111111")
TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


def _auth_headers() -> dict[str, str]:
    return {
        "X-User-Id": str(DOCENTE_USER_ID),
        "X-Tenant-Id": str(TENANT_ID),
        "X-User-Email": "docente@utn.test",
        "X-User-Roles": "docente",
    }


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_classification(
    *,
    episode_id: UUID,
    comision_id: UUID,
    classifier_config_hash: str,
    is_current: bool = True,
) -> Classification:
    """Construye una fila Classification persistida (como si viniera de DB)."""
    return Classification(
        id=42,
        tenant_id=TENANT_ID,
        episode_id=episode_id,
        comision_id=comision_id,
        classifier_config_hash=classifier_config_hash,
        appropriation="apropiacion_superficial",
        appropriation_reason="caso de prueba",
        ct_summary=0.5,
        ccd_mean=0.5,
        ccd_orphan_ratio=0.3,
        cii_stability=0.4,
        cii_evolution=0.4,
        features={"k": 1},
        is_current=is_current,
    )


def _fake_episode_payload(episode_id: UUID, comision_id: UUID) -> dict[str, Any]:
    """Payload que devolveria el ctr-service para `_fetch_episode_from_ctr`.

    Lista de eventos minima que pasa el classifier y devuelve un resultado
    deterministico. Lo que importa para estos tests es el contrato HTTP del
    handler, no la calidad del pipeline.
    """
    return {
        "episode_id": str(episode_id),
        "comision_id": str(comision_id),
        "events": [
            {
                "seq": 0,
                "event_type": "episodio_abierto",
                "ts": "2026-09-01T10:00:00Z",
                "payload": {},
            },
            {
                "seq": 1,
                "event_type": "episodio_cerrado",
                "ts": "2026-09-01T10:05:00Z",
                "payload": {"reason": "completed"},
            },
        ],
    }


def _make_session(
    *,
    existing_first_select: Classification | None,
    persist_raises: Exception | None = None,
    existing_second_select: Classification | None = None,
) -> Any:
    """Mock de AsyncSession para el handler.

    - `existing_first_select`: lo que devuelve el SELECT idempotente que
      hace el handler ANTES de pegarle al CTR (pre-check).
    - `persist_raises`: si se setea, `session.flush()` lanza esa exception
      (simulando race condition con IntegrityError post-pre-SELECT).
    - `existing_second_select`: lo que devuelve el SELECT post-rollback en
      el recovery path del race-condition guard.

    El mock usa un contador interno para distinguir el primer SELECT (pre-CTR
    en el handler) del segundo SELECT (post-rollback). El SELECT que hace
    `persist_classification` internamente cuenta como el "segundo" en orden,
    pero en los tests de race-condition simulamos que ese SELECT no encuentra
    nada (por eso intenta INSERT).
    """
    session = MagicMock()
    session.added_rows = []
    session.commit = AsyncMock(return_value=None)
    session.rollback = AsyncMock(return_value=None)

    select_call_count = {"n": 0}

    def _add(obj: Any) -> None:
        session.added_rows.append(obj)

    session.add = _add

    async def _flush() -> None:
        if persist_raises is not None:
            raise persist_raises

    session.flush = _flush

    async def _execute(stmt: Any, *args: Any, **kwargs: Any) -> Any:
        repr_stmt = str(stmt).strip().upper()
        if repr_stmt.startswith("SELECT SET_CONFIG") or "SET_CONFIG" in repr_stmt:
            # set_config de RLS — devolvemos un Result vacio
            return MagicMock()
        if repr_stmt.startswith("SELECT"):
            select_call_count["n"] += 1
            res = MagicMock()
            if select_call_count["n"] == 1:
                # Primer SELECT: pre-check idempotencia del handler
                res.scalar_one_or_none = MagicMock(return_value=existing_first_select)
            elif select_call_count["n"] == 2:
                # Segundo SELECT: el que hace persist_classification
                # internamente (idempotency check del service layer).
                # En todos los tests del archivo este SELECT no encuentra
                # nada para forzar el INSERT/race path (si encontrara, ya
                # habria cortado en el pre-check del handler).
                res.scalar_one_or_none = MagicMock(return_value=None)
            else:
                # Tercer SELECT en adelante: recovery post-rollback
                res.scalar_one_or_none = MagicMock(return_value=existing_second_select)
            return res
        # UPDATE u otros: devolver Result vacio
        return MagicMock()

    session.execute = _execute
    return session


@contextlib.asynccontextmanager
async def _fake_tenant_session(session: Any, _tenant_id: UUID) -> Any:
    yield session


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Test A: episodio nuevo -> 201 CREATED ────────────────────────────────


@pytest.mark.asyncio
async def test_classify_episode_201_cuando_no_existe(client: AsyncClient) -> None:
    """Primera clasificacion del episodio -> 201 CREATED."""
    episode_id = uuid4()
    comision_id = uuid4()
    session = _make_session(existing_first_select=None)

    with (
        patch(
            "classifier_service.routes.classify_ep.tenant_session",
            lambda tid: _fake_tenant_session(session, tid),
        ),
        patch(
            "classifier_service.routes.classify_ep._fetch_episode_from_ctr",
            AsyncMock(return_value=_fake_episode_payload(episode_id, comision_id)),
        ),
    ):
        r = await client.post(f"/api/v1/classify_episode/{episode_id}", headers=_auth_headers())

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["episode_id"] == str(episode_id)
    assert body["is_current"] is True
    # Se persistio una fila nueva (path INSERT)
    assert len(session.added_rows) == 1


# ── Test B: re-POST misma config -> 200 OK idempotente ───────────────────


@pytest.mark.asyncio
async def test_classify_episode_200_cuando_existe_misma_config(
    client: AsyncClient,
) -> None:
    """Re-POST con mismo (episode_id, classifier_config_hash) e
    is_current=true -> 200 OK con la classification existente.

    CRITICA: no debe haber fetch al CTR (ahorro de roundtrip) ni INSERT.
    """
    episode_id = uuid4()
    comision_id = uuid4()
    config_hash = compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE, "v1.0.0")
    existing = _make_classification(
        episode_id=episode_id,
        comision_id=comision_id,
        classifier_config_hash=config_hash,
        is_current=True,
    )
    session = _make_session(existing_first_select=existing)
    ctr_mock = AsyncMock()

    with (
        patch(
            "classifier_service.routes.classify_ep.tenant_session",
            lambda tid: _fake_tenant_session(session, tid),
        ),
        patch(
            "classifier_service.routes.classify_ep._fetch_episode_from_ctr",
            ctr_mock,
        ),
    ):
        r = await client.post(f"/api/v1/classify_episode/{episode_id}", headers=_auth_headers())

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["episode_id"] == str(episode_id)
    assert body["classifier_config_hash"] == config_hash
    assert body["is_current"] is True
    # No se persistio nada (idempotencia pura)
    assert session.added_rows == []
    # No se llamo al CTR (corte temprano por pre-check)
    ctr_mock.assert_not_called()


# ── Test C: re-POST con config distinta -> 201 reclasificacion ───────────


@pytest.mark.asyncio
async def test_classify_episode_201_cuando_cambia_config_hash(
    client: AsyncClient,
) -> None:
    """Re-POST con classifier_config_hash DISTINTO (bump LABELER_VERSION o
    profile cambiado) -> 201 CREATED con fila nueva.

    El pre-check NO encuentra nada (los hashes difieren), entonces
    `persist_classification` ejecuta el path de reclasificacion:
      UPDATE vieja is_current=false + INSERT nueva.

    Esto es comportamiento correcto (ADR-010 append-only): cross-version
    NO es idempotente por diseno.
    """
    episode_id = uuid4()
    comision_id = uuid4()
    # El pre-check busca por el config_hash CURRENT (v3.0.0). Como la fila
    # vieja tiene hash distinto, el pre-check devuelve None (mismo path que
    # el caso "episodio nuevo" en el handler — la distincion la hace
    # persist_classification, no el handler).
    session = _make_session(existing_first_select=None)

    with (
        patch(
            "classifier_service.routes.classify_ep.tenant_session",
            lambda tid: _fake_tenant_session(session, tid),
        ),
        patch(
            "classifier_service.routes.classify_ep._fetch_episode_from_ctr",
            AsyncMock(return_value=_fake_episode_payload(episode_id, comision_id)),
        ),
    ):
        r = await client.post(f"/api/v1/classify_episode/{episode_id}", headers=_auth_headers())

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["is_current"] is True
    # Se persistio UNA fila nueva
    assert len(session.added_rows) == 1
    new = session.added_rows[0]
    assert new.classifier_config_hash == compute_classifier_config_hash(
        DEFAULT_REFERENCE_PROFILE, "v3.0.0"
    )


# ── Test D: race condition con IntegrityError -> 200 OK recuperado ───────


@pytest.mark.asyncio
async def test_classify_episode_200_en_race_condition(client: AsyncClient) -> None:
    """Race condition: pre-check no encuentra fila, pero entre el SELECT y
    el INSERT otro POST concurrente gana e inserta. El UniqueConstraint
    revienta `flush()` con IntegrityError.

    Recovery: rollback + re-SELECT devuelve la fila ganadora -> 200 OK.
    NO se filtra el 500 duplicate-key al cliente.
    """
    episode_id = uuid4()
    comision_id = uuid4()
    config_hash = compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE, "v1.0.0")
    winner = _make_classification(
        episode_id=episode_id,
        comision_id=comision_id,
        classifier_config_hash=config_hash,
        is_current=True,
    )
    session = _make_session(
        existing_first_select=None,
        persist_raises=IntegrityError("INSERT", {}, Exception("duplicate key")),
        existing_second_select=winner,
    )

    with (
        patch(
            "classifier_service.routes.classify_ep.tenant_session",
            lambda tid: _fake_tenant_session(session, tid),
        ),
        patch(
            "classifier_service.routes.classify_ep._fetch_episode_from_ctr",
            AsyncMock(return_value=_fake_episode_payload(episode_id, comision_id)),
        ),
    ):
        r = await client.post(f"/api/v1/classify_episode/{episode_id}", headers=_auth_headers())

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["episode_id"] == str(episode_id)
    assert body["classifier_config_hash"] == config_hash
    # Se llamo rollback (recovery del race)
    session.rollback.assert_awaited()
