"""Aceptacion HU-050 (orquestador, antes de construir; el constructor no la
modifica). La clasificacion espera la traza completa.

Origen: revisando el paper CIbSE (26/11) aparecio que el POST de cierre del
alumno clasifica leyendo el CTR ANTES de que la cola termine de guardar los
eventos (en prod: a53845e4 se clasifico 2 s antes de que se guardara su
primer mensaje; dfb7c906, 2 h 30 min antes). La etiqueta se calcula con la
traza a medias y queda congelada: el pre-check de idempotencia devuelve la
fila vieja sin volver a mirar el CTR. 233 de 6.387 episodios del semestre.

Criterios (aprobados por Juani el 26/11):

C01  Si el CTR todavia no tiene guardado el cierre (no hay `episodio_cerrado`
     entre los eventos, estado != closed), POST /classify_episode responde
     202 «traza incompleta», NO guarda ninguna fila y NO llama al juez.
C02  Con la traza completa clasifica como hoy: 201 y la misma appropriation
     que `classify_episode_from_events` sobre esos eventos.
C03  La fila guarda cuantos eventos vio en `features["eventos_vistos"]`
     (= len de los eventos que devolvio el CTR). Si un POST posterior
     encuentra MAS eventos que los vistos por la vigente, recalcula: fila
     nueva vigente con el conteo nuevo, la anterior queda is_current=false y
     no se borra (append-only).
N01  Con una revision humana vigente, el recalculo de C03 se registra pero no
     gobierna: la fila humana sigue siendo la vigente.
N02  Re-POST con los mismos eventos: 200 con la misma fila, sin insertar y sin
     llamar al juez.
N03  Una fila hecha con la traza completa (eventos_vistos == eventos actuales)
     no cambia aunque el clasificador hoy diera otra cosa.
N04  (agregado por el orquestador: «¿que implementacion mala pasaria?») Una
     fila vigente SIN `eventos_vistos` (todas las anteriores a esta HU, entre
     ellas las del periodo del estudio) no se recalcula con un POST: 200 con
     la fila existente. Recalcular historia es decision aparte (HU-051 N02).

Contra Postgres real (`classifier_db` del stack local), porque C03/N01 viven
en la interaccion con el UniqueConstraint(episode_id, classifier_config_hash)
y con la gobernanza humana de `persist_classification`. URL:
`CLASSIFIER_TEST_DB_URL` (default: el `ainative-pg` local en 55433). Usuario
no superuser (RLS forzado). Cada prueba usa un tenant y episodio aleatorios,
commitea de verdad (como el e2e de composicion) y limpia en `finally`.
Sin base, las pruebas FALLAN (no se saltean): una aceptacion salteada no es
exito.

El CTR se dobla con `_fetch_episode_from_ctr`; el juez, con
`_aplicar_juez_eje_fino` (contrato: es el unico punto de entrada al juez).
"""

from __future__ import annotations

import contextlib
import os
import socket
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from classifier_service.main import app
from classifier_service.services import classify_episode_from_events
from classifier_service.services.pipeline import ClassificationResult
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DB_URL = os.environ.get(
    "CLASSIFIER_TEST_DB_URL",
    "postgresql+asyncpg://classifier_user:classifier_pass@127.0.0.1:55433/classifier_db",
)

RUTA = "classifier_service.routes.classify_ep"


def _db_disponible() -> bool:
    p = urlsplit(DB_URL.replace("+asyncpg", ""))
    try:
        with socket.create_connection((p.hostname, p.port or 5432), timeout=1):
            return True
    except OSError:
        return False


# ── Dobles ────────────────────────────────────────────────────────────────


def _evento(seq: int, tipo: str, payload: dict | None = None) -> dict:
    return {
        "seq": seq,
        "event_type": tipo,
        "ts": f"2026-10-14T20:{seq // 60:02d}:{seq % 60:02d}Z",
        "payload": payload or {},
    }


def _eventos(prompts: int, *, cierre: bool, extra_trabajo: int = 0) -> list[dict]:
    """Traza con `prompts` consultas al tutor (cada una con edicion y
    ejecucion) y, si `cierre`, el `episodio_cerrado` al final.
    `extra_trabajo` agrega ediciones/ejecuciones antes del cierre (los
    eventos que en prod se guardaron tarde)."""
    ev = [_evento(0, "episodio_abierto")]
    for _ in range(prompts):
        ev.append(_evento(len(ev), "prompt_enviado", {"prompt_kind": "consulta"}))
        ev.append(_evento(len(ev), "tutor_respondio"))
        ev.append(_evento(len(ev), "edicion_codigo"))
        ev.append(_evento(len(ev), "codigo_ejecutado", {"stdout": "ok", "stderr": ""}))
    for i in range(extra_trabajo):
        tipo = "edicion_codigo" if i % 2 == 0 else "codigo_ejecutado"
        ev.append(_evento(len(ev), tipo, {"stdout": "ok", "stderr": ""}))
    if cierre:
        ev.append(_evento(len(ev), "episodio_cerrado", {"reason": "completed"}))
    return ev


def _episodio(episode_id: UUID, comision_id: UUID, eventos: list[dict]) -> dict[str, Any]:
    cerrado = any(e["event_type"] == "episodio_cerrado" for e in eventos)
    return {
        "id": str(episode_id),
        "episode_id": str(episode_id),
        "comision_id": str(comision_id),
        "estado": "closed" if cerrado else "open",
        "events_count": len(eventos),
        "events": eventos,
    }


def _headers(tenant_id: UUID, role: str = "docente") -> dict[str, str]:
    return {
        "X-User-Id": str(uuid4()),
        "X-Tenant-Id": str(tenant_id),
        "X-User-Email": f"{role}@utn.test",
        "X-User-Roles": role,
    }


class _Base:
    """Engine propio por prueba, con el mismo set_config de RLS que el real."""

    def __init__(self) -> None:
        self.engine = create_async_engine(DB_URL)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    @contextlib.asynccontextmanager
    async def tenant_session(self, tenant_id: UUID) -> AsyncIterator[Any]:
        async with self.factory() as session:
            await session.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(tenant_id)},
            )
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def filas(self, tenant_id: UUID, episode_id: UUID) -> list[dict]:
        async with self.tenant_session(tenant_id) as s:
            r = await s.execute(
                text(
                    "SELECT id, is_current, appropriation, features "
                    "FROM classifications WHERE episode_id = :ep ORDER BY id"
                ),
                {"ep": str(episode_id)},
            )
            return [dict(m) for m in r.mappings().all()]

    async def limpiar(self, tenant_id: UUID, episode_id: UUID) -> None:
        async with self.tenant_session(tenant_id) as s:
            await s.execute(
                text("DELETE FROM classification_reviews WHERE episode_id = :ep"),
                {"ep": str(episode_id)},
            )
            await s.execute(
                text("DELETE FROM classifications WHERE episode_id = :ep"),
                {"ep": str(episode_id)},
            )
        await self.engine.dispose()


@pytest.fixture
async def ctx() -> AsyncIterator[dict]:
    if not _db_disponible():
        pytest.fail(
            f"Sin Postgres en {urlsplit(DB_URL).netloc.split('@')[-1]}: la aceptacion "
            "HU-050 no se puede saltear. Levanta el stack local o exporta "
            "CLASSIFIER_TEST_DB_URL."
        )
    base = _Base()
    tenant_id, episode_id, comision_id = uuid4(), uuid4(), uuid4()
    juez = AsyncMock(return_value=None)
    ctr = AsyncMock()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with (
                patch(f"{RUTA}.tenant_session", base.tenant_session),
                patch("classifier_service.routes.review.tenant_session", base.tenant_session),
                patch(f"{RUTA}._fetch_episode_from_ctr", ctr),
                patch(f"{RUTA}._aplicar_juez_eje_fino", juez),
            ):
                yield {
                    "client": client,
                    "base": base,
                    "tenant": tenant_id,
                    "ep": episode_id,
                    "com": comision_id,
                    "juez": juez,
                    "ctr": ctr,
                }
    finally:
        await base.limpiar(tenant_id, episode_id)


def _ctr_devuelve(c: dict, eventos: list[dict]) -> None:
    c["ctr"].return_value = _episodio(c["ep"], c["com"], eventos)
    c["ctr"].side_effect = None


async def _post(c: dict, role: str = "docente"):
    return await c["client"].post(
        f"/api/v1/classify_episode/{c['ep']}", headers=_headers(c["tenant"], role)
    )


# ── C01 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_c01_sin_cierre_guardado_202_y_no_persiste_nada(ctx: dict) -> None:
    _ctr_devuelve(ctx, _eventos(3, cierre=False))
    r = await _post(ctx)
    assert r.status_code == 202, r.text
    assert "incompleta" in r.text.lower(), r.text
    assert await ctx["base"].filas(ctx["tenant"], ctx["ep"]) == [], (
        "Con la traza sin cierre no tiene que quedar NINGUNA fila: una etiqueta "
        "calculada a medias queda congelada para siempre."
    )
    ctx["juez"].assert_not_called()


@pytest.mark.asyncio
async def test_c01_sin_cierre_varias_veces_y_despues_con_cierre_clasifica(ctx: dict) -> None:
    """La cola se atrasa: dos pedidos ven la traza sin cierre (202, nada
    guardado) y el tercero la ve completa (201, una sola fila, con todo)."""
    _ctr_devuelve(ctx, _eventos(2, cierre=False))
    assert (await _post(ctx)).status_code == 202
    assert (await _post(ctx)).status_code == 202
    completos = _eventos(3, cierre=True)
    _ctr_devuelve(ctx, completos)
    r = await _post(ctx)
    assert r.status_code == 201, r.text
    filas = await ctx["base"].filas(ctx["tenant"], ctx["ep"])
    assert len(filas) == 1
    assert filas[0]["features"].get("eventos_vistos") == len(completos)


# ── C02 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_c02_traza_completa_clasifica_como_hoy(ctx: dict) -> None:
    eventos = _eventos(3, cierre=True)
    _ctr_devuelve(ctx, eventos)
    r = await _post(ctx)
    assert r.status_code == 201, r.text
    esperado = classify_episode_from_events(eventos).appropriation
    assert r.json()["appropriation"] == esperado
    assert r.json()["is_current"] is True
    filas = await ctx["base"].filas(ctx["tenant"], ctx["ep"])
    assert len(filas) == 1 and filas[0]["appropriation"] == esperado


# ── C03 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_c03_guarda_eventos_vistos(ctx: dict) -> None:
    eventos = _eventos(2, cierre=True)
    _ctr_devuelve(ctx, eventos)
    assert (await _post(ctx)).status_code == 201
    filas = await ctx["base"].filas(ctx["tenant"], ctx["ep"])
    assert filas[0]["features"].get("eventos_vistos") == len(eventos)


@pytest.mark.asyncio
async def test_c03_mas_eventos_recalcula_append_only(ctx: dict) -> None:
    primeros = _eventos(1, cierre=True)
    _ctr_devuelve(ctx, primeros)
    assert (await _post(ctx)).status_code == 201

    # Llegaron tarde: 3 consultas mas y trabajo (la traza real es mas larga).
    completos = _eventos(4, cierre=True, extra_trabajo=6)
    assert len(completos) > len(primeros)
    _ctr_devuelve(ctx, completos)
    r = await _post(ctx)
    assert r.status_code == 201, r.text
    assert r.json()["is_current"] is True
    assert r.json()["appropriation"] == classify_episode_from_events(completos).appropriation

    filas = await ctx["base"].filas(ctx["tenant"], ctx["ep"])
    assert len(filas) == 2, "append-only: la fila vieja no se borra"
    vieja, nueva = filas
    assert vieja["is_current"] is False
    assert vieja["features"].get("eventos_vistos") == len(primeros)
    assert nueva["is_current"] is True
    assert nueva["features"].get("eventos_vistos") == len(completos)


# ── N01 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_n01_recalculo_no_pisa_la_revision_humana(ctx: dict) -> None:
    _ctr_devuelve(ctx, _eventos(1, cierre=True))
    assert (await _post(ctx)).status_code == 201
    rv = await ctx["client"].post(
        f"/api/v1/classifications/{ctx['ep']}/review",
        json={"verdict": "apropiacion_reflexiva", "reason": "aceptacion HU-050"},
        # Oversight: la revision es solo el setup; el acceso por comision
        # (base academica) no es lo que mide esta prueba.
        headers=_headers(ctx["tenant"], "docente_admin"),
    )
    assert rv.status_code == 201, rv.text

    _ctr_devuelve(ctx, _eventos(4, cierre=True, extra_trabajo=6))
    r = await _post(ctx)
    assert r.status_code == 201, r.text
    assert r.json()["is_current"] is False, "la fila de maquina se registra pero no gobierna"

    filas = await ctx["base"].filas(ctx["tenant"], ctx["ep"])
    vigentes = [f for f in filas if f["is_current"]]
    assert len(vigentes) == 1
    assert "revision_humana" in vigentes[0]["features"]
    assert vigentes[0]["appropriation"] == "apropiacion_reflexiva"


# ── N02 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_n02_mismos_eventos_200_sin_insertar_ni_juez(ctx: dict) -> None:
    eventos = _eventos(3, cierre=True)
    _ctr_devuelve(ctx, eventos)
    r1 = await _post(ctx)
    assert r1.status_code == 201
    llamadas_juez = ctx["juez"].await_count

    r2 = await _post(ctx)
    assert r2.status_code == 200, r2.text
    assert r2.json()["appropriation"] == r1.json()["appropriation"]
    assert ctx["juez"].await_count == llamadas_juez, "no se vuelve a llamar al juez"
    filas = await ctx["base"].filas(ctx["tenant"], ctx["ep"])
    assert len(filas) == 1


# ── N03 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_n03_fila_con_traza_completa_no_cambia(ctx: dict) -> None:
    eventos = _eventos(3, cierre=True)
    _ctr_devuelve(ctx, eventos)
    r1 = await _post(ctx)
    assert r1.status_code == 201
    antes = await ctx["base"].filas(ctx["tenant"], ctx["ep"])

    # El clasificador "de hoy" daria otra cosa: igual no se toca.
    otra = classify_episode_from_events(eventos)
    otra.appropriation = (
        "apropiacion_superficial"
        if otra.appropriation != "apropiacion_superficial"
        else "apropiacion_reflexiva"
    )
    with patch(f"{RUTA}.classify_episode_from_events", return_value=otra):
        r2 = await _post(ctx)
    assert r2.status_code == 200, r2.text
    assert r2.json()["appropriation"] == r1.json()["appropriation"]
    assert await ctx["base"].filas(ctx["tenant"], ctx["ep"]) == antes


# ── N04 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_n04_fila_vieja_sin_eventos_vistos_no_se_recalcula(ctx: dict) -> None:
    """Una fila de antes de la HU (sin `eventos_vistos`) con hash vigente:
    un POST que ve mas eventos NO la recalcula."""
    from classifier_service.services import (
        DEFAULT_REFERENCE_PROFILE,
        compute_classifier_config_hash,
    )

    config_hash = compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE)
    async with ctx["base"].tenant_session(ctx["tenant"]) as s:
        await s.execute(
            text(
                "INSERT INTO classifications (tenant_id, episode_id, comision_id, "
                "classifier_config_hash, appropriation, appropriation_reason, features, "
                "is_current) VALUES (:t, :ep, :c, :h, 'autonomo', 'fila previa a HU-050', "
                "CAST(:f AS jsonb), true)"
            ),
            {
                "t": str(ctx["tenant"]),
                "ep": str(ctx["ep"]),
                "c": str(ctx["com"]),
                "h": config_hash,
                "f": '{"subgrupo": {"key": "autonomo_competente"}}',
            },
        )
    antes = await ctx["base"].filas(ctx["tenant"], ctx["ep"])

    _ctr_devuelve(ctx, _eventos(4, cierre=True, extra_trabajo=6))
    r = await _post(ctx)
    assert r.status_code == 200, r.text
    assert r.json()["appropriation"] == "autonomo"
    assert await ctx["base"].filas(ctx["tenant"], ctx["ep"]) == antes
    ctx["juez"].assert_not_called()


def test_contrato_resultado_tiene_features() -> None:
    """Guarda contra la prueba vacia: los dobles usan el ClassificationResult real."""
    r = classify_episode_from_events(_eventos(3, cierre=True))
    assert isinstance(r, ClassificationResult)
    assert isinstance(r.features, dict)
