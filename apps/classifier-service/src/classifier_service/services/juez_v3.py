"""Juez LLM v3: el juez v2 aplicando el codebook MTAC v2 (HU-005).

El codebook v2 es el v1 con la D4 reescrita: mide QUIÉN DECIDE en cada
intercambio con el tutor, con preguntas en orden (P1 a P8, P1b) y una regla de
conteo por mayoría con desempate por P3. Todo lo demás es el v2: la traza
(`juez_v2.armar_traza_v2`), el verificador de evidencia, la regla en código
(`regla_mtac.regimen_segun_regla_mtac`) y el flujo (`juez_v2._juzgar_mtac`).
Este módulo solo aporta el prompt, los ejemplos y la salida, que suma la marca
de frontera (`es_frontera`, `frontera_entre`).

Se elige con `settings.eje_fino_juez_version = "v3"`. El prompt queda congelado
por `HUELLA_PROMPT_V3`. Ningún texto sale de la muestra de 150 del estudio.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import field_validator

from classifier_service.services.juez_v2 import (
    _SECCION_D1_D3,
    _SECCION_EJEMPLOS,
    _SECCION_FRONTERAS_COMUNES,
    _SECCION_NO_EVALUABLE,
    _SECCION_PRINCIPIOS_Y_TRAZA,
    _SECCION_REGIMENES_Y_REGLA,
    RESPONSE_JSON_SCHEMA_V2,
    EstadoV2,
    RegimenV2Raw,
    RegimenV2Result,
    _armar_prompt,
    _bloque_ejemplos,
    _dim,
    _fewshot,
    _juzgar_mtac,
    _mensaje_usuario,
    armar_traza_v2,  # noqa: F401 — reexportado: el v3 usa la misma traza (C02)
)
from classifier_service.services.regimen_llm import CompleteFn
from classifier_service.services.regla_mtac import (  # noqa: F401 — reexportada: misma regla (C02)
    regimen_segun_regla_mtac,
)

JUEZ_VERSION = "v3"
# Bumpear ante cualquier cambio del prompt, los ejemplos, los few-shot o el schema.
# v3.1.0 (HU-009, 2026-11-20): regla de Juani sobre CUÁNDO se pide la solución
# (`_SECCION_PEDIR_SOLUCION_V3`). El juez v2 no cambia.
PROMPT_VERSION_V3 = "mtac_v2_juez_v3.1.0"

_REGIMENES = ["REFLEXIVA", "SUPERFICIAL", "PASIVA", "EVIDENCIA_INSUFICIENTE"]
RegimenFrontera = Literal["REFLEXIVA", "SUPERFICIAL", "PASIVA", "EVIDENCIA_INSUFICIENTE"]


# ── Salida ─────────────────────────────────────────────────────────────────
class RegimenV3Raw(RegimenV2Raw):
    """Salida del v2 más la marca de frontera (`extra=forbid` heredado)."""

    es_frontera: bool
    # Vacía, o los dos regímenes entre los que está el caso.
    frontera_entre: list[RegimenFrontera]

    @field_validator("frontera_entre")
    @classmethod
    def _cero_o_dos_distintos(cls, v: list[str]) -> list[str]:
        if len(v) not in (0, 2) or len(set(v)) != len(v):
            raise ValueError("frontera_entre: vacía o dos regímenes distintos")
        return v


RESPONSE_JSON_SCHEMA_V3: dict[str, Any] = copy.deepcopy(RESPONSE_JSON_SCHEMA_V2)
RESPONSE_JSON_SCHEMA_V3["json_schema"]["name"] = "ClasificacionRegimenMTACv2"
_schema = RESPONSE_JSON_SCHEMA_V3["json_schema"]["schema"]
_schema["required"] += ["es_frontera", "frontera_entre"]
_schema["properties"]["es_frontera"] = {"type": "boolean"}
_schema["properties"]["frontera_entre"] = {
    "type": "array",
    "items": {"type": "string", "enum": _REGIMENES},
    "maxItems": 2,
    "uniqueItems": True,
}


class RegimenV3Result(RegimenV2Result):
    """Como `RegimenV2Result`, con la salida v3 y `juez_version="v3"`."""

    raw: RegimenV3Raw | None
    juez_version: Literal["v3"] = "v3"  # type: ignore[assignment]


# ── Prompt ─────────────────────────────────────────────────────────────────
# Mismas fuentes que el v2 (anclas fuera de la muestra, codebook §8, sintéticos
# de Alberto). Cada texto se revisó contra la D4 del codebook v2 y dice qué
# pregunta decide el valor.
EJEMPLOS_FRONTERA_V3: list[dict[str, str]] = [
    {
        "d4": "interlocutor",
        "fuente": "9a54cd3b",
        "texto": (
            "Reflexiva (D1 presente, D2 presente, D3 presente, D4 interlocutor). El alumno "
            'explica por qué eligió un while ("no sé cuántos dígitos puede tener el número", '
            "mensaje 1), describe cómo va a funcionar su algoritmo (mensaje 2) y cuenta que ya "
            "lo probó con las pruebas antes de ejecutarlo (mensaje 4, ejecución 1). D4: sus "
            "pedidos traen un criterio propio (P2) y lo que pide confirmar ya lo había decidido "
            "él (P1b): decide el alumno."
        ),
    },
    {
        "d4": "interlocutor",
        "fuente": "c06498f3",
        "texto": (
            "Reflexiva (D1 presente, D2 presente, D3 presente, D4 interlocutor). Propone una "
            'solución y pregunta si está bien (mensaje 1), la defiende con un criterio ("no '
            'tendríamos id repetidos", mensaje 2) y después la pone a prueba con un caso propio: '
            '"tenemos 6 empleados, eliminamos uno, el total_empleados = 6" (mensaje 4). D4: '
            "había producción propia antes de preguntar (P1) y el mensaje trae su criterio (P2)."
        ),
    },
    {
        "d4": "interlocutor",
        "fuente": "11007e5f",
        "texto": (
            "Superficial, frontera con reflexiva (D1 ausente, D2 presente, D3 ausente, D4 "
            "interlocutor). Hace una consulta conceptual (mensaje 1), cuenta su plan (mensaje 2) "
            'y contesta las repreguntas del tutor con respuestas cortas ("un else", "float"). '
            "Ejecuta, ve un NameError por un nombre mal escrito y lo corrige (ejecuciones 2 y 3): "
            "eso es D2. Las decisiones las toma él, a partir de su plan: D4 interlocutor. Pero "
            "nunca pone en palabras por qué hace lo que hace: eso es D1, no D4. Sin D1 no puede "
            "ser reflexiva."
        ),
    },
    {
        "d4": "interlocutor",
        "fuente": "codebook_v1 §8",
        "texto": (
            'Reflexiva (D1 presente, D3 presente, D4 interlocutor). El alumno escribe: "tengo '
            "que usar 'a', ya que 'r' es solo lectura y 'w' reescribiría de 0 el archivo\", y más "
            "adelante: \"el formato 'a' es el correcto, porque el ejercicio pide agregar al "
            'final". La decisión y el criterio son suyos (P2).'
        ),
    },
    {
        "d4": "oraculo",
        "fuente": "2c3a952b",
        "texto": (
            "Superficial, frontera con pasiva (D1 ausente, D2 presente, D3 ausente, D4 oráculo). "
            'Arranca volcando el problema ("no entiendo mi error", mensaje 1) y contesta casi '
            'todo con una o dos palabras, dos veces "no lo sé". Tenía código propio, pero sus '
            "mensajes traen solo el síntoma (P2), la causa la nombra el tutor (P3) y aplica las "
            "pistas sin agregar nada propio (P4): oráculo. No es transferencia, porque las "
            'respuestas del tutor sí producen cambios (P8): "por 2", "numero % 2", "nada" '
            "(mensajes 3, 4 y 7), y al final el código anda y lo prueba con un par, un impar y "
            "otro par (ejecuciones 7 a 9). Construye sobre lo que le devuelve el tutor: "
            "superficial, no pasiva."
        ),
    },
    {
        "d4": "oraculo",
        "fuente": "codebook_v1 §8",
        "texto": (
            'Superficial, la trampa fina (D1 ausente, D4 oráculo). "No me anda, error en la '
            'línea 8, ¿cómo lo arreglo?". El tutor nombra la causa (P3) y el alumno cierra con '
            '"ah ok, entonces la 8 abre el archivo y la 9 lee las líneas": aplicó la corrección '
            "sin agregar nada propio (P4) y después solo narró."
        ),
    },
    {
        "d4": "oraculo",
        "fuente": "sintetico_alberto s-2c9e",
        "texto": (
            "Superficial (D1 ausente, D2 presente, D3 ausente, D4 oráculo). La pregunta de cómo "
            "convertir la entrada a número es un dato puntual: no cuenta (P5). Ejecuta, ve que "
            'imprime todas las categorías y pide "¿cómo lo arreglo?"; el tutor le marca la '
            'diferencia entre if y elif y él la aplica (P3, P4). Pregunta "¿así está bien?" y '
            "prueba con 7 solo porque el tutor se lo sugiere (P4). En la mayoría de los "
            "intercambios decide el tutor."
        ),
    },
    {
        "d4": "transferencia",
        "fuente": "622a9ba0",
        "texto": (
            "Pasiva (D1 ausente, D2 ausente, D3 ausente, D4 transferencia). Pega el mismo error "
            "tres veces sin preguntarse la causa (mensajes 1, 3 y 4) y, cuando el tutor le explica "
            'que está usando un texto como si fuera una función, contesta "pero está bien '
            'escrito" (mensaje 5). Ejecuta siete veces con el mismo TypeError (ejecuciones 7 a '
            "10 y 12 a 14) sin tocar lo que lo causa, y termina con el código roto. Ninguna "
            "respuesta del tutor produce un cambio relacionado (P8): transferencia."
        ),
    },
    {
        "d4": "transferencia",
        "fuente": "codebook_v1 §8",
        "texto": (
            "Pasiva (D4 transferencia, sin citas en D1, D2 ni D3). El alumno vuelca errores uno "
            'tras otro ("SyntaxError: invalid syntax", "IndentationError: unexpected '
            'indent"), responde a las repreguntas del tutor con "cual", "si", y ejecuta '
            "decenas de veces con el mismo error sin cambiar lo que el error señala. Lo que el "
            "tutor le devuelve no cambia nada de lo que hace (P8)."
        ),
    },
    {
        "d4": "transferencia",
        "fuente": "sintetico_alberto s-7f3a",
        "texto": (
            'Pasiva (D1 ausente, D2 ausente, D3 ausente, D4 transferencia). Pide "hacé el '
            'ejercicio 9"; ante cada repregunta del tutor contesta "no se pasame el codigo", '
            '"cual" y "pasame el codigo completo porfa"; el código le llega con un pegado, no '
            'a partir de las pistas; pega el error de su ejecución tal cual, responde "no se" a '
            "la pregunta sobre input() y abandona. Ninguna respuesta del tutor produce un cambio "
            "relacionado (P8)."
        ),
    },
    {
        "d4": "no_evaluable",
        "fuente": "codebook_v1 §8",
        "texto": (
            "Evidencia insuficiente (todas las dimensiones no_evaluable). El alumno abre el "
            'ejercicio, pregunta "¿esto se entrega por acá?", y lo cierra sin escribir código: '
            "no hay eventos de código (P7)."
        ),
    },
]

_SECCION_INTRO_V3 = """\
Sos un codificador experto en didáctica de la programación. Aplicás el codebook MTAC v2 a UN episodio: la sesión de un alumno que resuelve un ejercicio con un tutor de IA. Codificás cómo se relaciona el alumno con el tutor, no si el resultado está bien ni qué tan difícil era el tema."""

_SECCION_POR_QUE_V3 = """\
POR QUÉ ESTE JUEZ EXISTE
En el estudio que valida este codebook, D4 (autonomía) fue la dimensión con más desacuerdo entre los codificadores, y casi todo ese desacuerdo fue interlocutor contra oráculo: la D4 se leía como "¿razona o no razona?" y se pisaba con D1. Por eso en esta versión D4 mide quién decide, intercambio por intercambio, con preguntas en orden. Además, la delegación pasiva fue muy sobrediagnosticada por reglas automáticas que contaban mensajes: leé contenido, no cuentes actividad, y no asignes transferencia sin evidencia positiva."""

_SECCION_D4_V3 = """\
D4. Autonomía cognitiva: QUIÉN DECIDE en cada intercambio con el tutor, el alumno o el tutor. No mide si el alumno razona bien: eso es D1. Un alumno puede razonar poco y aun así decidir él (interlocutor), o razonar y dejarle la decisión al tutor (oráculo). Un valor:
- interlocutor: el alumno decide; el tutor le sirve para contrastar, entender o confirmar algo que él propuso.
- oraculo: el tutor decide (la solución, la corrección, la causa del error o el veredicto) y el alumno lo aplica.
- transferencia: ninguna respuesta del tutor produce un cambio relacionado en lo que hace el alumno.
- no_evaluable: no hay intercambios con el tutor sobre el problema, o el episodio no tiene eventos de código que respalden lo que el alumno dice (P7).

Cómo se decide D4. Se trabaja intercambio por intercambio. Un intercambio es un pedido del alumno, la respuesta del tutor y lo que el alumno hace después, hasta su próximo pedido. Cada respuesta sale de un mensaje o un evento de la traza.

Primero descartá los intercambios que no cuentan:
- P5. ¿Lo pedido es un dato o una sintaxis puntual ("¿cómo redondeo a dos decimales?", "¿cómo se escribe un f-string?") y no la decisión del ejercicio? No cuenta.
- P6. ¿El intercambio lo causó una falla ajena al alumno (una prueba mal armada, una falla de la plataforma, un mensaje del sistema)? No cuenta. Si sacarlo cambiaría el régimen, marcá frontera.
- P1b. ¿Es un pedido de confirmación sobre una producción propia completa, y el tutor confirma sin pedir cambios? No cuenta: el alumno ya había decidido. Si el tutor marca un problema, el intercambio sí cuenta y seguís con P2.

A cada intercambio que cuenta asignale un valor, en este orden:
- P1. ¿Había producción propia sobre ese punto antes del pedido (código editado o una propuesta en el chat)? Si no la había y pide la solución o la corrección: oráculo. Si la había, seguí.
- P2. ¿El mensaje del alumno trae una hipótesis, una causa o un criterio propio? Si lo trae: interlocutor. Si trae solo el síntoma ("no anda", el error pegado) o alternativas sin criterio, seguí.
- P3. ¿Quién nombra primero la causa del problema? Si la nombra el alumno, aunque antes haya pegado el error: interlocutor. Si la nombra el tutor, seguí.
- P4. Después de la respuesta, ¿el alumno hace algo que la respuesta no le dio (elige entre alternativas, discute, prueba un caso nuevo o corrige otra cosa por su cuenta)? Si lo hace: interlocutor. Si solo aplica lo que le dieron: oráculo.

Para todo el episodio:
- P7. ¿Hay eventos de código (ediciones o ejecuciones) que respalden lo que el alumno dice? Si no hay ninguno, D4 es no_evaluable.
- P8. ¿Alguna respuesta del tutor produce un cambio relacionado, en el código o en la pregunta siguiente? Si ninguna respuesta del tutor produce un cambio: transferencia. Insistir en la solución o contestar con monosílabos es un indicio, no un requisito. La poca interacción por sí sola no es transferencia.

Regla de conteo de D4:
1. Si P7 no encuentra eventos de código, D4 es no_evaluable.
2. Tomá los intercambios que cuentan (sin los de P5, P6 y P1b).
3. Si P8 da transferencia, D4 es transferencia.
4. Si no, asigná interlocutor u oráculo a cada intercambio con P1 a P4: D4 es el valor de la mayoría.
5. Si hay empate, decide P3 aplicada al problema principal del episodio (el que más intercambios ocupó).
6. Si no queda ningún intercambio que cuente: interlocutor si hubo producción propia (trabajó solo y solo pidió datos o confirmaciones), no_evaluable si no la hubo.
La cita de D4 sale del intercambio que decide: uno de la mayoría, o el del desempate por P3."""

_SECCION_CONDUCTA_MIXTA_V3 = """\
- Conducta mixta: si cambia a lo largo del episodio, D1, D2 y D3 se marcan presentes con una evidencia citable, y D4 sale de la regla de conteo por intercambios.

MARCA DE FRONTERA
Marcá "es_frontera": true cuando el caso está en el borde entre dos regímenes, en especial cuando la mayoría de intercambios de D4 es ajustada o la decide el desempate por P3, o cuando sacar un intercambio por P6 cambiaría el régimen. En "frontera_entre" poné los dos regímenes, primero el que asignás. Si no es frontera: false y una lista vacía."""

_SECCION_TRAMPAS_V3 = """\
LAS SIETE TRAMPAS
1. Narrar no es razonar.
2. Pedir la solución es oráculo, aunque después el alumno explique lo que le dieron sin discutirlo. Pedir un dato o una sintaxis puntual no cuenta para D4.
3. Ejecutar mucho no es verificar: cuenta la reacción al resultado, no la cantidad de ejecuciones.
4. Escribir mucho o rápido no es delegar: el ritmo y la cantidad de mensajes no son criterio.
5. Equivocarse no baja el régimen.
6. Poco rastro no es pasiva: sin material para juzgar es evidencia insuficiente, no delegación.
7. D4 no es D1. Que el alumno razone poco no lo hace oráculo: D4 mira quién decide en cada intercambio."""

# HU-009 (v3.1.0): regla de Juani (20/11/2026): "si es para ver si todo le
# quedó perfecto y comparar es reflexiva; si es al principio es un indicio de
# pasiva". Un solo párrafo, después de las trampas porque precisa la 2.
_SECCION_PEDIR_SOLUCION_V3 = """\
CUÁNDO SE PIDE LA SOLUCIÓN
El momento en que el alumno pide la solución cambia lo que significa, y precisa la trampa 2. Si la pide al principio, antes de intentar el ejercicio por su cuenta (sin producción propia sobre ese punto, P1), es un indicio de pasiva: ese intercambio es oráculo. Si la pide al final, con el ejercicio ya resuelto por él, para ver si todo le quedó perfecto y comparar la solución con la suya, es conducta reflexiva y no un indicio de pasiva: verifica su propia producción, cuenta para D2 si contrasta las dos versiones, y para D4 se trata como P1b, porque la decisión ya la había tomado él. Un indicio no es un veredicto: la transferencia sigue necesitando la evidencia positiva de P8, y el régimen sigue saliendo de la regla sobre las cuatro dimensiones."""

_SECCION_SALIDA_V3 = """\
SALIDA
Devolvé EXCLUSIVAMENTE un JSON con esta forma, sin texto adicional:
- "d1_verbalizacion", "d2_verificacion", "d3_justificacion": {{"valor": "presente" | "ausente" | "no_evaluable", "localizador": ..., "cita": ...}}
- "d4_autonomia": {{"valor": "interlocutor" | "oraculo" | "transferencia" | "no_evaluable", "localizador": ..., "cita": ...}}
- "regimen": "REFLEXIVA" | "SUPERFICIAL" | "PASIVA" | "EVIDENCIA_INSUFICIENTE"
- "confianza": decimal entre 0 y 1 (menor a 0.70 si la evidencia es ambigua)
- "justificacion_global": por qué, en dos o tres oraciones; para D4, qué intercambios contaste y qué pregunta decidió.
- "es_frontera": true o false
- "frontera_entre": [] o dos regímenes distintos, por ejemplo ["SUPERFICIAL", "REFLEXIVA"]
Reglas del "localizador": lista separada por comas, cada elemento "<tipo> <N>" tal como aparece en la traza ("mensaje 3", "ejecución 2", "prueba 1", "nota 1", "edición 4"). Sin rangos ni "y": "ejecución 7, ejecución 8". Cadena vacía si no hay evidencia. Nunca inventes un número que no esté en la traza.
Reglas de la "cita": copia TEXTUAL de algo que escribió el alumno (un mensaje, una nota o su código), sin parafrasear ni traducir; podés recortar y unir fragmentos con "...". Nunca cites al tutor. Cadena vacía si la dimensión es ausente o no_evaluable. D1 y D3 presentes necesitan cita; D4 (salvo no_evaluable) necesita cita; D2 presente necesita cita o al menos un localizador de ejecución o prueba. Una cita que no está textual en lo que escribió el alumno invalida todo el veredicto."""

_SECCIONES_HASTA_TRAMPAS_V3 = (
    _SECCION_INTRO_V3,
    _SECCION_POR_QUE_V3,
    _SECCION_PRINCIPIOS_Y_TRAZA,
    _SECCION_D1_D3,
    _SECCION_D4_V3,
    _SECCION_NO_EVALUABLE,
    _SECCION_REGIMENES_Y_REGLA,
    _SECCION_FRONTERAS_COMUNES + "\n" + _SECCION_CONDUCTA_MIXTA_V3,
    _SECCION_TRAMPAS_V3,
)
_SECCIONES_FINALES_V3 = (_SECCION_EJEMPLOS, _SECCION_SALIDA_V3)

# N03 (HU-009): cada versión del prompt sigue pudiéndose armar; una versión nueva
# se agrega acá y nunca reescribe una anterior. La que corre la elige
# `settings.eje_fino_juez_v3_prompt`; el default es `PROMPT_VERSION_V3`.
PROMPTS_V3: dict[str, str] = {
    "mtac_v2_juez_v3.0.0": _armar_prompt(
        *_SECCIONES_HASTA_TRAMPAS_V3,
        *_SECCIONES_FINALES_V3,
        ejemplos=_bloque_ejemplos(EJEMPLOS_FRONTERA_V3),
    ),
    "mtac_v2_juez_v3.1.0": _armar_prompt(
        *_SECCIONES_HASTA_TRAMPAS_V3,
        _SECCION_PEDIR_SOLUCION_V3,
        *_SECCIONES_FINALES_V3,
        ejemplos=_bloque_ejemplos(EJEMPLOS_FRONTERA_V3),
    ),
}

SYSTEM_PROMPT_V3 = PROMPTS_V3[PROMPT_VERSION_V3]


def _prompt_v3(version: str | None) -> str:
    """System prompt de `version` (None = `PROMPT_VERSION_V3`); KeyError si no existe."""
    v = PROMPT_VERSION_V3 if version is None else version
    if v not in PROMPTS_V3:
        raise KeyError(f"versión de prompt del juez v3 desconocida: {v!r}")
    return PROMPTS_V3[v]


# Few-shot con los sintéticos de Alberto, salida v3. Mismo régimen que su clave;
# la verificación y la regla los aceptan como `ok` (tests/unit/test_juez_v3.py).
_SALIDAS_FEWSHOT_V3: dict[str, dict[str, Any]] = {
    "s-7f3a": {
        "d1_verbalizacion": _dim("ausente"),
        "d2_verificacion": _dim("ausente"),
        "d3_justificacion": _dim("ausente"),
        "d4_autonomia": _dim(
            "transferencia",
            "mensaje 2, mensaje 4, mensaje 6",
            "pasame el codigo completo porfa",
        ),
        "regimen": "PASIVA",
        "confianza": 0.85,
        "justificacion_global": (
            "Hay código (P7), pero ninguna respuesta del tutor produce un cambio relacionado "
            "(P8): pide el código entero, contesta 'cual' y 'no se', el código le llega con un "
            "pegado y pega el error sin preguntarse la causa. Transferencia sin citas de "
            "apropiación."
        ),
        "es_frontera": False,
        "frontera_entre": [],
    },
    "s-b41d": {
        "d1_verbalizacion": _dim(
            "presente",
            "mensaje 3",
            "int() no acepta un texto con punto decimal y falla antes",
        ),
        "d2_verificacion": _dim(
            "presente",
            "ejecución 2, mensaje 5",
            "con 3 esperaba «Leve», porque 3 < 3 es falso y pasa a la siguiente condición",
        ),
        "d3_justificacion": _dim(
            "presente",
            "mensaje 4",
            "De menor a mayor con elif, así cada condición solo necesita el límite de arriba",
        ),
        "d4_autonomia": _dim(
            "interlocutor",
            "mensaje 1",
            "porque las categorías van de número entero en número entero",
        ),
        "regimen": "REFLEXIVA",
        "confianza": 0.9,
        "justificacion_global": (
            "Los tres intercambios que cuentan los decide él: trae su criterio (mensaje 1, P2), "
            "nombra la causa del error antes que el tutor (mensaje 3, P3) y prueba bordes por su "
            "cuenta (P4). Verbaliza, verifica y justifica: conduce el proceso."
        ),
        "es_frontera": False,
        "frontera_entre": [],
    },
    "s-2c9e": {
        "d1_verbalizacion": _dim("ausente"),
        "d2_verificacion": _dim(
            "presente",
            "ejecución 1, edición 2, ejecución 2",
            "me imprime todas las categorías",
        ),
        "d3_justificacion": _dim("ausente"),
        "d4_autonomia": _dim("oraculo", "mensaje 3, mensaje 5", "¿cómo lo arreglo?"),
        "regimen": "SUPERFICIAL",
        "confianza": 0.8,
        "justificacion_global": (
            "El pedido de cómo convertir a número es un dato puntual y no cuenta (P5). En los "
            "dos intercambios que cuentan decide el tutor: le marca el elif y le propone probar "
            "con 7, y él lo aplica (P3, P4). Integra las pistas y avanza: superficial."
        ),
        "es_frontera": False,
        "frontera_entre": [],
    },
}

FEWSHOT_V3: list[dict[str, str]] = _fewshot(_SALIDAS_FEWSHOT_V3)


def construir_mensajes_v3(
    traza: str, enunciado: str, episode_id: str, version: str | None = None
) -> list[dict[str, str]]:
    """System v3 de `version`, few-shot sintéticos y el episodio a codificar (último)."""
    return [
        {"role": "system", "content": _prompt_v3(version)},
        *FEWSHOT_V3,
        {"role": "user", "content": _mensaje_usuario(traza, enunciado, episode_id)},
    ]


def huella_prompt_v3(version: str | None = None) -> str:
    """sha256 del prompt congelado de `version`: system + ejemplos + few-shot + schema."""
    contenido = (
        _prompt_v3(version)
        + json.dumps(EJEMPLOS_FRONTERA_V3, ensure_ascii=False, sort_keys=True)
        + json.dumps(FEWSHOT_V3, ensure_ascii=False, sort_keys=True)
        + json.dumps(RESPONSE_JSON_SCHEMA_V3, ensure_ascii=False, sort_keys=True)
    )
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


# Literal congelado (C05): si `huella_prompt_v3()` deja de dar esto, el prompt
# cambió y hay que bumpear `PROMPT_VERSION_V3` antes de actualizar el literal.
# v3.0.0 sigue dando e3ae5d5c6f6cf1e2a93c889992f1513543178e55cfa610858cdf239baf1da4ed.
HUELLA_PROMPT_V3 = "1e3e477898af36ae13a60a7fd080d5c4f2fd28049899ad79304da48eab24b24f"


async def clasificar_regimen_v3(
    *,
    events: list[dict],
    enunciado: str,
    episode_id: str,
    complete: CompleteFn,
    model: str,
    tenant_id: UUID,
    materia_id: UUID | None = None,
    confianza_min: float = 0.70,
    max_tokens: int = 6000,
    max_reintentos: int = 2,
    prompt_version: str | None = None,
) -> RegimenV3Result:
    """Codifica el episodio con el codebook MTAC v2; mismo flujo que el v2.

    `prompt_version` elige el prompt (None = `PROMPT_VERSION_V3`) y queda
    registrada en el resultado.
    """
    version = PROMPT_VERSION_V3 if prompt_version is None else prompt_version
    _prompt_v3(version)  # una versión desconocida falla antes de llamar al modelo

    def _result(
        estado: EstadoV2, razon: str, raw: RegimenV3Raw | None, regimen: str | None
    ) -> RegimenV3Result:
        return RegimenV3Result(
            estado=estado,
            regimen=regimen,
            confianza=raw.confianza if raw is not None else None,
            raw=raw,
            razon=razon,
            model_used=model,
            prompt_version=version,
        )

    return await _juzgar_mtac(
        events=events,
        enunciado=enunciado,
        episode_id=episode_id,
        complete=complete,
        model=model,
        tenant_id=tenant_id,
        materia_id=materia_id,
        confianza_min=confianza_min,
        max_tokens=max_tokens,
        max_reintentos=max_reintentos,
        construir_mensajes=functools.partial(construir_mensajes_v3, version=version),
        clase_raw=RegimenV3Raw,
        response_format=RESPONSE_JSON_SCHEMA_V3,
        resultado=_result,
        etiqueta="juez_v3",
    )
