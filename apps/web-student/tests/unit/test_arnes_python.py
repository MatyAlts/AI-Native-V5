"""Arnes de ejecucion Python del editor del alumno, contra CPython.

El sujeto es `apps/web-student/src/lib/arnesPython/arnes.py`: el MISMO texto
que el navegador le manda a Pyodide. Estos tests lo exec'ean en CPython, sin
navegador y sin Pyodide, porque casi todo lo que hace es Python puro — el
override de `input()`, el watchdog por opcode, la captura de stdout del runner
de casos y el aislamiento de namespaces no dependen de nada del browser.

Por que importa: hasta 2026-08-30 el arnes vivia como cuatro literales de
plantilla adentro de `CodeEditor.tsx`. Para ejercitar una sola de esas lineas
habia que montar el componente entero con Pyodide real, y no lo hacia nadie.
Es exactamente donde caen los alumnos: un video de produccion del 2026-08-28
muestra a uno cargando datos con `input()` durante 2:40 minutos, y hay
reportes de que "las validaciones fallan cuando escribe un input".

Lo que NO se puede probar aca (necesita Pyodide de verdad):
  - `py.setStdout({batched})` / `setStdin` — la captura de stdout de la corrida
    INTERACTIVA la hace Pyodide, no el arnes;
  - el bloqueo real de `import js` / `import pyodide_js` (aca esos modulos no
    existen: se prueba el mecanismo del finder, no que tape el DOM);
  - `window.prompt` y el eco del prompt a la terminal (vive en `askForInput`,
    del lado JS);
  - que una llamada C eterna (`time.sleep(1e9)`) NO sea interrumpible — es
    cierto en los dos, pero verificarlo cuelga el proceso.

Los cinco HALLAZGOS del final son bugs del arnes, no de estos tests: van en
rojo (`xfail(strict=True)`) y sin arreglar a proposito. Si alguien los arregla,
el xfail estricto pasa a XPASS y la suite lo grita.
"""

from __future__ import annotations

import builtins
import io
import json
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path

import pytest

ARNES_PY = Path(__file__).resolve().parents[2] / "src" / "lib" / "arnesPython" / "arnes.py"

# Presupuesto corto para los tests del watchdog. El de produccion son 5s: con
# tracing por opcode, esperarlos de verdad son 5s de reloj por test.
TIMEOUT_TEST = 0.15


@dataclass
class Arnes:
    """El arnes ya exec'eado, mas los mandos para manejarlo desde el test."""

    ns: dict
    #: Lo que va a devolver la proxima llamada a `input()` interactivo.
    respuestas: list[str] = field(default_factory=list)
    #: Los prompts que el arnes le paso al host, en orden.
    prompts_vistos: list[str] = field(default_factory=list)
    #: Hook opcional para simular al humano tardando en tipear.
    antes_de_responder: Callable[[], None] | None = None

    def con_timeout(self, segundos: float) -> None:
        """Achica el presupuesto de computo.

        Funciona porque `__tutor_run_student_code` lee `_TUTOR_TIMEOUT_SECONDS`
        del namespace en cada llamada, no lo captura al definirse.
        """
        self.ns["_TUTOR_TIMEOUT_SECONDS"] = segundos

    def correr(self, codigo: str) -> str:
        """Corrida interactiva. Devuelve lo que el programa imprimio."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.ns["__tutor_run_student_code"](codigo)
        return buf.getvalue()

    def correr_tests(self, codigo: str, casos: list[dict]) -> list[dict]:
        crudo = self.ns["__tutor_run_tests"](codigo, json.dumps(casos))
        return json.loads(crudo)


@pytest.fixture
def arnes() -> Iterator[Arnes]:
    """Exec'ea el arnes en un namespace propio y limpia TODO lo que ensucia.

    El arnes es invasivo a proposito: pisa `builtins.input`, mete un finder en
    `sys.meta_path` y prende `sys.settrace`. En el navegador eso es el mundo
    entero del alumno; aca es el proceso de pytest, compartido con el resto de
    la suite y con el tracer de coverage. Sin esta restauracion, un solo test
    del watchdog apaga coverage para todo lo que corra despues.
    """
    trace_previo = sys.gettrace()
    meta_path_previo = sys.meta_path[:]
    input_previo = builtins.input

    control = Arnes(ns={})

    def ask_input(prompt: str) -> str:
        control.prompts_vistos.append(prompt)
        if control.antes_de_responder is not None:
            control.antes_de_responder()
        if not control.respuestas:
            raise AssertionError("el programa pidio mas inputs de los que el test preparo")
        return control.respuestas.pop(0)

    control.ns["__tutor_ask_input"] = ask_input
    # El arnes ES codigo para exec: es el sujeto del test, no un descuido.
    exec(  # noqa: S102
        compile(ARNES_PY.read_text(encoding="utf-8"), str(ARNES_PY), "exec"), control.ns
    )

    try:
        yield control
    finally:
        sys.settrace(trace_previo)
        sys.meta_path[:] = meta_path_previo
        builtins.input = input_previo


# ---------------------------------------------------------------------------
# input() interactivo — que devuelve, exactamente
# ---------------------------------------------------------------------------

VALORES = [
    pytest.param("", id="vacio"),
    pytest.param("   ", id="solo-espacios"),
    pytest.param("José Ñandú", id="acentos-y-enie"),
    pytest.param("x" * 10_000, id="muy-largo"),
    pytest.param("linea1\nlinea2", id="con-salto-adentro"),
    pytest.param("42", id="numero-donde-se-espera-texto"),
    pytest.param("  Juan  ", id="con-blancos-a-los-costados"),
    pytest.param("\t", id="tab"),
    pytest.param("Juan\n", id="ya-trae-un-salto-al-final"),
]


@pytest.mark.parametrize("valor", VALORES)
def test_input_devuelve_exactamente_lo_que_se_escribio(arnes: Arnes, valor: str) -> None:
    """El invariante central del arnes: `input()` no agrega ni recorta nada.

    Si volviera con un `\\n` pegado, `"Juan\\n".isalpha()` da False y la
    validacion que escribio el alumno falla sin motivo aparente. Es la
    hipotesis principal del bug reportado en produccion.
    """
    arnes.respuestas = [valor]
    arnes.ns["__resultado"] = None
    arnes.correr("__resultado = input('Dato: ')")
    assert arnes.ns["__resultado"] == valor


def test_input_no_le_pega_un_salto_de_linea_y_isalpha_sobrevive(arnes: Arnes) -> None:
    """La misma propiedad, dicha en el idioma del alumno."""
    arnes.respuestas = ["Juan"]
    arnes.ns["__ok"] = None
    arnes.correr("__ok = input('Nombre: ').isalpha()")
    assert arnes.ns["__ok"] is True


def test_input_es_el_mismo_objeto_str_que_devolvio_el_host(arnes: Arnes) -> None:
    """Ni copia normalizada ni strip: el arnes pasa el valor tal cual.

    `is` y no `==` a proposito — un `.strip()` sobre una cadena sin blancos
    devuelve una cadena igual pero distinta, y `==` no lo veria.
    """
    valor = "Ana"
    arnes.respuestas = [valor]
    arnes.ns["__resultado"] = None
    arnes.correr("__resultado = input()")
    assert arnes.ns["__resultado"] is valor


def test_input_le_pasa_el_prompt_al_host_convertido_a_str(arnes: Arnes) -> None:
    """`input(42)` tiene que llegar como `"42"`, no como el int."""
    arnes.respuestas = ["x", "y", "z"]
    arnes.correr("input(42)\ninput('Nombre: ')\ninput()")
    assert arnes.prompts_vistos == ["42", "Nombre: ", ""]
    assert all(isinstance(p, str) for p in arnes.prompts_vistos)


def test_input_queda_instalado_en_builtins(arnes: Arnes) -> None:
    """El override es global: alcanza al codigo del alumno sin ceremonias."""
    assert builtins.input is arnes.ns["__tutor_input"]


# ---------------------------------------------------------------------------
# Watchdog de ejecucion
# ---------------------------------------------------------------------------


def test_watchdog_corta_un_bucle_infinito_de_varias_lineas(arnes: Arnes) -> None:
    arnes.con_timeout(TIMEOUT_TEST)
    with pytest.raises(TimeoutError) as exc:
        arnes.correr("while True:\n    x = 1\n    y = 2\n")
    assert "bucle infinito" in str(exc.value)


def test_watchdog_corta_un_bucle_apretado_de_UNA_sola_linea(arnes: Arnes) -> None:
    """El caso que motivo el refuerzo del 2026-06-19 (`f_trace_opcodes`).

    OJO con lo que este test prueba y lo que NO: prueba que el bucle se corta.
    NO prueba que lo corte el tracing por opcode — en CPython 3.12 el evento
    `line` ya dispara solo con este codigo, y el mutante que apaga
    `f_trace_opcodes` sobrevive a este test. Ver HALLAZGO 5 abajo, y
    `test_el_trace_prende_el_tracing_por_opcode` para el mecanismo.
    """
    arnes.con_timeout(TIMEOUT_TEST)
    with pytest.raises(TimeoutError):
        arnes.correr("while True: pass")


def test_el_trace_prende_el_tracing_por_opcode(arnes: Arnes) -> None:
    """El mecanismo, directo, sin pasar por una corrida.

    Existe porque el test de arriba no lo pinea: en 3.12 el bucle se corta
    igual con o sin opcodes, y un mutante que apague la linea pasaria de largo.
    """

    class FrameFalso:
        f_trace_opcodes = False

    frame = FrameFalso()
    devuelto = arnes.ns["_tutor_trace"](frame, "line", None)
    assert frame.f_trace_opcodes is True
    # Devolverse a si mismo es lo que hace que siga trazando el frame local.
    assert devuelto is arnes.ns["_tutor_trace"]


def test_watchdog_no_corta_al_alumno_que_tarda_dos_minutos_en_tipear(arnes: Arnes) -> None:
    """El caso del video: 2:40 minutos cargando datos con `input()`.

    El presupuesto es de COMPUTO CONTINUO, no de reloj. Mientras el humano
    piensa, el watchdog esta en pausa; al volver arranca un presupuesto entero.
    Aca el 'humano' tarda 4x el timeout, tres veces seguidas.
    """
    arnes.con_timeout(TIMEOUT_TEST)
    arnes.respuestas = ["uno", "dos", "tres"]
    arnes.antes_de_responder = lambda: time.sleep(TIMEOUT_TEST * 4)
    salida = arnes.correr("for _ in range(3):\n    print(input('Dato: '))\n")
    assert salida == "uno\ndos\ntres\n"


def test_el_presupuesto_vuelve_a_correr_despues_del_input(arnes: Arnes) -> None:
    """Pausar no es apagar: tras el `input()` el watchdog tiene que rearmarse.

    Sin esto, un `input()` al principio del programa desactivaria el watchdog
    para toda la corrida y el bucle infinito de despues colgaria la pestaña.
    """
    arnes.con_timeout(TIMEOUT_TEST)
    arnes.respuestas = ["hola"]
    with pytest.raises(TimeoutError):
        arnes.correr("input('Dato: ')\nwhile True: pass")


def test_un_except_Exception_del_alumno_no_se_traga_el_watchdog(arnes: Arnes) -> None:
    """La propiedad que le importa al alumno: el timeout llega igual.

    El mecanismo real NO es la herencia de BaseException: cuando una trace
    function levanta, CPython desenrolla el frame SIN correr sus handlers, asi
    que ni un `except BaseException:` la ve pasar. Verificado con el mutante M6
    (`_TutorTimeout(Exception)`), que sobrevive a este test. La herencia de
    BaseException se pinea aparte, como intencion de diseño.
    """
    arnes.con_timeout(TIMEOUT_TEST)
    with pytest.raises(TimeoutError):
        arnes.correr("try:\n    while True: pass\nexcept Exception:\n    pass\n")


def test_TutorTimeout_no_es_una_Exception(arnes: Arnes) -> None:
    """Intencion de diseño, no comportamiento observable hoy.

    Es defensa en profundidad: si alguna vez el timeout se levantara desde
    dentro del frame del alumno (y no desde la trace function), heredar de
    BaseException es lo unico que impide que un `except Exception:` lo tape.
    """
    excepcion = arnes.ns["_TutorTimeout"]
    assert issubclass(excepcion, BaseException)
    assert not issubclass(excepcion, Exception)


def test_el_watchdog_no_queda_armado_despues_de_una_corrida_normal(arnes: Arnes) -> None:
    arnes.correr("x = 1")
    assert arnes.ns["_tutor_watchdog"]["deadline"] is None
    assert sys.gettrace() is None


def test_el_watchdog_no_queda_armado_despues_de_un_timeout(arnes: Arnes) -> None:
    arnes.con_timeout(TIMEOUT_TEST)
    with pytest.raises(TimeoutError):
        arnes.correr("while True: pass")
    assert arnes.ns["_tutor_watchdog"]["deadline"] is None
    assert sys.gettrace() is None


def test_las_variables_persisten_entre_corridas(arnes: Arnes) -> None:
    """`exec(..., globals())`: la terminal del alumno es una sesion, no un batch."""
    arnes.correr("saludo = 'hola'")
    salida = arnes.correr("print(saludo)")
    assert salida == "hola\n"


# ---------------------------------------------------------------------------
# stdout
# ---------------------------------------------------------------------------


def test_print_con_acentos_llega_entero_al_runner_de_casos(arnes: Arnes) -> None:
    [caso] = arnes.correr_tests(
        "print('Camión, ñandú, ábaco')", [{"id": "1", "type": "stdin_stdout", "expected": ""}]
    )
    assert caso["actual"] == "Camión, ñandú, ábaco\n"


def test_un_print_sin_salto_final_no_se_pierde(arnes: Arnes) -> None:
    """`print(..., end='')` no cierra la linea; el buffer igual tiene que traerlo."""
    [caso] = arnes.correr_tests(
        "print('sin salto', end='')", [{"id": "1", "type": "stdin_stdout", "expected": ""}]
    )
    assert caso["actual"] == "sin salto"


def test_la_corrida_interactiva_no_toca_el_stdout_del_programa(arnes: Arnes) -> None:
    """El arnes NO redirige stdout en la corrida interactiva — eso es de Pyodide.

    Lo que se afirma aca es que no lo intercepta ni lo reordena: lo que el
    alumno imprime sale, en orden, sin agregados.
    """
    salida = arnes.correr("print('uno')\nprint('dos', end='')\nprint('tres')")
    assert salida == "uno\ndostres\n"


# ---------------------------------------------------------------------------
# Runner de casos publicos
# ---------------------------------------------------------------------------

CODIGO_QUE_PIDE_DOS_DATOS = "n = input('Nombre: ')\ne = input('Edad: ')\nprint(f'{n} tiene {e}')"


def test_el_runner_alimenta_input_desde_el_caso_no_desde_window_prompt(arnes: Arnes) -> None:
    [caso] = arnes.correr_tests(
        CODIGO_QUE_PIDE_DOS_DATOS,
        [{"id": "1", "type": "stdin_stdout", "code": "Juan\n25", "expected": "Juan tiene 25"}],
    )
    assert caso["error"] is None
    assert caso["actual"] == "Juan tiene 25\n"
    # El host interactivo no se toco: window.prompt no participa de las pruebas.
    assert arnes.prompts_vistos == []


def test_el_runner_entrega_la_linea_exacta_incluidos_acentos(arnes: Arnes) -> None:
    [caso] = arnes.correr_tests(
        "print(repr(input()))",
        [{"id": "1", "type": "stdin_stdout", "code": "José Ñandú", "expected": None}],
    )
    assert caso["actual"] == "'José Ñandú'\n"


def test_el_runner_avisa_cuando_el_caso_no_trae_suficientes_datos(arnes: Arnes) -> None:
    [caso] = arnes.correr_tests(
        CODIGO_QUE_PIDE_DOS_DATOS,
        [{"id": "1", "type": "stdin_stdout", "code": "Juan", "expected": None}],
    )
    assert caso["error"] is not None
    assert caso["error"].startswith("EOFError:")
    assert "mas datos" in caso["error"]


def test_cada_caso_corre_en_un_namespace_fresco(arnes: Arnes) -> None:
    """Aislamiento entre casos: el estado de uno no puede filtrarse al siguiente."""
    codigo = "import builtins\nvisto = getattr(builtins, '__filtrado', False)\n"
    codigo += "builtins.__filtrado = True\nprint(visto)"
    casos = [
        {"id": "1", "type": "stdin_stdout", "code": "", "expected": None},
        {"id": "2", "type": "stdin_stdout", "code": "", "expected": None},
    ]
    try:
        primero, segundo = arnes.correr_tests(codigo, casos)
    finally:
        if hasattr(builtins, "__filtrado"):
            del builtins.__filtrado
    # El namespace es fresco (lo verificamos abajo con una global comun); esta
    # via builtins es la unica forma de que algo cruce, y demuestra que el
    # aislamiento es del namespace, no del proceso.
    assert primero["actual"] == "False\n"
    assert segundo["actual"] == "True\n"


def test_una_global_del_alumno_no_sobrevive_al_caso_siguiente(arnes: Arnes) -> None:
    codigo = "acumulador = globals().get('acumulador', 0) + 1\nprint(acumulador)"
    casos = [
        {"id": "1", "type": "stdin_stdout", "code": "", "expected": None},
        {"id": "2", "type": "stdin_stdout", "code": "", "expected": None},
    ]
    primero, segundo = arnes.correr_tests(codigo, casos)
    assert primero["actual"] == "1\n"
    assert segundo["actual"] == "1\n"


def test_stdin_stdout_deja_passed_en_False_para_que_lo_decida_el_lado_JS(arnes: Arnes) -> None:
    """JAVA-1: el veredicto lo pone `resolverVeredictosPython`, no el Python.

    Un solo criterio de comparacion por runtime. Si el arnes empezara a decidir
    aca, el mismo codigo aprobaria en Python y fallaria en Java.
    """
    [caso] = arnes.correr_tests(
        "print('exacto')",
        [{"id": "1", "type": "stdin_stdout", "code": "", "expected": "exacto"}],
    )
    assert caso["passed"] is False
    assert caso["actual"] == "exacto\n"
    assert caso["expected"] == "exacto"


def test_pytest_assert_pasa_cuando_la_asercion_se_cumple(arnes: Arnes) -> None:
    [caso] = arnes.correr_tests(
        "def doble(x):\n    return x * 2",
        [{"id": "1", "type": "pytest_assert", "code": "assert doble(3) == 6", "expected": None}],
    )
    assert caso["passed"] is True
    assert caso["error"] is None


def test_pytest_assert_reporta_el_mensaje_de_la_asercion(arnes: Arnes) -> None:
    [caso] = arnes.correr_tests(
        "def doble(x):\n    return x * 3",
        [
            {
                "id": "1",
                "type": "pytest_assert",
                "code": "assert doble(3) == 6, 'el doble de 3 es 6'",
                "expected": None,
            }
        ],
    )
    assert caso["passed"] is False
    assert caso["error"] == "La comprobacion no se cumplio: el doble de 3 es 6"


def test_el_runner_corta_un_caso_que_se_cuelga_y_sigue_con_el_proximo(arnes: Arnes) -> None:
    """Un bucle infinito en un caso no puede llevarse puesta la corrida entera."""
    arnes.con_timeout(TIMEOUT_TEST)
    colgado, sano = arnes.correr_tests(
        "if input() == 'colgar':\n    while True: pass\nprint('ok')",
        [
            {"id": "1", "type": "stdin_stdout", "code": "colgar", "expected": None},
            {"id": "2", "type": "stdin_stdout", "code": "seguir", "expected": "ok"},
        ],
    )
    assert colgado["error"] == "La ejecucion supero el limite de tiempo (posible bucle infinito)."
    assert sano["error"] is None
    assert sano["actual"] == "ok\n"


def test_el_runner_conserva_lo_impreso_antes_del_error(arnes: Arnes) -> None:
    [caso] = arnes.correr_tests(
        "print('alcance a imprimir')\nraise ValueError('roto')",
        [{"id": "1", "type": "stdin_stdout", "code": "", "expected": None}],
    )
    assert caso["actual"] == "alcance a imprimir\n"
    assert caso["error"] == "ValueError: roto"


def test_el_runner_devuelve_los_metadatos_del_caso_intactos(arnes: Arnes) -> None:
    [caso] = arnes.correr_tests(
        "pass",
        [{"id": "abc", "name": "Caso uno", "type": "stdin_stdout", "code": "x", "expected": "y"}],
    )
    assert caso["id"] == "abc"
    assert caso["name"] == "Caso uno"
    assert caso["type"] == "stdin_stdout"
    assert caso["stdin"] == "x"


def test_el_runner_no_deja_el_tracer_prendido(arnes: Arnes) -> None:
    arnes.correr_tests("pass", [{"id": "1", "type": "stdin_stdout", "code": "", "expected": None}])
    assert sys.gettrace() is None
    assert arnes.ns["_tutor_watchdog"]["deadline"] is None


# ---------------------------------------------------------------------------
# Sandbox de imports
# ---------------------------------------------------------------------------


def test_el_guard_rechaza_los_modulos_del_navegador(arnes: Arnes) -> None:
    """Aca no existe `js`, asi que se prueba el mecanismo: el finder decide.

    Que el bloqueo tape de verdad el DOM solo se puede ver con Pyodide.
    """
    guard = next(f for f in sys.meta_path if type(f).__name__ == "_TutorImportGuard")
    for nombre in ("js", "pyodide_js", "js.document"):
        with pytest.raises(ImportError, match="bloqueado"):
            guard.find_spec(nombre)


def test_el_guard_no_se_mete_con_los_imports_normales(arnes: Arnes) -> None:
    guard = next(f for f in sys.meta_path if type(f).__name__ == "_TutorImportGuard")
    for nombre in ("math", "random", "json", "jsonschema", "javalang"):
        assert guard.find_spec(nombre) is None
    salida = arnes.correr("import math\nprint(math.floor(2.7))")
    assert salida == "2\n"


def test_el_guard_se_instala_primero_en_el_meta_path(arnes: Arnes) -> None:
    """Si quedara ultimo, el finder de siempre resolveria `js` antes que el."""
    assert type(sys.meta_path[0]).__name__ == "_TutorImportGuard"


# ---------------------------------------------------------------------------
# HALLAZGOS — bugs del arnes. Documentados en rojo, NO arreglados aca.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "HALLAZGO 1 (candidato al bug reportado: 'las validaciones fallan cuando "
        "escribe un input'). El runner del ALUMNO no escribe el prompt de input() a "
        "stdout; el del DOCENTE (apps/web-teacher/src/lib/pyodideRunner.ts, _fake_input) "
        "si lo escribe, replicando a CPython. El docente valida su `expected` con SU "
        "runner —- y ese expected queda con el prompt adentro -—, el alumno corre el "
        "mismo caso y su `actual` viene sin el. salidaCoincide() los ve distintos y el "
        "caso falla, con el codigo del alumno correcto. Solo pasa en ejercicios con "
        "input(): es justo el sintoma reportado. Decide otro agente."
    ),
)
def test_HALLAZGO_el_runner_del_alumno_no_imprime_el_prompt_como_CPython(arnes: Arnes) -> None:
    [caso] = arnes.correr_tests(
        CODIGO_QUE_PIDE_DOS_DATOS,
        [{"id": "1", "type": "stdin_stdout", "code": "Juan\n25", "expected": None}],
    )
    # Lo que devuelve CPython de verdad (y el runner del docente): los prompts
    # forman parte de la salida del programa.
    assert caso["actual"] == "Nombre: Edad: Juan tiene 25\n"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "HALLAZGO 2. `_feed` parte el stdin con split('\\n') pelado: si el caso viene "
        "con finales de linea CRLF (importado de un archivo, pegado desde Windows), "
        "cada valor vuelve con un '\\r' colgado. `'Juan\\r'.isalpha()` es False y la "
        "validacion del alumno falla sin motivo visible — el '\\r' no se ve en pantalla. "
        "CPython usa universal newlines y nunca devuelve el '\\r'. Decide otro agente."
    ),
)
def test_HALLAZGO_el_runner_deja_el_retorno_de_carro_de_un_stdin_CRLF(arnes: Arnes) -> None:
    [caso] = arnes.correr_tests(
        "print(input().isalpha())",
        [{"id": "1", "type": "stdin_stdout", "code": "Juan\r\n25", "expected": None}],
    )
    assert caso["actual"] == "True\n"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "HALLAZGO 3. Cuando el codigo del alumno atrapa BaseException (o usa un "
        "`except:` pelado), se come la _TutorTimeout — y como CPython DESARMA el trace "
        "function cuando esta levanta, el watchdog queda muerto para el resto de la "
        "corrida: el bucle infinito que venga despues congela la pestaña sin timeout. "
        "El comentario del arnes solo promete cubrir `except Exception:`, que si cubre. "
        "Decide otro agente."
    ),
)
def test_HALLAZGO_un_except_pelado_desarma_el_watchdog_para_el_resto_de_la_corrida(
    arnes: Arnes,
) -> None:
    arnes.con_timeout(TIMEOUT_TEST)
    arnes.correr("try:\n    while True: pass\nexcept BaseException:\n    pass\n")
    # Tras tragarse el timeout, el watchdog deberia seguir de pie.
    assert sys.gettrace() is not None


@pytest.mark.xfail(
    strict=True,
    reason=(
        "HALLAZGO 4. Un caso cuyo stdin termina en '\\n' (lo natural al escribirlo) "
        "produce una linea vacia de mas: split('\\n') sobre 'Juan\\n' da ['Juan', '']. "
        "El tercer input() del alumno recibe '' en vez del EOFError que le corresponde, "
        "y el programa sigue con un dato vacio en vez de fallar donde el docente espera. "
        "Decide otro agente."
    ),
)
def test_HALLAZGO_un_stdin_terminado_en_salto_regala_una_linea_vacia(arnes: Arnes) -> None:
    [caso] = arnes.correr_tests(
        "input()\nprint('pidiendo el segundo')\ninput()",
        [{"id": "1", "type": "stdin_stdout", "code": "Juan\n", "expected": None}],
    )
    assert caso["error"] is not None, "el segundo input() deberia dar EOFError, no ''"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "HALLAZGO 5. El comentario del arnes dice que sin `f_trace_opcodes` un "
        "`while True: pass` 'nunca re-invocaba el watchdog -> no cortaba'. En CPython "
        "3.12 —la version que shippea Pyodide 0.26.3— eso ya no es cierto: el evento "
        "`line` dispara ~24k veces en 50 ms sobre ese mismo bucle, y el watchdog corta "
        "igual con opcodes apagados. Peor: sobre ESE codigo el tracing por opcode ni "
        "se activa (0 eventos `opcode`; solo aparecen en bucles multilinea, donde el "
        "tracing por linea ya alcanzaba). O sea que hoy la linea no agrega cobertura, "
        "y hace pagar el sobrecosto del tracing por bytecode. Falta confirmarlo contra "
        "Pyodide real antes de sacarla. Decide otro agente."
    ),
)
def test_HALLAZGO_sin_tracing_por_opcode_el_bucle_de_una_linea_igual_se_corta() -> None:
    """Verifica la PREMISA del comentario del arnes, no el arnes.

    Reimplementa el watchdog con `f_trace_opcodes` apagado: si la premisa fuera
    cierta, el bucle no se cortaria y el `pytest.raises` fallaria.
    """

    class Corte(BaseException):
        pass

    fin = time.monotonic() + TIMEOUT_TEST

    def trazar(frame, event, arg):
        frame.f_trace_opcodes = False  # <- lo unico que cambia respecto del arnes
        if time.monotonic() > fin:
            raise Corte()
        return trazar

    trace_previo = sys.gettrace()
    sys.settrace(trazar)
    try:
        with pytest.raises(Corte):
            exec(compile("while True: pass", "<editor>", "exec"), {})  # noqa: S102
    finally:
        sys.settrace(trace_previo)
    pytest.fail("el bucle se corto sin tracing por opcode: la premisa del comentario no aplica")
