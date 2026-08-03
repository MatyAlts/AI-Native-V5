"""Tests de la habilitación progresiva y el apagado (tareas 9.2 y 9.3)."""

from __future__ import annotations

from execution_service.config import Settings

COMISION_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
COMISION_B = "bbbb0002-bbbb-bbbb-bbbb-bbbbbbbb0002"


# `execution_enabled=True` va EXPLICITO en los tests de la lista de comisiones.
# Antes se heredaba del default, y cuando el default paso a `false` (falla
# cerrado, 2026-08-03) estos tres se cayeron sin que la logica de la lista
# hubiera cambiado: probaban el interruptor sin querer. Declarar la precondicion
# los deja midiendo una sola cosa.


def test_sin_lista_configurada_todas_pueden() -> None:
    """Con el interruptor puesto, la lista vacia no bloquea a nadie."""
    s = Settings(execution_enabled=True, execution_enabled_comisiones="")
    assert s.comision_habilitada(COMISION_A) is True
    assert s.comision_habilitada(None) is True


def test_con_lista_solo_las_declaradas() -> None:
    """Tarea 9.3 — se habilita para UNA comision antes que para todas."""
    s = Settings(execution_enabled=True, execution_enabled_comisiones=COMISION_A)
    assert s.comision_habilitada(COMISION_A) is True
    assert s.comision_habilitada(COMISION_B) is False


def test_la_lista_admite_varias_y_tolera_espacios() -> None:
    s = Settings(
        execution_enabled=True, execution_enabled_comisiones=f"{COMISION_A} , {COMISION_B}"
    )
    assert s.comision_habilitada(COMISION_A) is True
    assert s.comision_habilitada(COMISION_B) is True


def test_el_default_falla_cerrado() -> None:
    """Candado del arreglo: sin tocar nada, NO se ejecuta.

    Es la propiedad que el PR #57 tenia invertida — el unico flag del ADR-060
    que fallaba abierto. Un deploy que no configure la variable deja la
    ejecucion apagada, no prendida para el piloto entero.
    """
    s = Settings()
    assert s.execution_enabled is False
    assert s.comision_habilitada(COMISION_A) is False
    assert s.comision_habilitada(None) is False


def test_con_lista_una_request_sin_comision_no_pasa() -> None:
    """Si hay lista, no declarar comision no es un permiso implicito."""
    s = Settings(execution_enabled_comisiones=COMISION_A)
    assert s.comision_habilitada(None) is False


def test_el_interruptor_general_apaga_todo() -> None:
    """Tarea 9.2 — el procedimiento de apagado.

    Con `execution_enabled=false` el servicio rechaza toda ejecucion y el editor
    vuelve solo al estado "ejecucion no disponible", sin desplegar nada. Los
    episodios en curso NO se rompen: ejecutar es un agregado, el alumno sigue
    con el enunciado y el tutor.
    """
    s = Settings(execution_enabled=False, execution_enabled_comisiones=COMISION_A)
    assert s.comision_habilitada(COMISION_A) is False, "el interruptor gana sobre la lista"
    assert s.comision_habilitada(None) is False
