"""Juez LLM v2: alineado al codebook MTAC v1 (HU-001).

Convive con el juez v1 (`regimen_llm.py`), que sigue siendo el default. Se
elige con `settings.eje_fino_juez_version` ("v1" | "v2"); `routes/classify_ep.py`
decide cuál corre.

Qué cambia respecto del v1:

  - Las dimensiones son las del codebook MTAC v1 (D1 verbalización, D2
    verificación, D3 justificación, D4 autonomía con tres valores:
    interlocutor, oráculo, transferencia), cada una con `localizador` y `cita`.
  - El juez ve la MISMA evidencia que los codificadores humanos: la traza se
    arma sobre `traza_ciega.filtrar_traza` (sin marcas del sistema como el
    sobreuso) y con los mismos localizadores (`mensaje N`, `ejecución N`...).
  - La delegación pasiva pasa por el juez: exige evidencia POSITIVA de
    transferencia, nunca falta de evidencia ni cantidad de mensajes.
  - El régimen lo decide la regla en código (`regla_mtac.py`), no el modelo.
    Si el modelo propone otro, el resultado es `inconsistente`.
  - Las citas se verifican contra la traza: tienen que ser textuales de algo
    que escribió el alumno (nunca del tutor) y los localizadores tienen que
    existir. Si no, `salida_invalida`; una dimensión afirmada sin cita,
    `derivado_evidencia_insuficiente`.
  - Sin proveedor real (ai-gateway en mock) no hay veredicto silencioso:
    `proveedor_no_disponible` con un warning.

El prompt queda congelado por huella (`HUELLA_PROMPT_V2`): cambiar el system
prompt, los ejemplos, los few-shot o el schema exige bumpear
`PROMPT_VERSION_V2` y actualizar la huella. Ningún texto del prompt sale de la
muestra de 150 episodios del estudio CIbSE 2027 (N01 de HU-001).
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
import unicodedata
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from classifier_service.services.juez_v2_sinteticos import SINTETICOS_ALBERTO
from classifier_service.services.regimen_llm import (
    SUBGRUPOS_JUZGADOS_POR_JUEZ,
    CompleteFn,
    _limpiar_json,
)
from classifier_service.services.regla_mtac import regimen_segun_regla_mtac
from classifier_service.services.traza_ciega import filtrar_traza

logger = logging.getLogger(__name__)

JUEZ_VERSION = "v2"
# Bumpear ante CUALQUIER cambio del system prompt, los ejemplos, los few-shot,
# el schema, el armado de la traza o la regla: cada veredicto persiste esta
# versión y dice bajo qué prompt se emitió.
PROMPT_VERSION_V2 = "mtac_v1_juez_v2.0.0"

# Con v2 la delegación pasiva también la decide el juez.
SUBGRUPOS_PASIVA_ETAPA_DURA = frozenset({"dependiente_delegador", "dependiente_sobreuso"})
SUBGRUPOS_JUZGADOS_POR_JUEZ_V2 = SUBGRUPOS_JUZGADOS_POR_JUEZ | SUBGRUPOS_PASIVA_ETAPA_DURA

REGIMEN_V2_TO_APPROPRIATION: dict[str, str] = {
    "REFLEXIVA": "apropiacion_reflexiva",
    "SUPERFICIAL": "apropiacion_superficial",
    "PASIVA": "delegacion_pasiva",
}


# ── Contrato de salida ─────────────────────────────────────────────────────
class _DimV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valor: Literal["presente", "ausente", "no_evaluable"]
    localizador: str
    cita: str


class _AutonomiaV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valor: Literal["interlocutor", "oraculo", "transferencia", "no_evaluable"]
    localizador: str
    cita: str


class RegimenV2Raw(BaseModel):
    """Salida cruda del modelo, validada contra el contrato v2."""

    model_config = ConfigDict(extra="forbid")

    d1_verbalizacion: _DimV2
    d2_verificacion: _DimV2
    d3_justificacion: _DimV2
    d4_autonomia: _AutonomiaV2
    regimen: Literal["REFLEXIVA", "SUPERFICIAL", "PASIVA", "EVIDENCIA_INSUFICIENTE"]
    confianza: float = Field(ge=0, le=1)
    justificacion_global: str


def _schema_dim(valores: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["valor", "localizador", "cita"],
        "additionalProperties": False,
        "properties": {
            "valor": {"type": "string", "enum": valores},
            "localizador": {"type": "string"},
            "cita": {"type": "string"},
        },
    }


_D123 = ["presente", "ausente", "no_evaluable"]

RESPONSE_JSON_SCHEMA_V2: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "ClasificacionRegimenMTAC",
        "schema": {
            "type": "object",
            "required": [
                "d1_verbalizacion",
                "d2_verificacion",
                "d3_justificacion",
                "d4_autonomia",
                "regimen",
                "confianza",
                "justificacion_global",
            ],
            "additionalProperties": False,
            "properties": {
                "d1_verbalizacion": _schema_dim(_D123),
                "d2_verificacion": _schema_dim(_D123),
                "d3_justificacion": _schema_dim(_D123),
                "d4_autonomia": _schema_dim(
                    ["interlocutor", "oraculo", "transferencia", "no_evaluable"]
                ),
                "regimen": {
                    "type": "string",
                    "enum": ["REFLEXIVA", "SUPERFICIAL", "PASIVA", "EVIDENCIA_INSUFICIENTE"],
                },
                "confianza": {"type": "number", "minimum": 0, "maximum": 1},
                "justificacion_global": {"type": "string", "minLength": 1},
            },
        },
    },
}

EstadoV2 = Literal[
    "ok",
    "inconsistente",
    "baja_confianza",
    "error_parseo",
    "abstencion_traza_insuficiente",
    "derivado_evidencia_insuficiente",
    "salida_invalida",
    "proveedor_no_disponible",
]


class RegimenV2Result(BaseModel):
    """Resultado del juez v2, listo para persistir en features['regimen_llm']."""

    estado: EstadoV2
    # Solo con estado == "ok": el régimen que decidió la regla.
    regimen: Literal["REFLEXIVA", "SUPERFICIAL", "PASIVA"] | None
    confianza: float | None
    raw: RegimenV2Raw | None
    razon: str
    model_used: str
    prompt_version: str
    juez_version: Literal["v2"] = "v2"


# ── Traza: la misma evidencia ciega que leen los codificadores humanos ─────
MAX_SALIDA = 1500  # caracteres de stdout/stderr por ejecución
MAX_DIFF = 4000  # caracteres por bloque de diff de código
MAX_TUTOR = 6000  # caracteres por respuesta del tutor

# tipo de la traza ciega -> nombre del localizador
_LOCALIZADOR = {
    "mensaje_alumno": "mensaje",
    "ejecucion": "ejecución",
    "prueba": "prueba",
    "nota": "nota",
    "codigo": "edición",
}


def _corta(s: str | None, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + f"\n[... recortado, {len(s) - n} caracteres más]"


def _diff(a: str, b: str) -> str:
    d = difflib.unified_diff((a or "").splitlines(), (b or "").splitlines(), lineterm="", n=1)
    lineas = [linea for linea in d if not linea.startswith(("---", "+++"))]
    return _corta("\n".join(lineas), MAX_DIFF)


def _mm(t: float | None) -> str:
    t = int(t or 0)
    return f"{t // 60:02d}:{t % 60:02d}"


def _elementos(events: list[dict]) -> list[dict[str, Any]]:
    if not events:
        return []
    seq_tope = max(e["seq"] for e in events)
    return filtrar_traza(events, seq_tope)


def _renderizar(elementos: list[dict[str, Any]]) -> str:  # noqa: PLR0912, PLR0915 — un if/elif por tipo de la traza ciega, como compactar_referencia
    """Texto de la traza con los localizadores que ve el codificador humano."""
    out: list[str] = []
    codigo_actual = ""
    codigo_ejecutado: str | None = None
    i = 0
    while i < len(elementos):
        e = elementos[i]
        tipo, d, k = e["tipo"], e["datos"], e["k"]
        p = f"[t={_mm(e['t_seg'])}]"
        if tipo == "codigo":
            j = i
            while j + 1 < len(elementos) and elementos[j + 1]["tipo"] == "codigo":
                j += 1
            ultimo = elementos[j]
            nuevo = ultimo["datos"].get("snapshot") or ""
            rango = f"edición {k}" + (f" a edición {ultimo['k']}" if j > i else "")
            if not codigo_actual:
                cuerpo = "Código del alumno:\n```\n" + _corta(nuevo, MAX_DIFF) + "\n```"
            else:
                cambios = _diff(codigo_actual, nuevo)
                cuerpo = (
                    "Sin cambios netos."
                    if not cambios
                    else "Cambios netos respecto del código anterior:\n```diff\n"
                    + cambios
                    + "\n```"
                )
            cuantas = f", {j - i + 1} ediciones" if j > i else ""
            out.append(f"{p} {rango} (CÓDIGO DEL ALUMNO{cuantas}). {cuerpo}")
            codigo_actual = nuevo
            i = j + 1
            continue
        if tipo == "mensaje_alumno":
            out.append(f"{p} mensaje {k} · ALUMNO: {d.get('content')}")
        elif tipo == "respuesta_tutor":
            turno = f"responde al mensaje {k}" if k is not None else "antes del primer mensaje"
            out.append(f"{p} TUTOR ({turno}): {_corta(d.get('content'), MAX_TUTOR)}")
        elif tipo == "ejecucion":
            codigo = d.get("code") or ""
            if codigo == codigo_actual:
                bloque = "Código ejecutado: el vigente (el de la última edición)."
            elif codigo == codigo_ejecutado:
                bloque = "Código ejecutado: igual al de la ejecución anterior."
            elif not codigo_actual:
                bloque = "Código ejecutado:\n```\n" + _corta(codigo, MAX_DIFF) + "\n```"
            else:
                bloque = (
                    "Código ejecutado: difiere del vigente en:\n```diff\n"
                    + _diff(codigo_actual, codigo)
                    + "\n```"
                )
            casos = ""
            if d.get("total") is not None:
                casos = f" Casos: {d.get('passed')}/{d.get('total')} pasados"
                if d.get("failed_test_names"):
                    casos += f", fallaron {d.get('failed_test_names')}"
                casos += "."
            texto = (
                f"{p} ejecución {k}.{casos}\n{bloque}\nSalida:\n```\n"
                f"{_corta((d.get('stdout') or '').rstrip(), MAX_SALIDA)}\n```"
            )
            if d.get("stderr"):
                texto += f"\nError:\n```\n{_corta(d.get('stderr').rstrip(), MAX_SALIDA)}\n```"
            out.append(texto)
            codigo_ejecutado = codigo
        elif tipo == "prueba":
            out.append(
                f"{p} prueba {k}: {d.get('test_count_passed')}/{d.get('test_count_total')} "
                f"pasadas, {d.get('test_count_failed')} fallidas."
            )
        elif tipo == "nota":
            out.append(f"{p} nota {k} · NOTA DEL ALUMNO: {d.get('content')}")
        elif tipo == "lectura":
            out.append(f"{p} lectura del enunciado ({round(d.get('duration_seconds') or 0)} s)")
        elif tipo == "copia":
            out.append(
                f"{p} copió texto ({d.get('seleccion_chars')} caracteres, {d.get('metodo')})"
            )
        elif tipo == "pegado":
            out.append(
                f"{p} intento de pegar ({d.get('contenido_longitud')} caracteres, {d.get('metodo')})"
            )
        elif tipo == "inicio":
            out.append(f"{p} inicio del episodio ({d.get('language')})")
        elif tipo == "fin_cerrado":
            out.append(f"{p} FIN: episodio cerrado")
        elif tipo == "fin_abandonado":
            out.append(f"{p} FIN: episodio abandonado")
        i += 1
    return "\n\n".join(out) if out else "(traza vacía)"


def armar_traza_v2(events: list[dict]) -> str:
    """Traza que lee el juez: la traza ciega completa del episodio, como texto."""
    return _renderizar(_elementos(events))


# ── Verificación de evidencia (C05) ────────────────────────────────────────
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s or "")).strip().casefold()


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


_RE_LOCALIZADOR = re.compile(r"^(mensaje|ejecucion|prueba|nota|edicion) (\d+)$")
_COMILLAS = " \"'“”«»‘’"


def _localizadores_existentes(elementos: list[dict[str, Any]]) -> set[str]:
    return {
        _sin_tildes(f"{_LOCALIZADOR[e['tipo']]} {e['k']}")
        for e in elementos
        if e["tipo"] in _LOCALIZADOR and e["k"] is not None
    }


def _parsear_localizadores(texto: str) -> list[str] | None:
    """Lista de localizadores normalizados, o None si alguno no tiene formato."""
    partes = [_sin_tildes(_norm(p)) for p in (texto or "").split(",")]
    partes = [p for p in partes if p]
    if any(not _RE_LOCALIZADOR.match(p) for p in partes):
        return None
    return partes


def _textos_del_alumno(elementos: list[dict[str, Any]]) -> list[str]:
    """Todo lo que escribió el alumno: mensajes, notas y su código."""
    textos: list[str] = []
    for e in elementos:
        d = e["datos"]
        if e["tipo"] in ("mensaje_alumno", "nota"):
            textos.append(d.get("content") or "")
        elif e["tipo"] == "codigo":
            textos.append(d.get("snapshot") or "")
        elif e["tipo"] == "ejecucion":
            textos.append(d.get("code") or "")
    return [_norm(t) for t in textos if t]


def _cita_textual(cita: str, textos_alumno: list[str]) -> bool:
    """La cita aparece textual (salvo mayúsculas y espacios) en algo del alumno.

    Se toleran comillas alrededor y fragmentos separados por puntos
    suspensivos; cada fragmento tiene que estar en el MISMO texto.
    """
    fragmentos = [
        _norm(f).strip(_COMILLAS) for f in re.split(r"\.\.\.|…", cita) if _norm(f).strip(_COMILLAS)
    ]
    if not fragmentos:
        return False
    return any(all(f in t for f in fragmentos) for t in textos_alumno)


def _codigo_del_alumno(elementos: list[dict[str, Any]]) -> list[str]:
    """Todo el código que escribió el alumno: cada snapshot y cada código ejecutado."""
    codigos = [
        e["datos"].get("snapshot" if e["tipo"] == "codigo" else "code") or ""
        for e in elementos
        if e["tipo"] in ("codigo", "ejecucion")
    ]
    return [_norm(c) for c in codigos if c]


def _cita_de_diff(cita: str, codigo_alumno: list[str]) -> bool:
    """Cita copiada de un bloque diff de la traza (`+`, `-` o contexto al comienzo).

    La traza muestra las ediciones como diff, así que el modelo puede citar
    `+while n != 0:`. Vale solo contra el CÓDIGO del alumno: cada línea, sin su
    marca, tiene que estar en alguno de sus snapshots o códigos ejecutados. Una
    línea `-` es código borrado, que también escribió el alumno (está en un
    snapshot anterior). Los mensajes y el texto del tutor no entran acá.
    """
    lineas = [linea for linea in cita.strip(_COMILLAS).splitlines() if linea.strip()]
    if not lineas or not any(linea.startswith(("+", "-")) for linea in lineas):
        return False
    sin_marca = [
        _norm(linea[1:] if linea.startswith(("+", "-", " ")) else linea)
        for linea in lineas
        if not linea.startswith("@@")
    ]
    sin_marca = [linea for linea in sin_marca if linea]
    return bool(sin_marca) and all(
        any(linea in codigo for codigo in codigo_alumno) for linea in sin_marca
    )


def _verificar_evidencia(  # noqa: PLR0911 — un return por motivo, cada uno con su razón auditable
    raw: RegimenV2Raw, elementos: list[dict[str, Any]]
) -> tuple[EstadoV2, str] | None:
    existentes = _localizadores_existentes(elementos)
    textos = _textos_del_alumno(elementos)
    codigo = _codigo_del_alumno(elementos)
    dims = (
        ("D1", raw.d1_verbalizacion),
        ("D2", raw.d2_verificacion),
        ("D3", raw.d3_justificacion),
        ("D4", raw.d4_autonomia),
    )
    parseados: dict[str, list[str]] = {}
    for nombre, dim in dims:
        locs = _parsear_localizadores(dim.localizador)
        if locs is None:
            return (
                "salida_invalida",
                f"{nombre}: localizador con formato inválido ({dim.localizador!r}); "
                "se espera una lista '<tipo> <N>' separada por comas.",
            )
        faltan = [loc for loc in locs if loc not in existentes]
        if faltan:
            return (
                "salida_invalida",
                f"{nombre}: localizador inexistente en la traza ({', '.join(faltan)}).",
            )
        if (
            dim.cita.strip()
            and not _cita_textual(dim.cita, textos)
            and not _cita_de_diff(dim.cita, codigo)
        ):
            return (
                "salida_invalida",
                f"{nombre}: la cita {dim.cita!r} no aparece textual en lo que escribió el "
                "alumno (una cita del tutor o una paráfrasis no vale).",
            )
        parseados[nombre] = locs

    for nombre, dim in dims:
        tiene_cita = bool(dim.cita.strip())
        if nombre == "D2" and dim.valor == "presente":
            por_acciones = any(
                loc.startswith(("ejecucion ", "prueba ")) for loc in parseados[nombre]
            )
            if not (tiene_cita or por_acciones):
                return (
                    "derivado_evidencia_insuficiente",
                    "D2 presente sin cita textual ni localizador de ejecución o prueba.",
                )
        elif nombre in ("D1", "D3") and dim.valor == "presente" and not tiene_cita:
            return (
                "derivado_evidencia_insuficiente",
                f"{nombre} presente sin cita textual del alumno.",
            )
        elif nombre == "D4" and dim.valor != "no_evaluable" and not tiene_cita:
            return (
                "derivado_evidencia_insuficiente",
                f"D4 {dim.valor} sin cita textual del alumno.",
            )
    return None


# ── Prompt ─────────────────────────────────────────────────────────────────
# Ejemplos de frontera. Fuentes permitidas, y SOLO estas: las anclas del
# entrenamiento (`anclas_v1`, episodios fuera de la muestra de 150), los
# ejemplos ilustrativos del codebook §8 y los sintéticos de Alberto.
EJEMPLOS_FRONTERA_V2: list[dict[str, str]] = [
    {
        "d4": "interlocutor",
        "fuente": "9a54cd3b",
        "texto": (
            "Reflexiva (D1 presente, D2 presente, D3 presente, D4 interlocutor). El alumno "
            'explica por qué eligió un while ("no sé cuántos dígitos puede tener el número", '
            "mensaje 1), describe cómo va a funcionar su algoritmo (mensaje 2) y cuenta que ya "
            "lo probó con las pruebas antes de ejecutarlo (mensaje 4, ejecución 1). Usa al tutor "
            "para exponer y confirmar su propio razonamiento."
        ),
    },
    {
        "d4": "interlocutor",
        "fuente": "c06498f3",
        "texto": (
            "Reflexiva (D1 presente, D2 presente, D3 presente, D4 interlocutor). Propone una "
            'solución y pregunta si está bien (mensaje 1), la defiende con un criterio ("no '
            'tendríamos id repetidos", mensaje 2) y después la pone a prueba con un caso propio: '
            '"tenemos 6 empleados, eliminamos uno, el total_empleados = 6" (mensaje 4). '
            "Anticipar un caso que rompe la idea es verificar, aunque sea en el chat. D4 "
            "interlocutor: el tutor le sirve para contrastar lo que ya pensó."
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
            "eso es D2. Pero nunca pone en palabras por qué hace lo que hace: describir un plan "
            "no es razonarlo. Sin D1 no puede ser reflexiva."
        ),
    },
    {
        "d4": "interlocutor",
        "fuente": "codebook_v1 §8",
        "texto": (
            'Reflexiva (D1 presente, D3 presente, D4 interlocutor). El alumno escribe: "tengo '
            "que usar 'a', ya que 'r' es solo lectura y 'w' reescribiría de 0 el archivo\", y más "
            "adelante: \"el formato 'a' es el correcto, porque el ejercicio pide agregar al "
            'final". Da razones y justifica contra la consigna.'
        ),
    },
    {
        "d4": "oraculo",
        "fuente": "2c3a952b",
        "texto": (
            "Superficial, frontera con pasiva (D1 ausente, D2 presente, D3 ausente, D4 oráculo). "
            'Arranca volcando el problema ("no entiendo mi error", mensaje 1) y contesta casi '
            'todo con una o dos palabras, dos veces "no lo sé". Parece pasiva. Pero cada '
            'respuesta corta usa la pista anterior: "por 2", "numero % 2", "nada" (mensajes '
            "3, 4 y 7), y al final el código anda y lo prueba con un par, un impar y otro par "
            "(ejecuciones 7 a 9). Avanza con lo que el tutor le devuelve, aunque sea poco: "
            "construye sobre lo que le devuelve el tutor, no hay transferencia. Eso es "
            "superficial, no pasiva."
        ),
    },
    {
        "d4": "oraculo",
        "fuente": "codebook_v1 §8",
        "texto": (
            'Superficial, la trampa fina (D1 ausente, D4 oráculo). "No me anda, error en la '
            'línea 8, ¿cómo lo arreglo?". El tutor responde y el alumno cierra con "ah ok, '
            'entonces la 8 abre el archivo y la 9 lee las líneas". Pidió la corrección y la '
            "aplicó, y después solo narró: narrar no es razonar."
        ),
    },
    {
        "d4": "oraculo",
        "fuente": "sintetico_alberto s-2c9e",
        "texto": (
            "Superficial (D1 ausente, D2 presente, D3 ausente, D4 oráculo). Pregunta cómo "
            'convertir la entrada a número, contesta "sí, float", ejecuta y ve que imprime '
            'todas las categorías, pide "¿cómo lo arreglo?", cambia los if por elif y pregunta '
            '"¿así está bien?"; cuando el tutor le sugiere probar con 7, lo prueba. Incorpora '
            "cada pista y avanza, pero pide la corrección y el veredicto y no da razones propias."
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
            "10 y 12 a 14) sin tocar lo que lo causa, y termina con el código roto. Contar qué "
            "quiere calcular (mensaje 4) es narrar, no razonar. No construye sobre lo que le "
            "devuelve el tutor: transferencia."
        ),
    },
    {
        "d4": "transferencia",
        "fuente": "codebook_v1 §8",
        "texto": (
            "Pasiva (D4 transferencia, sin citas en D1, D2 ni D3). El alumno vuelca errores uno "
            'tras otro ("SyntaxError: invalid syntax", "IndentationError: unexpected '
            'indent"), responde a las repreguntas del tutor con "cual", "si", y ejecuta '
            "decenas de veces con el mismo error sin cambiar lo que el error señala. No integra "
            "lo que el tutor le devuelve."
        ),
    },
    {
        "d4": "transferencia",
        "fuente": "sintetico_alberto s-7f3a",
        "texto": (
            'Pasiva (D1 ausente, D2 ausente, D3 ausente, D4 transferencia). Pide "hacé el '
            'ejercicio 9"; ante cada repregunta del tutor contesta "no se pasame el codigo", '
            '"cual" y "pasame el codigo completo porfa"; pega el error de su ejecución tal '
            'cual, responde "no se" a la pregunta sobre input() y abandona. No incorpora '
            "ninguna pista: evidencia positiva de transferencia."
        ),
    },
    {
        "d4": "no_evaluable",
        "fuente": "codebook_v1 §8",
        "texto": (
            "Evidencia insuficiente (todas las dimensiones no_evaluable). El alumno abre el "
            'ejercicio, pregunta "¿esto se entrega por acá?", y lo cierra sin escribir código.'
        ),
    },
]

_NOMBRE_D4 = {
    "interlocutor": "D4 INTERLOCUTOR",
    "oraculo": "D4 ORÁCULO",
    "transferencia": "D4 TRANSFERENCIA",
    "no_evaluable": "D4 NO EVALUABLE",
}


def _bloque_ejemplos() -> str:
    lineas: list[str] = []
    for valor in ("interlocutor", "oraculo", "transferencia", "no_evaluable"):
        lineas.append(f"{_NOMBRE_D4[valor]}:")
        lineas.extend(f"- {e['texto']}" for e in EJEMPLOS_FRONTERA_V2 if e["d4"] == valor)
    return "\n".join(lineas)


_SYSTEM_PROMPT_BASE = """\
Sos un codificador experto en didáctica de la programación. Aplicás el codebook MTAC v1 a UN episodio: la sesión de un alumno que resuelve un ejercicio con un tutor de IA. Codificás cómo se relaciona el alumno con el tutor, no si el resultado está bien ni qué tan difícil era el tema.

POR QUÉ ESTE JUEZ EXISTE
En el estudio que valida este codebook, D4 (autonomía) fue la dimensión con más desacuerdo entre los codificadores humanos, y la delegación pasiva fue muy sobrediagnosticada por reglas automáticas que contaban mensajes. Por eso: leé contenido, no cuentes actividad, y no asignes transferencia sin evidencia positiva.

PRINCIPIOS
1. Se codifica lo que el alumno hace y dice, no lo que el tutor logra explicarle.
2. Se lee contenido, no se cuenta actividad. La cantidad o el ritmo de mensajes y de ejecuciones no deciden nada por sí solos.
3. Se codifica la conducta observable, no lo que el alumno dice de sí mismo.

LA TRAZA
Ves la misma línea de tiempo que los codificadores humanos, con estos localizadores: "mensaje N" (lo que escribe el ALUMNO), "ejecución N" (con su salida y su error), "prueba N" (pasadas/total), "nota N" (nota del alumno) y "edición N" (cambios en el código del alumno). Las líneas TUTOR son respuestas del tutor: no son evidencia de lo que hizo el alumno y nunca se citan.

LAS CUATRO DIMENSIONES
Alcanza con UNA evidencia citable para marcar D1, D2 o D3 como presente.

D1. Verbalización del razonamiento: ¿el alumno pone en palabras POR QUÉ hace lo que hace, qué espera que pase o qué cree que está fallando?
- presente: da una razón, una causa, una comparación, una expectativa o un criterio ("uso 'a' porque necesito conservar lo anterior"; "¿el for está iterando sobre la palabra en vez de sobre la línea?").
- ausente: describe qué hace el código sin razones; mensajes de una palabra; vuelca un error sin agregar nada.
- Narrar no es razonar: contar qué hace cada línea o contar un plan no cuenta.

D2. Verificación: ¿el alumno pone a prueba lo que piensa y reacciona a lo que encuentra?
- presente en el chat: anticipa un resultado y lo contrasta; razona la causa de un error; relee la consigna y detecta su propio error.
- presente en las acciones: ejecuta o corre las pruebas Y DESPUÉS hace algo que responde a ese resultado (corrige justo lo que el error señalaba, menciona el resultado, prueba un caso nuevo para comprobar una idea).
- ausente: no ejecuta, o ejecuta una y otra vez sin cambios relacionados con el error (fuerza bruta).
- Ejecutar no es verificar: una ejecución sola no alcanza; tiene que estar seguida de una reacción a su resultado.

D3. Justificación de decisiones: ¿el alumno defiende una elección con criterio propio?
- presente: elige entre alternativas y dice por qué; contrasta su solución con la consigna.
- ausente: acepta lo que el tutor sugiere sin evaluarlo; cambia el código sin explicar por qué.

D4. Autonomía cognitiva: ¿usa la IA para pensar o para que piense por él? Un valor:
- interlocutor: pregunta para entender, contrastar una idea propia o confirmar una hipótesis que él formuló; pide una pista o una explicación conceptual y después decide él.
- oraculo: pide la solución, la corrección o el veredicto y lo aplica sin razonarlo ("¿cómo lo arreglo?", "corregime", "¿está bien así?"), o vuelca el error esperando que el tutor se lo resuelva.
- transferencia: no asume la tarea. Insiste en que el tutor le dé la solución y se resiste a pensar, o no integra nada de lo que el tutor le devuelve: repite el pedido, contesta con monosílabos, no avanza a partir de las repreguntas.
- D4 se marca según el patrón PREDOMINANTE del episodio. Un pedido de solución seguido de discusión (la discute, la pone a prueba o la reformula con sus palabras) cuenta como interlocutor. Si pide soluciones o veredictos en la mayor parte de los intercambios, es oráculo aunque discuta alguno.

"no_evaluable" en cualquier dimensión significa que la traza no tiene material para juzgarla (episodio muy breve, la conversación no toca el ejercicio, faltan eventos). Es un juicio sobre la traza, no sobre tu confianza: si hay material pero el caso es ambiguo, decidí y bajá "confianza".

LOS REGÍMENES
- REFLEXIVA: el alumno conduce el proceso; el asistente ayuda, pero el pensamiento es suyo. Equivocarse no baja el régimen: importa cómo trabaja el error.
- SUPERFICIAL: seguimiento competente. Integra las pistas en su propio código y avanza, hace consultas conceptuales puntuales o muestra conocimiento previo, pero reacciona a lo que el tutor le señala sin proponer, verificar ni justificar por su cuenta.
- PASIVA: exige evidencia POSITIVA de transferencia: no integra lo que el tutor le devuelve, repite el pedido, contesta con monosílabos, ejecuta una y otra vez con el mismo error sin diagnóstico. La pasiva NO se asigna por falta de evidencia, ni por la cantidad o el ritmo de mensajes, ni por una falla de captura. Poco rastro no es pasiva: si el alumno trabajó en silencio, es evidencia insuficiente. Escribir mucho o rápido no es delegar: puede estar pensando en voz alta.
- EVIDENCIA_INSUFICIENTE: no hay material para aplicar la regla, o el alumno solo hace consultas administrativas ("¿cómo entrego?") y nunca toca el problema. Marcá las dimensiones como no_evaluable. No fuerces una categoría.

REGLA DE DECISIÓN (la aplica el código sobre tus dimensiones; tu "regimen" tiene que coincidir)
- REFLEXIVA si D1 presente, Y (D2 presente O D3 presente), Y D4 interlocutor.
- PASIVA si D4 transferencia, con cita, Y ninguna de D1, D2, D3 presente.
- SUPERFICIAL en el resto de los episodios con algún aporte del alumno.
- EVIDENCIA_INSUFICIENTE si con lo que marcaste la regla no puede decidir.
Vos proponés las dimensiones con su evidencia; el régimen lo decide la regla en código. Si tu régimen no coincide con la regla aplicada a tus propias dimensiones, el veredicto se descarta.

FRONTERAS
- Pasiva o superficial: ¿el alumno incorpora y construye sobre lo que el tutor le devuelve? Si avanza a partir de las pistas, aunque sea poco y con respuestas cortas: superficial. Si extrae correcciones sueltas, repite, contesta con monosílabos y no progresa: pasiva.
- Superficial o reflexiva: ¿el alumno reacciona a las pistas o conduce el proceso? Si entiende lo que el tutor le marca y lo arregla, en respuestas breves y guiadas: superficial. Si propone, anticipa, verifica o explica por su cuenta: reflexiva, si se cumple la regla.
- Conducta mixta: si cambia a lo largo del episodio, cuenta lo que predomina para D4; D1, D2 y D3 se marcan presentes con una evidencia citable.

LAS SEIS TRAMPAS
1. Narrar no es razonar.
2. Pedir la solución es oráculo, aunque después el alumno explique lo que le dieron sin discutirlo.
3. Ejecutar mucho no es verificar: cuenta la reacción al resultado, no la cantidad de ejecuciones.
4. Escribir mucho o rápido no es delegar: el ritmo y la cantidad de mensajes no son criterio.
5. Equivocarse no baja el régimen.
6. Poco rastro no es pasiva: sin material para juzgar es evidencia insuficiente, no delegación.

EJEMPLOS DE FRONTERA (de fuera del estudio; los números de mensaje y ejecución son de esos episodios, no del que vas a codificar)
{ejemplos}

SALIDA
Devolvé EXCLUSIVAMENTE un JSON con esta forma, sin texto adicional:
- "d1_verbalizacion", "d2_verificacion", "d3_justificacion": {{"valor": "presente" | "ausente" | "no_evaluable", "localizador": ..., "cita": ...}}
- "d4_autonomia": {{"valor": "interlocutor" | "oraculo" | "transferencia" | "no_evaluable", "localizador": ..., "cita": ...}}
- "regimen": "REFLEXIVA" | "SUPERFICIAL" | "PASIVA" | "EVIDENCIA_INSUFICIENTE"
- "confianza": decimal entre 0 y 1 (menor a 0.70 si la evidencia es ambigua)
- "justificacion_global": por qué, en dos o tres oraciones.
Reglas del "localizador": lista separada por comas, cada elemento "<tipo> <N>" tal como aparece en la traza ("mensaje 3", "ejecución 2", "prueba 1", "nota 1", "edición 4"). Sin rangos ni "y": "ejecución 7, ejecución 8". Cadena vacía si no hay evidencia. Nunca inventes un número que no esté en la traza.
Reglas de la "cita": copia TEXTUAL de algo que escribió el alumno (un mensaje, una nota o su código), sin parafrasear ni traducir; podés recortar y unir fragmentos con "...". Nunca cites al tutor. Cadena vacía si la dimensión es ausente o no_evaluable. D1 y D3 presentes necesitan cita; D4 (salvo no_evaluable) necesita cita; D2 presente necesita cita o al menos un localizador de ejecución o prueba. Una cita que no está textual en lo que escribió el alumno invalida todo el veredicto."""

SYSTEM_PROMPT_V2 = _SYSTEM_PROMPT_BASE.format(ejemplos=_bloque_ejemplos())


def _mensaje_usuario(traza: str, enunciado: str, episode_id: str) -> str:
    return (
        f"EPISODIO A CODIFICAR (id: {episode_id})\n"
        f"--- Enunciado del ejercicio ---\n{enunciado or '(no provisto)'}\n"
        f"--- Traza (t = minutos:segundos desde el inicio) ---\n{traza}\n"
        f"--- Fin de la traza ---\n"
        f"Codificá las cuatro dimensiones con localizador y cita, y aplicá la regla. "
        f"Devolvé solo el JSON."
    )


def _dim(valor: str, localizador: str = "", cita: str = "") -> dict[str, str]:
    return {"valor": valor, "localizador": localizador, "cita": cita}


# Few-shot completos armados a partir de los sintéticos de Alberto (episodios
# inventados). La salida es la que el código acepta como `ok`: lo verifica
# `tests/unit/test_juez_v2.py`.
_SALIDAS_FEWSHOT: dict[str, dict[str, Any]] = {
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
            "Pide el código entero una y otra vez y contesta las repreguntas con 'cual' y "
            "'no se'; pega el error de la ejecución 1 sin preguntarse la causa y abandona. "
            "No incorpora ninguna pista: evidencia positiva de transferencia, sin citas de "
            "apropiación."
        ),
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
        "d4_autonomia": _dim("interlocutor", "mensaje 1", "¿Tiene sentido o conviene float?"),
        "regimen": "REFLEXIVA",
        "confianza": 0.9,
        "justificacion_global": (
            "Formula una hipótesis, la prueba y corrige su idea a partir del error; justifica "
            "el orden de las condiciones y prueba los bordes anticipando el resultado. Usa al "
            "tutor para contrastar lo que ya pensó: conduce el proceso."
        ),
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
            "Integra cada pista en su código y reacciona al resultado de la ejecución, pero "
            "pide la corrección y el veredicto y no da razones propias. Construye sobre lo "
            "que le devuelve el tutor: seguimiento competente, no transferencia."
        ),
    },
}


def _fewshot() -> list[dict[str, str]]:
    mensajes: list[dict[str, str]] = []
    for sid, salida in _SALIDAS_FEWSHOT.items():
        sintetico = SINTETICOS_ALBERTO[sid]
        traza = _renderizar(sintetico["elementos"])
        mensajes.append(
            {
                "role": "user",
                "content": _mensaje_usuario(
                    traza, sintetico["enunciado"], f"ejemplo sintético {sid}"
                ),
            }
        )
        mensajes.append({"role": "assistant", "content": json.dumps(salida, ensure_ascii=False)})
    return mensajes


FEWSHOT_V2: list[dict[str, str]] = _fewshot()


def construir_mensajes_v2(traza: str, enunciado: str, episode_id: str) -> list[dict[str, str]]:
    """System, few-shot sintéticos y el episodio a codificar (último)."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT_V2},
        *FEWSHOT_V2,
        {"role": "user", "content": _mensaje_usuario(traza, enunciado, episode_id)},
    ]


def huella_prompt_v2() -> str:
    """sha256 del prompt congelado: system + ejemplos + few-shot + schema."""
    contenido = (
        SYSTEM_PROMPT_V2
        + json.dumps(EJEMPLOS_FRONTERA_V2, ensure_ascii=False, sort_keys=True)
        + json.dumps(FEWSHOT_V2, ensure_ascii=False, sort_keys=True)
        + json.dumps(RESPONSE_JSON_SCHEMA_V2, ensure_ascii=False, sort_keys=True)
    )
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


# Literal congelado (C10): si `huella_prompt_v2()` deja de dar esto, el prompt
# cambió y hay que bumpear `PROMPT_VERSION_V2` antes de actualizar el literal.
HUELLA_PROMPT_V2 = "553e0f33001f4c261670574070fa36de8b3e09284e8584612fbd34d3744c62e8"


# ── Juez ───────────────────────────────────────────────────────────────────
async def clasificar_regimen_v2(  # noqa: PLR0911 — un return por estado terminal
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
) -> RegimenV2Result:
    """Codifica el episodio con el codebook MTAC v1 y decide el régimen por regla.

    Devuelve SIEMPRE un `RegimenV2Result`. Solo con `estado == "ok"` hay
    régimen; cualquier otro estado conserva lo que haya (raw incluido) para
    auditar y el episodio va a revisión humana.
    """
    elementos = _elementos(events)
    messages = construir_mensajes_v2(_renderizar(elementos), enunciado, episode_id)

    def _result(
        estado: EstadoV2,
        razon: str,
        raw: RegimenV2Raw | None = None,
        regimen: str | None = None,
    ) -> RegimenV2Result:
        return RegimenV2Result(
            estado=estado,
            regimen=regimen,
            confianza=raw.confianza if raw is not None else None,
            raw=raw,
            razon=razon,
            model_used=model,
            prompt_version=PROMPT_VERSION_V2,
        )

    raw: RegimenV2Raw | None = None
    motivo_fallo = "el modelo no devolvió un JSON válido"
    for intento in range(max_reintentos + 1):
        res = await complete(
            messages=messages,
            model=model,
            feature="episode_eje_fino",
            tenant_id=tenant_id,
            materia_id=materia_id,
            temperature=0.0,
            max_tokens=max_tokens,
            response_format=RESPONSE_JSON_SCHEMA_V2,
        )
        # C08: el ai-gateway en modo mock devuelve texto inventado. Nunca se
        # toma como veredicto, y se avisa: un mock silencioso parece un juez.
        if getattr(res, "provider", None) == "mock":
            logger.warning(
                "juez_v2_proveedor_mock: el ai-gateway respondió con el proveedor mock; "
                "no hay veredicto",
                extra={"episode_id": episode_id, "provider": "mock"},
            )
            return _result(
                "proveedor_no_disponible",
                "El ai-gateway respondió con el proveedor mock: no hay un LLM real "
                "detrás, así que no hay veredicto. Va a revisión humana.",
            )
        output_tokens = getattr(res, "output_tokens", 0) or 0
        try:
            raw = RegimenV2Raw.model_validate(json.loads(_limpiar_json(res.content)))
            break
        except (json.JSONDecodeError, ValidationError) as exc:
            # Truncado: con temperatura 0 reintentar devuelve el mismo corte.
            truncado = output_tokens >= max_tokens
            motivo_fallo = (
                f"respuesta truncada en {output_tokens} tokens (techo {max_tokens})"
                if truncado
                else f"{type(exc).__name__}: {exc}"
            )
            logger.warning(
                "juez_v2_parseo_fallo",
                extra={
                    "episode_id": episode_id,
                    "intento": intento,
                    "truncado": truncado,
                    "output_tokens": output_tokens,
                    "error": str(exc),
                },
            )
            raw = None
            if truncado:
                break

    if raw is None:
        return _result(
            "error_parseo",
            f"El juez no devolvió un veredicto usable: {motivo_fallo}. Va a revisión humana.",
        )

    fallo = _verificar_evidencia(raw, elementos)
    if fallo is not None:
        estado, motivo = fallo
        return _result(estado, f"{motivo} Va a revisión humana.", raw)

    esperado = regimen_segun_regla_mtac(
        raw.d1_verbalizacion.valor,
        raw.d2_verificacion.valor,
        raw.d3_justificacion.valor,
        raw.d4_autonomia.valor,
    )
    if esperado == "INDETERMINADO":
        return _result(
            "abstencion_traza_insuficiente",
            "La regla MTAC v1 no puede decidir: el valor no evaluable de alguna dimensión "
            "cambia el resultado. Va a revisión humana.",
            raw,
        )
    if raw.regimen != esperado:
        return _result(
            "inconsistente",
            f"El régimen del modelo ({raw.regimen}) no respeta la regla MTAC v1 aplicada a "
            f"sus propias dimensiones (esperado: {esperado}). Va a revisión humana.",
            raw,
        )
    if raw.confianza < confianza_min:
        return _result(
            "baja_confianza",
            f"Confianza {raw.confianza:.2f} < umbral {confianza_min}. Va a revisión humana.",
            raw,
        )
    return _result(
        "ok",
        "Dimensiones con evidencia verificada en la traza y régimen consistente con la "
        "regla MTAC v1.",
        raw,
        esperado,
    )
