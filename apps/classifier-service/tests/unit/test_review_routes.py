"""Tests HTTP del router de revisión humana (`GET .../review-queue`,
`POST .../{episode_id}/review`).

Estos tests NO tocan DB real — mockean `tenant_session` y el service layer,
igual que `test_classify_episode_idempotent.py`. Lo que verifican es la capa
HTTP: auth (403 sin policy), wiring de la respuesta, y que un 404 del service
layer se traduce a 404 HTTP. La lógica de la consulta/el reemplazo de
etiqueta la cubre `tests/integration/test_review_service_db.py` contra
Postgres real.
"""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from classifier_service.main import app
from classifier_service.services.review import (
    ReviewConflictError,
    ReviewResult,
    ReviewTargetNotFoundError,
)
from httpx import ASGITransport, AsyncClient

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


def _headers(role: str) -> dict[str, str]:
    return {
        "X-User-Id": str(uuid4()),
        "X-Tenant-Id": str(TENANT_ID),
        "X-User-Email": f"{role}@utn.test",
        "X-User-Roles": role,
    }


@contextlib.asynccontextmanager
async def _fake_tenant_session(_tenant_id):
    yield None  # el handler no usa la sesión directamente en estos tests (se patchea el service)


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Criterio 5.9 #4: un rol sin policy recibe 403 ─────────────────────────


@pytest.mark.asyncio
async def test_post_review_403_para_rol_sin_policy(client: AsyncClient) -> None:
    """`estudiante` no está en REVIEW_ROLES (decisión de design: docente,
    docente_admin, superadmin pueden anular; el estudiante no)."""
    episode_id = uuid4()
    r = await client.post(
        f"/api/v1/classifications/{episode_id}/review",
        json={"verdict": "apropiacion_reflexiva", "reason": "x"},
        headers=_headers("estudiante"),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_get_review_queue_403_para_rol_sin_policy(client: AsyncClient) -> None:
    r = await client.get("/api/v1/classifications/review-queue", headers=_headers("estudiante"))
    assert r.status_code == 403


# ── Wiring: 201 con service mockeado ──────────────────────────────────────


@pytest.mark.asyncio
async def test_post_review_201_cuando_el_service_resuelve(client: AsyncClient) -> None:
    episode_id = uuid4()
    fake_result = ReviewResult(review_id=7, previous_classification_id=1, new_classification_id=2)

    with (
        patch(
            "classifier_service.routes.review.tenant_session",
            lambda tid: _fake_tenant_session(tid),
        ),
        patch(
            "classifier_service.routes.review.submit_review",
            AsyncMock(return_value=fake_result),
        ),
    ):
        r = await client.post(
            f"/api/v1/classifications/{episode_id}/review",
            json={"verdict": "apropiacion_reflexiva", "reason": "Cita literal en el código."},
            headers=_headers("docente"),
        )

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["review_id"] == 7
    assert body["previous_classification_id"] == 1
    assert body["new_classification_id"] == 2
    assert body["verdict"] == "apropiacion_reflexiva"


@pytest.mark.asyncio
async def test_post_review_404_cuando_no_hay_clasificacion_vigente(client: AsyncClient) -> None:
    episode_id = uuid4()

    with (
        patch(
            "classifier_service.routes.review.tenant_session",
            lambda tid: _fake_tenant_session(tid),
        ),
        patch(
            "classifier_service.routes.review.submit_review",
            AsyncMock(side_effect=ReviewTargetNotFoundError("sin clasificacion")),
        ),
    ):
        r = await client.post(
            f"/api/v1/classifications/{episode_id}/review",
            json={"verdict": "apropiacion_reflexiva", "reason": "x"},
            headers=_headers("docente_admin"),
        )

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_review_409_cuando_el_service_reporta_conflicto_de_concurrencia(
    client: AsyncClient,
) -> None:
    """Hallazgo de QA (2026-09-27, ALTA): `ReviewConflictError` se traduce a
    409, no a 500 ni a un 201 que oculte el lost update."""
    episode_id = uuid4()

    with (
        patch(
            "classifier_service.routes.review.tenant_session",
            lambda tid: _fake_tenant_session(tid),
        ),
        patch(
            "classifier_service.routes.review.submit_review",
            AsyncMock(
                side_effect=ReviewConflictError("otra revisión ganó la carrera", retryable=False)
            ),
        ),
    ):
        r = await client.post(
            f"/api/v1/classifications/{episode_id}/review",
            json={"verdict": "apropiacion_reflexiva", "reason": "x"},
            headers=_headers("docente"),
        )

    assert r.status_code == 409


# ── Hallazgo de QA (2026-09-27, ronda 5, punto 1): el 409 tiene que decir
# QUIÉN ganó la carrera — no puede sonar igual si fue otro docente o el
# sistema. `retryable` viaja en el `detail` para que el frontend decida si
# ofrece "reintentar" o "recargá y mirá la decisión del otro".


@pytest.mark.asyncio
async def test_post_review_409_expone_retryable_false_cuando_gano_otro_docente(
    client: AsyncClient,
) -> None:
    episode_id = uuid4()

    with (
        patch(
            "classifier_service.routes.review.tenant_session",
            lambda tid: _fake_tenant_session(tid),
        ),
        patch(
            "classifier_service.routes.review.submit_review",
            AsyncMock(
                side_effect=ReviewConflictError(
                    "Otro docente ya revisó el episodio", retryable=False
                )
            ),
        ),
    ):
        r = await client.post(
            f"/api/v1/classifications/{episode_id}/review",
            json={"verdict": "apropiacion_reflexiva", "reason": "x"},
            headers=_headers("docente"),
        )

    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["retryable"] is False
    assert "docente" in detail["message"].lower()


@pytest.mark.asyncio
async def test_post_review_409_expone_retryable_true_cuando_gano_la_maquina(
    client: AsyncClient,
) -> None:
    episode_id = uuid4()

    with (
        patch(
            "classifier_service.routes.review.tenant_session",
            lambda tid: _fake_tenant_session(tid),
        ),
        patch(
            "classifier_service.routes.review.submit_review",
            AsyncMock(
                side_effect=ReviewConflictError(
                    "El sistema reclasificó automáticamente el episodio", retryable=True
                )
            ),
        ),
    ):
        r = await client.post(
            f"/api/v1/classifications/{episode_id}/review",
            json={"verdict": "apropiacion_reflexiva", "reason": "x"},
            headers=_headers("docente"),
        )

    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["retryable"] is True
    assert "sistema" in detail["message"].lower()


# ── Hallazgo de QA #3 (ALTA): `verdict` fuera del dominio conocido ───────


@pytest.mark.asyncio
async def test_post_review_400_cuando_verdict_no_es_un_valor_conocido(client: AsyncClient) -> None:
    """`verdict="banana"` no puede persistirse como etiqueta oficial vigente
    sin error — mismo patrón que `interrater.py::save_rating` (400, no
    silencio). El service NUNCA debe llegar a llamarse."""
    episode_id = uuid4()
    submit_mock = AsyncMock()

    with (
        patch(
            "classifier_service.routes.review.tenant_session",
            lambda tid: _fake_tenant_session(tid),
        ),
        patch("classifier_service.routes.review.submit_review", submit_mock),
    ):
        r = await client.post(
            f"/api/v1/classifications/{episode_id}/review",
            json={"verdict": "banana", "reason": "x"},
            headers=_headers("docente"),
        )

    assert r.status_code == 400
    submit_mock.assert_not_called()


@pytest.mark.asyncio
async def test_post_review_201_con_verdict_valido_autonomo(client: AsyncClient) -> None:
    """Triangulación del criterio anterior: un segundo valor válido del
    dominio (no solo `apropiacion_reflexiva`, ya cubierto arriba) también
    pasa la validación."""
    episode_id = uuid4()
    fake_result = ReviewResult(review_id=9, previous_classification_id=3, new_classification_id=4)

    with (
        patch(
            "classifier_service.routes.review.tenant_session",
            lambda tid: _fake_tenant_session(tid),
        ),
        patch(
            "classifier_service.routes.review.submit_review",
            AsyncMock(return_value=fake_result),
        ),
    ):
        r = await client.post(
            f"/api/v1/classifications/{episode_id}/review",
            json={"verdict": "autonomo", "reason": "Brazo sin tutor, prompts==0."},
            headers=_headers("docente"),
        )

    assert r.status_code == 201, r.text


# ── Hallazgo de QA #4 (BAJA): `reviewer_role` tiene que ser determinístico ──


@pytest.mark.asyncio
async def test_reviewer_role_es_deterministico_con_dos_roles(client: AsyncClient) -> None:
    """Un usuario con `docente` Y `docente_admin` a la vez tiene que grabar
    SIEMPRE el mismo rol en la auditoría, sin depender del orden de
    iteración de un `set`. Se corre varias veces: con la implementación
    vieja (`next(iter(set.intersection(...)))`) el orden de un `frozenset`
    de strings es estable dentro de UNA corrida de Python pero no es un
    contrato — este test fija la política explícita (mayor autoridad
    primero) en vez de confiar en el orden implícito."""
    episode_id = uuid4()
    fake_result = ReviewResult(review_id=1, previous_classification_id=1, new_classification_id=2)
    submit_mock = AsyncMock(return_value=fake_result)

    headers = _headers("docente")
    headers["X-User-Roles"] = "docente,docente_admin"

    with (
        patch(
            "classifier_service.routes.review.tenant_session",
            lambda tid: _fake_tenant_session(tid),
        ),
        patch("classifier_service.routes.review.submit_review", submit_mock),
    ):
        for _ in range(5):
            await client.post(
                f"/api/v1/classifications/{episode_id}/review",
                json={"verdict": "apropiacion_reflexiva", "reason": "x"},
                headers=headers,
            )

    recorded_roles = {call.kwargs["reviewer_role"] for call in submit_mock.await_args_list}
    assert recorded_roles == {"docente_admin"}, (
        f"El rol grabado en la auditoría debe ser siempre el mismo para el "
        f"mismo usuario. Se grabaron: {recorded_roles}"
    )


@pytest.mark.asyncio
async def test_get_review_queue_200_con_items(client: AsyncClient) -> None:
    from classifier_service.services.review import ReviewQueueItem

    comision_id = uuid4()
    episode_id = uuid4()
    fake_items = [
        ReviewQueueItem(
            episode_id=episode_id,
            comision_id=comision_id,
            classification_id=1,
            appropriation="apropiacion_superficial",
            needs_review_reason="juez_eje_fino_abstencion_traza_insuficiente",
            estado_juez="abstencion_traza_insuficiente",
        )
    ]

    with (
        patch(
            "classifier_service.routes.review.tenant_session",
            lambda tid: _fake_tenant_session(tid),
        ),
        patch(
            "classifier_service.routes.review.list_review_queue",
            AsyncMock(return_value=fake_items),
        ),
    ):
        r = await client.get(
            f"/api/v1/classifications/review-queue?comision_id={comision_id}",
            headers=_headers("superadmin"),
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["n"] == 1
    assert body["items"][0]["episode_id"] == str(episode_id)
