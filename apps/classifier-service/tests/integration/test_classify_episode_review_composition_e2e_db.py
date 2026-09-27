"""Composición de `POST /classify_episode/{id}` + `POST .../review` BAJO EL
ROUTER completo, contra Postgres real (hueco end-to-end declarado en 3
informes seguidos — ronda de auditoría 2026-09-27, ronda 5, punto 4).

Las dos mitades ya están probadas contra Postgres real, pero cada una POR
SEPARADO:
  - El pre-check ancho de `_find_current_classification` (`classify_ep.py`):
    `tests/integration/test_find_current_classification_human_review_db.py`.
  - La exclusión de filas `revision_humana` en `persist_classification`
    (`pipeline.py`): `tests/integration/test_persist_classification_human_governance_db.py`.

Ninguno de los dos ejercita el `POST /classify_episode/{id}` REAL — con su
propio `require_role`, su propio `tenant_session`, su propio manejo de
`IntegrityError` — encadenado con una anulación humana real vía
`POST /classifications/{id}/review`. Este archivo cierra ESE hueco: llama a
los DOS endpoints HTTP en secuencia, vía `ASGITransport` contra la app real,
con `_fetch_episode_from_ctr` mockeado (el ctr-service no está levantado en
este entorno) pero el resto de la cadena — auth por headers, `tenant_session`
real, `persist_classification` real, `submit_review` real — sin mockear.

Usa DOS hashes de config distintos para forzar que la SEGUNDA llamada a
`classify_episode` (después de la anulación humana) NO tome el atajo del
pre-check idempotente (que ya está probado aparte) sino que atraviese la
lógica de gobernanza de `persist_classification` de punta a punta — que es
la composición que nadie había ejercitado bajo el router.
"""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from classifier_service.main import app

TEST_DB_URL = "postgresql+asyncpg://classifier_user:classifier_pass@127.0.0.1:5432/classifier_db"


def _postgres_available() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 5432), timeout=1):
            return True
    except OSError:
        return False


requires_local_postgres = pytest.mark.skipif(
    not _postgres_available(),
    reason="platform-postgres no está corriendo en 127.0.0.1:5432",
)


def _headers(role: str, tenant_id, user_id=None) -> dict[str, str]:
    return {
        "X-User-Id": str(user_id or uuid4()),
        "X-Tenant-Id": str(tenant_id),
        "X-User-Email": f"{role}@utn.test",
        "X-User-Roles": role,
    }


def _fake_episode_payload(episode_id, comision_id) -> dict:
    """Mínimo: 0 prompts -> el subgrupo no cae en `SUBGRUPOS_JUZGADOS_POR_JUEZ`
    y `_aplicar_juez_eje_fino` no llama al ai-gateway (mismo payload mínimo
    que usa `test_classify_episode_idempotent.py`)."""
    return {
        "episode_id": str(episode_id),
        "comision_id": str(comision_id),
        "events": [
            {"seq": 0, "event_type": "episodio_abierto", "ts": "2026-09-01T10:00:00Z", "payload": {}},
            {
                "seq": 1,
                "event_type": "episodio_cerrado",
                "ts": "2026-09-01T10:05:00Z",
                "payload": {"reason": "completed"},
            },
        ],
    }


@requires_local_postgres
@pytest.mark.asyncio
async def test_precheck_mas_gobernanza_bajo_el_router_completo() -> None:
    """RED verificado (ver informe): antes de los fixes de las rondas 3 y 4,
    este flujo devolvía 201 con `is_current` ausente/incorrecto tras la
    anulación humana (el pre-check viejo no encontraba la fila y
    `persist_classification` no excluía la fila humana del UPDATE). Con
    ambos fixes: 201 en las tres llamadas, `is_current` fiel en cada una.
    """
    tenant_id = uuid4()
    episode_id = uuid4()
    comision_id = uuid4()
    docente_headers = _headers("docente", tenant_id)

    # Todo el cuerpo va en un único try/finally: estos POSTs commitean de
    # verdad (vía `tenant_session` real, sin rollback) — el cleanup tiene
    # que correr AUNQUE cualquier assert falle, o un RED deja basura en
    # `classifier_db` (pasó exactamente eso verificando este mismo RED:
    # quedaron 3 `classifications` + 1 `classification_reviews` de la
    # corrida que falló a propósito, limpiadas a mano antes de escribir
    # este comentario).
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch(
                "classifier_service.routes.classify_ep._fetch_episode_from_ctr",
                AsyncMock(return_value=_fake_episode_payload(episode_id, comision_id)),
            ):
                # 1. Primera clasificación real, bajo el router completo.
                r1 = await client.post(
                    f"/api/v1/classify_episode/{episode_id}", headers=docente_headers
                )
                assert r1.status_code == 201, r1.text
                assert r1.json()["is_current"] is True

                # 2. Anulación humana real, bajo el OTRO router.
                r2 = await client.post(
                    f"/api/v1/classifications/{episode_id}/review",
                    json={"verdict": "apropiacion_reflexiva", "reason": "e2e composición"},
                    headers=docente_headers,
                )
                assert r2.status_code == 201, r2.text

                # 3. Reclasificación automática con hash NUEVO (simula el
                #    bump de tree_version del bloque 6) — fuerza que NO tome
                #    el atajo del pre-check idempotente (ya probado aparte)
                #    y atraviese la lógica de gobernanza de punta a punta.
                with patch(
                    "classifier_service.routes.classify_ep.compute_classifier_config_hash",
                    return_value="hash-e2e-post-bump-tree-version",
                ):
                    r3 = await client.post(
                        f"/api/v1/classify_episode/{episode_id}", headers=docente_headers
                    )
                assert r3.status_code == 201, r3.text
                assert r3.json()["is_current"] is False, (
                    "La composición completa bajo el router — pre-check "
                    "ancho más exclusión por `revision_humana` en "
                    "`persist_classification` — tiene que devolver "
                    "`is_current` fiel (False, porque un humano gobierna) "
                    "en la respuesta HTTP real, no solo en las dos mitades "
                    "probadas por separado contra Postgres."
                )
    finally:
        engine = create_async_engine(TEST_DB_URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await session.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tenant_id)}
            )
            await session.execute(
                text("DELETE FROM classification_reviews WHERE episode_id = :ep"),
                {"ep": str(episode_id)},
            )
            await session.execute(
                text("DELETE FROM classifications WHERE episode_id = :ep"),
                {"ep": str(episode_id)},
            )
            await session.commit()
        await engine.dispose()
