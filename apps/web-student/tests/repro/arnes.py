"""
Arnes de reproduccion del runtime Python del editor (CodeEditor.tsx).

NO copia el codigo Python: lo EXTRAE del .tsx en tiempo de ejecucion, para que
un repro no pueda quedar mintiendo cuando el componente cambie.

Lo que se extrae:
  - el bloque del watchdog (_tutor_trace / __tutor_run_student_code)
  - el override de builtins.input (__tutor_input)
  - el runner de tests publicos (__tutor_run_tests)

Lo que se simula del lado JS:
  - `__tutor_ask_input(prompt)` = el `askForInput` de CodeEditor.tsx, incluido
    el `window.prompt(...) ?? ""` (cancelar -> cadena vacia) y el eco al
    outputBufferRef.

Diferencia honesta con el navegador: aca corre CPython, no Pyodide-WASM. La
logica del watchdog, del override de input y del runner es la misma (es Python
puro); lo que NO es igual es la VELOCIDAD del interprete. Donde eso importa, el
repro lo dice explicitamente.
"""

from __future__ import annotations

import re
from pathlib import Path

TSX = Path(__file__).resolve().parents[2] / "src" / "components" / "CodeEditor.tsx"
EXECUTION_TIMEOUT_SECONDS = 5


def _fuente_tsx() -> str:
    return TSX.read_text(encoding="utf-8")


def bloques_template() -> list[str]:
    """Los `await py.runPythonAsync(\\`...\\`)` (template literals)."""
    src = _fuente_tsx()
    bloques = re.findall(r"runPythonAsync\(`(.*?)`\)", src, re.DOTALL)
    return [
        b.replace("${EXECUTION_TIMEOUT_SECONDS}", str(EXECUTION_TIMEOUT_SECONDS))
        for b in bloques
    ]


def bloque_input() -> str:
    """El override de builtins.input, que en el .tsx es concatenacion de strings."""
    src = _fuente_tsx()
    m = re.search(
        r'runPythonAsync\(\s*\n\s*"import builtins as __tutor_builtins(.*?)\n\s*\)',
        src,
        re.DOTALL,
    )
    if not m:
        raise RuntimeError("no encontre el bloque de __tutor_input en CodeEditor.tsx")
    crudo = '"import builtins as __tutor_builtins' + m.group(1)
    partes = re.findall(r'"((?:[^"\\]|\\.)*)"', crudo)
    return "".join(p.encode().decode("unicode_escape") for p in partes)


def watchdog_src() -> str:
    for b in bloques_template():
        if "__tutor_run_student_code" in b:
            return b
    raise RuntimeError("no encontre el bloque del watchdog")


def runner_tests_src() -> str:
    for b in bloques_template():
        if "__tutor_run_tests" in b:
            return b
    raise RuntimeError("no encontre el runner de tests")


class Terminal:
    """Espejo de `outputBufferRef` + `askForInput` de CodeEditor.tsx."""

    def __init__(self, respuestas=(), *, cancelar_siempre=False, max_prompts=100_000):
        # `respuestas` = lo que devuelve window.prompt. `None` = el alumno cancelo.
        self.respuestas = list(respuestas)
        self.cancelar_siempre = cancelar_siempre
        self.buffer = ""
        self.prompts: list[str] = []
        self.max_prompts = max_prompts

    def _window_prompt(self, _mensaje: str):
        if self.cancelar_siempre:
            return None
        if not self.respuestas:
            return None  # se acabaron: el alumno cierra el cartel = cancelar
        return self.respuestas.pop(0)

    def ask_input(self, prompt_text: str) -> str:
        # --- traduccion 1:1 de askForInput (CodeEditor.tsx ~795) ---
        raw = prompt_text if prompt_text is not None else ""
        inline = raw.strip()
        guia = inline or self.buffer.strip()
        mensaje = (
            f"{guia}\n\n-> Ingresa el dato que pide el programa:"
            if guia
            else "El programa pide un dato de entrada (input):"
        )
        if len(self.prompts) >= self.max_prompts:
            raise RuntimeError(
                f"TOPE DEL REPRO: {self.max_prompts} window.prompt() seguidos sin salida"
            )
        self.prompts.append(mensaje)
        value = self._window_prompt(mensaje)
        value = "" if value is None else value  # <-- el `?? ""` del componente
        echo = f"{raw}{value}\n"
        self.buffer += echo
        return value

    def escribir_stdout(self, texto: str) -> None:
        """Espejo del `setStdout({batched})` del componente: SIEMPRE agrega \\n."""
        self.buffer += f"{texto}\n"


def montar(terminal: Terminal) -> dict:
    """Devuelve los globals de Pyodide con el runtime del editor ya instalado."""
    g: dict = {"__name__": "__main__"}
    g["__tutor_ask_input"] = terminal.ask_input
    exec(compile(watchdog_src(), "<watchdog>", "exec"), g)
    exec(compile(bloque_input(), "<input-override>", "exec"), g)
    return g


def montar_con_print(terminal: Terminal) -> dict:
    """`montar` + un `print` que escribe al buffer como el setStdout del componente.

    Sirve para que la salida del programa del alumno no se mezcle con la del
    repro, y para que el buffer crezca igual que en el navegador.
    """
    g = montar(terminal)

    def print_espejo(*args, **kw):
        sep = kw.get("sep", " ")
        terminal.escribir_stdout(sep.join(str(a) for a in args))

    g["print"] = print_espejo
    return g


def correr(codigo: str, terminal: Terminal, globals_py: dict | None = None):
    """Equivalente de apretar "Ejecutar" (runCode -> __tutor_run_student_code).

    Devuelve la excepcion que escapo, o None si termino bien.
    """
    import builtins

    original_input = builtins.input
    g = globals_py if globals_py is not None else montar(terminal)
    try:
        g["__tutor_run_student_code"](codigo)
        return None
    except BaseException as e:  # noqa: BLE001 - queremos ver TODO lo que escapa
        return e
    finally:
        builtins.input = original_input
