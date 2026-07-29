"""Tests de la habilitación progresiva y el apagado (tareas 9.2 y 9.3)."""

from __future__ import annotations

from execution_service.config import Settings

COMISION_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
COMISION_B = "bbbb0002-bbbb-bbbb-bbbb-bbbbbbbb0002"


def test_sin_lista_configurada_todas_pueden() -> None:
    """El default no bloquea a nadie: la lista es para la puesta en produccion."""
    s = Settings(execution_enabled_comisiones="")
    assert s.comision_habilitada(COMISION_A) is True
    assert s.comision_habilitada(None) is True


def test_con_lista_solo_las_declaradas() -> None:
    """Tarea 9.3 — se habilita para UNA comision antes que para todas."""
    s = Settings(execution_enabled_comisiones=COMISION_A)
    assert s.comision_habilitada(COMISION_A) is True
    assert s.comision_habilitada(COMISION_B) is False


def test_la_lista_admite_varias_y_tolera_espacios() -> None:
    s = Settings(execution_enabled_comisiones=f"{COMISION_A} , {COMISION_B}")
    assert s.comision_habilitada(COMISION_A) is True
    assert s.comision_habilitada(COMISION_B) is True


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
