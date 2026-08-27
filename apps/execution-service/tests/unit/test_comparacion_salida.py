"""JAVA-1 - comparacion de la salida del alumno, lado servidor.

La tabla de casos NO vive aca: vive en ``tests/fixtures/paridad-salida.json``,
en la raiz del monorepo, y la lee tambien
``apps/web-student/tests/comparacionSalida.test.ts``. Es a proposito: la paridad
entre el corrector de Java (este servicio, contenedor efimero) y el de Python
(navegador, Pyodide) es una PROPIEDAD DEL SISTEMA. Con dos tablas copiadas, la
primera correccion que toque una sola las separa y el mismo codigo del alumno
empieza a corregirse distinto segun el lenguaje - y los conteos
``passed``/``failed`` que ya viajaron al CTR dejan de ser comparables entre
cohortes.

Lo que se testea aca y NO en la tabla compartida:
  - la semantica de ``expected`` ``None``, que es DISTINTA a proposito entre los
    dos lados (aca ``None`` significa "no hay nada que comparar" y la decision
    se toma ANTES, en ``to_sandbox_result``);
  - que ``to_sandbox_result`` efectivamente use ``outputs_match`` y no una
    comparacion propia.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from execution_service.services.docker_runner import (
    DockerRunResult,
    normalize_output,
    outputs_match,
    to_sandbox_result,
)
from execution_service.services.sandbox_types import SandboxStatus

# tests/unit -> tests -> execution-service -> apps -> raiz del monorepo
_RAIZ = Path(__file__).resolve().parents[4]
_TABLA = _RAIZ / "tests" / "fixtures" / "paridad-salida.json"

_CASOS: list[dict] = json.loads(_TABLA.read_text(encoding="utf-8"))["casos"]


def test_la_tabla_compartida_se_encontro_y_tiene_los_dos_veredictos() -> None:
    """Guarda contra el modo de falla mas tonto de un test parametrizado.

    Si la tabla se movio o quedo vacia, `parametrize` no corre ningun caso y la
    suite pasa en verde sin haber comparado nada. Este test falla explicito.
    """
    assert _TABLA.exists(), f"la tabla compartida no esta en {_TABLA}"
    assert len(_CASOS) > 20
    assert any(c["coincide"] for c in _CASOS)
    assert any(not c["coincide"] for c in _CASOS)


@pytest.mark.parametrize("caso", _CASOS, ids=[c["nombre"] for c in _CASOS])
def test_paridad_con_el_navegador(caso: dict) -> None:
    """El mismo veredicto que da `salidaCoincide` del web-student."""
    assert outputs_match(caso["actual"], caso["esperado"]) is caso["coincide"], caso["porque"]


class TestFormaNormalizada:
    """Los mismos cuatro que el lado JS afirma sobre `normalizarSalida`.

    Comparar solo veredictos deja pasar dos normalizaciones que difieren en la
    forma y coinciden en el resultado por casualidad sobre esta tabla.
    """

    def test_unifica_los_fines_de_linea(self) -> None:
        assert normalize_output("a\r\nb\rc") == "a\nb\nc"

    def test_recorta_los_blancos_del_final_de_cada_linea(self) -> None:
        assert normalize_output("a  \nb\t\nc") == "a\nb\nc"

    def test_descarta_las_lineas_en_blanco_de_los_extremos_y_conserva_las_del_medio(self) -> None:
        assert normalize_output("\n\na\n\nb\n\n") == "a\n\nb"

    def test_una_salida_de_solo_blancos_normaliza_a_la_cadena_vacia(self) -> None:
        assert normalize_output("  \n\t\n\r\n") == ""


def _run(stdout: str) -> DockerRunResult:
    """Una corrida que TERMINO BIEN. El veredicto lo decide la comparacion."""
    return DockerRunResult(
        exit_code=0,
        stdout=stdout,
        stderr="",
        timed_out=False,
        compile_failed=False,
    )


class TestSemanticaDelExpectedNone:
    """`None` aca significa "no hay nada que comparar" - NO "no imprime nada".

    Es la semantica OPUESTA a la del navegador, donde el mismo nulo se trata
    como cadena vacia (`expected or ""`). No unificarlas: son decisiones
    distintas que se toman ANTES de normalizar. Lo unico que tiene que estar en
    paridad es la normalizacion.
    """

    def test_sin_expected_alcanza_con_que_haya_terminado_bien(self) -> None:
        # Caso `junit_assert`: la asercion ya corrio adentro del contenedor.
        r = to_sandbox_result(_run("lo que sea que haya impreso"), None)
        assert r.status is SandboxStatus.ACCEPTED

    def test_sin_expected_no_se_compara_ni_siquiera_contra_la_cadena_vacia(self) -> None:
        # Si el servidor copiara la semantica del navegador, esto seria
        # WRONG_ANSWER (imprimio algo cuando "se esperaba nada").
        assert to_sandbox_result(_run("Hola"), None).status is not SandboxStatus.WRONG_ANSWER


class TestToSandboxResultUsaLaNormalizacion:
    """El veredicto del servicio pasa por `outputs_match`, no por un `==` propio.

    Antes era `run.stdout.strip() == expected.strip()`. Estos casos fallarian
    con esa comparacion vieja: son exactamente los que la normalizacion nueva
    agrega (blancos al final de una linea intermedia, CRLF, lineas en blanco
    iniciales).
    """

    @pytest.mark.parametrize(
        "stdout,expected",
        [
            ("Hola   \nmundo\n", "Hola\nmundo"),
            ("Hola\r\nmundo\r\n", "Hola\nmundo"),
            ("\n\nHola\n", "Hola"),
        ],
    )
    def test_acepta_lo_que_el_strip_viejo_rechazaba(self, stdout: str, expected: str) -> None:
        assert to_sandbox_result(_run(stdout), expected).status is SandboxStatus.ACCEPTED

    @pytest.mark.parametrize(
        "stdout,expected",
        [
            ("hola", "Hola"),
            ("a\n\nb", "a\nb"),
            # `("  Hola", "Hola")` NO va aca: la sangria de la PRIMERA linea es
            # lo unico que el `strip()` viejo perdonaba, y se conserva para no
            # cambiar veredictos de conteos que ya viajaron al CTR. La sangria
            # de una linea POSTERIOR si sigue siendo contenido — ese caso vive
            # en `paridad-salida.json` con su porque.
            ("Hola\n  Chau", "Hola\nChau"),
        ],
    )
    def test_sigue_rechazando_lo_que_es_contenido_del_alumno(
        self, stdout: str, expected: str
    ) -> None:
        assert to_sandbox_result(_run(stdout), expected).status is SandboxStatus.WRONG_ANSWER
