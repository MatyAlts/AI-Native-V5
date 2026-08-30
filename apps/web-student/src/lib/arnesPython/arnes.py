# mypy: ignore-errors
#
# Este archivo no es un modulo que alguien importe: es un texto que se exec'ea
# dentro de otro interprete, con nombres que el host inyecta desde afuera
# (`__tutor_ask_input`) y un dict cuyo valor cambia de None a float a proposito.
# mypy no tiene forma de ver ninguna de las dos cosas, y el contrato real lo
# verifica `apps/web-student/tests/unit/test_arnes_python.py` ejecutandolo.
"""Arnes de ejecucion Python del editor del alumno.

Este archivo NO se importa como modulo: su texto se `exec`ea entero, una sola
vez, en el interprete que hospeda el codigo del alumno. Hoy tiene dos hosts:

  - Pyodide, en el navegador (`CodeEditor.tsx` lo manda por `runPythonAsync`);
  - CPython, en `apps/web-student/tests/unit/test_arnes_python.py`.

Que sea el MISMO texto en los dos es todo el punto del archivo. Antes vivia
como cuatro literales de plantilla adentro de `CodeEditor.tsx`, y para llegar a
cualquiera de estas lineas con un test habia que montar el componente entero
con Pyodide real: no lo cubria nadie. Es justo donde caen los alumnos.

Contrato con el host (lo que el arnes espera que ya exista en `globals()`):

  __tutor_ask_input(prompt: str) -> str
      Pide un dato al humano y devuelve EXACTAMENTE lo que escribio. En el
      navegador es `window.prompt`.

Contrato hacia el host (lo que el arnes deja definido):

  __tutor_run_student_code(code: str) -> None
  __tutor_run_tests(student_code: str, cases_json: str) -> str  (JSON)

El unico numero que el lado TS lee de aca es `_TUTOR_TIMEOUT_SECONDS`, que
parsea `arnesPython/index.ts`: la constante vive de este lado, no duplicada.
"""

import builtins as __tutor_builtins
import contextlib as _tutor_contextlib
import io as _tutor_io
import json as _tutor_json
import sys as _tutor_wd_sys
import time as _tutor_time

# ---------------------------------------------------------------------------
# Watchdog de ejecucion (fix 2026-06-10 #1, endurecido 2026-06-19).
#
# sys.settrace chequea un deadline en cada trace event y aborta con una
# BaseException propia (un `except Exception:` del alumno no la traga).
# El limite es de 5s de computo CONTINUO entre inputs (NO acumulado en toda la
# sesion): mientras el programa espera input() —que bloquea en window.prompt,
# tiempo humano— el watchdog se pausa (deadline=None) y al volver arranca un
# presupuesto fresco. Asi una sesion interactiva larga (muchos input, el alumno
# tardando lo que quiera en tipear) NO da falso positivo; solo se corta una
# rafaga de computo ininterrumpida > 5s.
#
# Refuerzo 2026-06-19: tracing por OPCODE (f_trace_opcodes). Sin esto settrace
# solo dispara al CAMBIAR de linea, y un loop apretado de una sola linea (ej.
# `while True: pass`) nunca re-invocaba el watchdog -> no cortaba. Con opcodes
# dispara en cada bytecode y corta igual.
# (Sigue sin cubrir una unica llamada C eterna —ej. time.sleep(1e9)—: eso
# requeriria mover Pyodide a un Web Worker con terminate().)
# ---------------------------------------------------------------------------

_TUTOR_TIMEOUT_SECONDS = 5.0


class _TutorTimeout(BaseException):
    pass


_tutor_watchdog = {"deadline": None}


def _tutor_trace(frame, event, arg):
    # Tracing por opcode: dispara en cada bytecode, no solo al cambiar de
    # linea, para cortar tambien loops apretados de una sola linea.
    frame.f_trace_opcodes = True
    deadline = _tutor_watchdog["deadline"]
    if deadline is not None and _tutor_time.monotonic() > deadline:
        raise _TutorTimeout()
    return _tutor_trace


def _tutor_pause_deadline():
    # Suspende el watchdog mientras input() bloquea en window.prompt (tiempo
    # humano): con deadline=None, _tutor_trace nunca aborta.
    _tutor_watchdog["deadline"] = None


def _tutor_reset_deadline():
    # Presupuesto de computo fresco. Se llama al volver de un input(): el tiempo
    # que el alumno tardo en tipear no cuenta, y el tramo de computo siguiente
    # arranca con _TUTOR_TIMEOUT_SECONDS completos.
    _tutor_watchdog["deadline"] = _tutor_time.monotonic() + _TUTOR_TIMEOUT_SECONDS


def __tutor_run_student_code(code):
    # `exec(..., globals())` preserva que las variables persistan entre corridas.
    _tutor_watchdog["deadline"] = _tutor_time.monotonic() + _TUTOR_TIMEOUT_SECONDS
    _tutor_wd_sys.settrace(_tutor_trace)
    try:
        exec(compile(code, "<editor>", "exec"), globals())  # noqa: S102
    except _TutorTimeout:
        raise TimeoutError(
            f"La ejecucion supero los {int(_TUTOR_TIMEOUT_SECONDS)} segundos y fue interrumpida. "
            "Revisa si tenes un bucle infinito (por ejemplo, un while cuya condicion nunca cambia)."
        ) from None
    finally:
        _tutor_wd_sys.settrace(None)
        _tutor_watchdog["deadline"] = None


# ---------------------------------------------------------------------------
# Soporte para input().
#
# Pyodide manda el prompt inline de input("texto") a stdout SIN salto de linea,
# asi que el handler `batched` lo bufferea y no llega a la ventanita a tiempo.
# Para no depender de stdout, interceptamos input() en Python (override de
# builtins.input) y recibimos el texto del prompt como argumento, explicito.
# ---------------------------------------------------------------------------


def __tutor_input(prompt=""):
    # Pausamos el watchdog mientras el alumno tipea (tiempo humano): sin esto,
    # si tardaba mas que el timeout lo mataba con un falso 'bucle infinito'.
    # Al volver, presupuesto de computo fresco.
    _tutor_pause_deadline()
    try:
        return __tutor_ask_input(str(prompt))  # noqa: F821  (lo inyecta el host)
    finally:
        _tutor_reset_deadline()


__tutor_builtins.input = __tutor_input


# ---------------------------------------------------------------------------
# FIX-22 (F-13): sandbox del editor.
#
# En Pyodide `import js` le da al codigo del alumno acceso al navegador (DOM,
# cookies, localStorage). Lo cerramos con un finder que rechaza js / pyodide_js
# + lo sacamos de sys.modules (sino `import js` devuelve la copia cacheada sin
# pasar por el finder). Los imports normales (math, random, etc.) no se tocan.
# ---------------------------------------------------------------------------

_TUTOR_BLOCKED = {"js", "pyodide_js"}


class _TutorImportGuard:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in _TUTOR_BLOCKED:
            raise ImportError("El acceso al navegador esta bloqueado en este editor")
        # El protocolo de finders exige None explicito para DELEGAR al resto del
        # meta_path: sin esto el guard decidiria sobre todos los imports.
        return None  # noqa: PLR1711


_tutor_wd_sys.meta_path.insert(0, _TutorImportGuard())
for _m in [k for k in list(_tutor_wd_sys.modules) if k.split(".")[0] in _TUTOR_BLOCKED]:
    del _tutor_wd_sys.modules[_m]


# ---------------------------------------------------------------------------
# F1: runner de test cases publicos.
#
# Corre el codigo del alumno contra cada caso en un NAMESPACE FRESCO (aislado
# entre casos) capturando su propia stdout (no toca la terminal interactiva) y
# alimentando input() desde el `code` del caso (NO window.prompt). Reusa el
# mismo watchdog de computo (_tutor_trace) que la corrida interactiva. Dos
# tipos:
#   - stdin_stdout: compara stdout (trim) contra `expected`.
#   - pytest_assert: corre el snippet de asercion tras el codigo; pasa si no
#     levanta excepcion.
# Devuelve JSON (lista de dicts) para que el lado JS lo parsee.
# ---------------------------------------------------------------------------


def __tutor_run_tests(student_code, cases_json):
    cases = _tutor_json.loads(cases_json)
    results = []
    for case in cases:
        ctype = case.get("type") or "stdin_stdout"
        stdin_text = (case.get("code") or "") if ctype == "stdin_stdout" else ""
        assert_code = (case.get("code") or "") if ctype == "pytest_assert" else ""
        expected = case.get("expected")
        _lines = iter(stdin_text.split("\n"))

        def _feed(prompt="", _it=_lines):
            try:
                return next(_it)
            except StopIteration:
                raise EOFError("El programa pidio mas datos (input) de los que este test provee.")

        buf = _tutor_io.StringIO()
        ns = {"__name__": "__main__", "input": _feed}
        error = None
        passed = False
        actual = ""
        _tutor_watchdog["deadline"] = _tutor_time.monotonic() + _TUTOR_TIMEOUT_SECONDS
        _tutor_wd_sys.settrace(_tutor_trace)
        try:
            with _tutor_contextlib.redirect_stdout(buf):
                exec(compile(student_code, "<editor>", "exec"), ns)  # noqa: S102
                if ctype == "pytest_assert":
                    exec(compile(assert_code, "<test>", "exec"), ns)  # noqa: S102
            actual = buf.getvalue()
            if ctype == "stdin_stdout":
                # JAVA-1: la comparacion NO se decide aca. La resuelve
                # salidaCoincide() de comparacionSalida.ts, del lado JS, que es
                # el gemelo exacto de la que aplica el execution-service para
                # Java. Un solo criterio por runtime: dos implementaciones de
                # la misma regla se separan con el tiempo y el mismo codigo
                # termina aprobando en un lenguaje y fallando en el otro.
                # Este False es un placeholder que el lado JS pisa.
                passed = False
            else:
                passed = True
        except _TutorTimeout:
            actual = buf.getvalue()
            error = "La ejecucion supero el limite de tiempo (posible bucle infinito)."
        except AssertionError as _e:
            actual = buf.getvalue()
            _msg = str(_e)
            error = "La comprobacion no se cumplio" + (": " + _msg if _msg else "")
        except BaseException as _e:
            actual = buf.getvalue()
            error = type(_e).__name__ + ": " + str(_e)
        finally:
            _tutor_wd_sys.settrace(None)
            _tutor_watchdog["deadline"] = None
        results.append(
            {
                "id": case.get("id"),
                "name": case.get("name"),
                "type": ctype,
                "passed": passed,
                "expected": expected,
                "actual": actual,
                "stdin": stdin_text,
                "error": error,
            }
        )
    return _tutor_json.dumps(results)
