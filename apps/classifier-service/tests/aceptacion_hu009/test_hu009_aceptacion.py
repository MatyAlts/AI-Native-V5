"""Aceptacion HU-009, lado classifier (orquestador, antes de construir; el
constructor no la modifica).

Sale de la prueba 2 como alumno en produccion (20/11/2026, 17 ejercicios).

C01  El POST /classify_episode (lo que usa la pantalla de cierre del alumno)
     devuelve `subgrupo`, `regimen_llm` y `pasiva_por_sobreuso` igual que el
     GET, en sus tres salidas: nueva, ya existente y carrera.
C04  En el subgrupo, Probar (`tests_ejecutados`) cuenta como ejecucion: quien
     solo uso Probar y paso todo no queda desenganchado.
C09  Juez v3 `mtac_v2_juez_v3.1.0` con la regla de Juani sobre pedir la
     solucion (al principio: indicio de pasiva; al final para comparar con la
     suya: reflexiva).
C12  El dato para no mostrar "Cambiaste mucho de estrategia" con pocas
     consultas llega al alumno: `cii_iteraciones` en la respuesta.
N02  Ejecutar sigue contando igual; sin Ejecutar ni Probar sigue siendo poco
     trabajo.
"""

from __future__ import annotations

import contextlib
import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from classifier_service.main import app
from classifier_service.models import Classification
from classifier_service.services.pipeline import compute_classifier_config_hash
from classifier_service.services.subgrupo import clasificar_subgrupo
from classifier_service.services.tree import DEFAULT_REFERENCE_PROFILE
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


def _headers() -> dict[str, str]:
    return {
        "X-User-Id": "11111111-1111-1111-1111-111111111111",
        "X-Tenant-Id": str(TENANT_ID),
        "X-User-Email": "alumno@utn.test",
        "X-User-Roles": "estudiante,docente",  # con Clerk toda cuenta trae los dos
    }


SUBGRUPO = {
    "key": "dependiente_sobreuso",
    "label": "Dependiente por sobreuso",
    "accion_docente": "x",
    "eje": "delegacion_pasiva",
    "dimensiones": {"autonomia": 0.2, "experimentacion": 0.5, "persistencia": 1.0, "foco": 1.0},
}


def _fila(episode_id: UUID, comision_id: UUID, config_hash: str) -> Classification:
    return Classification(
        id=7,
        tenant_id=TENANT_ID,
        episode_id=episode_id,
        comision_id=comision_id,
        classifier_config_hash=config_hash,
        appropriation="delegacion_pasiva",
        appropriation_reason="sobreuso",
        ct_summary=0.5,
        ccd_mean=0.5,
        ccd_orphan_ratio=0.3,
        cii_stability=0.2,
        cii_evolution=0.2,
        features={"subgrupo": SUBGRUPO, "cii": {"iterations": 2}},
        is_current=True,
    )


def _sesion(primero: Any, persist_raises: Exception | None = None, tercero: Any = None) -> Any:
    s = MagicMock()
    s.added_rows = []
    s.commit = AsyncMock()
    s.rollback = AsyncMock()
    n = {"i": 0}
    s.add = s.added_rows.append

    async def _flush() -> None:
        if persist_raises is not None:
            raise persist_raises

    s.flush = _flush

    async def _execute(stmt: Any, *a: Any, **k: Any) -> Any:
        txt = str(stmt).strip().upper()
        if "SET_CONFIG" in txt:
            return MagicMock()
        if txt.startswith("SELECT"):
            n["i"] += 1
            r = MagicMock()
            valor = primero if n["i"] == 1 else (None if n["i"] == 2 else tercero)
            r.scalar_one_or_none = MagicMock(return_value=valor)
            return r
        return MagicMock()

    s.execute = _execute
    return s


@contextlib.asynccontextmanager
async def _ts(s: Any, _t: UUID) -> Any:
    yield s


def _ev(seq: int, tipo: str, payload: dict | None = None) -> dict:
    return {
        "seq": seq,
        "event_type": tipo,
        "ts": f"2026-11-20T10:{seq:02d}:00Z",
        "payload": payload or {},
    }


def _episodio_sobreuso(episode_id: UUID, comision_id: UUID) -> dict[str, Any]:
    """Seis consultas en rafaga con dos marcas de sobreuso (como el ej4)."""
    eventos = [_ev(0, "episodio_abierto")]
    seq = 1
    for i in range(6):
        eventos.append(_ev(seq, "prompt_enviado", {"content": f"pregunta {i}", "prompt_kind": "x"}))
        seq += 1
        eventos.append(_ev(seq, "tutor_respondio", {"content": "r"}))
        seq += 1
    for _ in range(2):
        eventos.append(_ev(seq, "intento_adverso_detectado", {"category": "overuse"}))
        seq += 1
    eventos.append(_ev(seq, "episodio_cerrado", {"reason": "student_finished"}))
    return {"episode_id": str(episode_id), "comision_id": str(comision_id), "events": eventos}


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _campos_del_get(body: dict) -> None:
    assert body.get("subgrupo"), body
    assert body["subgrupo"]["key"] == "dependiente_sobreuso"
    assert "regimen_llm" in body
    assert body.get("pasiva_por_sobreuso") is True, body


# ── C01 ─────────────────────────────────────────────────────────────────────
async def test_c01_post_nueva_trae_los_campos_del_get(client: AsyncClient) -> None:
    ep, com = uuid4(), uuid4()
    s = _sesion(None)
    with (
        patch("classifier_service.routes.classify_ep.tenant_session", lambda t: _ts(s, t)),
        patch(
            "classifier_service.routes.classify_ep._fetch_episode_from_ctr",
            AsyncMock(return_value=_episodio_sobreuso(ep, com)),
        ),
    ):
        r = await client.post(f"/api/v1/classify_episode/{ep}", headers=_headers())
    assert r.status_code == 201, r.text
    _campos_del_get(r.json())


async def test_c01_post_ya_existente_trae_los_campos_del_get(client: AsyncClient) -> None:
    ep, com = uuid4(), uuid4()
    h = compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE)
    s = _sesion(_fila(ep, com, h))
    with (
        patch("classifier_service.routes.classify_ep.tenant_session", lambda t: _ts(s, t)),
        patch("classifier_service.routes.classify_ep._fetch_episode_from_ctr", AsyncMock()),
    ):
        r = await client.post(f"/api/v1/classify_episode/{ep}", headers=_headers())
    assert r.status_code == 200, r.text
    _campos_del_get(r.json())


async def test_c01_post_carrera_trae_los_campos_del_get(client: AsyncClient) -> None:
    ep, com = uuid4(), uuid4()
    h = compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE)
    s = _sesion(
        None,
        persist_raises=IntegrityError("x", {}, Exception("dup")),
        tercero=_fila(ep, com, h),
    )
    with (
        patch("classifier_service.routes.classify_ep.tenant_session", lambda t: _ts(s, t)),
        patch(
            "classifier_service.routes.classify_ep._fetch_episode_from_ctr",
            AsyncMock(return_value=_episodio_sobreuso(ep, com)),
        ),
    ):
        r = await client.post(f"/api/v1/classify_episode/{ep}", headers=_headers())
    assert r.status_code == 200, r.text
    _campos_del_get(r.json())


# ── C12 ─────────────────────────────────────────────────────────────────────
async def test_c12_post_trae_cuantas_consultas_hubo(client: AsyncClient) -> None:
    # La pantalla de cierre necesita saber cuantas consultas hubo para no dar
    # "Cambiaste mucho de estrategia" con dos mensajes. Las metricas CII no se
    # tocan (invariante de la tesis): solo se expone su cantidad de iteraciones.
    ep, com = uuid4(), uuid4()
    s = _sesion(None)
    with (
        patch("classifier_service.routes.classify_ep.tenant_session", lambda t: _ts(s, t)),
        patch(
            "classifier_service.routes.classify_ep._fetch_episode_from_ctr",
            AsyncMock(return_value=_episodio_sobreuso(ep, com)),
        ),
    ):
        r = await client.post(f"/api/v1/classify_episode/{ep}", headers=_headers())
    assert r.status_code == 201, r.text
    assert r.json().get("cii_iteraciones") == 6, r.text


# ── C04 / N02: Probar cuenta como ejecucion ─────────────────────────────────
def _ediciones(desde: int, n: int) -> list[dict]:
    return [
        _ev(desde + i, "edicion_codigo", {"snapshot": f"x = {i}", "origin": "student_typed"})
        for i in range(n)
    ]


def _probar(seq: int, total: int, passed: int) -> dict:
    return _ev(
        seq,
        "tests_ejecutados",
        {
            "test_count_total": total,
            "test_count_passed": passed,
            "test_count_failed": total - passed,
            "tests_publicos": total,
            "tests_hidden": 0,
        },
    )


def test_c04_autonomo_que_solo_uso_probar_y_paso_todo_es_competente() -> None:
    # Como los ej5, ej10 y ej16 de la prueba 2: sin tutor, pocas ediciones,
    # dos Probar y el ultimo pasa todo.
    ev = [_ev(0, "episodio_abierto"), *_ediciones(1, 4), _probar(5, 2, 1), _probar(6, 2, 2)]
    ev.append(_ev(7, "episodio_cerrado"))
    assert clasificar_subgrupo(ev).key == "autonomo_competente"


def test_c04_con_tutor_y_solo_probar_no_es_desenganchado() -> None:
    # Como los ej1, ej7 y ej13: reflexivo con tutor, solo Probar.
    ev = [_ev(0, "episodio_abierto")]
    seq = 1
    for i in range(3):
        ev.append(_ev(seq, "prompt_enviado", {"content": f"creo que {i}", "prompt_kind": "x"}))
        ev.append(_ev(seq + 1, "tutor_respondio", {"content": "r"}))
        seq += 2
    ev += _ediciones(seq, 4)
    seq += 4
    ev += [_probar(seq, 2, 1), _probar(seq + 1, 2, 2), _ev(seq + 2, "episodio_cerrado")]
    assert clasificar_subgrupo(ev).key != "desenganchado"


def test_n02_ejecutar_sigue_contando_igual() -> None:
    ev = [
        _ev(0, "episodio_abierto"),
        *_ediciones(1, 4),
        _ev(5, "codigo_ejecutado", {"stdout": "ok", "stderr": ""}),
        _ev(6, "codigo_ejecutado", {"stdout": "ok", "stderr": ""}),
        _ev(7, "episodio_cerrado"),
    ]
    assert clasificar_subgrupo(ev).key == "autonomo_competente"


def test_n02_sin_ejecutar_ni_probar_sigue_siendo_poco_trabajo() -> None:
    ev = [_ev(0, "episodio_abierto"), *_ediciones(1, 5), _ev(6, "episodio_cerrado")]
    assert clasificar_subgrupo(ev).key == "autonomo_desenganchado"


def test_n02_probar_que_no_pasa_todo_no_resuelve() -> None:
    ev = [_ev(0, "episodio_abierto"), *_ediciones(1, 4), _probar(5, 2, 1), _probar(6, 2, 1)]
    ev.append(_ev(7, "episodio_cerrado"))
    assert clasificar_subgrupo(ev).key != "autonomo_competente"


def test_c04_sube_tree_version() -> None:
    # Cambia como se etiquetan episodios del estudio: el hash de configuracion
    # tiene que ser otro que el de main (tree_version v4.1.0).
    assert compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE) != (
        compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE, "v4.1.0")
    )


# ── C09: juez v3.1.0 con la regla de pedir la solucion ──────────────────────
def test_c09_version_nueva_del_juez_v3() -> None:
    from classifier_service.services import juez_v3

    assert juez_v3.PROMPT_VERSION_V3 == "mtac_v2_juez_v3.1.0"
    assert juez_v3.huella_prompt_v3() == juez_v3.HUELLA_PROMPT_V3
    assert (
        juez_v3.HUELLA_PROMPT_V3
        != "e3ae5d5c6f6cf1e2a93c889992f1513543178e55cfa610858cdf239baf1da4ed"
    )


def test_c09_el_prompt_tiene_la_regla_de_pedir_la_solucion() -> None:
    from classifier_service.services.juez_v3 import SYSTEM_PROMPT_V3

    # Las dos mitades de la regla en un mismo parrafo: cuando se pide (al
    # principio / al final para comparar) y que indica (pasiva / reflexiva).
    parrafos = [re.sub(r"\s+", " ", p).lower() for p in re.split(r"\n\s*\n", SYSTEM_PROMPT_V3)]
    candidatos = [
        p
        for p in parrafos
        if re.search(r"soluci[oó]n", p)
        and re.search(r"(al principio|al inicio|antes de intentar)", p)
        and re.search(r"compar", p)
        and "pasiva" in p
        and "reflexiva" in p
    ]
    assert candidatos, "falta la regla sobre cuando se pide la solucion"


def test_c09_la_regla_llega_al_mensaje_que_se_manda() -> None:
    from classifier_service.services.juez_v3 import construir_mensajes_v3

    msgs = construir_mensajes_v3("[alumno] pasame la solucion", "enunciado", "ep")
    sistema = msgs[0]["content"].lower()
    assert "compar" in sistema and "pasiva" in sistema


def test_n03_juez_v2_intacto() -> None:
    from classifier_service.services import juez_v2

    assert juez_v2.huella_prompt_v2() == juez_v2.HUELLA_PROMPT_V2
