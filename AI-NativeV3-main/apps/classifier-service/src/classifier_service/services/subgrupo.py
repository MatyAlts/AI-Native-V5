"""Medición de apropiación por subgrupos (modo sombra — B1 Fase 2).

Calcula, sobre los eventos del episodio, **4 dimensiones observables** y un
**subgrupo** (1 de 8) que hace roll-up a los 3 ejes clásicos (reflexiva /
superficial / delegacion_pasiva).

ADITIVO Y REVERSIBLE: el resultado se persiste en `Classification.features['subgrupo']`
(JSONB) — NO toca `appropriation` ni `classifier_config_hash` (features no entra al
hash canónico), así que NO rompe la reproducibilidad bit-a-bit del piloto-1. Es un
dato "al lado" del clasificador oficial. Ver `docs/NUEVA-MEDICION-SUBGRUPOS.md`.

Corrige la inversión del motor viejo (alumnos autónomos sin tutor marcados como
`delegacion_pasiva`). Umbrales calibrados sobre datos reales de prod (2026-06-10):
`edicion_codigo.origin` ∈ {student_typed, pasted_external} (no existe copied_from_tutor),
`anotacion_creada` = 0, `resolvió` = última ejecución limpia (stdout sin stderr),
sin `tests_ejecutados`/`tp_entregada` en el CTR.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ── Umbrales calibrables (ver docs/NUEVA-MEDICION-SUBGRUPOS.md) ──
PROMPT_SCALE = 6
EXEC_SCALE = 8
FOCUS_SCALE = 3
MIN_EVENTS = 4
DEP_SOLICITA = 2
DEP_EXP = 0.4
REFLEX_EXP = 0.4
TRABADO_MIN_EJEC = 2
EDIT_MIN = 10

# Mismos kinds reflexivos que ccd.py
_REFLECTIVE_KINDS = frozenset(
    {"exploracion", "aclaracion_enunciado", "comparativa", "epistemologica", "validacion"}
)
# Mismas exclusiones que pipeline._EXCLUDED_FROM_FEATURES
_EXCLUDED = frozenset({"reflexion_completada", "tp_entregada", "tp_calificada"})


@dataclass(frozen=True)
class Subgrupo:
    key: str
    label: str
    accion_docente: str
    eje: str  # roll-up: reflexiva | superficial | delegacion_pasiva | sin_clasificar


INDETERMINADO = Subgrupo("indeterminado", "Indeterminado", "No concluir - episodio muy corto", "sin_clasificar")
AUTONOMO_COMPETENTE = Subgrupo("autonomo_competente", "Autonomo competente", "Darle mas desafio", "reflexiva")
AUTONOMO_TRABADO = Subgrupo("autonomo_trabado", "Autonomo trabado", "Ofrecer scaffolding", "superficial")
DESENGANCHADO = Subgrupo("desenganchado", "Desenganchado", "Re-enganchar", "superficial")
ESCRIBE_SIN_VALIDAR = Subgrupo("escribe_sin_validar", "Escribio sin validar", "Fomentar ejecutar y probar el codigo", "superficial")
DEPENDIENTE = Subgrupo("dependiente_delegador", "Dependiente / delegador", "Intervenir (copio de la IA)", "delegacion_pasiva")
COLABORADOR_REFLEXIVO = Subgrupo("colaborador_reflexivo", "Colaborador reflexivo", "Va bien", "reflexiva")
COLABORADOR_FUNCIONAL = Subgrupo("colaborador_funcional", "Colaborador funcional", "Empujar a profundizar", "superficial")


def _kind(e: dict) -> str:
    return (e.get("payload") or {}).get("prompt_kind") or ""


def _count(events: list[dict], et: str) -> int:
    return sum(1 for e in events if e.get("event_type") == et)


def _significativos(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("event_type") not in _EXCLUDED]


# ── Las 4 dimensiones (cada una en [0,1]) ──
def dim_autonomia(events: list[dict]) -> float:
    """1.0 = autónomo puro. origin real en prod: student_typed / pasted_external."""
    prompts = _count(events, "prompt_enviado")
    ediciones = [e for e in events if e.get("event_type") == "edicion_codigo"]
    pegadas = sum(1 for e in ediciones if (e.get("payload") or {}).get("origin") == "pasted_external")
    paste_ratio = pegadas / len(ediciones) if ediciones else 0.0
    return 0.5 * (1.0 - min(1.0, prompts / PROMPT_SCALE)) + 0.5 * (1.0 - paste_ratio)


def dim_experimentacion(events: list[dict]) -> float:
    return min(1.0, (_count(events, "codigo_ejecutado") + _count(events, "tests_ejecutados")) / EXEC_SCALE)


def dim_persistencia(events: list[dict]) -> float:
    """Recuperación tras error de ejecución (stderr no vacío)."""
    sev = sorted(events, key=lambda e: e.get("seq", 0))
    fallos = recup = 0
    for i, e in enumerate(sev):
        p = e.get("payload") or {}
        if e.get("event_type") == "codigo_ejecutado" and (p.get("stderr") or "") != "":
            fallos += 1
            if any(ev.get("event_type") in ("edicion_codigo", "codigo_ejecutado") for ev in sev[i + 1:]):
                recup += 1
    return 1.0 if fallos == 0 else recup / fallos


def dim_foco(events: list[dict]) -> float:
    distr = (
        _count(events, "pestana_perdida")
        + _count(events, "copia_intentada")
        + _count(events, "pega_intentada")
    )
    return 1.0 / (1.0 + distr / FOCUS_SCALE)


def _resolvio(events: list[dict]) -> bool:
    """La ÚLTIMA ejecución terminó limpia (stdout no vacío, sin stderr)."""
    ejec = [e for e in sorted(events, key=lambda e: e.get("seq", 0)) if e.get("event_type") == "codigo_ejecutado"]
    if not ejec:
        return False
    p = ejec[-1].get("payload") or {}
    return (p.get("stdout") or "") != "" and (p.get("stderr") or "") == ""


def clasificar_subgrupo(events: list[dict]) -> Subgrupo:
    """Árbol de 8 subgrupos. El gate `prompts == 0` corrige la inversión:
    sin prompts, delegar es imposible → rama autónoma."""
    sig = _significativos(events)
    if len(sig) < MIN_EVENTS:
        return INDETERMINADO

    prompts = _count(events, "prompt_enviado")
    ejec = _count(events, "codigo_ejecutado")
    ediciones = _count(events, "edicion_codigo")
    exp = dim_experimentacion(events)
    sol_directa = sum(
        1 for e in events
        if e.get("event_type") == "prompt_enviado" and _kind(e) == "solicitud_directa"
    )
    poco_trabajo = ediciones < EDIT_MIN and ejec < TRABADO_MIN_EJEC

    if prompts == 0:
        if poco_trabajo:
            return DESENGANCHADO
        if _resolvio(events):
            return AUTONOMO_COMPETENTE
        if ejec >= TRABADO_MIN_EJEC:
            return AUTONOMO_TRABADO
        return ESCRIBE_SIN_VALIDAR

    # con prompts: delegación ANTES que "poco trabajo" (el delegador copia, no trabaja)
    if sol_directa >= DEP_SOLICITA and exp < DEP_EXP:
        return DEPENDIENTE
    if poco_trabajo:
        return DESENGANCHADO
    if exp >= REFLEX_EXP:
        return COLABORADOR_REFLEXIVO
    return COLABORADOR_FUNCIONAL


def compute_subgrupo(events: list[dict]) -> dict[str, Any]:
    """Subgrupo + dimensiones, listo para persistir en Classification.features['subgrupo']."""
    sg = clasificar_subgrupo(events)
    return {
        "key": sg.key,
        "label": sg.label,
        "accion_docente": sg.accion_docente,
        "eje": sg.eje,
        "dimensiones": {
            "autonomia": round(dim_autonomia(events), 2),
            "experimentacion": round(dim_experimentacion(events), 2),
            "persistencia": round(dim_persistencia(events), 2),
            "foco": round(dim_foco(events), 2),
        },
    }
