"""Exportación del estudio para análisis (design D12). Funciones PURAS.

- `columnas_respuesta(extra, dims)`: columnas fijas del registro + una pareja
  `dim_<clave>_valor`/`dim_<clave>_cita` por dimensión del ESQUEMA (no del
  código) + régimen, régimen de la regla, propuesto, desacuerdo derivado,
  frontera, confianza y notas.
- `aplanar_respuesta`: una fila JSON-serializable (str, int, bool o None).
- `a_csv`: CSV con las mismas filas y valores que el JSON. Una celda de texto
  que empieza con `=`, `+`, `-`, `@`, tabulador o retorno de carro se prefija
  con `'` (inyección de fórmulas en planillas). `None` -> celda vacía; bool ->
  `true`/`false`.
"""

from __future__ import annotations

import csv
import io
from typing import Any

PELIGROSOS = ("=", "+", "-", "@", "\t", "\r")
_RESPUESTA = (
    "regimen",
    "regimen_regla",
    "regimen_propuesto",
    "disiente_de_regla",
    "es_frontera",
    "confianza",
    "notas",
)


def columnas_respuesta(
    extra: list[str], dims: list[str], despues: list[str] | None = None
) -> list[str]:
    columnas = list(extra)
    for dim in dims:
        columnas += [f"dim_{dim}_valor", f"dim_{dim}_cita"]
    return columnas + list(_RESPUESTA) + list(despues or [])


def aplanar_respuesta(
    extra: list[str], dims: list[str], registro: dict[str, Any], despues: list[str] | None = None
) -> dict[str, Any]:
    fila: dict[str, Any] = {c: registro.get(c) for c in extra}
    respuestas = registro.get("respuestas") or {}
    for dim in dims:
        respuesta = respuestas.get(dim) or {}
        fila[f"dim_{dim}_valor"] = respuesta.get("valor")
        fila[f"dim_{dim}_cita"] = respuesta.get("cita")
    propuesto = registro.get("regimen_propuesto")
    fila.update(
        {
            "regimen": registro.get("regimen"),
            "regimen_regla": registro.get("regimen_regla"),
            "regimen_propuesto": propuesto,
            "disiente_de_regla": propuesto is not None and propuesto != registro.get("regimen"),
            "es_frontera": bool(registro.get("es_frontera")),
            "confianza": registro.get("confianza"),
            "notas": registro.get("notas"),
        }
    )
    for c in despues or []:
        fila[c] = registro.get(c)
    return fila


def celda_csv(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    texto = str(valor)
    if isinstance(valor, str) and texto.startswith(PELIGROSOS):
        return "'" + texto
    return texto


def a_csv(columnas: list[str], filas: list[dict[str, Any]]) -> str:
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida, lineterminator="\n")
    escritor.writerow(columnas)
    for fila in filas:
        escritor.writerow([celda_csv(fila.get(c)) for c in columnas])
    return salida.getvalue()
