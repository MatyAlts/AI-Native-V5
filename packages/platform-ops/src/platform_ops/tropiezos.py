"""Tropiezos de un alumno a lo largo de sus episodios (HU-011, tramo 1).

Indicio de aprendizaje SIN IA y en MODO SOMBRA: no se guarda en ningun lado,
no se muestra a nadie y no entra al clasificador ni a su hash. Son funciones
puras sobre datos que ya existen:

- los eventos CTR de cada episodio (`codigo_ejecutado`, `tests_ejecutados`,
  `prompt_enviado`), y
- las clasificaciones del juez del eje fino (`features.regimen_llm`).

Un *tropiezo* es un error de Python al apretar Ejecutar, agrupado por el tipo
de la excepcion (ValueError, TypeError, ...). Se mira como lo resolvio el
alumno: solo, con el tutor en el medio, o si quedo sin resolver.

Limites que hay que tener presentes al leerlo (ver
`docs/research/indicio-aprendizaje.md`):

- El CTR guarda solo la ultima linea del error (`pyodideError.ts`), sin numero
  de linea: dos ValueError distintos se ven iguales.
- Probar (`tests_ejecutados`) no guarda que prueba fallo: los errores de logica
  no entran por esta via. Probar solo cuenta como resolucion si pasa todo.
- `prompt_kind` NO se usa (es un regex sin validar). Del tutor solo importa si
  hubo al menos un mensaje entre el error y la resolucion.
- `reflexion_completada` no se lee nunca.
"""

from __future__ import annotations

import builtins
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

TROPIEZOS_VERSION = "1.0.0"

OTRO_ERROR = "OtroError"

SOLO = "solo"
CON_TUTOR = "con_tutor"
SIN_RESOLVER = "sin_resolver"

MEJORA = "mejora"
SIN_CAMBIO = "sin_cambio"
SIN_DATOS = "sin_datos"

# Clase de excepcion al principio de la ultima linea: `ValueError: ...`.
_TIPO_RE = re.compile(r"^([A-Za-z_]+(?:Error|Exception))\b")

# Excepciones de Python que se reconocen por nombre. Una clase propia del
# alumno (`class MiError(Exception)`) o de Java cae en OtroError.
_TIPOS_PYTHON: frozenset[str] = frozenset(
    nombre
    for nombre, valor in vars(builtins).items()
    if isinstance(valor, type) and issubclass(valor, BaseException)
)

# Mensajes que emite la PLATAFORMA, no el programa del alumno (N01). Se
# reconocen solo cuando el mensaje ENTERO es de la plataforma (N08): cada
# patron esta anclado al principio de la primera o de la ultima linea y copia
# el texto que se emite. Una subcadena dentro de un error real no alcanza
# (`ValueError: el limite de tiempo debe ser positivo` es un tropiezo).
#
# Fuentes, en `apps/web-student/src/`:
#   - `components/CodeEditor.tsx`: el KeyboardInterrupt al cancelar el input(),
#     el TimeoutError del watchdog, el error de Probar por tiempo, el aviso de
#     la consola y "No hay entorno de ejecucion";
#   - `lib/pyodideError.ts`: reemplaza "TimeoutError: " por el reloj;
#   - `lib/corridaRemota.ts`: MENSAJE_TIMEOUT (corrida remota, Java).
_MENSAJES_PLATAFORMA = (
    re.compile(r"^KeyboardInterrupt: Cancelaste el pedido de dato"),
    re.compile(r"^\[Cancelaste el pedido de dato"),
    re.compile(r"^TimeoutError: La ejecucion supero los \d+ segundos y fue interrumpida"),
    re.compile("^\u23f1"),
    re.compile(r"^La ejecucion supero el limite de tiempo \(posible bucle infinito\)"),
    re.compile(r"^Tu programa supero el limite de tiempo y se interrumpio"),
    re.compile(r"^No hay entorno de ejecucion de "),
)

# Java. El `runtime` del evento dice "pyodide-0.26" tambien para Java
# (`tutor-service/routes/episodes.py`), asi que el lenguaje del episodio, si
# viene, manda (N06). Sin lenguaje se usa una heuristica: el error con formato
# de javac o de la JVM al principio de una linea, o una declaracion de Java en
# el codigo FUERA de strings y comentarios de Python (N07). El error que llega
# al CTR desde Java ya viene traducido por `lib/javaError.ts` y casi nunca se
# parece a nada; por eso hace falta mirar el codigo.
_JAVA_EN_ERROR = (
    re.compile(r"^\S*\.java:\d+:\s*error:", re.MULTILINE),
    re.compile(r"^Exception in thread ", re.MULTILINE),
)
_JAVA_EN_CODIGO = re.compile(r"\bclass\s+\w+[^\n:{]*\{|\bpublic\s+static\s+void\s+main\s*\(")
# Strings (triples y simples) y comentarios de Python, en una sola pasada de
# izquierda a derecha: un `#` dentro de un string queda en el string.
_STRINGS_Y_COMENTARIOS = re.compile(
    r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|#[^\n]*'
)


def _ultima_linea(stderr: str) -> str:
    for linea in reversed(stderr.splitlines()):
        if linea.strip():
            return linea.strip()
    return ""


def _es_de_plataforma(stderr: str, ultima: str) -> bool:
    primera = stderr.strip()
    return any(p.match(ultima) or p.match(primera) for p in _MENSAJES_PLATAFORMA)


def _parece_java(stderr: str, code: str) -> bool:
    if any(p.search(stderr) for p in _JAVA_EN_ERROR):
        return True
    sin_strings = _STRINGS_Y_COMENTARIOS.sub(" ", code)
    return bool(_JAVA_EN_CODIGO.search(sin_strings))


def tipo_de_error(stderr: str, code: str = "", language: str | None = None) -> str | None:
    """Tipo de tropiezo de un `stderr`, o None si no es un tropiezo.

    None cuando el stderr esta vacio, es un mensaje de la plataforma o es de
    Java. Con `language` dado, manda: "java" es siempre None y "python" nunca
    se descarta como Java. Si la ultima linea no empieza con una excepcion de
    Python conocida, el tipo es "OtroError".
    """
    if language == "java":
        return None
    if not stderr or not stderr.strip():
        return None
    ultima = _ultima_linea(stderr)
    if _es_de_plataforma(stderr, ultima):
        return None
    if language is None and _parece_java(stderr, code):
        return None
    m = _TIPO_RE.match(ultima)
    if m and m.group(1) in _TIPOS_PYTHON:
        return m.group(1)
    return OTRO_ERROR


def _payload(ev: Mapping[str, Any]) -> Mapping[str, Any]:
    p = ev.get("payload")
    return p if isinstance(p, Mapping) else {}


def _entero(x: Any) -> int:
    return x if isinstance(x, int) and not isinstance(x, bool) else 0


def _probar_pasa_todo(payload: Mapping[str, Any]) -> bool:
    total = _entero(payload.get("test_count_total"))
    fallidas = _entero(payload.get("test_count_failed"))
    return total > 0 and fallidas == 0


def tropiezos_de_episodio(
    events: Iterable[Mapping[str, Any]], language: str | None = None
) -> list[dict[str, Any]]:
    """Tropiezos de un episodio, en orden.

    `language` es el lenguaje del episodio ("python" o "java"), si se sabe. Un
    episodio Java no tiene tropiezos (N06): sus errores llegan al CTR ya
    traducidos y pueden parecer de Python.

    Cada uno: `tipo`, `intentos` (ejecuciones seguidas con ese tipo),
    `resolucion` ("solo", "con_tutor" o "sin_resolver"), `seq_inicio` (primer
    error), `seq_ultimo_error` y `seq_fin` (evento que lo resolvio; None si
    quedo sin resolver).
    """
    if language == "java":
        return []
    ordenados = sorted(events, key=lambda e: _entero(e.get("seq")))
    tropiezos: list[dict[str, Any]] = []
    abierto: dict[str, Any] | None = None
    hubo_tutor = False

    def cerrar(resolucion: str, seq_fin: int | None) -> None:
        nonlocal abierto, hubo_tutor
        if abierto is None:
            return
        abierto["resolucion"] = resolucion
        abierto["seq_fin"] = seq_fin
        tropiezos.append(abierto)
        abierto = None
        hubo_tutor = False

    for ev in ordenados:
        tipo_ev = ev.get("event_type")
        seq = _entero(ev.get("seq"))
        payload = _payload(ev)

        if tipo_ev == "prompt_enviado":
            if abierto is not None:
                hubo_tutor = True
            continue

        if tipo_ev == "tests_ejecutados":
            if abierto is not None and _probar_pasa_todo(payload):
                cerrar(CON_TUTOR if hubo_tutor else SOLO, seq)
            continue

        if tipo_ev != "codigo_ejecutado":
            # reflexion_completada y todo lo demas se ignora (N04).
            continue

        stderr = payload.get("stderr")
        stderr = stderr if isinstance(stderr, str) else ""
        code = payload.get("code")
        code = code if isinstance(code, str) else ""

        if stderr.strip():
            tipo = tipo_de_error(stderr, code, language)
            if tipo is None:
                # Mensaje de la plataforma o Java: ni tropiezo ni resolucion.
                continue
            if abierto is not None and abierto["tipo"] == tipo:
                abierto["intentos"] += 1
                abierto["seq_ultimo_error"] = seq
                continue
            # Un tipo distinto resuelve el anterior y abre otro.
            cerrar(CON_TUTOR if hubo_tutor else SOLO, seq)
            abierto = {
                "tipo": tipo,
                "intentos": 1,
                "seq_inicio": seq,
                "seq_ultimo_error": seq,
            }
            continue

        # Ejecucion limpia.
        cerrar(CON_TUTOR if hubo_tutor else SOLO, seq)

    cerrar(SIN_RESOLVER, None)
    return tropiezos


_SIN_FECHA = datetime.min.replace(tzinfo=UTC)


def _fecha_real(opened_at: Any) -> datetime | None:
    """`opened_at` como instante UTC; None si falta o no es una fecha ISO.

    Sin huso se asume UTC. El `Z` se normaliza a `+00:00`.
    """
    if not isinstance(opened_at, str) or not opened_at.strip():
        return None
    texto = opened_at.strip()
    if texto.endswith(("Z", "z")):
        texto = texto[:-1] + "+00:00"
    try:
        fecha = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=UTC)
    return fecha.astimezone(UTC)


def _clave_fecha(opened_at: Any, episode_id: Any) -> tuple[int, datetime, str]:
    """Orden por fecha real (C07); sin fecha valida, al final; empate por id."""
    fecha = _fecha_real(opened_at)
    if fecha is None:
        return (1, _SIN_FECHA, str(episode_id or ""))
    return (0, fecha, str(episode_id or ""))


def _clave_orden(ep: Mapping[str, Any]) -> tuple[int, datetime, str]:
    return _clave_fecha(ep.get("opened_at"), ep.get("episode_id"))


def _tendencia(apariciones: Sequence[Mapping[str, Any]], posicion: Mapping[str, int]) -> str:
    episodios = {a["episode_id"] for a in apariciones}
    if len(episodios) <= 1:
        return SIN_DATOS
    for i, antes in enumerate(apariciones):
        if antes["resolucion"] not in (CON_TUTOR, SIN_RESOLVER):
            continue
        for despues in apariciones[i + 1 :]:
            if (
                despues["resolucion"] == SOLO
                and posicion[despues["episode_id"]] > posicion[antes["episode_id"]]
            ):
                return MEJORA
    # Que un tipo deje de aparecer no es mejora (N03): sin una aparicion
    # posterior resuelta solo, no hay evidencia.
    return SIN_CAMBIO


def trayectoria_alumno(episodios: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Linea de tiempo de los tropiezos de un alumno, por tipo de error.

    `episodios`: [{"episode_id", "tarea_practica_id", "opened_at", "events",
    "language"?}]. `language` es opcional y, si viene, manda sobre la
    heuristica de Java. Se ordenan por la fecha real de `opened_at` (empate:
    `episode_id`; sin fecha valida, al final). Cada aparicion lleva
    `mismo_tp` respecto de la aparicion anterior del mismo tipo (None en la
    primera).
    """
    ordenados = sorted(episodios, key=_clave_orden)
    posicion = {str(ep.get("episode_id")): i for i, ep in enumerate(ordenados)}
    por_tipo: dict[str, dict[str, Any]] = {}

    for ep in ordenados:
        eid = str(ep.get("episode_id"))
        tp = ep.get("tarea_practica_id")
        language = ep.get("language")
        lenguaje = language if isinstance(language, str) else None
        for t in tropiezos_de_episodio(ep.get("events") or [], lenguaje):
            entrada = por_tipo.setdefault(t["tipo"], {"apariciones": []})
            previas = entrada["apariciones"]
            mismo_tp = None if not previas else previas[-1]["tarea_practica_id"] == tp
            previas.append(
                {
                    "episode_id": eid,
                    "tarea_practica_id": tp,
                    "opened_at": ep.get("opened_at"),
                    "mismo_tp": mismo_tp,
                    "intentos": t["intentos"],
                    "resolucion": t["resolucion"],
                    "seq_inicio": t["seq_inicio"],
                    "seq_fin": t["seq_fin"],
                }
            )

    for entrada in por_tipo.values():
        entrada["tendencia"] = _tendencia(entrada["apariciones"], posicion)

    return {"version": TROPIEZOS_VERSION, "por_tipo": por_tipo}


# ── Serie del juez ───────────────────────────────────────────────────────
#
# Misma normalizacion que `apps/web-teacher/src/utils/lecturaJuez.ts`: la
# forma del `raw` la decide D1 (`d1_verbalizacion` -> MTAC v2/v3,
# `verbalizacion` -> v1). Un valor que no se reconoce queda "no_evaluable".

_TRI = ("presente", "ausente", "no_evaluable")
_D4_MTAC = ("interlocutor", "oraculo", "transferencia", "no_evaluable")
_D4_V1 = {"presente": "interlocutor", "ausente": "oraculo", "no_evaluable": "no_evaluable"}


def _tri_v1(valor: Any) -> str:
    if isinstance(valor, bool):
        return "presente" if valor else "ausente"
    return valor if valor in _TRI else "no_evaluable"


def _dim(raw: Mapping[str, Any], clave: str) -> Mapping[str, Any]:
    d = raw.get(clave)
    return d if isinstance(d, Mapping) else {}


def _leer_v1(raw: Mapping[str, Any]) -> dict[str, str]:
    return {
        "d1": _tri_v1(_dim(raw, "verbalizacion").get("presente")),
        "d2": _tri_v1(_dim(raw, "verificacion").get("presente")),
        "d3": _tri_v1(_dim(raw, "justificacion").get("presente")),
        "d4": _D4_V1[_tri_v1(_dim(raw, "autonomia").get("presente"))],
    }


def _leer_mtac(raw: Mapping[str, Any]) -> dict[str, str]:
    def valor(clave: str, validos: Sequence[str]) -> str:
        v = _dim(raw, clave).get("valor")
        return v if isinstance(v, str) and v in validos else "no_evaluable"

    return {
        "d1": valor("d1_verbalizacion", _TRI),
        "d2": valor("d2_verificacion", _TRI),
        "d3": valor("d3_justificacion", _TRI),
        "d4": valor("d4_autonomia", _D4_MTAC),
    }


def serie_juez(clasificaciones: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """D1 a D4 del juez por episodio, en orden de la fecha real de `opened_at`.

    Solo entran los episodios donde el juez decidio (`estado == "ok"`) y el
    `raw` tiene una de las dos formas conocidas (N02).
    """
    filas: list[tuple[tuple[int, datetime, str], dict[str, str]]] = []
    for c in clasificaciones:
        features = c.get("features")
        features = features if isinstance(features, Mapping) else {}
        juez = features.get("regimen_llm")
        if not isinstance(juez, Mapping) or juez.get("estado") != "ok":
            continue
        raw = juez.get("raw")
        if not isinstance(raw, Mapping):
            continue
        if isinstance(raw.get("d1_verbalizacion"), Mapping):
            dims = _leer_mtac(raw)
        elif isinstance(raw.get("verbalizacion"), Mapping):
            dims = _leer_v1(raw)
        else:
            continue
        eid = str(c.get("episode_id"))
        filas.append((_clave_fecha(c.get("opened_at"), eid), {"episode_id": eid, **dims}))
    filas.sort(key=lambda f: f[0])
    return [fila for _, fila in filas]
