"""Muestra fija y anclas: parseo del CSV, episodio terminado y evidencia fija
(design D4b, D6, D14). Funciones PURAS sobre el dict crudo del CTR.
"""

from __future__ import annotations

import csv
import io
from typing import Any
from uuid import UUID

_CIERRES = ("episodio_cerrado", "episodio_abandonado")


def parsear_muestra_csv(texto: str) -> tuple[list[UUID], list[str]]:
    """Solo la columna `episode_id`; el resto se descarta sin leerse.

    Errores con número de fila (la primera de datos es la 2): UUID inválido o
    repetido; sin columna `episode_id`; muestra vacía."""
    lector = csv.DictReader(io.StringIO(texto.removeprefix("﻿"), newline=""))
    campos = [c.strip() for c in (lector.fieldnames or [])]
    if "episode_id" not in campos:
        return [], ["encabezado: falta la columna episode_id"]
    columna = (lector.fieldnames or [])[campos.index("episode_id")]
    episodios: list[UUID] = []
    errores: list[str] = []
    vistos: set[UUID] = set()
    for numero, fila in enumerate(lector, start=2):
        valor = (fila.get(columna) or "").strip()
        try:
            episodio = UUID(valor)
        except ValueError:
            errores.append(f"fila {numero}: episode_id no es UUID")
            continue
        if episodio in vistos:
            errores.append(f"fila {numero}: episode_id repetido")
            continue
        vistos.add(episodio)
        episodios.append(episodio)
    if not errores and not episodios:
        errores.append("muestra vacía")
    return ([], errores) if errores else (episodios, [])


def motivo_rechazo(episodio: dict[str, Any]) -> str | None:
    """None si el episodio está TERMINADO (D6); si no, el motivo.

    Terminado: `closed`, o `paused` cuyo último evento de cierre es
    `episodio_abandonado` (abandonado y no retomado: retomar lo vuelve `open`).
    Se rechazan `open`, `paused` sin abandono y los marcados con integridad
    comprometida (default confirmado por el humano, pregunta 5)."""
    if episodio.get("integrity_compromised"):
        return "integridad comprometida"
    eventos = sorted(episodio.get("events") or [], key=lambda e: e["seq"])
    if not eventos:
        return "sin eventos"
    estado = episodio.get("estado")
    if estado == "closed":
        return None
    if estado == "paused":
        cierres = [e["event_type"] for e in eventos if e["event_type"] in _CIERRES]
        if cierres and cierres[-1] == "episodio_abandonado":
            return None
        return "pausado sin abandono"
    return "no terminado"


def evidencia_fija(episodio: dict[str, Any]) -> dict[str, Any]:
    """Columnas de evidencia fija y de enunciado para `estudio_muestra`/`estudio_ancla`."""
    eventos = sorted(episodio["events"], key=lambda e: e["seq"])
    tope = eventos[-1]
    apertura = next((e for e in eventos if e["event_type"] == "episodio_abierto"), None)
    ejercicio = (apertura or {}).get("payload", {}).get("ejercicio_id")
    return {
        "seq_tope": tope["seq"],
        "chain_hash_tope": tope["chain_hash"],
        "events_count_carga": episodio["events_count"],
        "last_chain_hash_carga": episodio["last_chain_hash"],
        "estado_carga": episodio["estado"],
        "problema_id": UUID(str(episodio["problema_id"])),
        "ejercicio_id": UUID(str(ejercicio)) if ejercicio else None,
    }
