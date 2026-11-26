"""Aceptacion HU-051 (orquestador, antes de construir; el constructor no la
modifica). Barrido de episodios pendientes de clasificar.

Origen: la HU-050 hace que `POST /classify_episode` responda 202 cuando el
CTR todavia no guardo el cierre, y la web del alumno reintenta hasta 60 s.
Si la cola tarda mas (en prod hubo un atraso de 2 h 30 min), nadie vuelve a
pedir la clasificacion y el episodio queda sin etiqueta. Version aprobada por
Juani el 26/11: el clasificador se anota lo que no pudo clasificar y lo
reintenta solo, SIN tocar el ctr-service (no hay endpoint que liste cerrados).
Lo que no cubre, declarado: un cierre cuyo POST nunca llego.

Criterios:

C01  Cuando el POST responde 202 por traza incompleta, el classifier-service
     anota el episodio (tenant y comision) en la tabla de pendientes de su
     base. Repetir el 202 no duplica la anotacion.
C02  `barrer(tenant_id)` recorre los pendientes: si el CTR ya devuelve
     `episodio_cerrado`, clasifica por el mismo camino que el POST (misma
     etiqueta, guarda `eventos_vistos`) y el pendiente pasa a 'clasificado';
     si todavia no hay cierre, queda 'pendiente' y no se guarda ninguna
     clasificacion. Ademas corre periodicamente dentro del servicio.
C03  El barrido mira las clasificaciones vigentes CON `eventos_vistos` y
     `classified_at` de las ultimas 48 h: si el CTR tiene mas eventos,
     recalcula (fila nueva vigente, la anterior is_current=false, sin borrar;
     con revision humana vigente, la fila de maquina no gobierna). Una de
     hace mas de 48 h no se mira.
N01  No toca ctr-service ni tutor-service: ningun archivo bajo
     apps/ctr-service ni apps/tutor-service cambia respecto de la base
     `bf63cd5` (lo chequea esta aceptacion con git).
N02  No toca ninguna clasificacion SIN `eventos_vistos` (las previas a la
     HU-050, entre ellas las del periodo del estudio), aunque el CTR tenga mas
     eventos y aunque sea de hace menos de 48 h. Sin juez y sin filas nuevas.
N03  Un pendiente con mas de `barrido_pendiente_max_dias` (default 7) que
     sigue sin cierre pasa a 'descartado': queda registrado (no se borra) y
     el barrido no lo vuelve a pedir al CTR.
N04  Idempotencia: un pendiente ya clasificado (por el barrido o por un POST
     posterior del navegador) o una clasificacion ya al dia no generan filas
     ni llaman al juez en barridos sucesivos.

Contrato que fija esta aceptacion (el constructor lo implementa):

- Tabla `clasificaciones_pendientes` en classifier_db, con al menos las
  columnas `tenant_id uuid`, `episode_id uuid`, `comision_id uuid NULL`,
  `estado text` ('pendiente' | 'clasificado' | 'descartado') y
  `creado_at timestamptz` (cuando se anoto por primera vez). Una sola fila por
  (tenant_id, episode_id). Migracion alembic nueva, posterior a
  `20261126_0008`.
- Modulo `classifier_service.services.barrido` con:
    `async def barrer(tenant_id: UUID) -> Any` (una pasada para ese tenant)
    `async def bucle(intervalo_segundos: float, tenant_ids: Sequence[UUID])`
      (corre `barrer` para cada tenant cada `intervalo_segundos`, para
      siempre, sin morir si una pasada falla).
- El lifespan de `classifier_service.main` arranca el bucle.
- Settings: `barrido_intervalo_segundos` (default > 0) y
  `barrido_pendiente_max_dias` (default 7).
- El barrido usa el mismo camino que el POST: el CTR por
  `classifier_service.routes.classify_ep._fetch_episode_from_ctr` y el juez
  por `classifier_service.routes.classify_ep._aplicar_juez_eje_fino`,
  resueltos en tiempo de llamada (estas pruebas los doblan ahi; si el modulo
  `barrido` importa esos nombres, la prueba tambien los dobla en el).
- Sesiones por `classifier_service.db.tenant_session` (estas pruebas
  apuntan su fabrica a la base de prueba).

Contra Postgres real (`CLASSIFIER_TEST_DB_URL`, default el `ainative-pg` local
en 55433), usuario no superuser (RLS forzado). Tenant y episodio aleatorios
por prueba, commits reales y limpieza en `finally`. Sin base, las pruebas
FALLAN (no se saltean). Si falta el contrato, fallan por asercion explicita.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import inspect
import os
import socket
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from classifier_service import db as db_mod
from classifier_service.main import app
from classifier_service.services import classify_episode_from_events
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DB_URL = os.environ.get(
    "CLASSIFIER_TEST_DB_URL",
    "postgresql+asyncpg://classifier_user:classifier_pass@127.0.0.1:55433/classifier_db",
)
RUTA = "classifier_service.routes.classify_ep"
BASE_SHA = "bf63cd5"
TABLA = "clasificaciones_pendientes"


def _barrido() -> Any:
    try:
        return importlib.import_module("classifier_service.services.barrido")
    except ImportError:
        return None


def _exigir_barrido() -> Any:
    mod = _barrido()
    assert mod is not None, "falta el contrato: modulo classifier_service.services.barrido"
    assert inspect.iscoroutinefunction(getattr(mod, "barrer", None)), (
        "falta el contrato: async def barrer(tenant_id)"
    )
    return mod


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
        "ts": f"2026-10-24T20:{seq // 60:02d}:{seq % 60:02d}Z",
        "payload": payload or {},
    }


def _eventos(prompts: int, *, cierre: bool, extra_trabajo: int = 0) -> list[dict]:
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
    def __init__(self) -> None:
        self.engine = create_async_engine(DB_URL)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    @contextlib.asynccontextmanager
    async def sesion(self, tenant_id: UUID) -> AsyncIterator[Any]:
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
        async with self.sesion(tenant_id) as s:
            r = await s.execute(
                text(
                    "SELECT id, is_current, appropriation, features, classified_at "
                    "FROM classifications WHERE episode_id = :ep ORDER BY id"
                ),
                {"ep": str(episode_id)},
            )
            return [dict(m) for m in r.mappings().all()]

    async def tabla_existe(self) -> bool:
        async with self.factory() as s:
            r = await s.execute(text("SELECT to_regclass(:t)"), {"t": TABLA})
            return r.scalar() is not None

    async def pendientes(self, tenant_id: UUID, episode_id: UUID) -> list[dict]:
        assert await self.tabla_existe(), f"falta el contrato: tabla {TABLA}"
        async with self.sesion(tenant_id) as s:
            r = await s.execute(
                text(
                    f"SELECT tenant_id, episode_id, comision_id, estado, creado_at "
                    f"FROM {TABLA} WHERE episode_id = :ep"
                ),
                {"ep": str(episode_id)},
            )
            return [dict(m) for m in r.mappings().all()]

    async def ejecutar(self, tenant_id: UUID, sql: str, **params: Any) -> None:
        async with self.sesion(tenant_id) as s:
            await s.execute(text(sql), params)

    async def limpiar(self, tenant_id: UUID, episode_id: UUID) -> None:
        async with self.sesion(tenant_id) as s:
            await s.execute(
                text("DELETE FROM classification_reviews WHERE episode_id = :ep"),
                {"ep": str(episode_id)},
            )
            await s.execute(
                text("DELETE FROM classifications WHERE episode_id = :ep"),
                {"ep": str(episode_id)},
            )
        if await self.tabla_existe():
            async with self.sesion(tenant_id) as s:
                await s.execute(
                    text(f"DELETE FROM {TABLA} WHERE episode_id = :ep"),
                    {"ep": str(episode_id)},
                )
        await self.engine.dispose()


@pytest.fixture
async def ctx() -> AsyncIterator[dict]:
    if not _db_disponible():
        pytest.fail(
            f"Sin Postgres en {urlsplit(DB_URL).netloc.split('@')[-1]}: la aceptacion "
            "HU-051 no se puede saltear. Levanta el stack local o exporta "
            "CLASSIFIER_TEST_DB_URL."
        )
    base = _Base()
    tenant_id, episode_id, comision_id = uuid4(), uuid4(), uuid4()
    juez = AsyncMock(return_value=None)
    ctr = AsyncMock()
    mod = _barrido()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(db_mod, "_session_factory", base.factory))
                stack.enter_context(patch(f"{RUTA}._fetch_episode_from_ctr", ctr))
                stack.enter_context(patch(f"{RUTA}._aplicar_juez_eje_fino", juez))
                if mod is not None:
                    for nombre, doble in (
                        ("_fetch_episode_from_ctr", ctr),
                        ("_aplicar_juez_eje_fino", juez),
                    ):
                        if hasattr(mod, nombre):
                            stack.enter_context(patch.object(mod, nombre, doble))
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


def _pidio_al_ctr(c: dict) -> int:
    return sum(1 for call in c["ctr"].await_args_list if str(c["ep"]) in str(call))


async def _post(c: dict, role: str = "docente"):
    return await c["client"].post(
        f"/api/v1/classify_episode/{c['ep']}", headers=_headers(c["tenant"], role)
    )


async def _barrer(c: dict) -> None:
    mod = _exigir_barrido()
    await mod.barrer(c["tenant"])


async def _dejar_pendiente(c: dict) -> None:
    _ctr_devuelve(c, _eventos(2, cierre=False))
    r = await _post(c)
    assert r.status_code == 202, r.text


# ── C01 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_c01_el_202_anota_el_pendiente_con_tenant_y_comision(ctx: dict) -> None:
    await _dejar_pendiente(ctx)
    pend = await ctx["base"].pendientes(ctx["tenant"], ctx["ep"])
    assert len(pend) == 1, "el 202 tiene que dejar anotado el episodio"
    p = pend[0]
    assert str(p["tenant_id"]) == str(ctx["tenant"])
    assert str(p["comision_id"]) == str(ctx["com"])
    assert p["estado"] == "pendiente"
    assert await ctx["base"].filas(ctx["tenant"], ctx["ep"]) == [], (
        "anotar el pendiente no es clasificar (HU-050 C01)"
    )


@pytest.mark.asyncio
async def test_c01_repetir_el_202_no_duplica(ctx: dict) -> None:
    await _dejar_pendiente(ctx)
    await _dejar_pendiente(ctx)
    await _dejar_pendiente(ctx)
    pend = await ctx["base"].pendientes(ctx["tenant"], ctx["ep"])
    assert len(pend) == 1, f"tres 202 dejaron {len(pend)} anotaciones"


# ── C02 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_c02_con_el_cierre_guardado_el_barrido_clasifica(ctx: dict) -> None:
    await _dejar_pendiente(ctx)
    completos = _eventos(3, cierre=True)
    _ctr_devuelve(ctx, completos)
    await _barrer(ctx)

    filas = await ctx["base"].filas(ctx["tenant"], ctx["ep"])
    assert len(filas) == 1, "el barrido tiene que clasificar el pendiente"
    f = filas[0]
    assert f["is_current"] is True
    assert f["appropriation"] == classify_episode_from_events(completos).appropriation, (
        "misma etiqueta que daria el POST"
    )
    assert f["features"].get("eventos_vistos") == len(completos)
    assert ctx["juez"].await_count >= 1, "mismo camino que el POST: pasa por el juez"
    pend = await ctx["base"].pendientes(ctx["tenant"], ctx["ep"])
    assert [p["estado"] for p in pend] == ["clasificado"]


@pytest.mark.asyncio
async def test_c02_sin_cierre_todavia_queda_pendiente(ctx: dict) -> None:
    await _dejar_pendiente(ctx)
    _ctr_devuelve(ctx, _eventos(3, cierre=False))
    await _barrer(ctx)
    assert _pidio_al_ctr(ctx) >= 2, "el barrido tiene que volver a preguntarle al CTR"
    assert await ctx["base"].filas(ctx["tenant"], ctx["ep"]) == []
    pend = await ctx["base"].pendientes(ctx["tenant"], ctx["ep"])
    assert [p["estado"] for p in pend] == ["pendiente"]
    ctx["juez"].assert_not_called()


@pytest.mark.asyncio
async def test_c02_el_bucle_corre_solo(ctx: dict) -> None:
    mod = _exigir_barrido()
    assert inspect.iscoroutinefunction(getattr(mod, "bucle", None)), (
        "falta el contrato: async def bucle(intervalo_segundos, tenant_ids)"
    )
    await _dejar_pendiente(ctx)
    _ctr_devuelve(ctx, _eventos(3, cierre=True))
    tarea = asyncio.create_task(mod.bucle(0.05, [ctx["tenant"]]))
    try:
        for _ in range(60):
            await asyncio.sleep(0.05)
            if await ctx["base"].filas(ctx["tenant"], ctx["ep"]):
                break
        assert not tarea.done(), "el bucle no tiene que terminar solo"
    finally:
        tarea.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tarea
    assert len(await ctx["base"].filas(ctx["tenant"], ctx["ep"])) == 1


def test_c02_el_servicio_arranca_el_bucle_y_tiene_settings() -> None:
    from classifier_service import main as main_mod
    from classifier_service.config import settings

    fuente = inspect.getsource(main_mod)
    assert "barrido" in fuente and "bucle" in fuente, (
        "el lifespan de classifier_service.main tiene que arrancar barrido.bucle"
    )
    intervalo = getattr(settings, "barrido_intervalo_segundos", None)
    assert isinstance(intervalo, (int, float)) and intervalo > 0, (
        "falta el contrato: settings.barrido_intervalo_segundos > 0"
    )
    assert getattr(settings, "barrido_pendiente_max_dias", None) == 7, (
        "falta el contrato: settings.barrido_pendiente_max_dias (default 7)"
    )


# ── C03 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_c03_reciente_con_mas_eventos_se_recalcula(ctx: dict) -> None:
    primeros = _eventos(1, cierre=True)
    _ctr_devuelve(ctx, primeros)
    assert (await _post(ctx)).status_code == 201

    completos = _eventos(4, cierre=True, extra_trabajo=6)
    _ctr_devuelve(ctx, completos)
    await _barrer(ctx)

    filas = await ctx["base"].filas(ctx["tenant"], ctx["ep"])
    assert len(filas) == 2, "append-only: recalculo con fila nueva, la vieja queda"
    vieja, nueva = filas
    assert vieja["is_current"] is False
    assert vieja["features"].get("eventos_vistos") == len(primeros)
    assert nueva["is_current"] is True
    assert nueva["features"].get("eventos_vistos") == len(completos)
    assert nueva["appropriation"] == classify_episode_from_events(completos).appropriation


@pytest.mark.asyncio
async def test_c03_mas_de_48_horas_no_se_mira(ctx: dict) -> None:
    _ctr_devuelve(ctx, _eventos(1, cierre=True))
    assert (await _post(ctx)).status_code == 201
    await ctx["base"].ejecutar(
        ctx["tenant"],
        "UPDATE classifications SET classified_at = now() - interval '49 hours' "
        "WHERE episode_id = :ep",
        ep=str(ctx["ep"]),
    )
    antes = await ctx["base"].filas(ctx["tenant"], ctx["ep"])
    juez_antes = ctx["juez"].await_count

    _ctr_devuelve(ctx, _eventos(4, cierre=True, extra_trabajo=6))
    await _barrer(ctx)
    assert await ctx["base"].filas(ctx["tenant"], ctx["ep"]) == antes
    assert ctx["juez"].await_count == juez_antes


@pytest.mark.asyncio
async def test_c03_recalculo_del_barrido_no_pisa_la_revision_humana(ctx: dict) -> None:
    _ctr_devuelve(ctx, _eventos(1, cierre=True))
    assert (await _post(ctx)).status_code == 201
    rv = await ctx["client"].post(
        f"/api/v1/classifications/{ctx['ep']}/review",
        json={"verdict": "apropiacion_reflexiva", "reason": "aceptacion HU-051"},
        headers=_headers(ctx["tenant"], "docente_admin"),
    )
    assert rv.status_code == 201, rv.text

    _ctr_devuelve(ctx, _eventos(4, cierre=True, extra_trabajo=6))
    await _barrer(ctx)
    filas = await ctx["base"].filas(ctx["tenant"], ctx["ep"])
    vigentes = [f for f in filas if f["is_current"]]
    assert len(vigentes) == 1
    assert "revision_humana" in vigentes[0]["features"]
    assert vigentes[0]["appropriation"] == "apropiacion_reflexiva"


# ── N01 ───────────────────────────────────────────────────────────────────


def test_n01_no_toca_ctr_ni_tutor() -> None:
    raiz = Path(__file__).resolve()
    while not (raiz / ".git").exists() and raiz != raiz.parent:
        raiz = raiz.parent
    r = subprocess.run(  # noqa: S603
        ["git", "diff", "--name-only", BASE_SHA, "--", "apps/ctr-service", "apps/tutor-service"],
        cwd=raiz,
        capture_output=True,
        text=True,
        check=True,
    )
    assert r.stdout.strip() == "", f"la HU-051 toco servicios prohibidos:\n{r.stdout}"


# ── N02 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_n02_no_toca_filas_sin_eventos_vistos(ctx: dict) -> None:
    from classifier_service.services import (
        DEFAULT_REFERENCE_PROFILE,
        compute_classifier_config_hash,
    )

    await ctx["base"].ejecutar(
        ctx["tenant"],
        "INSERT INTO classifications (tenant_id, episode_id, comision_id, "
        "classifier_config_hash, appropriation, appropriation_reason, features, "
        "is_current) VALUES (:t, :ep, :c, :h, 'autonomo', 'fila previa a HU-050', "
        "CAST(:f AS jsonb), true)",
        t=str(ctx["tenant"]),
        ep=str(ctx["ep"]),
        c=str(ctx["com"]),
        h=compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE),
        f='{"subgrupo": {"key": "autonomo_competente"}}',
    )
    antes = await ctx["base"].filas(ctx["tenant"], ctx["ep"])
    assert antes and antes[0]["is_current"]

    _ctr_devuelve(ctx, _eventos(4, cierre=True, extra_trabajo=6))
    await _barrer(ctx)
    await _barrer(ctx)
    assert await ctx["base"].filas(ctx["tenant"], ctx["ep"]) == antes, (
        "una fila sin eventos_vistos (historia previa) no se recalcula"
    )
    ctx["juez"].assert_not_called()


# ── N03 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_n03_pendiente_viejo_sin_cierre_se_descarta_y_no_se_pide_mas(ctx: dict) -> None:
    await _dejar_pendiente(ctx)
    assert await ctx["base"].tabla_existe(), f"falta el contrato: tabla {TABLA}"
    await ctx["base"].ejecutar(
        ctx["tenant"],
        f"UPDATE {TABLA} SET creado_at = now() - interval '8 days' WHERE episode_id = :ep",
        ep=str(ctx["ep"]),
    )
    _ctr_devuelve(ctx, _eventos(3, cierre=False))
    await _barrer(ctx)
    pend = await ctx["base"].pendientes(ctx["tenant"], ctx["ep"])
    assert [p["estado"] for p in pend] == ["descartado"], (
        "despues del maximo queda registrado como descartado, no se borra"
    )

    pedidos = _pidio_al_ctr(ctx)
    await _barrer(ctx)
    assert _pidio_al_ctr(ctx) == pedidos, "un descartado no se le vuelve a pedir al CTR"
    assert await ctx["base"].filas(ctx["tenant"], ctx["ep"]) == []


@pytest.mark.asyncio
async def test_n03_pendiente_reciente_no_se_descarta(ctx: dict) -> None:
    await _dejar_pendiente(ctx)
    assert await ctx["base"].tabla_existe(), f"falta el contrato: tabla {TABLA}"
    await ctx["base"].ejecutar(
        ctx["tenant"],
        f"UPDATE {TABLA} SET creado_at = now() - interval '6 days' WHERE episode_id = :ep",
        ep=str(ctx["ep"]),
    )
    _ctr_devuelve(ctx, _eventos(3, cierre=False))
    await _barrer(ctx)
    pend = await ctx["base"].pendientes(ctx["tenant"], ctx["ep"])
    assert [p["estado"] for p in pend] == ["pendiente"]


# ── N04 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_n04_barridos_sucesivos_no_generan_filas_ni_juez(ctx: dict) -> None:
    await _dejar_pendiente(ctx)
    _ctr_devuelve(ctx, _eventos(3, cierre=True))
    await _barrer(ctx)
    filas = await ctx["base"].filas(ctx["tenant"], ctx["ep"])
    assert len(filas) == 1
    juez = ctx["juez"].await_count

    await _barrer(ctx)
    await _barrer(ctx)
    assert await ctx["base"].filas(ctx["tenant"], ctx["ep"]) == filas
    assert ctx["juez"].await_count == juez


@pytest.mark.asyncio
async def test_n04_pendiente_que_clasifico_el_navegador_no_se_duplica(ctx: dict) -> None:
    """El reintento del navegador gano: 202 (pendiente) y despues 201. El
    barrido no vuelve a clasificar ni llama al juez; el pendiente queda
    resuelto."""
    await _dejar_pendiente(ctx)
    _ctr_devuelve(ctx, _eventos(3, cierre=True))
    assert (await _post(ctx)).status_code == 201
    filas = await ctx["base"].filas(ctx["tenant"], ctx["ep"])
    juez = ctx["juez"].await_count

    await _barrer(ctx)
    assert await ctx["base"].filas(ctx["tenant"], ctx["ep"]) == filas
    assert ctx["juez"].await_count == juez
    pend = await ctx["base"].pendientes(ctx["tenant"], ctx["ep"])
    assert [p["estado"] for p in pend] != ["pendiente"], (
        "un pendiente ya clasificado no puede quedar como pendiente para siempre"
    )
