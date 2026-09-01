"""El detector de entregas fantasma, sobre todo su falso positivo mas caro.

`all([])` es True en Python. Sin el guard de lista vacia, `es_fantasma` marca
como atrapada a TODA entrega recien creada — que son la mayoria — y el informe
deja de servir para lo unico que tiene que hacer: decir quien esta trabado.

Un informe con 400 filas de las cuales 3 importan es peor que no tener informe:
nadie lo lee dos veces.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

# El script vive en `scripts/`, que no es un paquete importable. Se carga por
# path para poder testear la funcion pura sin tocar la base ni el CLI.
_RUTA = Path(__file__).resolve().parents[4] / "scripts" / "entregas-fantasma.py"
_spec = importlib.util.spec_from_file_location("entregas_fantasma", _RUTA)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules["entregas_fantasma"] = _mod
_spec.loader.exec_module(_mod)

es_fantasma = _mod.es_fantasma


def _ej(orden: int, completado: bool) -> dict[str, Any]:
    return {"orden": orden, "completado": completado, "ejercicio_id": None, "episode_id": None}


class TestElFalsoPositivoDeAllVacio:
    def test_lista_vacia_NO_es_fantasma(self) -> None:
        """El corazon del guard.

        Verificado por reversion: sin el `if not estados`, `all([])` devuelve
        True y toda entrega recien creada entra al informe.
        """
        assert es_fantasma([]) is False

    def test_none_NO_es_fantasma(self) -> None:
        """Una TP monolitica puede tener `ejercicio_estados` en NULL."""
        assert es_fantasma(None) is False


class TestDetecta:
    def test_todos_completados_SI_es_fantasma(self) -> None:
        assert es_fantasma([_ej(1, True), _ej(2, True), _ej(3, True)]) is True

    def test_uno_solo_completado_tambien(self) -> None:
        """Una TP de un ejercicio es igual de atrapable."""
        assert es_fantasma([_ej(1, True)]) is True


class TestNoDetectaLoQueNoEs:
    def test_uno_incompleto_NO(self) -> None:
        """Todavia tiene un boton con el que seguir: no esta atrapado."""
        assert es_fantasma([_ej(1, True), _ej(2, False)]) is False

    def test_ninguno_completado_NO(self) -> None:
        assert es_fantasma([_ej(1, False), _ej(2, False)]) is False

    @pytest.mark.parametrize("valor", [None, 0, "", "false"])
    def test_un_completado_falsy_cuenta_como_incompleto(self, valor: object) -> None:
        """Un estado guardado por una version vieja puede no tener la clave.

        Tratarlo como completado marcaria atrapado a alguien que no lo esta, y
        `--destrabar` le des-marcaria ejercicios que si habia terminado.
        """
        assert es_fantasma([{"orden": 1, "completado": valor}]) is False
