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

# Mensajes que emite la PLATAFORMA, no el programa del alumno (N01). Salen de
# `apps/web-student/src/components/CodeEditor.tsx` (cancelar el input(), el
# watchdog de tiempo), `lib/pyodideError.ts` (prefija con el reloj el
# TimeoutError del watchdog) y `lib/corridaRemota.ts` (timeout de Java).
_MENSAJES_PLATAFORMA = (
    re.compile(r"^KeyboardInterrupt\b"),
    re.compile(r"cancelaste el pedido de dato", re.IGNORECASE),
    re.compile(r"l[ií]mite de tiempo", re.IGNORECASE),
    re.compile(r"fue interrumpida", re.IGNORECASE),
    re.compile("⏱"),
    re.compile(r"no hay entorno de ejecuci[oó]n", re.IGNORECASE),
)

# Java. El `runtime` del evento dice "pyodide-0.26" tambien para Java
# (`tutor-service/routes/episodes.py`), asi que se reconoce por el error o por
# el codigo. El error que llega al CTR desde Java ya viene parseado por
# `lib/javaError.ts` y a veces no se parece a nada; por eso se mira el codigo.
_JAVA_EN_ERROR = (
    re.compile(r"\.java:\d+:\s*error"),
    re.compile(r"Exception in thread"),
    re.compile(r"\bjava\.[a-z]+\.[A-Z]"),
)
_JAVA_EN_CODIGO = re.compile(r"public\s+static\s+void\s+main|System\.out\.print")


def _ultima_linea(stderr: str) -> str:
    for linea in reversed(stderr.splitlines()):
        if linea.strip():
            return linea.strip()
    return ""


def _es_de_plataforma(stderr: str, ultima: str) -> bool:
    return any(p.search(ultima) or p.search(stderr) for p in _MENSAJES_PLATAFORMA)


def _es_java(stderr: str, code: str) -> bool:
    if any(p.search(stderr) for p in _JAVA_EN_ERROR):
        return True
    return bool(_JAVA_EN_CODIGO.search(code))


def tipo_de_error(stderr: str, code: str = "") -> str | None:
    """Tipo de tropiezo de un `stderr`, o None si no es un tropiezo.

    None cuando el stderr esta vacio, es un mensaje de la plataforma o es de
    Java. Si la ultima linea no empieza con una excepcion de Python conocida,
    el tipo es "OtroError".
    """
    if not stderr or not stderr.strip():
        return None
    ultima = _ultima_linea(stderr)
    if _es_de_plataforma(stderr, ultima) or _es_java(stderr, code):
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


def tropiezos_de_episodio(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Tropiezos de un episodio, en orden.

    Cada uno: `tipo`, `intentos` (ejecuciones seguidas con ese tipo),
    `resolucion` ("solo", "con_tutor" o "sin_resolver"), `seq_inicio` (primer
    error), `seq_ultimo_error` y `seq_fin` (evento que lo resolvio; None si
    quedo sin resolver).
    """
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
            tipo = tipo_de_error(stderr, code)
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


def _clave_orden(ep: Mapping[str, Any]) -> tuple[str, str]:
    return (str(ep.get("opened_at") or ""), str(ep.get("episode_id") or ""))


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

    `episodios`: [{"episode_id", "tarea_practica_id", "opened_at", "events"}].
    Se ordenan por `opened_at` (empate: `episode_id`). Cada aparicion lleva
    `mismo_tp` respecto de la aparicion anterior del mismo tipo (None en la
    primera).
    """
    ordenados = sorted(episodios, key=_clave_orden)
    posicion = {str(ep.get("episode_id")): i for i, ep in enumerate(ordenados)}
    por_tipo: dict[str, dict[str, Any]] = {}

    for ep in ordenados:
        eid = str(ep.get("episode_id"))
        tp = ep.get("tarea_practica_id")
        for t in tropiezos_de_episodio(ep.get("events") or []):
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
    """D1 a D4 del juez por episodio, en orden de `opened_at`.

    Solo entran los episodios donde el juez decidio (`estado == "ok"`) y el
    `raw` tiene una de las dos formas conocidas (N02).
    """
    filas: list[tuple[tuple[str, str], dict[str, str]]] = []
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
        filas.append(((str(c.get("opened_at") or ""), eid), {"episode_id": eid, **dims}))
    filas.sort(key=lambda f: f[0])
    return [fila for _, fila in filas]
