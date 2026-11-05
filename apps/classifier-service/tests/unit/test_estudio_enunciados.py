"""Enunciados cargados a mano: parseo del CSV, cobertura y alertas
(tarea 7.0 más A4-2 del plan-reviewer, design D14).

CSVs sintéticos escritos en el test; ningún texto real de TP ni de ejercicio.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from classifier_service.services.estudio_enunciados import (
    alertas_enunciado,
    cobertura,
    parsear_enunciados_csv,
    sha256_texto,
)

TP = UUID("11111111-1111-4111-8111-111111111111")
TP2 = UUID("22222222-2222-4222-8222-222222222222")
EJ = UUID("33333333-3333-4333-8333-333333333333")
ENCABEZADO = "tipo,tp_id,ejercicio_id,enunciado"


def _csv(*filas: str) -> str:
    return "\n".join([ENCABEZADO, *filas]) + "\n"


# ── parseo ────────────────────────────────────────────────────────────────


def test_csv_valido_con_texto_multilinea_entre_comillas() -> None:
    texto = _csv(
        f'tp,{TP},,"Consigna\nen dos lineas, con coma y ""comillas"""',
        f"ejercicio,,{EJ},Sumar pares",
        f'ejercicio,{TP},{UUID(int=EJ.int + 1)},"Otro ejercicio"',
    )
    filas, errores = parsear_enunciados_csv(texto)
    assert errores == []
    assert [(f.fuente, f.fuente_id, f.texto) for f in filas] == [
        ("tp", TP, 'Consigna\nen dos lineas, con coma y "comillas"'),
        ("ejercicio", EJ, "Sumar pares"),
        ("ejercicio", UUID(int=EJ.int + 1), "Otro ejercicio"),
    ]


def test_crlf_y_bom_se_aceptan() -> None:
    filas, errores = parsear_enunciados_csv("﻿" + ENCABEZADO + "\r\n" + f"tp,{TP},,Hola\r\n")
    assert errores == []
    assert [(f.fuente, f.fuente_id, f.texto) for f in filas] == [("tp", TP, "Hola")]


@pytest.mark.parametrize(
    ("texto", "fragmento"),
    [
        ("tipo,tp,ejercicio,enunciado\n", "encabezado"),
        ("", "encabezado"),
        (_csv(f"tarea,{TP},,x"), "fila 2"),
        (_csv("tp,no-es-uuid,,x"), "fila 2"),
        (_csv(f"tp,,{EJ},x"), "fila 2"),
        (_csv(f"ejercicio,{TP},,x"), "fila 2"),
        (_csv(f"ejercicio,no-uuid,{EJ},x"), "fila 2"),
        (_csv(f"tp,{TP},,x", f"tp,{TP},,y"), "fila 3"),
        (_csv(f"tp,{TP},,   "), "fila 2"),
        (_csv(f"tp,{TP},,x,columna-de-mas"), "fila 2"),
    ],
)
def test_csv_invalido_informa_la_fila(texto: str, fragmento: str) -> None:
    filas, errores = parsear_enunciados_csv(texto)
    assert filas == []
    assert errores
    assert any(fragmento in e for e in errores), errores


def test_duplicado_por_tipo_e_id_aunque_cambie_el_texto() -> None:
    _, errores = parsear_enunciados_csv(_csv(f"ejercicio,,{EJ},a", f"ejercicio,{TP},{EJ},b"))
    assert errores == ["fila 3: (ejercicio, " + str(EJ) + ") repetido"]


def test_mismo_id_con_distinto_tipo_no_es_duplicado() -> None:
    filas, errores = parsear_enunciados_csv(_csv(f"tp,{TP},,a", f"ejercicio,,{TP},b"))
    assert errores == []
    assert len(filas) == 2


def test_sha256_utf8_literal() -> None:
    texto = "Implementá una función que sume los números pares. ñandú"
    assert sha256_texto(texto) == "bcee7b620fea264497a2d3bd1c1a6b6d809f8db54b64776d828287cf1c2978a0"


# ── cobertura ─────────────────────────────────────────────────────────────


def test_cobertura_con_faltante_y_sin_revisar() -> None:
    requeridos = {("tp", TP): ["i1", "i2"], ("ejercicio", EJ): ["i2"], ("tp", TP2): ["i3"]}
    resultado = cobertura(requeridos, cargados={("tp", TP), ("tp", TP2)}, revisados={("tp", TP)})
    assert resultado == {
        "requeridos": 3,
        "cargados": 2,
        "revisados": 1,
        "faltantes": [{"tipo": "ejercicio", "id": str(EJ), "items_afectados": 1}],
        "sin_revisar": [{"tipo": "tp", "id": str(TP2), "items_afectados": 1}],
    }


def test_cobertura_ignora_cargados_sin_uso() -> None:
    resultado = cobertura({("tp", TP): ["i1"]}, cargados={("tp", TP), ("tp", TP2)}, revisados=set())
    assert (resultado.get("requeridos"), resultado.get("cargados"), resultado.get("faltantes")) == (
        1,
        1,
        [],
    )


# ── alertas ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("texto", "alerta"),
    [
        ("Entregar antes del 12/05/2026.", "fecha"),
        ("La clase del 5 de mayo vemos esto.", "fecha"),
        ("Dudas a docente@utn.edu.ar", "email"),
        ("Consultar con Prof. Pérez", "docente"),
        ("Como explicó la profesora Gómez", "docente"),
        ("Solo para Comisión 2", "comision"),
        ("Com. B entrega aparte", "comision"),
        ("Consultas a las 18:30", "horario"),
        ("Se evalúa con la rúbrica adjunta", "rubrica"),
        ("Criterios de evaluación: legibilidad", "rubrica"),
        ("Caso de prueba: entrada 3, salida 6", "tests"),
        ("Hay un test oculto que verifica bordes", "tests"),
        ("assert suma([1,2]) == 3", "tests"),
        ("Salida esperada: 42", "tests"),
        ("Pista: usá un acumulador", "pista"),
        ("La solución es recorrer la lista", "solucion"),
    ],
)
def test_alertas_por_patron(texto: str, alerta: str) -> None:
    assert alerta in alertas_enunciado(texto)


def test_texto_limpio_no_tiene_alertas() -> None:
    texto = "Escribí una función que reciba una lista de enteros y devuelva la suma de los pares."
    assert alertas_enunciado(texto) == []


def test_alertas_sin_repetir_y_en_orden_estable() -> None:
    texto = "Prof. Pérez y Prof. Gómez, 12/05/2026 y 13/05/2026"
    assert alertas_enunciado(texto) == ["fecha", "docente"]
