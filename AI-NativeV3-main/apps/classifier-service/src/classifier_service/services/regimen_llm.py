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

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# Versión del prompt congelado. Bumpear ante CUALQUIER cambio del system prompt
# o de los ejemplos few-shot — la salida del modelo puede cambiar, y el κ
# reportado se ancla a una versión concreta (snapshot reproducible).
PROMPT_VERSION = "eje_fino_v1.1.0"

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
class _Dim(BaseModel):
    presente: bool
    evidencia: str


class _Autonomia(BaseModel):
    oraculo: bool
    evidencia: str


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
                "verbalizacion", "verificacion", "justificacion",
                "autonomia", "regimen", "confianza", "justificacion_global",
            ],
            "additionalProperties": False,
            "properties": {
                "verbalizacion": {
                    "type": "object", "required": ["presente", "evidencia"],
                    "additionalProperties": False,
                    "properties": {"presente": {"type": "boolean"}, "evidencia": {"type": "string"}},
                },
                "verificacion": {
                    "type": "object", "required": ["presente", "evidencia"],
                    "additionalProperties": False,
                    "properties": {"presente": {"type": "boolean"}, "evidencia": {"type": "string"}},
                },
                "justificacion": {
                    "type": "object", "required": ["presente", "evidencia"],
                    "additionalProperties": False,
                    "properties": {"presente": {"type": "boolean"}, "evidencia": {"type": "string"}},
                },
                "autonomia": {
                    "type": "object", "required": ["oraculo", "evidencia"],
                    "additionalProperties": False,
                    "properties": {"oraculo": {"type": "boolean"}, "evidencia": {"type": "string"}},
                },
                "regimen": {"type": "string", "enum": ["REFLEXIVA", "SUPERFICIAL"]},
                "confianza": {"type": "number", "minimum": 0, "maximum": 1},
                "justificacion_global": {"type": "string", "minLength": 1},
            },
        },
    },
}


Estado = Literal["ok", "inconsistente", "baja_confianza", "error_parseo"]


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


# ── Regla de decisión en código (la garantía, no el LLM) ──────────────────
def regimen_segun_regla(raw: RegimenLLMRaw) -> Literal["REFLEXIVA", "SUPERFICIAL"]:
    """Aplica la regla del manual a las 4 dimensiones citadas por el LLM.

    REFLEXIVA si y solo si:
      (a) VERBALIZACIÓN presente, Y
      (b) VERIFICACIÓN presente O JUSTIFICACIÓN presente, Y
      (c) AUTONOMÍA no es de tipo oráculo.
    En cualquier otro caso, SUPERFICIAL. La cantidad de actividad nunca decide.
    """
    a = raw.verbalizacion.presente
    b = raw.verificacion.presente or raw.justificacion.presente
    c = not raw.autonomia.oraculo
    return "REFLEXIVA" if (a and b and c) else "SUPERFICIAL"


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
        "codigo_y_notas": "\n".join(codigo_notas) if codigo_notas else "(sin código ni anotaciones)",
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

RÚBRICA (marcá presente=false y evidencia="" si no hay evidencia clara; no inventes):
1. VERBALIZACIÓN DEL RAZONAMIENTO — ¿explica el porqué de sus decisiones o muestra un criterio propio?
2. VERIFICACIÓN CONCEPTUAL — ¿contrasta/anticipa resultados o razona el error con su cabeza, más allá de ejecutar?
3. JUSTIFICACIÓN DE DECISIONES — ¿defiende sus elecciones con criterio propio?
4. AUTONOMÍA COGNITIVA — ¿usa la IA para PENSAR (interlocutor) o para EXTRAER la solución/corrección (oráculo)?

REGLA DE DECISIÓN (las tres condiciones deben cumplirse)
REFLEXIVA si y solo si: (a) VERBALIZACIÓN del porqué presente, Y (b) VERIFICACIÓN presente O JUSTIFICACIÓN presente, Y (c) AUTONOMÍA no es oráculo. Si la autonomía es oráculo, SUPERFICIAL siempre. En cualquier otro caso, SUPERFICIAL.

Para cada dimensión citá la frase textual del alumno que la sustenta. La confianza es un decimal entre 0 y 1: si la evidencia es ambigua, asigná confianza menor a 0,70.

SALIDA — devolvé EXCLUSIVAMENTE el JSON con la estructura pedida, sin texto adicional. Para cada dimensión, "presente"/"oraculo" es un booleano real y "evidencia" es la frase textual (o cadena vacía). "regimen" es "REFLEXIVA" o "SUPERFICIAL". "confianza" es un decimal entre 0 y 1."""

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
        'ALUMNO: "Me salio esto SyntaxError: invalid syntax. Maybe you meant \'==\' '
        "or ':=' instead of '='?\"\n[ejecutó el código 11 veces; ningún otro mensaje]",
        {
            "verbalizacion": {"presente": False, "evidencia": ""},
            "verificacion": {"presente": False, "evidencia": ""},
            "justificacion": {"presente": False, "evidencia": ""},
            "autonomia": {"oraculo": True, "evidencia": "volcó el error sin preguntar la causa"},
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
        'ALUMNO: "tengo que usar el formato append, o sea \'a\', verdad?, ya que el '
        "formato 'r' es solo de lectura y el formato 'w' volveria a escribir de 0 el "
        'archivo"\nALUMNO: "el formato \'a\' es el correcto, ya que el ejercicio me pide '
        'agregar un producto al final, sin modificar el archivo"\nALUMNO: "la linea 13 '
        'lo que hace es agregar el producto nuevo al final de la lista"\n[ejecutó el código 2 veces]',
        {
            "verbalizacion": {"presente": True, "evidencia": "la linea 13 lo que hace es agregar el producto al final"},
            "verificacion": {"presente": True, "evidencia": "'r' es solo lectura y 'w' volveria a escribir de 0"},
            "justificacion": {"presente": True, "evidencia": "el formato 'a' es el correcto, ya que el ejercicio me pide agregar al final"},
            "autonomia": {"oraculo": False, "evidencia": "razona los modos sin que se lo pidan"},
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
            "verbalizacion": {"presente": False, "evidencia": ""},
            "verificacion": {"presente": False, "evidencia": ""},
            "justificacion": {"presente": False, "evidencia": ""},
            "autonomia": {"oraculo": True, "evidencia": "pidió 'como lo arreglo' en vez de razonar el error él mismo"},
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
            estado=estado, regimen=regimen, confianza=conf, raw=raw, razon=razon,
            model_used=model, prompt_version=PROMPT_VERSION,
        )

    raw: RegimenLLMRaw | None = None
    for intento in range(max_reintentos + 1):
        res = await complete(
            messages=messages,
            model=model,
            feature="episode_eje_fino",
            tenant_id=tenant_id,
            materia_id=materia_id,
            temperature=0.0,  # determinismo (§4.3)
            # Gemini 2.5 consume tokens de "thinking" del presupuesto de salida;
            # con 700 el JSON se truncaba (~89 tokens visibles). 3000 deja margen
            # para el thinking + el JSON completo de las 4 dimensiones.
            max_tokens=3000,
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
            logger.warning(
                "regimen_llm_parseo_fallo",
                extra={"episode_id": episode_id, "intento": intento, "error": str(exc)},
            )
            raw = None

    if raw is None:
        return _result("error_parseo", None, None, None,
                       "El modelo no devolvió un JSON válido tras los reintentos.")

    # Verificación de consistencia EN CÓDIGO (la regla manda, no el LLM).
    esperado = regimen_segun_regla(raw)
    if raw.regimen != esperado or not _hay_evidencia_citable(raw):
        return _result("inconsistente", None, raw.confianza, raw,
                       f"El régimen del modelo ({raw.regimen}) no respeta la regla "
                       f"aplicada a sus dimensiones (esperado: {esperado}) o no hay "
                       f"evidencia citable. Va a revisión humana.")

    if raw.confianza < confianza_min:
        return _result("baja_confianza", None, raw.confianza, raw,
                       f"Confianza {raw.confianza:.2f} < umbral {confianza_min}. "
                       f"Va a revisión humana.")

    return _result("ok", raw.regimen, raw.confianza, raw,
                   "Clasificación consistente con la regla y confianza suficiente.")
