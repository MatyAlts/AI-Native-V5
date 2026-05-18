"""Contenido academico de los 3 instrumentos del diseño cuasi-experimental.

================================================================================
[PENDIENTE VALIDACION COAUTORAL — ANA GARIS]
[PENDIENTE APROBACION COMITE ETICO UNSL]
================================================================================

Este archivo define el catalogo de items, escalas de respuesta y soluciones
canonicas para los 3 instrumentos del esqueleto tecnico que cierra P2-1, P2-2
y P2-3 del PlanMejora.md.

TODO el contenido academico esta marcado como version v0.1.0-draft y debe ser
revisado coautoralmente con Ana Garis + aprobado por el comite etico UNSL
antes de la aplicacion en el piloto real. Mientras tanto, sirve como:
1. Esqueleto operacional para validar el flujo backend + frontend end-to-end.
2. Plantilla concreta para que Garis pueda hacer review item-por-item.
3. Versionado: cuando el contenido validado este listo, se bumpea version
   a `-v1.0.0` y se mantiene este draft como historico para trazabilidad.

Cada catalogo expone:
- `ITEMS`: lista de items con `id`, `text`, `type` (likert/multiple/code/etc.),
  `scale_min`, `scale_max`, `required`.
- `validate_responses(responses: dict) -> list[str]`: devuelve errores; vacío = OK.
- `compute_scores(responses: dict) -> dict | None`: scoring opcional.
"""

from __future__ import annotations

from typing import Any


# ============================================================================
# CUESTIONARIO IA PREVIA (P2-2)
# Version: cuestionario-ia-v0.1.0-draft
# ============================================================================


CUESTIONARIO_IA_ITEMS: list[dict[str, Any]] = [
    {
        "id": "uso_general_meses",
        "text": "[PLACEHOLDER GARIS] ¿Hace cuantos meses usas asistentes de IA generativa (ChatGPT, Claude, Copilot, etc.)?",
        "type": "single_choice",
        "options": ["Nunca", "<1 mes", "1-6 meses", "6-12 meses", ">12 meses"],
        "required": True,
    },
    {
        "id": "frecuencia_uso",
        "text": "[PLACEHOLDER GARIS] ¿Con que frecuencia los usas para programar?",
        "type": "single_choice",
        "options": ["Nunca", "Mensual", "Semanal", "Diario", "Multiples veces al dia"],
        "required": True,
    },
    {
        "id": "tipos_tarea",
        "text": "[PLACEHOLDER GARIS] ¿Para que tipos de tarea de programacion usas IA? (puede seleccionar varios)",
        "type": "multiple_choice",
        "options": [
            "Generar codigo desde cero",
            "Depurar errores",
            "Entender codigo ajeno",
            "Aprender conceptos nuevos",
            "Refactor / optimizacion",
            "Documentacion",
            "Otra",
        ],
        "required": True,
    },
    {
        "id": "autopercepcion_dependencia",
        "text": "[PLACEHOLDER GARIS] En una escala 1-5, ¿cuanto sentis que dependes de la IA para programar?",
        "type": "likert",
        "scale_min": 1,
        "scale_max": 5,
        "scale_labels": {
            "1": "Nada — programo sin necesidad de IA",
            "3": "Moderadamente — la uso a veces",
            "5": "Totalmente — no programo sin IA",
        },
        "required": True,
    },
    {
        "id": "episodios_delegacion_previos",
        "text": "[PLACEHOLDER GARIS] ¿Alguna vez aceptaste codigo de la IA sin entender por que funcionaba? (autorreporte honesto)",
        "type": "single_choice",
        "options": ["Nunca", "Pocas veces", "A veces", "Frecuentemente", "Casi siempre"],
        "required": True,
    },
    {
        "id": "verificacion_critica",
        "text": "[PLACEHOLDER GARIS] Cuando la IA te da una respuesta, ¿cuanto verificas que sea correcta antes de usarla?",
        "type": "likert",
        "scale_min": 1,
        "scale_max": 5,
        "scale_labels": {
            "1": "No verifico, copio y pego",
            "5": "Verifico siempre con tests o pensando paso a paso",
        },
        "required": True,
    },
    {
        "id": "experiencia_otros_dominios",
        "text": "[PLACEHOLDER GARIS] ¿Usas IA para tareas no-programacion (escritura, estudio, etc.)?",
        "type": "single_choice",
        "options": ["Nunca", "Raramente", "A veces", "Frecuentemente", "Diariamente"],
        "required": False,
    },
    {
        "id": "expectativa_carrera",
        "text": "[PLACEHOLDER GARIS] ¿Crees que vas a trabajar como programador sin usar IA en 5 anos?",
        "type": "single_choice",
        "options": [
            "Imposible — sera obligatoria",
            "Improbable",
            "Posible",
            "Probable — preferiria evitarla",
            "Seguro — no la necesito",
        ],
        "required": False,
    },
]


def validate_cuestionario_ia_responses(responses: dict[str, Any]) -> list[str]:
    """Valida que las respuestas cumplan el schema de los items.

    Devuelve lista de errores; vacia = OK.
    """
    errors: list[str] = []
    required_ids = {item["id"] for item in CUESTIONARIO_IA_ITEMS if item.get("required")}
    given_ids = set(responses.keys())
    missing = required_ids - given_ids
    if missing:
        errors.append(f"Items obligatorios faltantes: {sorted(missing)}")

    # Validar tipo de cada respuesta segun item.type
    items_by_id = {item["id"]: item for item in CUESTIONARIO_IA_ITEMS}
    for item_id, value in responses.items():
        item = items_by_id.get(item_id)
        if not item:
            errors.append(f"Item desconocido en respuestas: {item_id}")
            continue
        item_type = item["type"]
        if item_type == "likert":
            if not isinstance(value, int) or not (
                item["scale_min"] <= value <= item["scale_max"]
            ):
                errors.append(
                    f"Item {item_id} (likert) requiere int en [{item['scale_min']}, {item['scale_max']}], recibido: {value!r}"
                )
        elif item_type == "single_choice":
            if value not in item["options"]:
                errors.append(f"Item {item_id} (single_choice) valor invalido: {value!r}")
        elif item_type == "multiple_choice":
            if not isinstance(value, list) or not all(v in item["options"] for v in value):
                errors.append(
                    f"Item {item_id} (multiple_choice) requiere lista de opciones validas, recibido: {value!r}"
                )
    return errors


# ============================================================================
# PRETEST AUTOEFICACIA (P2-1)
# Version: lishinski-2016-es-utn-v0.1.0-draft
# Adaptacion al castellano rioplatense pendiente de validacion coautoral.
# ============================================================================


# Lishinski et al. (2016): 4 sub-escalas con ~7 items cada una (total ~28).
# Aqui se materializa un EXTRACTO PLACEHOLDER de 12 items (3 por sub-escala)
# para que el flujo backend + frontend se pueda validar end-to-end.
# El contenido COMPLETO (28 items) se inyecta cuando la adaptacion al castellano
# este aprobada por Garis + comite etico.
PRETEST_AUTOEFICACIA_ITEMS: list[dict[str, Any]] = [
    # Sub-escala: dominio independiente
    {
        "id": "ind_01",
        "text": "[PLACEHOLDER GARIS — Lishinski 2016 #1] Puedo escribir un programa corto si tengo la consigna clara.",
        "type": "likert",
        "scale_min": 1,
        "scale_max": 7,
        "subscale": "independencia",
        "required": True,
    },
    {
        "id": "ind_02",
        "text": "[PLACEHOLDER GARIS — Lishinski 2016 #5] Puedo depurar un error de logica en mi propio codigo sin ayuda.",
        "type": "likert",
        "scale_min": 1,
        "scale_max": 7,
        "subscale": "independencia",
        "required": True,
    },
    {
        "id": "ind_03",
        "text": "[PLACEHOLDER GARIS — Lishinski 2016 #9] Puedo elegir entre dos estructuras de datos para resolver un problema.",
        "type": "likert",
        "scale_min": 1,
        "scale_max": 7,
        "subscale": "independencia",
        "required": True,
    },
    # Sub-escala: complejidad
    {
        "id": "comp_01",
        "text": "[PLACEHOLDER GARIS — Lishinski 2016 #12] Puedo entender codigo de mas de 100 lineas escrito por otra persona.",
        "type": "likert",
        "scale_min": 1,
        "scale_max": 7,
        "subscale": "complejidad",
        "required": True,
    },
    {
        "id": "comp_02",
        "text": "[PLACEHOLDER GARIS — Lishinski 2016 #15] Puedo escribir un programa con varias funciones que interactuan entre si.",
        "type": "likert",
        "scale_min": 1,
        "scale_max": 7,
        "subscale": "complejidad",
        "required": True,
    },
    {
        "id": "comp_03",
        "text": "[PLACEHOLDER GARIS — Lishinski 2016 #18] Puedo razonar sobre la complejidad temporal de un algoritmo (O(n), O(n log n)).",
        "type": "likert",
        "scale_min": 1,
        "scale_max": 7,
        "subscale": "complejidad",
        "required": True,
    },
    # Sub-escala: aprendizaje
    {
        "id": "apr_01",
        "text": "[PLACEHOLDER GARIS — Lishinski 2016 #20] Puedo aprender un lenguaje de programacion nuevo en pocas semanas.",
        "type": "likert",
        "scale_min": 1,
        "scale_max": 7,
        "subscale": "aprendizaje",
        "required": True,
    },
    {
        "id": "apr_02",
        "text": "[PLACEHOLDER GARIS — Lishinski 2016 #22] Puedo leer documentacion tecnica y aplicarla a mi codigo.",
        "type": "likert",
        "scale_min": 1,
        "scale_max": 7,
        "subscale": "aprendizaje",
        "required": True,
    },
    {
        "id": "apr_03",
        "text": "[PLACEHOLDER GARIS — Lishinski 2016 #24] Puedo identificar mis lagunas de conocimiento y trabajarlas.",
        "type": "likert",
        "scale_min": 1,
        "scale_max": 7,
        "subscale": "aprendizaje",
        "required": True,
    },
    # Sub-escala: persistencia
    {
        "id": "per_01",
        "text": "[PLACEHOLDER GARIS — Lishinski 2016 #25] Sigo intentando aunque mi programa no funcione despues de varios intentos.",
        "type": "likert",
        "scale_min": 1,
        "scale_max": 7,
        "subscale": "persistencia",
        "required": True,
    },
    {
        "id": "per_02",
        "text": "[PLACEHOLDER GARIS — Lishinski 2016 #27] Confio en mi capacidad para resolver problemas dificiles si me da el tiempo.",
        "type": "likert",
        "scale_min": 1,
        "scale_max": 7,
        "subscale": "persistencia",
        "required": True,
    },
    {
        "id": "per_03",
        "text": "[PLACEHOLDER GARIS — Lishinski 2016 #28] No me rindo aunque la consigna parezca demasiado dificil al principio.",
        "type": "likert",
        "scale_min": 1,
        "scale_max": 7,
        "subscale": "persistencia",
        "required": True,
    },
]


def validate_pretest_autoeficacia_responses(responses: dict[str, Any]) -> list[str]:
    """Valida respuestas del pretest. Devuelve lista de errores."""
    errors: list[str] = []
    required_ids = {item["id"] for item in PRETEST_AUTOEFICACIA_ITEMS if item.get("required")}
    given_ids = set(responses.keys())
    missing = required_ids - given_ids
    if missing:
        errors.append(f"Items obligatorios faltantes: {sorted(missing)}")
    items_by_id = {item["id"]: item for item in PRETEST_AUTOEFICACIA_ITEMS}
    for item_id, value in responses.items():
        item = items_by_id.get(item_id)
        if not item:
            errors.append(f"Item desconocido: {item_id}")
            continue
        if item["type"] == "likert":
            if not isinstance(value, int) or not (1 <= value <= 7):
                errors.append(f"Item {item_id} requiere int Likert 1-7, recibido: {value!r}")
    return errors


def compute_pretest_autoeficacia_scores(
    responses: dict[str, Any],
) -> tuple[int, dict[str, float]]:
    """Calcula score total + scores por subescala.

    [PLACEHOLDER GARIS] La formula final de scoring (promedio aritmetico vs
    ponderado vs estandarizado z-score sobre cohorte) la confirma Garis al
    aprobar el instrumento.

    Implementacion v0.1.0-draft: suma total + promedio por sub-escala.
    """
    items_by_id = {item["id"]: item for item in PRETEST_AUTOEFICACIA_ITEMS}
    subscale_sums: dict[str, list[int]] = {}
    total = 0
    for item_id, value in responses.items():
        item = items_by_id.get(item_id)
        if not item or item["type"] != "likert":
            continue
        if not isinstance(value, int):
            continue
        total += value
        subscale = item.get("subscale", "general")
        subscale_sums.setdefault(subscale, []).append(value)

    subscale_scores: dict[str, float] = {
        subscale: round(sum(values) / len(values), 2) if values else 0.0
        for subscale, values in subscale_sums.items()
    }
    return total, subscale_scores


# ============================================================================
# TEST DE TRANSFERENCIA (P2-3)
# Version: transfer-test-v0.1.0-draft
# ============================================================================


# El draft `docs/research/diseno-test-transfer.md` propone 5 problemas
# de 3-5 min cada uno. Aqui se materializan 3 placeholders para validar
# el flujo end-to-end; los 5 finales los aprueba la catedra UNSL.
TEST_TRANSFERENCIA_PROBLEMS: list[dict[str, Any]] = [
    {
        "test_id": "transfer-01",
        "title": "[PLACEHOLDER CATEDRA UNSL — TP-1] Segundo mayor de una lista",
        "description": (
            "[PLACEHOLDER CATEDRA UNSL] Dada una lista de enteros con al menos "
            "2 elementos, devolver el segundo mayor. Asumir que puede haber repetidos en el maximo."
        ),
        "expected_type": "code",
        "expected_solution_pattern": "[PLACEHOLDER — patron de evaluacion automatica pendiente]",
        "max_time_seconds": 300,
    },
    {
        "test_id": "transfer-02",
        "title": "[PLACEHOLDER CATEDRA UNSL — TP-2] Invertir un diccionario",
        "description": (
            "[PLACEHOLDER CATEDRA UNSL] Dado un dict {k: v} donde los valores "
            "son unicos, devolver el dict inverso {v: k}."
        ),
        "expected_type": "code",
        "expected_solution_pattern": "[PLACEHOLDER — patron de evaluacion automatica pendiente]",
        "max_time_seconds": 240,
    },
    {
        "test_id": "transfer-03",
        "title": "[PLACEHOLDER CATEDRA UNSL — TP-3] Razonamiento sobre complejidad",
        "description": (
            "[PLACEHOLDER CATEDRA UNSL] Dadas dos implementaciones de un mismo "
            "algoritmo, elegir cual tiene menor complejidad temporal y justificar brevemente."
        ),
        "expected_type": "multiple_choice_with_justification",
        "options": ["Implementacion A", "Implementacion B", "Tienen la misma complejidad"],
        "expected_answer": "[PLACEHOLDER]",
        "max_time_seconds": 180,
    },
]


def get_test_by_id(test_id: str) -> dict[str, Any] | None:
    """Devuelve la definicion de un problema por su test_id."""
    return next((t for t in TEST_TRANSFERENCIA_PROBLEMS if t["test_id"] == test_id), None)


def evaluate_test_transferencia_answer(
    test_id: str, response_detail: dict[str, Any]
) -> bool:
    """Evalua si la respuesta del estudiante es correcta.

    [PLACEHOLDER CATEDRA UNSL] La logica de evaluacion automatica (matching
    de patron, ejecucion de tests, comparacion semantica) se define cuando
    la catedra apruebe el contenido. Mientras tanto, devuelve False por defecto
    para no inflar metricas espureas en el dashboard.
    """
    _ = (test_id, response_detail)  # placeholder explicito
    return False
