"""Orden por codificador reproducible (tarea 7.2, design D7).

Los órdenes literales se calcularon FUERA de la implementación, con
`printf '%s' "<semilla>:<item_id>" | sha256sum` y `sort` del hex, para la
semilla 12345 y para 9007199254740993 (mayor que 2^53: una implementación que
pase la semilla por float la escribiría mal).
"""

from __future__ import annotations

from uuid import UUID

from classifier_service.services.estudio_orden import orden_codificador

A = "0f3c2d1e-5b6a-4c7d-8e9f-a0b1c2d3e4f5"
B = "7a8b9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c0d"
C = "c1d2e3f4-a5b6-4c7d-9e8f-0a1b2c3d4e5f"
D = "3e4f5a6b-7c8d-4e9f-a0b1-c2d3e4f5a6b7"


def test_orden_literal_semilla_12345() -> None:
    assert orden_codificador(12345, [A, B, C, D]) == [(B, 1), (C, 2), (D, 3), (A, 4)]


def test_orden_literal_semilla_mayor_que_2_a_la_53() -> None:
    assert orden_codificador(9007199254740993, [A, B, C, D]) == [(C, 1), (D, 2), (B, 3), (A, 4)]


def test_item_id_en_mayusculas_o_como_uuid_se_normaliza() -> None:
    entrada = [A.upper(), UUID(B), C, D.upper()]
    assert orden_codificador(12345, entrada) == [(B, 1), (C, 2), (D, 3), (A, 4)]


def test_el_orden_de_entrada_no_importa() -> None:
    assert orden_codificador(12345, [D, C, B, A]) == orden_codificador(12345, [A, B, C, D])


def test_lista_vacia() -> None:
    assert orden_codificador(1, []) == []
