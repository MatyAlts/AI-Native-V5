"""Aplanado de la exportación y CSV seguro (tarea 10.1, design D12, spec exportación)."""

from __future__ import annotations

import csv
import io

import pytest
from classifier_service.services.estudio_export import (
    a_csv,
    aplanar_respuesta,
    columnas_respuesta,
)

DIMS = ["d1", "d2", "d4"]


def _registro(**cambios) -> dict:
    base = {
        "episode_id": "00000000-0000-4000-8000-000000000001",
        "item_id": "00000000-0000-4000-8000-0000000000aa",
        "alias": "C1",
        "membresia_id": "00000000-0000-4000-8000-0000000000bb",
        "respuestas": {
            "d1": {"valor": "presente", "cita": "turno 1"},
            "d4": {"valor": "interlocutor", "cita": None},
        },
        "regimen": "evidencia_insuficiente",
        "regimen_regla": "reflexiva",
        "regimen_propuesto": None,
        "es_frontera": False,
        "confianza": None,
        "notas": "traza corta",
    }
    base.update(cambios)
    return base


EXTRA = ["episode_id", "item_id", "alias", "membresia_id"]


def test_columnas_de_dimensiones_derivadas_del_esquema() -> None:
    columnas = columnas_respuesta(EXTRA, DIMS)
    assert columnas[:4] == EXTRA
    assert [c for c in columnas if c.startswith("dim_")] == [
        "dim_d1_valor",
        "dim_d1_cita",
        "dim_d2_valor",
        "dim_d2_cita",
        "dim_d4_valor",
        "dim_d4_cita",
    ]
    for c in (
        "regimen",
        "regimen_regla",
        "regimen_propuesto",
        "disiente_de_regla",
        "es_frontera",
        "confianza",
        "notas",
    ):
        assert c in columnas
    assert not [c for c in columnas if "email" in c]


def test_fila_exenta_conserva_regimen_regla_distinto() -> None:
    fila = aplanar_respuesta(EXTRA, DIMS, _registro())
    assert (fila.get("regimen"), fila.get("regimen_regla"), fila.get("disiente_de_regla")) == (
        "evidencia_insuficiente",
        "reflexiva",
        False,
    )
    assert (
        fila.get("dim_d1_valor"),
        fila.get("dim_d1_cita"),
        fila.get("dim_d2_valor"),
        fila.get("dim_d2_cita"),
    ) == (
        "presente",
        "turno 1",
        None,
        None,
    )


def test_disiente_derivado_del_propuesto() -> None:
    fila = aplanar_respuesta(
        EXTRA, DIMS, _registro(regimen="reflexiva", regimen_propuesto="superficial")
    )
    assert fila.get("disiente_de_regla") is True


@pytest.mark.parametrize(
    "peligroso", ['=HYPERLINK("x")', "+1", "-1+2", "@SUMA(A1)", "\tcmd", "\rcmd"]
)
def test_csv_prefija_las_celdas_que_parecen_formula(peligroso: str) -> None:
    columnas = columnas_respuesta(EXTRA, DIMS)
    texto = a_csv(columnas, [aplanar_respuesta(EXTRA, DIMS, _registro(notas=peligroso))])
    filas = list(csv.DictReader(io.StringIO(texto, newline="")))
    assert [f.get("notas") for f in filas] == ["'" + peligroso]


def test_celdas_vacias_y_booleanos() -> None:
    columnas = columnas_respuesta(EXTRA, DIMS)
    filas = list(
        csv.DictReader(
            io.StringIO(a_csv(columnas, [aplanar_respuesta(EXTRA, DIMS, _registro())]), newline="")
        )
    )
    assert [
        (
            f.get("dim_d2_valor"),
            f.get("confianza"),
            f.get("es_frontera"),
            f.get("disiente_de_regla"),
        )
        for f in filas
    ] == [("", "", "false", "false")]


def test_estudio_vacio_solo_encabezado() -> None:
    columnas = columnas_respuesta(EXTRA, DIMS)
    texto = a_csv(columnas, [])
    assert texto.splitlines() == [",".join(columnas)]


def test_csv_y_json_tienen_las_mismas_filas_y_valores() -> None:
    columnas = columnas_respuesta(EXTRA, DIMS)
    filas = [
        aplanar_respuesta(EXTRA, DIMS, _registro()),
        aplanar_respuesta(
            EXTRA,
            DIMS,
            _registro(alias="C2", notas='=HYPERLINK("a")', es_frontera=True, confianza="alta"),
        ),
    ]
    leidas = list(csv.DictReader(io.StringIO(a_csv(columnas, filas), newline="")))
    assert len(leidas) == len(filas)

    def como_csv(valor):
        if valor is None:
            return ""
        if isinstance(valor, bool):
            return "true" if valor else "false"
        texto = str(valor)
        return "'" + texto if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto

    for json_fila, csv_fila in zip(filas, leidas, strict=True):
        assert list(csv_fila) == columnas
        assert {c: como_csv(json_fila[c]) for c in columnas} == csv_fila


def test_propuesto_igual_al_regimen_no_disiente() -> None:
    fila = aplanar_respuesta(
        EXTRA, DIMS, _registro(regimen="reflexiva", regimen_propuesto="reflexiva")
    )
    assert fila.get("disiente_de_regla") is False
