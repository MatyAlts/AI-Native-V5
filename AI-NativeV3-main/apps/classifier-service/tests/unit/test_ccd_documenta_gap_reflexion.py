"""F19: ancla la operacionalización CCD vigente (v2.0.0, 2026-05-21).

El gap declarado en v1.0.0 (que el `prompt_kind="reflexion"` nunca se
emitía y por eso CCD subestimaba la verbalización) fue cerrado en
v2.0.0 reconociendo los 5 kinds reflexivos reales que el tutor-service
emite via `infer_prompt_kind`. Este test ancla el nuevo set para
prevenir regresiones (alguien sumando un kind reflexivo nuevo al
contract sin agregarlo a `_REFLECTIVE_KINDS` de ccd.py).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from classifier_service.services.ccd import compute_ccd
from platform_contracts.ctr.events import PromptEnviadoPayload


def _ev(seq: int, event_type: str, sec_offset: int, payload: dict[str, Any]) -> dict[str, Any]:
    base = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
    return {
        "seq": seq,
        "event_type": event_type,
        "ts": (base + timedelta(seconds=sec_offset)).isoformat().replace("+00:00", "Z"),
        "payload": payload,
    }


def test_prompt_kind_admite_6_valores_v2() -> None:
    """v2.0.0: PromptKind admite 6 valores. 'exploracion' fue agregado el
    2026-05-21 porque el runtime ya lo emitía (100 eventos en DB) y faltaba
    en el contrato.

    Si se agrega un kind nuevo al contract:
      - Decidir si es reflexivo o no
      - Agregarlo a `_REFLECTIVE_KINDS` de `ccd.py` si corresponde
      - Bumpear `LABELER_VERSION` si cambia la operacionalización
    """
    field_info = PromptEnviadoPayload.model_fields["prompt_kind"]
    valores_admitidos = set(field_info.annotation.__args__)
    assert valores_admitidos == {
        "solicitud_directa",
        "comparativa",
        "epistemologica",
        "validacion",
        "aclaracion_enunciado",
        "exploracion",
    }


def test_prompt_solicitud_directa_de_contenido_reflexivo_cuenta_como_huerfano() -> None:
    """Un prompt con contenido reflexivo emitido como 'solicitud_directa'
    (lo que pasa hoy en el runtime real) NO se cuenta como reflexión y
    queda como acción huérfana — confirmando el sesgo declarado en docstring.
    """
    events = [
        _ev(
            0, "codigo_ejecutado", 0, {"code": "print(x)", "duration_ms": 10, "runtime": "pyodide"}
        ),
        # Prompt con contenido reflexivo, PERO tagged 'solicitud_directa'
        # (porque tutor_core.py:201 hardcodea ese kind para todos los prompts):
        _ev(
            1,
            "prompt_enviado",
            5,
            {
                "content": "Acabo de darme cuenta que mi loop tiene complejidad cuadrática y por eso no escala",
                "prompt_kind": "solicitud_directa",
                "chunks_used_hash": None,
            },
        ),
    ]
    r = compute_ccd(events)
    # Sin `anotacion_creada` y sin `prompt_kind="reflexion"`, el ejecutado
    # queda huérfano. El prompt "reflexivo" cuenta como acción, no como giro.
    assert r["pairs"] >= 1, "El codigo_ejecutado debe figurar como acción"
    assert r["orphans"] >= 1, (
        "Sin reflexión correlacionada, el ejecutado queda huérfano — confirma el sesgo del v1.0.0."
    )
    assert r["ccd_orphan_ratio"] == r["orphans"] / r["pairs"]


def test_anotacion_creada_si_se_correlaciona_como_reflexion() -> None:
    """Sanity: la rama (a) del docstring sí funciona — `anotacion_creada`
    correlaciona con la acción previa dentro de la ventana de 2 min.
    """
    events = [
        _ev(
            0, "codigo_ejecutado", 0, {"code": "print(x)", "duration_ms": 10, "runtime": "pyodide"}
        ),
        _ev(1, "anotacion_creada", 30, {"content": "ahora se por que falla", "words": 6}),
    ]
    r = compute_ccd(events)
    assert r["pairs"] == 1
    assert r["orphans"] == 0
    assert r["aligned"] == 1
