"""Enunciados cargados a mano por el investigador (design D14). Funciones PURAS.

- `parsear_enunciados_csv`: CSV `tipo,tp_id,ejercicio_id,enunciado` exportado
  de la consola de Postgres. Todo o nada: con un error, no se devuelve ninguna
  fila. Acepta BOM y CRLF; el texto puede tener comas, comillas y saltos de
  línea entre comillas (CSV estándar).
- `cobertura`: requeridos por la muestra y las anclas contra lo cargado y lo
  revisado.
- `alertas_enunciado`: marcas para la revisión obligatoria del investigador.
  No reemplazan esa revisión: detectan señales de identidad (fechas, emails,
  docentes, comisiones, horarios) y de material que el codificador no debe ver
  (rúbrica, tests, pistas, soluciones; A4-2 del plan-reviewer).
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

ENCABEZADO = ["tipo", "tp_id", "ejercicio_id", "enunciado"]
FUENTES = ("tp", "ejercicio")


@dataclass(frozen=True)
class FilaEnunciado:
    fuente: str
    fuente_id: UUID
    texto: str


def sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _uuid(valor: str) -> UUID | None:
    try:
        return UUID(valor.strip())
    except ValueError:
        return None


def _validar_fila(numero: int, celdas: list[str]) -> tuple[FilaEnunciado | None, str | None]:
    if len(celdas) != len(ENCABEZADO):
        return None, f"fila {numero}: se esperaban {len(ENCABEZADO)} columnas"
    tipo, tp_id, ejercicio_id, texto = (c if i == 3 else c.strip() for i, c in enumerate(celdas))
    if tipo not in FUENTES:
        return None, f"fila {numero}: tipo desconocido"
    if not texto.strip():
        return None, f"fila {numero}: enunciado vacío"
    if tipo == "tp":
        fuente_id = _uuid(tp_id)
        if fuente_id is None or ejercicio_id:
            return None, f"fila {numero}: una fila 'tp' lleva tp_id UUID y ejercicio_id vacío"
    else:
        fuente_id = _uuid(ejercicio_id)
        if fuente_id is None or (tp_id and _uuid(tp_id) is None):
            return None, f"fila {numero}: una fila 'ejercicio' lleva ejercicio_id UUID"
    return FilaEnunciado(tipo, fuente_id, texto), None


def parsear_enunciados_csv(texto: str) -> tuple[list[FilaEnunciado], list[str]]:
    lector = csv.reader(io.StringIO(texto.removeprefix("﻿"), newline=""))
    encabezado = next(lector, None)
    if encabezado is None or [c.strip() for c in encabezado] != ENCABEZADO:
        return [], [f"encabezado: se esperaba {','.join(ENCABEZADO)}"]
    filas: list[FilaEnunciado] = []
    errores: list[str] = []
    vistos: set[tuple[str, UUID]] = set()
    for numero, celdas in enumerate(lector, start=2):
        if not celdas:
            continue
        fila, error = _validar_fila(numero, celdas)
        if error:
            errores.append(error)
            continue
        assert fila is not None
        clave = (fila.fuente, fila.fuente_id)
        if clave in vistos:
            errores.append(f"fila {numero}: ({fila.fuente}, {fila.fuente_id}) repetido")
            continue
        vistos.add(clave)
        filas.append(fila)
    if errores:
        return [], errores
    return filas, []


def _detalle(
    claves: Iterable[tuple[str, UUID]], requeridos: Mapping[Any, Sequence[Any]]
) -> list[dict[str, Any]]:
    return [
        {"tipo": tipo, "id": str(fuente_id), "items_afectados": len(requeridos[(tipo, fuente_id)])}
        for tipo, fuente_id in sorted(claves, key=lambda c: (c[0], str(c[1])))
    ]


def cobertura(
    requeridos: Mapping[tuple[str, UUID], Sequence[Any]],
    cargados: set[tuple[str, UUID]],
    revisados: set[tuple[str, UUID]],
) -> dict[str, Any]:
    """`requeridos`: `(fuente, id) -> ítems que lo usan`. Lo cargado sin uso no cuenta."""
    claves = set(requeridos)
    cargados_req = claves & cargados
    revisados_req = claves & revisados & cargados
    return {
        "requeridos": len(claves),
        "cargados": len(cargados_req),
        "revisados": len(revisados_req),
        "faltantes": _detalle(claves - cargados_req, requeridos),
        "sin_revisar": _detalle(cargados_req - revisados_req, requeridos),
    }


_MESES = "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre"
_NOMBRE = r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+"

# (alerta, patrones). Orden estable: es el orden en que se devuelven.
_PATRONES: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "fecha",
        (
            re.compile(r"\b\d{1,2}/\d{1,2}(/\d{2,4})?\b"),
            re.compile(rf"\b\d{{1,2}}\s+de\s+({_MESES})\b", re.IGNORECASE),
        ),
    ),
    ("email", (re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+"),)),
    (
        "docente",
        (
            re.compile(rf"\bProf\.\s*{_NOMBRE}"),
            re.compile(rf"\b(?:[Pp]rofesor(?:a)?|[Dd]ocente)\s+{_NOMBRE}"),
        ),
    ),
    ("comision", (re.compile(r"\b(?:[Cc]omisi[oó]n|[Cc]om\.)\s*(?:\d+|[A-Z])\b"),)),
    ("horario", (re.compile(r"\b\d{1,2}:\d{2}\b"),)),
    ("rubrica", (re.compile(r"\br[uú]brica|\bcriterios?\s+de\s+evaluaci[oó]n", re.IGNORECASE),)),
    (
        "tests",
        (
            re.compile(
                r"\bcasos?\s+de\s+prueba|\btests?\s+ocultos?|\bsalida\s+esperada", re.IGNORECASE
            ),
            re.compile(r"\bassert\b"),
        ),
    ),
    ("pista", (re.compile(r"\bpistas?\b", re.IGNORECASE),)),
    ("solucion", (re.compile(r"\bsoluci[oó]n(?:es)?\b", re.IGNORECASE),)),
)


def alertas_enunciado(texto: str) -> list[str]:
    return [alerta for alerta, patrones in _PATRONES if any(p.search(texto) for p in patrones)]
