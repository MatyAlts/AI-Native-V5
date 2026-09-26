"""Tests del borde de lectura de `features['regimen_llm']` (`GET /classifications/{id}`).

Bug real encontrado por QA (2026-09-25): `regimen_llm.py` trivalúa las 4
dimensiones y traduce el campo legado `oraculo: bool` de autonomía a
`presente: str` — pero SOLO cuando el dict pasa por `RegimenLLMRaw.model_validate`.
El único lugar de código no-test que valida contra ese modelo es
`clasificar_regimen_llm`, sobre la salida FRESCA del LLM. El endpoint de
lectura (`classify_ep.py::get_current_classification`) hacía
`out.regimen_llm = feats.get("regimen_llm")` — el dict crudo del JSONB, SIN
pasar por el modelo. Para V/E/J no se notaba (mismo nombre de campo, el
frontend ya toleraba booleano). Para autonomía SÍ: el campo se RENOMBRÓ
(`oraculo` → `presente`), y un registro juzgado bajo `eje_fino_v1.1.0` con la
forma real `{"oraculo": false, "evidencia": "..."}` (SIN clave `presente`)
perdía la dimensión de Autonomía en el frontend — en blanco, sin excepción y
sin log.

Fix: normalizar en el borde de lectura, en el único lugar que lee
`features['regimen_llm']` para devolverlo a un cliente (verificado con grep:
no hay otro camino de código en todo el monorepo).

## Cuáles de estos 6 tests son RED real contra el bug, y cuáles no

**Corrección post-auditoría (2026-09-25).** Un informe anterior afirmó "verifiqué
el RED de cada test nuevo" sin decir contra qué código. El auditor copió los 6
tests al código ANTERIOR al fix (`out.regimen_llm = feats.get("regimen_llm")`,
sin `normalizar_regimen_llm_persistido`) y corrió la suite completa:

```
2 failed, 4 passed
FAILED test_lectura_normaliza_autonomia_legada_de_solo_oraculo
FAILED test_lectura_normaliza_autonomia_legada_oraculo_true_a_ausente
```

Eso es la verificación real, y separa los 6 en dos categorías que NO son
intercambiables:

- **RED real (fallan sin el fix — reproducen el bug que QA reportó)**:
  `test_lectura_normaliza_autonomia_legada_de_solo_oraculo` y
  `test_lectura_normaliza_autonomia_legada_oraculo_true_a_ausente`. Son los
  únicos dos que ejercitan la clave `oraculo` sin `presente` — la forma exacta
  que el endpoint viejo devolvía sin traducir.

- **Guardas hacia adelante (pasan CON y SIN el fix)**:
  `test_lectura_sin_regimen_llm_no_rompe`,
  `test_lectura_con_regimen_llm_corrupto_degrada_sin_romper`,
  `test_lectura_pasa_forma_nativa_sin_alterarla` y
  `test_lectura_con_raw_none_no_rompe_ni_pierde_el_veredicto`. Ninguno de los
  cuatro detectó el bug de QA — el código viejo ya los pasaba, porque ninguno
  mete la clave `oraculo` sin `presente` por el único camino que la traducía
  mal. Lo que SÍ hacen es fijar un contrato que una reescritura futura de
  `normalizar_regimen_llm_persistido` podría romper (verificado para el de
  `raw=None`: simulando una implementación que accede a
  `data["raw"]["autonomia"]` sin guardar `None`, ESE test sí rompe con
  `TypeError`). Presentarlos como si hubieran atrapado el bug de QA sería
  exactamente el error que este comentario corrige: un test que no discrimina
  entre "esto ya andaba" y "esto lo arreglé yo" se lee como protección del
  pasado cuando en realidad es protección del futuro — y la próxima persona
  que lo lea merece saber cuál de las dos está comprando.

Cada docstring de test individual, más abajo, repite su categoría.
"""

from __future__ import annotations

import contextlib
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from classifier_service.main import app
from classifier_service.models import Classification
from httpx import ASGITransport, AsyncClient

DOCENTE_USER_ID = UUID("11111111-1111-1111-1111-111111111111")
TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


def _auth_headers() -> dict[str, str]:
    return {
        "X-User-Id": str(DOCENTE_USER_ID),
        "X-Tenant-Id": str(TENANT_ID),
        "X-User-Email": "docente@utn.test",
        "X-User-Roles": "docente",
    }


# Forma REAL persistida por un episodio juzgado bajo `eje_fino_v1.1.0` (ANTES
# de esta change): autonomía SOLO tiene `oraculo`, nunca tuvo `presente`. Esto
# es literalmente lo que hay hoy en `classifications.features` del piloto —
# no una forma fabricada para que el test pase.
_REGIMEN_LLM_LEGADO_REAL: dict[str, Any] = {
    "estado": "ok",
    "regimen": "REFLEXIVA",
    "confianza": 0.95,
    "raw": {
        "verbalizacion": {"presente": True, "evidencia": "explica el porque"},
        "verificacion": {"presente": True, "evidencia": "contrasta el resultado"},
        "justificacion": {"presente": True, "evidencia": "defiende su eleccion"},
        "autonomia": {"oraculo": False, "evidencia": "razona sin que se lo pidan"},
        "regimen": "REFLEXIVA",
        "confianza": 0.95,
        "justificacion_global": "consenso docente",
    },
    "razon": "Clasificación consistente con la regla y confianza suficiente.",
    "model_used": "gpt-4o",
    "prompt_version": "eje_fino_v1.1.0",
}


def _make_classification_con_regimen_llm(
    *, episode_id: UUID, comision_id: UUID, regimen_llm: dict[str, Any]
) -> Classification:
    return Classification(
        id=99,
        tenant_id=TENANT_ID,
        episode_id=episode_id,
        comision_id=comision_id,
        classifier_config_hash="hash-test",
        appropriation="apropiacion_reflexiva",
        appropriation_reason="juez",
        ct_summary=0.5,
        ccd_mean=0.5,
        ccd_orphan_ratio=0.3,
        cii_stability=0.4,
        cii_evolution=0.4,
        features={"regimen_llm": regimen_llm},
        is_current=True,
    )


def _make_readonly_session(classification: Classification | None) -> Any:
    session = MagicMock()

    async def _execute(*_args: Any, **_kwargs: Any) -> Any:
        res = MagicMock()
        res.scalar_one_or_none = MagicMock(return_value=classification)
        return res

    session.execute = _execute
    return session


@contextlib.asynccontextmanager
async def _fake_tenant_session(session: Any, _tenant_id: UUID) -> Any:
    yield session


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_lectura_normaliza_autonomia_legada_de_solo_oraculo(client: AsyncClient) -> None:
    """RED REAL (falla sin el fix — verificado corriendo esta suite contra
    `out.regimen_llm = feats.get("regimen_llm")`, sin normalizar: 2 failed,
    4 passed, ver docstring del módulo). Un registro juzgado bajo
    `eje_fino_v1.1.0`, con autonomía en su forma real (`oraculo`, SIN
    `presente`), tiene que llegar al cliente con `raw.autonomia.presente`
    seteado — no en blanco, no con la clave vieja."""
    episode_id = uuid4()
    comision_id = uuid4()
    classification = _make_classification_con_regimen_llm(
        episode_id=episode_id,
        comision_id=comision_id,
        regimen_llm=_REGIMEN_LLM_LEGADO_REAL,
    )
    session = _make_readonly_session(classification)

    with patch(
        "classifier_service.routes.classify_ep.tenant_session",
        lambda tid: _fake_tenant_session(session, tid),
    ):
        r = await client.get(f"/api/v1/classifications/{episode_id}", headers=_auth_headers())

    assert r.status_code == 200, r.text
    autonomia = r.json()["regimen_llm"]["raw"]["autonomia"]
    assert autonomia["presente"] == "presente", (
        f"esperaba autonomia normalizada a 'presente', llegó: {autonomia}"
    )
    assert "oraculo" not in autonomia, "la clave legada no debe llegar al cliente"


@pytest.mark.asyncio
async def test_lectura_normaliza_autonomia_legada_oraculo_true_a_ausente(
    client: AsyncClient,
) -> None:
    """RED REAL (falla sin el fix — mismo run de arriba). Segundo caso
    (triangulación): `oraculo: true` → `presente: "ausente"`."""
    episode_id = uuid4()
    comision_id = uuid4()
    regimen_llm = {
        **_REGIMEN_LLM_LEGADO_REAL,
        "regimen": "SUPERFICIAL",
        "raw": {
            **_REGIMEN_LLM_LEGADO_REAL["raw"],
            "autonomia": {"oraculo": True, "evidencia": "acepta sin cuestionar"},
            "regimen": "SUPERFICIAL",
        },
    }
    classification = _make_classification_con_regimen_llm(
        episode_id=episode_id, comision_id=comision_id, regimen_llm=regimen_llm
    )
    session = _make_readonly_session(classification)

    with patch(
        "classifier_service.routes.classify_ep.tenant_session",
        lambda tid: _fake_tenant_session(session, tid),
    ):
        r = await client.get(f"/api/v1/classifications/{episode_id}", headers=_auth_headers())

    assert r.status_code == 200, r.text
    autonomia = r.json()["regimen_llm"]["raw"]["autonomia"]
    assert autonomia["presente"] == "ausente"


@pytest.mark.asyncio
async def test_lectura_sin_regimen_llm_no_rompe(client: AsyncClient) -> None:
    """GUARDA HACIA ADELANTE (pasa CON y SIN el fix — no detectó el bug de QA,
    ver docstring del módulo). Episodio sin veredicto del juez (`features` sin
    `regimen_llm`) sigue devolviendo `regimen_llm: null`, no explota la
    normalización."""
    episode_id = uuid4()
    comision_id = uuid4()
    classification = Classification(
        id=100,
        tenant_id=TENANT_ID,
        episode_id=episode_id,
        comision_id=comision_id,
        classifier_config_hash="hash-test",
        appropriation="apropiacion_superficial",
        appropriation_reason="proxy",
        ct_summary=0.5,
        ccd_mean=0.5,
        ccd_orphan_ratio=0.3,
        cii_stability=0.4,
        cii_evolution=0.4,
        features={},
        is_current=True,
    )
    session = _make_readonly_session(classification)

    with patch(
        "classifier_service.routes.classify_ep.tenant_session",
        lambda tid: _fake_tenant_session(session, tid),
    ):
        r = await client.get(f"/api/v1/classifications/{episode_id}", headers=_auth_headers())

    assert r.status_code == 200, r.text
    assert r.json()["regimen_llm"] is None


@pytest.mark.asyncio
async def test_lectura_con_regimen_llm_corrupto_degrada_sin_romper(client: AsyncClient) -> None:
    """GUARDA HACIA ADELANTE (pasa CON y SIN el fix: sin normalización no hay
    nada que romperse — el dict corrupto se devolvía tal cual antes también.
    No detectó el bug de QA; ver docstring del módulo). Documenta que un
    `features['regimen_llm']` corrupto (forma no anticipada, le falta todo lo
    requerido) NO debe tirar 500 después del fix — la lectura se degrada
    devolviendo el dict tal cual llegó, y el caso queda para investigar por
    log, no por un episodio que el docente no puede ni siquiera abrir."""
    episode_id = uuid4()
    comision_id = uuid4()
    regimen_llm_corrupto = {"esto": "no tiene la forma esperada"}
    classification = _make_classification_con_regimen_llm(
        episode_id=episode_id, comision_id=comision_id, regimen_llm=regimen_llm_corrupto
    )
    session = _make_readonly_session(classification)

    with patch(
        "classifier_service.routes.classify_ep.tenant_session",
        lambda tid: _fake_tenant_session(session, tid),
    ):
        r = await client.get(f"/api/v1/classifications/{episode_id}", headers=_auth_headers())

    assert r.status_code == 200, r.text
    assert r.json()["regimen_llm"] == regimen_llm_corrupto


# Forma REAL de un veredicto `error_parseo` (dato duro, consultado por el
# coordinador contra la base del piloto 2026-09-25): de 689 episodios con
# `regimen_llm`, 26 NO tienen `raw.autonomia` — porque `raw` es directamente
# `None`. Es literal lo que `regimen_llm.py::clasificar_regimen_llm` persiste
# para `error_parseo`/`baja_confianza`/`inconsistente`: nunca un dict con la
# clave `autonomia` ausente, sino `raw: None` entero.
_REGIMEN_LLM_SIN_RAW_REAL: dict[str, Any] = {
    "estado": "error_parseo",
    "regimen": None,
    "confianza": None,
    "raw": None,
    "razon": "El juez no devolvió un veredicto usable: JSONDecodeError. Va a revisión humana.",
    "model_used": "gpt-4o",
    "prompt_version": "eje_fino_v1.1.0",
}


# Forma nueva nativa (0 casos hoy en producción, medido — el código todavía
# no se desplegó; será la forma de todo episodio juzgado DESPUÉS del deploy).
_REGIMEN_LLM_NATIVO_REAL: dict[str, Any] = {
    **_REGIMEN_LLM_LEGADO_REAL,
    "prompt_version": "eje_fino_v1.2.0",
    "raw": {
        **_REGIMEN_LLM_LEGADO_REAL["raw"],
        "autonomia": {"presente": "presente", "evidencia": "razona sin que se lo pidan"},
    },
}


@pytest.mark.asyncio
async def test_lectura_pasa_forma_nativa_sin_alterarla(client: AsyncClient) -> None:
    """GUARDA HACIA ADELANTE (pasa CON y SIN el fix, porque el dict ya viene en
    forma nativa — no hay traducción que hacer en ningún caso. No detectó el
    bug de QA; ver docstring del módulo). Documenta una de las tres formas
    reales que hoy circulan (o van a circular) en producción: un registro ya
    juzgado con el código nuevo. Tiene que llegar al cliente sin alteración —
    la normalización es idempotente."""
    episode_id = uuid4()
    comision_id = uuid4()
    classification = _make_classification_con_regimen_llm(
        episode_id=episode_id,
        comision_id=comision_id,
        regimen_llm=_REGIMEN_LLM_NATIVO_REAL,
    )
    session = _make_readonly_session(classification)

    with patch(
        "classifier_service.routes.classify_ep.tenant_session",
        lambda tid: _fake_tenant_session(session, tid),
    ):
        r = await client.get(f"/api/v1/classifications/{episode_id}", headers=_auth_headers())

    assert r.status_code == 200, r.text
    assert r.json()["regimen_llm"]["raw"]["autonomia"]["presente"] == "presente"


@pytest.mark.asyncio
async def test_lectura_con_raw_none_no_rompe_ni_pierde_el_veredicto(client: AsyncClient) -> None:
    """GUARDA HACIA ADELANTE, NO RED contra el bug de QA (pasa CON y SIN el
    fix — verificado en el mismo run del módulo: `feats.get("regimen_llm")`
    sin normalizar ya devolvía `raw: None` intacto, porque no hay ninguna
    clave que traducir cuando `raw` es `None`). Lo que SÍ certifica, y para
    lo que sirve de acá en adelante: la forma real de 26/689 episodios en
    producción (`error_parseo`, `raw=None`) no rompe la NORMALIZACIÓN. Fue
    verificado deliberadamente rompiendo el código a propósito — reemplazando
    `normalizar_regimen_llm_persistido` por una versión ingenua que hace
    `data["raw"]["autonomia"]` sin guardar `None` — y confirmando que ESTE
    test sí revienta ahí con `TypeError: 'NoneType' object is not
    subscriptable`. Esa es la regresión futura que atrapa; el bug de QA no."""
    episode_id = uuid4()
    comision_id = uuid4()
    classification = _make_classification_con_regimen_llm(
        episode_id=episode_id,
        comision_id=comision_id,
        regimen_llm=_REGIMEN_LLM_SIN_RAW_REAL,
    )
    session = _make_readonly_session(classification)

    with patch(
        "classifier_service.routes.classify_ep.tenant_session",
        lambda tid: _fake_tenant_session(session, tid),
    ):
        r = await client.get(f"/api/v1/classifications/{episode_id}", headers=_auth_headers())

    assert r.status_code == 200, r.text
    body = r.json()["regimen_llm"]
    assert body["estado"] == "error_parseo"
    assert body["raw"] is None
