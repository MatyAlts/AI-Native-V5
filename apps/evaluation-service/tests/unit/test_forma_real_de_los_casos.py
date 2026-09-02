"""Ata `_casos_para_el_prompt` al productor REAL de los casos.

POR QUE ESTE ARCHIVO EXISTE
---------------------------
`test_correccion_nativa.py` prueba el corrector con diccionarios armados a mano.
Eso es correcto para la logica —es rapido y no arrastra dependencias— pero deja
una junta sin cubrir: **que la forma del diccionario sea la que el sistema
produce**.

No es una hipotesis. En la revision del PR se encontro que
`_casos_para_el_prompt` leia `name` / `is_public` / `passed` / `expected` /
`got` — las claves del SANDBOX — cuando lo que le llega, via
`ResultadoTests.as_dict()`, son las que `_mapear` traduce: `nombre` / `paso` /
`salida_obtenida` / `es_publico`. Ni una coincidia. El modelo recibia
`{"nombre": null, "paso": null}` por cada caso, y como `bool(None)` es `False`,
todo caso se trataba como oculto.

Y el fixture del otro archivo tenia las claves del sandbox, asi que el test
seguia verde: probaba que los ocultos no filtran sobre una forma que el sistema
nunca produce.

Este archivo importa `ResultadoTests` de verdad. Si `_mapear` cambia la forma de
`casos`, ESTO se cae — en vez de que el corrector deje de ver los hechos en
silencio y le ponga nota a un alumno con la mitad de la evidencia.

Es la tercera vez que este repo se come el mismo modo de falla (ver el docstring
de `_mapear`, y los PRs #86 y #88): logica correcta, tests verdes, y la costura
que la conecta sin cubrir.
"""

from __future__ import annotations

from evaluation_service.services.correccion_nativa import _casos_para_el_prompt
from evaluation_service.services.correccion_pre_ejecucion import ResultadoTests


def _tests_como_los_produce_el_sistema() -> dict:
    """Un `ResultadoTests` armado con la forma exacta que `_mapear` emite.

    Se construye el dataclass REAL y se llama a su `as_dict()` — que es
    literalmente lo que `correccion_ejecutor` le pasa al corrector en
    `tests=tests.as_dict()`.
    """
    return ResultadoTests(
        compila=True,
        total=2,
        passed=1,
        failed=1,
        casos=[
            {
                "id": "c1",
                "nombre": "suma dos positivos",
                "paso": True,
                "salida_obtenida": "5",
                "es_publico": True,
            },
            {
                "id": "c2",
                "nombre": "caso oculto de borde",
                "paso": False,
                "salida_obtenida": "0",
                "es_publico": False,
            },
        ],
    ).as_dict()


class TestLosHechosLleganAlModelo:
    def test_el_nombre_del_caso_llega(self) -> None:
        """Sin el nombre, el modelo no puede citar QUE caso fallo.

        Verificado por reversion: leyendo `caso.get("name")` esto da
        `[None, None]`.
        """
        vistos = _casos_para_el_prompt(_tests_como_los_produce_el_sistema())

        assert [c["nombre"] for c in vistos] == ["suma dos positivos", "caso oculto de borde"]

    def test_si_el_caso_paso_o_no_llega(self) -> None:
        """La regla 4 del prompt: "los resultados de los tests son HECHOS".

        Con `paso: None` en todos, el modelo no tiene un solo hecho por caso —
        solo los conteos agregados del nivel de arriba— y el prompt le esta
        pidiendo que confie en una evidencia que no llego.
        """
        vistos = _casos_para_el_prompt(_tests_como_los_produce_el_sistema())

        assert [c["paso"] for c in vistos] == [True, False]

    def test_la_salida_del_alumno_llega_en_los_dos(self) -> None:
        """Es su codigo, no la solucion. `_mapear` la incluye para todos los
        casos a proposito, y es lo que el modelo necesita para justificar un
        descuento sobre un caso que fallo."""
        vistos = _casos_para_el_prompt(_tests_como_los_produce_el_sistema())

        assert [c["obtenido"] for c in vistos] == ["5", "0"]


class TestElPublicoSeReconoceComoPublico:
    def test_un_caso_publico_no_se_trata_como_oculto(self) -> None:
        """`bool(caso.get("is_public"))` sobre una clave que se llama
        `es_publico` da False SIEMPRE."""
        vistos = _casos_para_el_prompt(_tests_como_los_produce_el_sistema())

        assert vistos[0]["publico"] is True

    def test_un_caso_oculto_sigue_oculto(self) -> None:
        """Arreglar una cosa no puede abrir la otra."""
        vistos = _casos_para_el_prompt(_tests_como_los_produce_el_sistema())

        assert vistos[1]["publico"] is False

    def test_un_caso_sin_la_marca_se_considera_publico(self) -> None:
        """Mismo criterio que `_mapear` (`is not False`), y no al reves.

        Que las dos capas discrepen sobre el caso ausente es como se llega a
        que una proteja algo que la otra ya dejo pasar. Es seguro porque lo
        unico que la marca gatea es la salida ESPERADA, y `_mapear` no la
        emite.
        """
        vistos = _casos_para_el_prompt({"casos": [{"nombre": "x", "paso": True}]})

        assert vistos[0]["publico"] is True


class TestLaSolucionDelOcultoNoViaja:
    def test_el_esperado_de_un_oculto_se_excluye(self) -> None:
        """El guard, ejercitado contra un dato que EXISTE.

        `_mapear` no emite `salida_esperada` hoy, asi que el guard no filtra
        nada real. Se conserva —y se prueba con el campo puesto a mano— para
        que el dia que alguien la agregue aguas arriba no entre por aca sin que
        nadie lo note.
        """
        tests = {
            "casos": [
                {
                    "nombre": "oculto",
                    "paso": False,
                    "salida_obtenida": "x",
                    "es_publico": False,
                    "salida_esperada": "LA-SOLUCION",
                }
            ]
        }

        vistos = _casos_para_el_prompt(tests)

        assert "esperado" not in vistos[0]


class TestBordes:
    def test_sin_casos_no_explota(self) -> None:
        """Una TP monolitica, o un ejercicio sin casos cargados."""
        assert _casos_para_el_prompt({"casos": []}) == []
        assert _casos_para_el_prompt({}) == []

    def test_una_entrada_que_no_es_dict_se_saltea(self) -> None:
        """Basura en el JSONB no puede tumbar una correccion entera."""
        vistos = _casos_para_el_prompt({"casos": ["basura", None, {"nombre": "ok", "paso": True}]})

        assert len(vistos) == 1
        assert vistos[0]["nombre"] == "ok"
