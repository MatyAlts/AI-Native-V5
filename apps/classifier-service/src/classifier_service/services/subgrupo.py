"""Medición de apropiación por subgrupos (modo sombra — B1 Fase 2).

Calcula, sobre los eventos del episodio, **4 dimensiones observables** y un
**subgrupo** que hace roll-up a los ejes (reflexiva / superficial /
delegacion_pasiva / autonomo / sin_clasificar). El eje `autonomo` (v4.0.0) se
lleva TODO el brazo sin-tutor (`prompts == 0`): sin conversación que juzgar, no
hay apropiación reflexiva/superficial que medir contra el discurso.

ADITIVO Y REVERSIBLE: el resultado se persiste en `Classification.features['subgrupo']`
(JSONB) — NO toca `appropriation` ni `classifier_config_hash` (features no entra al
hash canónico), así que NO rompe la reproducibilidad bit-a-bit del piloto-1. Es un
dato "al lado" del clasificador oficial. Ver `docs/NUEVA-MEDICION-SUBGRUPOS.md`.

Corrige la inversión del motor viejo (alumnos autónomos sin tutor marcados como
`delegacion_pasiva`). Umbrales calibrados sobre datos reales de prod (2026-06-10):
`edicion_codigo.origin` ∈ {student_typed, pasted_external} (no existe copied_from_tutor;
`snippet_expanded` se agregó después y NO cuenta como pegada — un snippet de ceremonia
del editor no es delegación, así que no baja la autonomía),
`anotacion_creada` = 0, `resolvió` = última ejecución limpia (stdout sin stderr).

HU-009 (tree_version v4.2.0): Probar (`tests_ejecutados`) cuenta como ejecución.
Cuando se calibró, Probar no emitía evento; hoy lo emite el execution-service, y
un alumno que solo usaba Probar y pasaba todo caía en "poco trabajo"
(`desenganchado` / `autonomo_desenganchado`). Ahora suma al conteo de
ejecuciones y el último Probar que pasa todo (`test_count_failed == 0` y
`test_count_total > 0`) cuenta como resuelto. Ejecutar sigue contando igual.

HU-010 (tree_version v4.3.0): quien Probó y pasó todo NO trabajó poco. La regla
de "poco trabajo" (menos de `EDIT_MIN` ediciones y menos de `TRABADO_MIN_EJEC`
ejecuciones) no miraba si el alumno había resuelto, así que el que escribía la
solución de una y la Probaba una sola vez, pasando todo, salía `desenganchado`
("Quedó a mitad de camino", prueba como alumno del 21/11/2026). Ahora, si el
ÚLTIMO Probar pasó todos sus casos (`_probar_paso_todo`), el episodio nunca es
"poco trabajo". La excepción mira SOLO Probar, no `_resolvio` entero: un único
Ejecutar que imprime algo sin error (un `print("hola")`) no compara contra lo
esperado y no prueba que resolvió, así que sigue siendo poco trabajo. Vale en
los dos brazos:
sin tutor sale `autonomo_competente`; con tutor sigue el árbol, y el sobreuso y
la delegación por solicitud directa se siguen chequeando ANTES (el que pidió la
solución sigue siendo `dependiente_delegador` aunque después Probar pase todo).
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
# Sobreuso del tutor (v3.1.0, hallazgo 2026-06-20): cantidad de marcas
# `intento_adverso_detectado` (category=overuse) a partir de la cual el alumno
# se considera DEPENDIENTE (se apoya de mas en el tutor) en lugar de reflexivo.
# Antes el motor ignoraba esta senal e inflaba "apropiacion_reflexiva" con
# alumnos que en realidad abusaban del tutor. Umbral CALIBRABLE — confirmar con
# direccion de tesis (ver 00-Inbox/2026-06-20-hallazgo-clasificador-...).
OVERUSE_DEP_THRESHOLD = 2

# Mismos kinds reflexivos que ccd.py
_REFLECTIVE_KINDS = frozenset(
    {"exploracion", "aclaracion_enunciado", "comparativa", "epistemologica", "validacion"}
)
# Mismas exclusiones que pipeline._EXCLUDED_FROM_FEATURES
_EXCLUDED = frozenset(
    {"reflexion_completada", "tp_entregada", "tp_calificada", "episodio_reabierto"}
)


@dataclass(frozen=True)
class Subgrupo:
    key: str
    label: str
    accion_docente: str
    eje: str  # roll-up: reflexiva | superficial | delegacion_pasiva | autonomo | sin_clasificar


INDETERMINADO = Subgrupo(
    "indeterminado", "Indeterminado", "No concluir - episodio muy corto", "sin_clasificar"
)
# Brazo sin-tutor (prompts == 0): TODO el brazo rollea al eje `autonomo` (v4.0.0).
# Estos subgrupos son SOLO alcanzables desde el gate `prompts == 0` en
# `clasificar_subgrupo`, por eso su eje fijo es `autonomo` sin ambiguedad.
AUTONOMO_COMPETENTE = Subgrupo(
    "autonomo_competente", "Autonomo competente", "Darle mas desafio", "autonomo"
)
AUTONOMO_TRABADO = Subgrupo(
    "autonomo_trabado", "Autonomo trabado", "Ofrecer scaffolding", "autonomo"
)
ESCRIBE_SIN_VALIDAR = Subgrupo(
    "escribe_sin_validar",
    "Escribio sin validar",
    "Fomentar ejecutar y probar el codigo",
    "autonomo",
)
# `autonomo_desenganchado` = el "poco trabajo" del brazo SIN tutor. Es un subgrupo
# PROPIO (no el `desenganchado` compartido) justamente para que el brazo prompts==0
# NUNCA emita el `desenganchado` (eje superficial) — el `desenganchado` queda
# reservado al brazo CON tutor (prompts > 0), que sigue rolleando a `superficial`.
AUTONOMO_DESENGANCHADO = Subgrupo(
    "autonomo_desenganchado",
    "Autonomo desenganchado",
    "Re-enganchar (trabajo solo, sin avance)",
    "autonomo",
)
DESENGANCHADO = Subgrupo("desenganchado", "Desenganchado", "Re-enganchar", "superficial")
DEPENDIENTE = Subgrupo(
    "dependiente_delegador",
    "Dependiente / delegador",
    "Intervenir (copio de la IA)",
    "delegacion_pasiva",
)
DEPENDIENTE_SOBREUSO = Subgrupo(
    "dependiente_sobreuso",
    "Dependiente (sobreuso)",
    "Intervenir - se apoya de mas en el tutor (overuse)",
    "delegacion_pasiva",
)
COLABORADOR_REFLEXIVO = Subgrupo(
    "colaborador_reflexivo", "Colaborador reflexivo", "Va bien", "reflexiva"
)
COLABORADOR_FUNCIONAL = Subgrupo(
    "colaborador_funcional", "Colaborador funcional", "Empujar a profundizar", "superficial"
)


def _kind(e: dict) -> str:
    return (e.get("payload") or {}).get("prompt_kind") or ""


def _count(events: list[dict], et: str) -> int:
    return sum(1 for e in events if e.get("event_type") == et)


def _significativos(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("event_type") not in _EXCLUDED]


# ── Las 4 dimensiones (cada una en [0,1]) ──
def dim_autonomia(events: list[dict]) -> float:
    """1.0 = autónomo puro. origin real en prod: student_typed / pasted_external.

    `pasted_internal` (el alumno reordenando su propio código) NO cuenta como
    pegada, y es deliberado: la dimensión mide dependencia de fuentes ajenas, y
    mover un bloque propio de lugar no lo es. Cae del lado autónomo por la
    comparación de abajo, que pregunta por `pasted_external` y no por "hubo un
    paste" — si algún día se reescribe como denylist, este es el caso que se
    rompe en silencio y le baja la autonomía a quien ordena su código.
    """
    prompts = _count(events, "prompt_enviado")
    ediciones = [e for e in events if e.get("event_type") == "edicion_codigo"]
    pegadas = sum(
        1 for e in ediciones if (e.get("payload") or {}).get("origin") == "pasted_external"
    )
    paste_ratio = pegadas / len(ediciones) if ediciones else 0.0
    return 0.5 * (1.0 - min(1.0, prompts / PROMPT_SCALE)) + 0.5 * (1.0 - paste_ratio)


def dim_experimentacion(events: list[dict]) -> float:
    return min(
        1.0, (_count(events, "codigo_ejecutado") + _count(events, "tests_ejecutados")) / EXEC_SCALE
    )


def dim_persistencia(events: list[dict]) -> float:
    """Recuperación tras error de ejecución (stderr no vacío)."""
    sev = sorted(events, key=lambda e: e.get("seq", 0))
    fallos = recup = 0
    for i, e in enumerate(sev):
        p = e.get("payload") or {}
        if e.get("event_type") == "codigo_ejecutado" and (p.get("stderr") or "") != "":
            fallos += 1
            if any(
                ev.get("event_type") in ("edicion_codigo", "codigo_ejecutado")
                for ev in sev[i + 1 :]
            ):
                recup += 1
    return 1.0 if fallos == 0 else recup / fallos


def dim_foco(events: list[dict]) -> float:
    distr = (
        _count(events, "pestana_perdida")
        + _count(events, "copia_intentada")
        + _count(events, "pega_intentada")
    )
    return 1.0 / (1.0 + distr / FOCUS_SCALE)


def _ultimo(events: list[dict], et: str) -> dict | None:
    del_tipo = [
        e for e in sorted(events, key=lambda e: e.get("seq", 0)) if e.get("event_type") == et
    ]
    return del_tipo[-1] if del_tipo else None


def _probar_paso_todo(events: list[dict]) -> bool:
    """El ÚLTIMO Probar pasó todos sus casos (`test_count_total > 0` y
    `test_count_failed == 0`). Es la única señal que compara contra lo esperado."""
    probar = _ultimo(events, "tests_ejecutados")
    if probar is None:
        return False
    p = probar.get("payload") or {}
    return (p.get("test_count_total") or 0) > 0 and p.get("test_count_failed") == 0


def _resolvio(events: list[dict]) -> bool:
    """La ÚLTIMA ejecución terminó limpia (stdout no vacío, sin stderr), o el
    ÚLTIMO Probar pasó todos sus casos (HU-009).

    Son dos señales independientes y alcanza con una: Probar pasa todo y
    después un Ejecutar sin datos de entrada termina en error de `input()` es
    un patrón común, y no deshace lo que Probar ya verificó.
    """
    ejec = _ultimo(events, "codigo_ejecutado")
    if ejec is not None:
        p = ejec.get("payload") or {}
        if (p.get("stdout") or "") != "" and (p.get("stderr") or "") == "":
            return True
    return _probar_paso_todo(events)


def _verbaliza(events: list[dict]) -> bool:
    """Hay reflexion explicita: una anotacion escrita o un prompt reflexivo
    (mismos kinds que ccd.py). Un alumno que reflexiona NO es un delegador puro."""
    if _count(events, "anotacion_creada") > 0:
        return True
    return any(
        e.get("event_type") == "prompt_enviado" and _kind(e) in _REFLECTIVE_KINDS for e in events
    )


def clasificar_subgrupo(events: list[dict]) -> Subgrupo:  # noqa: PLR0911
    """Árbol de 10 subgrupos. El gate `prompts == 0` corrige la inversión:
    sin prompts, delegar es imposible → rama autónoma."""
    sig = _significativos(events)
    if len(sig) < MIN_EVENTS:
        return INDETERMINADO

    prompts = _count(events, "prompt_enviado")
    # Ejecutar y Probar cuentan como ejecución (HU-009, tree_version v4.2.0).
    ejec = _count(events, "codigo_ejecutado") + _count(events, "tests_ejecutados")
    ediciones = _count(events, "edicion_codigo")
    exp = dim_experimentacion(events)
    sol_directa = sum(
        1
        for e in events
        if e.get("event_type") == "prompt_enviado" and _kind(e) == "solicitud_directa"
    )
    # Quien Probó y pasó todo no trabajó poco, aunque lo haya hecho de una
    # (HU-010, v4.3.0). Solo Probar: un Ejecutar limpio no alcanza (N03).
    poco_trabajo = (
        ediciones < EDIT_MIN and ejec < TRABADO_MIN_EJEC and not _probar_paso_todo(events)
    )
    overuse = sum(
        1
        for e in events
        if e.get("event_type") == "intento_adverso_detectado"
        and (e.get("payload") or {}).get("category") == "overuse"
    )

    if prompts == 0:
        # Brazo SIN tutor: todo rollea al eje `autonomo`. Ojo: el "poco trabajo"
        # de acá emite `autonomo_desenganchado` (eje autonomo), NUNCA el
        # `desenganchado` compartido (eje superficial) — ese queda solo para el
        # brazo con-tutor de mas abajo.
        if poco_trabajo:
            return AUTONOMO_DESENGANCHADO
        if _resolvio(events):
            return AUTONOMO_COMPETENTE
        if ejec >= TRABADO_MIN_EJEC:
            return AUTONOMO_TRABADO
        return ESCRIBE_SIN_VALIDAR

    # con prompts: la dependencia se decide ANTES que reflexivo/funcional.
    # Sobreuso (v3.1.0): el alumno se apoya compulsivamente en el tutor
    # (intento_adverso_detectado category=overuse). Es dependencia, no reflexion —
    # antes caia en colaborador_reflexivo e inflaba "apropiacion_reflexiva"
    # (hallazgo 2026-06-20). Por eso se chequea primero.
    if overuse >= OVERUSE_DEP_THRESHOLD:
        return DEPENDIENTE_SOBREUSO
    # delegación por solicitud directa ANTES que "poco trabajo" (el delegador copia, no trabaja)
    if sol_directa >= DEP_SOLICITA and exp < DEP_EXP and not _verbaliza(events):
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
