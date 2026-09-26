"""Juez LLM del eje superficial↔reflexiva (componente de contenido).

Reemplaza, SOLO en la zona gris (colaboradores), el proxy conductual
`exp >= REFLEX_EXP` de `subgrupo.py` por un modelo de lenguaje que LEE la
conversación del episodio y juzga el razonamiento, como el codificador humano.

Diseño: `Diseno-clasificador-cognitivo-LLM-v4`. Principios:

  - LLM-as-judge con EXTRACCIÓN DE EVIDENCIA previa a la decisión: el modelo
    primero cita evidencia de 4 dimensiones (verbalización, verificación,
    justificación, autonomía) y recién después dicta el régimen. La etiqueta
    (3er orden) queda anclada a evidencia citada (1er orden) → auditable.
  - VERIFICACIÓN DE CONSISTENCIA EN CÓDIGO: la regla de decisión la garantiza
    `regimen_segun_regla()` (Python), NO el LLM. Si el modelo devuelve un
    régimen que no respeta la regla aplicada a sus propias dimensiones, se
    descarta como inconsistente y se rutea a revisión humana.
  - MODO SOMBRA: el resultado se persiste en `Classification.features['regimen_llm']`
    (aditivo, NO toca `appropriation` ni el `classifier_config_hash`), igual que
    el subgrupo. No rompe la reproducibilidad bit-a-bit del piloto-1.
  - REPRODUCIBILIDAD por configuración fijada: temperatura 0 + pinneo de modelo
    y versión de prompt (se registran en el resultado para auditoría).

La delegación pasiva NO pasa por acá: la resuelve la etapa dura (overuse).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ValidationError, field_validator, model_validator

logger = logging.getLogger(__name__)

# Versión del prompt congelado. Bumpear ante CUALQUIER cambio del system prompt
# o de los ejemplos few-shot — la salida del modelo puede cambiar, y el κ
# reportado se ancla a una versión concreta (snapshot reproducible).
#
# v1.2.0 (B2a, Tabla 3.11 + Tabla B.2): la regla deja de ser binaria y pasa a
# trivaluada con Kleene fuerte — cambio de SEMÁNTICA, no solo de redacción.
# NO mueve `classifier_config_hash` (ese hash cubre {tree_version, profile};
# la regla del juez se versiona acá, aparte, y esa versión ya se persiste en
# features['regimen_llm']['prompt_version'] — D1 del design.md).
PROMPT_VERSION = "eje_fino_v1.2.0"

# Zona gris histórica de colaboradores (se conserva por referencia / compat).
ZONA_GRIS_SUBGRUPOS = frozenset({"colaborador_reflexivo", "colaborador_funcional"})

# v4.0.0 — el juez GOBIERNA la etiqueta oficial de estos subgrupos: todos los
# CON-TUTOR (prompts > 0) que NO son delegación pasiva. Incluye `desenganchado`
# (con-tutor), que tras la separación del eje autónomo es exclusivo del brazo
# prompts>0 (el "poco trabajo" sin tutor ahora es `autonomo_desenganchado`).
# Quedan FUERA del juez (los resuelve la etapa dura / el árbol, §7 del contrato):
#   - delegación pasiva: dependiente_delegador, dependiente_sobreuso (overuse)
#   - eje autónomo (prompts == 0): autonomo_*, escribe_sin_validar (no hubo
#     conversación que juzgar)
#   - indeterminado (episodio muy corto)
SUBGRUPOS_JUZGADOS_POR_JUEZ = frozenset(
    {"colaborador_reflexivo", "colaborador_funcional", "desenganchado"}
)

# Mapa del veredicto del juez a la etiqueta oficial `appropriation` (v4.0.0).
REGIMEN_TO_APPROPRIATION: dict[str, str] = {
    "REFLEXIVA": "apropiacion_reflexiva",
    "SUPERFICIAL": "apropiacion_superficial",
}


# ── Contrato de salida del juez (validado contra el LLM) ──────────────────
#
# B2a (Tabla B.2 de la tesis, adjunta en `tabla-3.11-de-la-tesis.md`): las
# CUATRO dimensiones (V, E, J, A) son trivaluadas — `presente`, `ausente` o
# `no_evaluable`. El campo sigue llamándose `presente` (D2 del design): un
# `field_validator(mode="before")` coacciona los booleanos legados
# (`True`→"presente", `False`→"ausente") para que las clasificaciones ya
# persistidas antes de esta change se sigan parseando sin romper.
def _coaccionar_booleano_legado(v: Any) -> Any:
    if isinstance(v, bool):
        return "presente" if v else "ausente"
    return v


class _Dim(BaseModel):
    presente: Literal["presente", "ausente", "no_evaluable"]
    evidencia: str

    @field_validator("presente", mode="before")
    @classmethod
    def _coaccionar(cls, v: Any) -> Any:
        return _coaccionar_booleano_legado(v)


class _Autonomia(BaseModel):
    """Misma forma que `_Dim`: la Tabla B.2 define Autonomía con la misma
    escala presente/ausente/no_evaluable que V, E y J — no es un caso aparte.

    Corrección de D4 (design.md): D4 suponía que autonomía podía quedar
    booleana porque el juez solo corre sobre subgrupos con `prompts > 0`. La
    Tabla B.2 lo contradice: que haya prompts del ALUMNO no garantiza que haya
    PROPUESTAS DEL ASISTENTE que cuestionar, y ese es exactamente el caso
    `no_evaluable` de A («no hay propuestas del asistente sobre las que
    observar la conducta, o el registro está incompleto»).

    `presente` acá significa que el alumno ejerce autonomía (cuestiona o
    transforma la propuesta) — lo opuesto del campo legado `oraculo: bool`, que
    marcaba lo contrario. La retrocompatibilidad traduce la clave Y el sentido:
    `oraculo=True` (comportamiento oráculo) → `presente="ausente"`;
    `oraculo=False` (interlocutor) → `presente="presente"`.
    """

    presente: Literal["presente", "ausente", "no_evaluable"]
    evidencia: str

    @model_validator(mode="before")
    @classmethod
    def _coaccionar_oraculo_legado(cls, data: Any) -> Any:
        if isinstance(data, dict) and "presente" not in data and "oraculo" in data:
            data = dict(data)
            oraculo = data.pop("oraculo")
            if isinstance(oraculo, bool):
                data["presente"] = "ausente" if oraculo else "presente"
        return data

    @field_validator("presente", mode="before")
    @classmethod
    def _coaccionar(cls, v: Any) -> Any:
        return _coaccionar_booleano_legado(v)


class RegimenLLMRaw(BaseModel):
    """Salida cruda del LLM, validada contra el JSON Schema (§5.4 del diseño)."""

    model_config = {"extra": "forbid"}

    verbalizacion: _Dim
    verificacion: _Dim
    justificacion: _Dim
    autonomia: _Autonomia
    regimen: Literal["REFLEXIVA", "SUPERFICIAL"]
    confianza: float
    justificacion_global: str


# JSON Schema que se pasa al ai-gateway como `response_format` (structured output).
RESPONSE_JSON_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "ClasificacionRegimen",
        "schema": {
            "type": "object",
            "required": [
                "verbalizacion",
                "verificacion",
                "justificacion",
                "autonomia",
                "regimen",
                "confianza",
                "justificacion_global",
            ],
            "additionalProperties": False,
            "properties": {
                "verbalizacion": {
                    "type": "object",
                    "required": ["presente", "evidencia"],
                    "additionalProperties": False,
                    "properties": {
                        "presente": {
                            "type": "string",
                            "enum": ["presente", "ausente", "no_evaluable"],
                        },
                        "evidencia": {"type": "string"},
                    },
                },
                "verificacion": {
                    "type": "object",
                    "required": ["presente", "evidencia"],
                    "additionalProperties": False,
                    "properties": {
                        "presente": {
                            "type": "string",
                            "enum": ["presente", "ausente", "no_evaluable"],
                        },
                        "evidencia": {"type": "string"},
                    },
                },
                "justificacion": {
                    "type": "object",
                    "required": ["presente", "evidencia"],
                    "additionalProperties": False,
                    "properties": {
                        "presente": {
                            "type": "string",
                            "enum": ["presente", "ausente", "no_evaluable"],
                        },
                        "evidencia": {"type": "string"},
                    },
                },
                # D4 CORREGIDA (ver comentario en `_Autonomia`): la Tabla B.2
                # trivalúa también Autonomía — misma forma que las otras tres,
                # ya no `{"oraculo": boolean}`.
                "autonomia": {
                    "type": "object",
                    "required": ["presente", "evidencia"],
                    "additionalProperties": False,
                    "properties": {
                        "presente": {
                            "type": "string",
                            "enum": ["presente", "ausente", "no_evaluable"],
                        },
                        "evidencia": {"type": "string"},
                    },
                },
                "regimen": {"type": "string", "enum": ["REFLEXIVA", "SUPERFICIAL"]},
                "confianza": {"type": "number", "minimum": 0, "maximum": 1},
                "justificacion_global": {"type": "string", "minLength": 1},
            },
        },
    },
}


# Estados terminales que la Tabla 3.11 (`tabla-3.11-de-la-tesis.md`) exige,
# más los 4 que el código ya tenía. Correspondencia con los seis casos de la
# tabla, documentada acá porque el nombre de la tabla y el nombre del código
# NO coinciden uno a uno:
#   - casos 1 y 3 (clasificación automática)  → "ok" (con `regimen` REFLEXIVA/SUPERFICIAL)
#   - caso 2  (verdadero, no auditable)       → "derivado_evidencia_insuficiente"
#     NO IMPLEMENTADO. Depende de la verificación literal de citas (B4, no
#     construida). Solo se declara la constante del punto de extensión más
#     abajo — agregar el valor acá sin un camino de código que lo produzca
#     sería documentación disfrazada de contrato.
#   - caso 4  (indeterminado)                 → "abstencion_traza_insuficiente" (ESTE COMMIT)
#   - caso 5  (no evaluable por formato)       → "salida_invalida"
#     PARCIALMENTE cubierto hoy por "error_parseo" (JSON inválido). El caso
#     puntual que la tesis exige — cita atribuida a un turno del tutor, o
#     campo fuera de dominio — NO está implementado (depende de B4). Mismo
#     tratamiento que el caso 2: constante declarada, sin validador.
#   - caso 6  (conflicto de reglas)           → "inconsistente" (ya existía;
#     es exactamente "el régimen del modelo no coincide con el que la regla
#     determinista deriva de sus propias dimensiones")
Estado = Literal[
    "ok",
    "inconsistente",
    "baja_confianza",
    "error_parseo",
    "abstencion_traza_insuficiente",
]

# Casos 2 y 5 de la Tabla 3.11: brecha declarada, no implementada (ver el
# comentario de `Estado` arriba). Dependen del pendiente B4 (verificación
# literal de citas), que no existe en este repo. Se nombran acá para que el
# día que B4 se construya el estado ya tenga nombre fijado por la tesis, y no
# se improvise uno nuevo — pero NO se agregan a `Estado` ni a ningún `Literal`
# vivo, porque hoy ningún camino de código las produce.
CASO_2_ESTADO_FUTURO_NO_IMPLEMENTADO = "derivado_evidencia_insuficiente"
CASO_5_ESTADO_FUTURO_NO_IMPLEMENTADO = "salida_invalida"


class RegimenLLMResult(BaseModel):
    """Resultado final del juez, listo para persistir en features['regimen_llm']."""

    estado: Estado
    # Régimen final SOLO si estado == "ok" (consistente y con confianza suficiente).
    regimen: Literal["REFLEXIVA", "SUPERFICIAL"] | None
    confianza: float | None
    raw: RegimenLLMRaw | None
    razon: str  # por qué este estado (auditable)
    # Pinneo para reproducibilidad (§4.3 del diseño).
    model_used: str
    prompt_version: str


def normalizar_regimen_llm_persistido(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normaliza un `features['regimen_llm']` YA PERSISTIDO a la forma vigente.

    Bug real (QA, 2026-09-25): la coacción de booleanos legados y la
    traducción de `oraculo` legado a `presente` viven en los validadores de
    `_Dim`/`_Autonomia`, pero esos validadores SOLO corren cuando el dict pasa
    por `RegimenLLMRaw.model_validate` — y el único lugar de código no-test
    que hace eso es `clasificar_regimen_llm`, sobre la salida FRESCA del LLM.
    El endpoint de lectura devolvía el dict crudo del JSONB tal cual. Para V/E/J
    no se notaba (mismo nombre de campo); para autonomía SÍ, porque el campo se
    RENOMBRÓ (`oraculo` → `presente`) y un registro legado sin esa clave perdía
    la dimensión en el frontend, en blanco y sin log.

    Este es el ÚNICO lugar donde se debe llamar esta función: el borde de
    lectura (`classify_ep.py::get_current_classification`). Reusa la
    validación completa de `RegimenLLMResult`/`RegimenLLMRaw`/`_Autonomia`
    para que el dato que sale por HTTP tenga SIEMPRE la forma vigente, sin que
    el frontend tenga que conocer dos formas del mismo dato (D2 del design.md).

    Si el dato persistido no valida (corrupción o forma no anticipada), se
    degrada devolviendo el dict original tal cual — la LECTURA nunca debe
    romper por un registro viejo — y se loguea para que el caso se investigue.
    """
    if data is None:
        return None
    try:
        return RegimenLLMResult.model_validate(data).model_dump(mode="json")
    except ValidationError as exc:
        logger.warning(
            "regimen_llm_normalizacion_fallo",
            extra={"error": str(exc)},
        )
        return data


# ── Regla de decisión en código (la garantía, no el LLM) ──────────────────
def _kleene_desde_dim(valor: Literal["presente", "ausente", "no_evaluable"]) -> bool | None:
    """Traduce el valor trivaluado al tri-estado de Kleene: True/False/None."""
    if valor == "presente":
        return True
    if valor == "ausente":
        return False
    return None  # no_evaluable


def _kleene_and(a: bool | None, b: bool | None) -> bool | None:
    """AND fuerte de Kleene: un `False` GANA sobre cualquier `None`."""
    if a is False or b is False:
        return False
    if a is None or b is None:
        return None
    return True


def _kleene_or(a: bool | None, b: bool | None) -> bool | None:
    """OR fuerte de Kleene: un `True` GANA sobre cualquier `None`."""
    if a is True or b is True:
        return True
    if a is None or b is None:
        return None
    return False


def regimen_segun_regla(
    raw: RegimenLLMRaw,
) -> Literal["REFLEXIVA", "SUPERFICIAL", "INDETERMINADO"]:
    """Aplica la regla del manual a las 4 dimensiones citadas por el LLM.

    Tabla 3.11 de la tesis (`openspec/changes/remediaciones-mtac-b2-b5/
    tabla-3.11-de-la-tesis.md`), criterio V ∧ (E ∨ J) ∧ A, evaluado con
    **Kleene fuerte**: el valor `no_evaluable` (desconocido) se propaga SOLO
    cuando puede cambiar el resultado. Una dimensión que por sí sola hace
    falsa la fórmula (ej. V ausente) decide SUPERFICIAL sin importar que las
    demás sean `no_evaluable` (caso 3) — esa es la propiedad que distingue
    Kleene fuerte de Kleene débil, donde cualquier `no_evaluable` derivaría.

      (a) VERBALIZACIÓN, (b) VERIFICACIÓN ∨ JUSTIFICACIÓN, (c) AUTONOMÍA.

    Devuelve "INDETERMINADO" (caso 4, abstención por traza insuficiente)
    cuando ninguna dimensión hace falsa la fórmula pero el desconocido de
    alguna impide decidir. La cantidad de actividad nunca decide.
    """
    a = _kleene_desde_dim(raw.verbalizacion.presente)
    b = _kleene_or(
        _kleene_desde_dim(raw.verificacion.presente),
        _kleene_desde_dim(raw.justificacion.presente),
    )
    c = _kleene_desde_dim(raw.autonomia.presente)
    resultado = _kleene_and(_kleene_and(a, b), c)
    if resultado is True:
        return "REFLEXIVA"
    if resultado is False:
        return "SUPERFICIAL"
    return "INDETERMINADO"


def _hay_evidencia_citable(raw: RegimenLLMRaw) -> bool:
    """Al menos una dimensión con evidencia textual no vacía."""
    return any(
        d.evidencia.strip()
        for d in (raw.verbalizacion, raw.verificacion, raw.justificacion, raw.autonomia)
    )


def _limpiar_json(texto: str) -> str:
    """Extrae el objeto JSON de la respuesta, tolerando fences ```json ... ```.

    Algunos modelos (según el provider que resuelva el ai-gateway) envuelven la
    salida en un bloque de código markdown. Quita el fence y toma desde la
    primera `{` hasta la última `}`; si no encuentra objeto, devuelve el texto tal cual.
    """
    t = texto.strip()
    if t.startswith("```"):
        t = t.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    i, j = t.find("{"), t.rfind("}")
    return t[i : j + 1] if (i != -1 and j != -1) else t


# ── Armado del contexto del episodio (la evidencia cruda que lee el juez) ──
_REFLECTIVE_KINDS = frozenset(
    {"exploracion", "aclaracion_enunciado", "comparativa", "epistemologica", "validacion"}
)


def _payload(e: dict) -> dict:
    return e.get("payload") or {}


def armar_contexto(events: list[dict]) -> dict[str, Any]:
    """Serializa el episodio como texto, igual evidencia que ve el docente.

    Devuelve transcript (alumno↔tutor en orden), código/notas, y los conteos
    de actividad (que van como CONTEXTO, nunca como criterio de decisión).
    """
    ordenados = sorted(events, key=lambda e: e.get("seq", 0))
    transcript: list[str] = []
    codigo_notas: list[str] = []
    n_exec = 0
    n_prompts = 0

    for e in ordenados:
        et = e.get("event_type")
        p = _payload(e)
        if et == "prompt_enviado":
            n_prompts += 1
            txt = (p.get("content") or "").strip()
            if txt:
                transcript.append(f"ALUMNO: {txt}")
        elif et == "tutor_respondio":
            txt = (p.get("content") or "").strip()
            if txt:
                transcript.append(f"TUTOR: {txt}")
        elif et in ("codigo_ejecutado", "tests_ejecutados"):
            n_exec += 1
        elif et == "anotacion_creada":
            txt = (p.get("content") or "").strip()
            if txt:
                codigo_notas.append(f"[anotación] {txt}")

    # Último snapshot de código (estado final del buffer del alumno).
    ediciones = [e for e in ordenados if e.get("event_type") == "edicion_codigo"]
    if ediciones:
        snap = (_payload(ediciones[-1]).get("snapshot") or "").strip()
        if snap:
            codigo_notas.append(f"[código final]\n{snap}")

    return {
        "transcript": "\n".join(transcript) if transcript else "(sin diálogo con el tutor)",
        "codigo_y_notas": "\n".join(codigo_notas)
        if codigo_notas
        else "(sin código ni anotaciones)",
        "n_exec": n_exec,
        "n_prompts": n_prompts,
    }


# ── Prompt (system + few-shot + user) — §5 del diseño ─────────────────────
SYSTEM_PROMPT = """\
Sos un evaluador experto en didáctica de la programación. Clasificás UN episodio de un alumno que resolvió un ejercicio con un tutor de IA en UNO de dos regímenes: SUPERFICIAL o REFLEXIVA.

NO clasifiques por cantidad de actividad (ejecuciones, prompts, intentos). Clasificás leyendo el CONTENIDO de lo que el alumno escribió y razonó.

DEFINICIONES
- REFLEXIVA: el alumno razonó con su cabeza Y (verificó conceptualmente O justificó sus decisiones). Explica el porqué, anticipa o contrasta resultados, o defiende sus elecciones con criterio propio. Puede haber ejecutado poco si entendía lo que hacía.
- SUPERFICIAL: hizo algo y obtuvo un resultado sin razonamiento crítico. Pidió la solución/corrección y la aplicó, volcó errores y esperó respuesta, o "anduvo y listo".

DOS DISTINCIONES CLAVE (afinan el juicio, pero NO te vuelvas injusto con quien sí razonó):
- NARRAR no es RAZONAR: describir qué hace el código ("la línea 8 abre el archivo") por sí solo no es verbalizar el porqué. La verbalización está presente cuando el alumno explica la RAZÓN de una decisión o muestra un criterio propio. PERO si el alumno da una razón, una causa, una comparación o un criterio ("uso 'a' porque necesito conservar lo anterior", "tiene que ser un for porque recorro la lista"), eso SÍ es verbalización: contala.
- PEDIR LA SOLUCIÓN es ORÁCULO: si el alumno pidió "cómo lo arreglo", "corregime", "está bien así?" o volcó un error esperando la respuesta, la autonomía es oráculo, y entonces es SUPERFICIAL aunque narre o explique algo después. PERO preguntar para DISCUTIR una idea, contrastar un razonamiento propio o confirmar una hipótesis que él mismo formuló ("pensé que con 'a' se agrega al final, ¿es así?") NO es oráculo: es usar la IA como interlocutor.

RÚBRICA — cada dimensión vale "presente", "ausente" o "no_evaluable" (nunca inventes; sin evidencia clara, no fuerces "presente"):
1. VERBALIZACIÓN (V) — presente: el alumno formula con sus propias palabras una hipótesis, explicación o plan, más allá de reproducir o parafrasear al tutor. ausente: hay turnos suficientes del alumno y ninguno expresa razonamiento propio (solo pedidos de solución, pegado de errores o aceptaciones). no_evaluable: turnos del alumno escasos o truncados, episodio interrumpido, o actividad fuera del sistema que impide juzgar.
2. VERIFICACIÓN (E) — presente: el alumno ejecuta, prueba, compara o comprueba una propuesta y refiere el resultado. ausente: acepta propuestas sin ninguna acción ni argumento de contraste, en un episodio con eventos suficientes. no_evaluable: eventos de ejecución o prueba no registrados, o registro incompleto.
3. JUSTIFICACIÓN (J) — presente: el alumno explica por qué una decisión propia es correcta o preferible, con fundamento causal, argumentado o estratégico. ausente: las decisiones se adoptan sin fundamento expresado, en una traza suficiente para observarlo. no_evaluable: la traza no contiene decisiones propias observables, o está truncada.
4. AUTONOMÍA (A) — presente: el alumno transforma, cuestiona o pone a prueba la propuesta del tutor en vez de tratarla como oráculo. ausente: incorpora las propuestas sin modificación ni cuestionamiento, con evidencia positiva de aceptación (ej. pegado literal seguido de entrega). no_evaluable: NO HAY PROPUESTAS DEL TUTOR sobre las que observar la conducta del alumno, o el registro está incompleto — que haya mensajes del alumno no alcanza si el tutor no propuso nada que cuestionar o aceptar.

IMPORTANTE sobre "no_evaluable": es un juicio sobre la TRAZA (falta lo que haría falta para decidir presente/ausente), NO sobre tu confianza en la lectura. Si la traza alcanza pero el caso es ambiguo, decidí presente o ausente y bajá "confianza" (para eso existe el campo); "no_evaluable" es exclusivamente "no hay con qué juzgar esta dimensión".

REGLA DE DECISIÓN
REFLEXIVA si y solo si: (a) VERBALIZACIÓN presente, Y (b) VERIFICACIÓN presente O JUSTIFICACIÓN presente, Y (c) AUTONOMÍA presente. Si alguna dimensión necesaria es "no_evaluable" y ninguna otra ya decide SUPERFICIAL, no elijas un régimen por descarte: reportá igual tu mejor lectura en "regimen", que el código verifica y deriva a revisión si la regla no puede resolverla con lo que citaste.

Para cada dimensión citá la frase textual del alumno que la sustenta (cadena vacía si es ausente/no_evaluable). La confianza es un decimal entre 0 y 1: si la evidencia es ambigua, asigná confianza menor a 0,70.

SALIDA — devolvé EXCLUSIVAMENTE el JSON con la estructura pedida, sin texto adicional. Para cada una de las CUATRO dimensiones, "presente" es un string ("presente", "ausente" o "no_evaluable") y "evidencia" es la frase textual (o cadena vacía). "regimen" es "REFLEXIVA" o "SUPERFICIAL". "confianza" es un decimal entre 0 y 1."""

# Ejemplos few-shot: casos REALES del piloto, etiquetados por consenso docente.
# NOTA DE VALIDACIÓN (§6 del diseño): en la validación k-fold, estos ejemplos
# DEBEN salir del split de entrenamiento del fold en curso (nunca del fold de
# evaluación) para evitar data leakage. Acá quedan como default para uso en
# producción/sombra una vez validados.
# v1.1.0: 3 ejemplos. El 3ro enseña la condición (c) — narra/pide pero autonomía
# es oráculo → SUPERFICIAL — que era la principal fuente de falsos positivos en la
# validación sobre el corpus real (informe-validacion-juez-llm).
_FEWSHOT: list[tuple[str, dict[str, Any]]] = [
    (
        # Episodio 01ab7004 — consenso docente = SUPERFICIAL
        "ALUMNO: \"Me salio esto SyntaxError: invalid syntax. Maybe you meant '==' "
        "or ':=' instead of '='?\"\n[ejecutó el código 11 veces; ningún otro mensaje]",
        {
            "verbalizacion": {"presente": "ausente", "evidencia": ""},
            "verificacion": {"presente": "ausente", "evidencia": ""},
            "justificacion": {"presente": "ausente", "evidencia": ""},
            "autonomia": {
                "presente": "ausente",
                "evidencia": "volcó el error sin preguntar la causa",
            },
            "regimen": "SUPERFICIAL",
            "confianza": 0.9,
            "justificacion_global": (
                "Copió el error y esperó solución. Muchas ejecuciones pero cero "
                "razonamiento verbalizado: extracción, no comprensión."
            ),
        },
    ),
    (
        # Episodio 23ad4ade — consenso docente = REFLEXIVA
        "ALUMNO: \"tengo que usar el formato append, o sea 'a', verdad?, ya que el "
        "formato 'r' es solo de lectura y el formato 'w' volveria a escribir de 0 el "
        "archivo\"\nALUMNO: \"el formato 'a' es el correcto, ya que el ejercicio me pide "
        'agregar un producto al final, sin modificar el archivo"\nALUMNO: "la linea 13 '
        'lo que hace es agregar el producto nuevo al final de la lista"\n[ejecutó el código 2 veces]',
        {
            "verbalizacion": {
                "presente": "presente",
                "evidencia": "la linea 13 lo que hace es agregar el producto al final",
            },
            "verificacion": {
                "presente": "presente",
                "evidencia": "'r' es solo lectura y 'w' volveria a escribir de 0",
            },
            "justificacion": {
                "presente": "presente",
                "evidencia": "el formato 'a' es el correcto, ya que el ejercicio me pide agregar al final",
            },
            "autonomia": {
                "presente": "presente",
                "evidencia": "razona los modos sin que se lo pidan",
            },
            "regimen": "REFLEXIVA",
            "confianza": 0.95,
            "justificacion_global": (
                "Justifica cada decisión y explica qué hace cada línea, con pocas "
                "ejecuciones porque comprende. Razonamiento de sobra."
            ),
        },
    ),
    (
        # Caso oráculo (condición c): pide la corrección a la IA y después narra
        # qué hace el código, sin razonar el porqué → SUPERFICIAL.
        'ALUMNO: "tutor no me anda, me tira error en la linea 8, como lo arreglo?"\n'
        'TUTOR: "fijate el modo de apertura del archivo"\n'
        'ALUMNO: "ah ok ya esta, entonces la linea 8 abre el archivo y la 9 lee las '
        'lineas"\n[ejecutó el código 6 veces]',
        {
            "verbalizacion": {"presente": "ausente", "evidencia": ""},
            "verificacion": {"presente": "ausente", "evidencia": ""},
            "justificacion": {"presente": "ausente", "evidencia": ""},
            "autonomia": {
                "presente": "ausente",
                "evidencia": "pidió 'como lo arreglo' en vez de razonar el error él mismo",
            },
            "regimen": "SUPERFICIAL",
            "confianza": 0.9,
            "justificacion_global": (
                "Pidió la corrección a la IA (oráculo) y después solo narró qué hacen "
                "las líneas, sin razonar el porqué. Condición (c) no se cumple."
            ),
        },
    ),
]


# Prefijos de los episodios usados como few-shot. El harness de validación los
# usa para detectar LEAKAGE (un few-shot dentro del conjunto de evaluación).
_FEWSHOT_EPISODE_IDS = ("01ab7004", "23ad4ade")


def construir_mensajes(
    ctx: dict[str, Any],
    enunciado: str,
    episode_id: str,
    fewshot: list[tuple[str, dict[str, Any]]] | None = None,
) -> list[dict[str, str]]:
    """Arma la lista de mensajes (system + few-shot + user) para el ai-gateway."""
    ejemplos = _FEWSHOT if fewshot is None else fewshot
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for entrada, salida in ejemplos:
        messages.append({"role": "user", "content": entrada})
        messages.append({"role": "assistant", "content": json.dumps(salida, ensure_ascii=False)})
    user = (
        f"EPISODIO A CLASIFICAR (id: {episode_id})\n"
        f"Enunciado del ejercicio: {enunciado or '(no provisto)'}\n"
        f"--- Conversación alumno ↔ tutor IA ---\n{ctx['transcript']}\n"
        f"--- Código y anotaciones del cuaderno ---\n{ctx['codigo_y_notas']}\n"
        f"--- Señales de actividad (CONTEXTO, no criterio de decisión) ---\n"
        f"ejecuciones: {ctx['n_exec']} · prompts: {ctx['n_prompts']}\n"
        f"Clasificá según la rúbrica. Devolvé solo el JSON."
    )
    messages.append({"role": "user", "content": user})
    return messages


# ── Cliente del LLM (Protocol — se inyecta el real o un mock en tests) ─────
class CompleteFn(Protocol):
    async def __call__(
        self,
        messages: list[dict],
        model: str,
        feature: str,
        tenant_id: UUID,
        materia_id: UUID | None = ...,
        temperature: float = ...,
        max_tokens: int = ...,
        response_format: dict | None = ...,
    ) -> Any: ...


async def clasificar_regimen_llm(
    *,
    events: list[dict],
    enunciado: str,
    episode_id: str,
    complete: CompleteFn,
    model: str,
    tenant_id: UUID,
    materia_id: UUID | None = None,
    confianza_min: float = 0.70,
    max_reintentos: int = 2,
    # Techo de salida del juez. Gemini 2.5 consume tokens de "thinking" del MISMO
    # presupuesto con el que escribe, asi que un numero que alcanza para el JSON
    # no alcanza cuando el modelo piensa mas. Ya se subio a mano una vez (700 ->
    # 3000) y volvio a quedar corto: 14 de 324 episodios juzgados terminaron en
    # `error_parseo`. Parametro y no constante para poder moverlo sin tocar codigo.
    max_tokens: int = 6000,
    fewshot: list[tuple[str, dict[str, Any]]] | None = None,
) -> RegimenLLMResult:
    """Clasifica el eje superficial↔reflexiva leyendo el contenido del episodio.

    `complete` es un callable async con la firma de `AIGatewayClient.complete`
    (se inyecta para poder testear con un mock sin pegarle al ai-gateway).

    Devuelve SIEMPRE un RegimenLLMResult: si la salida es inválida o
    inconsistente con la regla, el `estado` lo refleja y `regimen` queda None
    (el episodio se rutea a revisión humana, nunca se infiere una etiqueta de
    una salida dudosa).
    """
    ctx = armar_contexto(events)
    messages = construir_mensajes(ctx, enunciado, episode_id, fewshot)

    def _result(estado: Estado, regimen, conf, raw, razon) -> RegimenLLMResult:
        return RegimenLLMResult(
            estado=estado,
            regimen=regimen,
            confianza=conf,
            raw=raw,
            razon=razon,
            model_used=model,
            prompt_version=PROMPT_VERSION,
        )

    raw: RegimenLLMRaw | None = None
    motivo_fallo = "el modelo no devolvió un JSON válido"
    for intento in range(max_reintentos + 1):
        res = await complete(
            messages=messages,
            model=model,
            feature="episode_eje_fino",
            tenant_id=tenant_id,
            materia_id=materia_id,
            temperature=0.0,  # determinismo (§4.3)
            max_tokens=max_tokens,
            # El ai-gateway acepta response_format como dict[str,str] (JSON mode
            # simple), NO el json_schema anidado. El esquema lo garantizan el
            # prompt + la validación de RegimenLLMRaw aguas abajo (RESPONSE_JSON_SCHEMA
            # queda como documentación del contrato de salida).
            response_format={"type": "json_object"},
        )
        try:
            data = json.loads(_limpiar_json(res.content))
            raw = RegimenLLMRaw.model_validate(data)
            break
        except (json.JSONDecodeError, ValidationError) as exc:
            # Truncado = la salida llego al techo y vino cortada por la mitad.
            # NO se reintenta: con `temperature=0.0` el reintento es determinista
            # y devuelve el MISMO corte, quemando tres llamadas al LLM para el
            # mismo fallo. Es exactamente el error que costo el incidente del
            # wizard de ejercicios (27/07), donde tres 502 identicos venian de un
            # JSON bien formado pero cortado en el mismo caracter.
            truncado = res.output_tokens >= max_tokens
            motivo_fallo = (
                f"respuesta truncada en {res.output_tokens} tokens (techo {max_tokens})"
                if truncado
                else f"{type(exc).__name__}: {exc}"
            )
            logger.warning(
                "regimen_llm_parseo_fallo",
                extra={
                    "episode_id": episode_id,
                    "intento": intento,
                    "truncado": truncado,
                    "output_tokens": res.output_tokens,
                    "error": str(exc),
                },
            )
            raw = None
            if truncado:
                break

    if raw is None:
        return _result(
            "error_parseo",
            None,
            None,
            None,
            # El motivo CONCRETO queda en features['regimen_llm']['razon'], que se
            # persiste. Antes decia solo "no devolvio JSON valido tras los
            # reintentos" y para separar truncado / JSON roto / campos faltantes
            # habia que ir a los logs del contenedor, que rotan. El diagnostico
            # del 2026-08-06 tuvo que adivinar entre las tres.
            f"El juez no devolvió un veredicto usable: {motivo_fallo}. Va a revisión humana.",
        )

    # Verificación de consistencia EN CÓDIGO (la regla manda, no el LLM).
    #
    # Las DOS causas van separadas a proposito. Antes eran un solo `or` con un
    # solo mensaje ("no respeta la regla ... O no hay evidencia citable"), y eso
    # producia lineas que se leian como autocontradictorias: "el regimen del
    # modelo (SUPERFICIAL) no respeta la regla (esperado: SUPERFICIAL)". Para
    # saber cual de las dos habia disparado no alcanzaba el registro guardado:
    # habia que reconstruirlo a mano contra el JSON crudo (2026-08-06).
    esperado = regimen_segun_regla(raw)

    # Caso 4 de la Tabla 3.11: la regla determinista NO puede decidir (Kleene
    # fuerte devolvió indeterminado). Esto se chequea ANTES de comparar contra
    # `raw.regimen` — el modelo siempre afirma REFLEXIVA o SUPERFICIAL binario,
    # pero si la propia regla no puede resolverlo, esa afirmación es irrelevante:
    # se abstiene, nunca se infiere una etiqueta de una regla indecisa.
    if esperado == "INDETERMINADO":
        return _result(
            "abstencion_traza_insuficiente",
            None,
            raw.confianza,
            raw,
            "La regla determinista no puede decidir: ninguna dimensión hace "
            "falsa la fórmula V ∧ (E ∨ J) ∧ A, pero el valor no evaluable de "
            "alguna dimensión necesaria impide resolverla (Tabla 3.11, caso 4). "
            "Va a revisión humana.",
        )

    if raw.regimen != esperado:
        return _result(
            "inconsistente",
            None,
            raw.confianza,
            raw,
            f"El régimen del modelo ({raw.regimen}) no respeta la regla aplicada a sus "
            f"propias dimensiones (esperado: {esperado}). Va a revisión humana.",
        )

    # La evidencia citable se exige SOLO cuando el juez afirma REFLEXIVA.
    #
    # Antes se exigia siempre, y eso descartaba el veredicto justo en los
    # episodios que el juez lee con mas claridad: si el alumno no razono, no
    # verifico y no justifico, las cuatro dimensiones vuelven `presente: false`
    # con `evidencia: ""` — no hay frase que citar porque no ocurrio. Pedir una
    # cita de algo que NO paso es pedir evidencia de una ausencia.
    #
    # El efecto era una inflacion silenciosa: descartado el SUPERFICIAL correcto,
    # la etiqueta oficial caia al proxy conductual, que en esos casos puede decir
    # "apropiacion reflexiva" — la mas alta. Medido el 2026-08-06 sobre el piloto:
    # 7 de 12 `inconsistente` eran este caso (las cuatro evidencias vacias).
    #
    # Para REFLEXIVA la exigencia se mantiene y es la que importa: ahi el juez
    # esta AFIRMANDO que hubo marcadores, y una afirmacion sin una sola cita no
    # es verificable.
    if raw.regimen == "REFLEXIVA" and not _hay_evidencia_citable(raw):
        return _result(
            "inconsistente",
            None,
            raw.confianza,
            raw,
            "El régimen del modelo (REFLEXIVA) afirma que hubo razonamiento pero no cita "
            "evidencia en ninguna dimensión. Va a revisión humana.",
        )

    if raw.confianza < confianza_min:
        return _result(
            "baja_confianza",
            None,
            raw.confianza,
            raw,
            f"Confianza {raw.confianza:.2f} < umbral {confianza_min}. Va a revisión humana.",
        )

    return _result(
        "ok",
        raw.regimen,
        raw.confianza,
        raw,
        "Clasificación consistente con la regla y confianza suficiente.",
    )
