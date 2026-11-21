"""Aceptacion HU-009, segunda vuelta (orquestador, antes de construir; el
constructor no la modifica).

Sale de la verificacion independiente del PR #141 (21/11/2026): para el juez
v3.1.0 se agrego la seccion "CUANDO SE PIDE LA SOLUCION" en el mismo prompt, y
el v3.0.0 dejo de poder armarse. N03 pide que las versiones anteriores no
cambien y que solo se agreguen versiones nuevas.

N03b  El prompt del juez v3.0.0 sigue pudiendose armar, con su huella de
      siempre (e3ae5d5c...), y sin la seccion nueva.
N03c  v3.1.0 sigue siendo la version por defecto, con su huella (1e3e4778...)
      y con la seccion nueva.
N03d  La version se elige por configuracion (`eje_fino_juez_v3_prompt`) y el
      resultado del juez registra la version que de verdad uso.

Contrato que fija esta prueba:
  juez_v3.PROMPTS_V3: dict  version -> system prompt
  juez_v3.huella_prompt_v3(version: str | None = None) -> str
  juez_v3.construir_mensajes_v3(traza, enunciado, episode_id, version=None)
  juez_v3.clasificar_regimen_v3(..., prompt_version=None)
  Settings.eje_fino_juez_v3_prompt, por defecto "mtac_v2_juez_v3.1.0"
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from classifier_service.config import Settings
from classifier_service.services import juez_v3

V300 = "mtac_v2_juez_v3.0.0"
V310 = "mtac_v2_juez_v3.1.0"
HUELLA_V300 = "e3ae5d5c6f6cf1e2a93c889992f1513543178e55cfa610858cdf239baf1da4ed"
HUELLA_V310 = "1e3e477898af36ae13a60a7fd080d5c4f2fd28049899ad79304da48eab24b24f"
SECCION_NUEVA = "CUÁNDO SE PIDE LA SOLUCIÓN"


def test_n03b_v300_se_puede_armar_con_su_huella() -> None:
    assert V300 in juez_v3.PROMPTS_V3
    assert juez_v3.huella_prompt_v3(V300) == HUELLA_V300
    assert SECCION_NUEVA not in juez_v3.PROMPTS_V3[V300]


def test_n03c_v310_es_la_de_siempre_por_defecto() -> None:
    assert juez_v3.PROMPT_VERSION_V3 == V310
    assert juez_v3.huella_prompt_v3() == HUELLA_V310
    assert juez_v3.huella_prompt_v3(V310) == HUELLA_V310
    assert SECCION_NUEVA in juez_v3.PROMPTS_V3[V310]
    assert juez_v3.SYSTEM_PROMPT_V3 == juez_v3.PROMPTS_V3[V310]


def test_n03b_las_dos_versiones_solo_difieren_en_la_seccion_nueva() -> None:
    viejo = juez_v3.PROMPTS_V3[V300]
    nuevo = juez_v3.PROMPTS_V3[V310]
    assert len(nuevo) > len(viejo)
    inicio = nuevo.index(SECCION_NUEVA)
    # Lo que esta antes de la seccion nueva es identico.
    assert viejo[:inicio] == nuevo[:inicio]


@pytest.mark.parametrize("version", [V300, V310])
def test_n03d_los_mensajes_usan_la_version_pedida(version: str) -> None:
    mensajes = juez_v3.construir_mensajes_v3("traza", "enunciado", "ep", version=version)
    assert mensajes[0]["role"] == "system"
    assert mensajes[0]["content"] == juez_v3.PROMPTS_V3[version]


def test_n03d_version_desconocida_no_se_inventa() -> None:
    with pytest.raises((KeyError, ValueError)):
        juez_v3.construir_mensajes_v3("traza", "enunciado", "ep", version="mtac_v2_juez_v9.9.9")


def test_n03d_la_configuracion_elige_y_por_defecto_es_v310() -> None:
    assert Settings().eje_fino_juez_v3_prompt == V310
    assert Settings(eje_fino_juez_v3_prompt=V300).eje_fino_juez_v3_prompt == V300


@pytest.mark.asyncio
@pytest.mark.parametrize("version", [V300, V310])
async def test_n03d_el_resultado_registra_la_version_usada(version: str) -> None:
    vistos: list[str] = []

    async def complete(*, messages, **_kw):  # noqa: ANN001, ANN003
        vistos.append(messages[0]["content"])
        return SimpleNamespace(
            content=json.dumps({"no": "es un json valido para el juez"}),
            provider="prueba",
            output_tokens=10,
        )

    resultado = await juez_v3.clasificar_regimen_v3(
        events=[],
        enunciado="x",
        episode_id="ep",
        complete=complete,
        model="m",
        tenant_id=uuid4(),
        max_reintentos=0,
        prompt_version=version,
    )
    assert resultado.prompt_version == version
    assert vistos, "el juez no llamo al modelo"
    assert all(v == juez_v3.PROMPTS_V3[version] for v in vistos)
