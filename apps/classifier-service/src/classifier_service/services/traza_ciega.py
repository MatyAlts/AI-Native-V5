"""Traza ciega del episodio para el estudio de codificación (design D4, D4b).

Función PURA sobre los dicts crudos que devuelve el CTR. Falla CERRADA: cada
elemento se arma desde cero copiando solo las claves de la lista blanca; un
tipo de evento que no está en `TIPOS_INCLUIDOS` se omite (incluidos los tipos
futuros). `TIPOS_OMITIDOS` existe para que el test de cobertura de tipos exija
una decisión explícita por cada `event_type` del contrato.

`traza_v1` incluye además el enunciado (D14), que arma el endpoint.

Cambiar la lista blanca exige una versión nueva: un estudio con otra
`traza_version` responde 409 `traza_version_distinta` al servir la traza.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

TRAZA_VERSION = "traza_v1"

# event_type del CTR -> (tipo mostrado, claves permitidas del payload)
TIPOS_INCLUIDOS: dict[str, tuple[str, tuple[str, ...]]] = {
    "episodio_abierto": ("inicio", ("language",)),
    "lectura_enunciado": ("lectura", ("duration_seconds",)),
    "prompt_enviado": ("mensaje_alumno", ("content",)),
    "tutor_respondio": ("respuesta_tutor", ("content",)),
    "edicion_codigo": ("codigo", ("snapshot", "language")),
    "codigo_ejecutado": (
        "ejecucion",
        ("code", "stdout", "stderr", "passed", "failed", "total", "failed_test_names"),
    ),
    "tests_ejecutados": (
        "prueba",
        (
            "test_count_total",
            "test_count_passed",
            "test_count_failed",
            "tests_publicos",
            "tests_hidden",
        ),
    ),
    "anotacion_creada": ("nota", ("content",)),
    "copia_intentada": ("copia", ("seleccion_chars", "metodo")),
    # Sin `contenido_preview`: es el texto pegado.
    "pega_intentada": ("pegado", ("contenido_longitud", "metodo")),
    "episodio_cerrado": ("fin_cerrado", ()),
    # Sin `reason`: `timeout` y `distraccion_pestana` son marcas del sistema.
    "episodio_abandonado": ("fin_abandonado", ()),
}

# Decisión explícita de omitir: marcas o decisiones automáticas, eventos
# posteriores al cierre, calificación y detección del navegador.
TIPOS_OMITIDOS: frozenset[str] = frozenset(
    {
        "intento_adverso_detectado",
        "reflexion_completada",
        "tp_entregada",
        "tp_calificada",
        "episodio_reabierto",
        "pestana_perdida",
        "pestana_recuperada",
    }
)

# Tipos mostrados que llevan localizador propio (`k`).
_CON_LOCALIZADOR = frozenset({"lectura", "mensaje_alumno", "codigo", "ejecucion", "prueba", "nota"})


def _instante(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def filtrar_traza(events: list[dict[str, Any]], seq_tope: int) -> list[dict[str, Any]]:
    """Elementos `{n, tipo, k, t_seg, datos}` de la traza ciega.

    - Solo eventos con `seq <= seq_tope` (evidencia fija, D4b), en orden de `seq`.
    - `n`: localizador global contiguo desde 1, asignado después de omitir.
    - `k`: localizador por tipo; las respuestas del tutor llevan el turno del
      último mensaje del alumno (None antes del primero). Inicio, copia,
      pegado y fin no llevan.
    - Latidos `lectura_enunciado` sin otro evento INCLUIDO entre ellos se
      agrupan en un elemento con la suma de `duration_seconds`.
    - `t_seg`: segundos desde el primer evento del episodio (no el `ts`).
    """
    ordenados = sorted(events, key=lambda e: e["seq"])
    if not ordenados:
        return []
    inicio = _instante(ordenados[0]["ts"])
    contadores: dict[str, int] = {}
    turno: int | None = None
    elementos: list[dict[str, Any]] = []

    for evento in ordenados:
        if evento["seq"] > seq_tope:
            break
        regla = TIPOS_INCLUIDOS.get(evento["event_type"])
        if regla is None:
            continue
        tipo, permitidas = regla
        payload = evento.get("payload") or {}

        if tipo == "lectura" and elementos and elementos[-1]["tipo"] == "lectura":
            anterior = elementos[-1]["datos"]
            anterior["duration_seconds"] = (anterior["duration_seconds"] or 0) + (
                payload.get("duration_seconds") or 0
            )
            continue

        if tipo == "respuesta_tutor":
            k = turno
        elif tipo in _CON_LOCALIZADOR:
            contadores[tipo] = contadores.get(tipo, 0) + 1
            k = contadores[tipo]
            if tipo == "mensaje_alumno":
                turno = k
        else:
            k = None

        elementos.append(
            {
                "n": len(elementos) + 1,
                "tipo": tipo,
                "k": k,
                "t_seg": round((_instante(evento["ts"]) - inicio).total_seconds(), 3),
                "datos": {clave: payload.get(clave) for clave in permitidas},
            }
        )
    return elementos
