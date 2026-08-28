"""La nota de Active-IA: un solo campo, y viaja como string.

Confirmado por ellos el 2026-08-27, respondiendo al §4.2 de nuestro documento:

> Es `nota`. Bajen la cascada y dejen ese solo. No existe ni `nota_100`, ni
> `nota_final`, ni `calificacion`.

Y un detalle que no habiamos preguntado y nos avisaron:

> `nota` viaja como string JSON, no como numero: `"85.50"`, con comillas. Es el
> default de Pydantic v2 para Decimal y lo dejamos a proposito: una nota no
> deberia pasar por un float en ningun tramo del camino.

Por que estos tests existen y no alcanza con que "ande": `float("85.50")`
funciona. Un parser que no castea explicito anda por accidente durante meses y
se rompe el dia que alguien agrega una comparacion de tipos o un `if not nota`.
Es el MISMO mecanismo silencioso por el que `salida_obtenida` se perdia del lado
de ellos sin un solo error — Pydantic descartaba el campo desconocido sin
excepcion, sin log y sin validacion fallida.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from evaluation_service.services.correccion_ejecutor import _corregir_ejercicio

TESTS_OK = {"compila": True, "passed": 1, "total": 1}


class _Cliente:
    def __init__(self, cuerpo: dict) -> None:
        self._cuerpo = cuerpo

    async def corregir_ejercicio(self, **kw: object) -> tuple[int, dict]:
        return 200, self._cuerpo


async def _correr(cuerpo: dict) -> dict:
    return await _corregir_ejercicio(
        cliente=_Cliente(cuerpo),
        ejercicio_ref="EJ-1",
        alumno_nombre="pseudo",
        codigo="x",
        tests=TESTS_OK,
    )


class TestLaNotaLlegaComoString:
    async def test_el_string_con_comillas_se_castea(self) -> None:
        """La forma exacta que documentaron: `{"nota": "85.50"}`."""
        r = await _correr({"correccion_id": 10, "nota": "85.50", "criterios": []})

        assert r.get("error_code") is None, r
        assert r["nota_100"] == Decimal("85.50")

    async def test_no_pasa_por_float(self) -> None:
        """Un decimal que un float no representa exacto.

        Si el casteo fuera `float(...)`, esto daria 8.324999999999999 y la nota
        del alumno quedaria con un digito de mas en la base.
        """
        r = await _correr({"nota": "8.325"})

        assert r["nota_100"] == Decimal("8.325")
        assert str(r["nota_100"]) == "8.325"

    async def test_un_cero_es_una_nota(self) -> None:
        """El alumno que entrega el template vacio saca 0, y eso NO es un fallo.

        Ya paso una vez con `or`: el cero falsy caia a `SIN_NOTA`, que esta en
        el set de infraestructura, la UI ofrecia "Reintentar" y cada intento
        pagaba una corrida de Gemini sobre una correccion que termino bien.
        """
        r = await _correr({"nota": "0.00"})

        assert r.get("error_code") is None, r
        assert r["nota_100"] == Decimal("0.00")

    async def test_tambien_si_llega_como_numero(self) -> None:
        """Hoy mandan string, pero ofrecieron cambiarlo. El casteo aguanta las dos."""
        r = await _correr({"nota": 85.5})

        assert r["nota_100"] == Decimal("85.5")


class TestLaCascadaSeBajo:
    @pytest.mark.parametrize("clave", ["nota_100", "nota_final", "calificacion"])
    async def test_los_tres_nombres_viejos_ya_no_se_leen(self, clave: str) -> None:
        """Ellos confirmaron que NINGUNO de los tres existe.

        Que se sigan leyendo no es inofensivo: si algun dia mandan uno de esos
        con otro significado, lo tomariamos por nota. La cascada funciona hasta
        el dia que devuelve el campo equivocado.
        """
        r = await _correr({clave: "85.50"})

        assert r["error_code"] == "SIN_NOTA"
        assert "nota_100" not in r


class TestUnaNotaIlegibleNoEsUnaNota:
    @pytest.mark.parametrize("basura", ["", "ochenta", "N/A", "8,5"])
    async def test_no_se_escribe_basura_en_la_fila(self, basura: str) -> None:
        """Cae a `SIN_NOTA` —infraestructura, reintentable— en vez de reventar
        despues contra el CHECK de la base."""
        r = await _correr({"nota": basura})

        assert r["error_code"] == "SIN_NOTA"
        assert "nota_100" not in r
