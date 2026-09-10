"""Los tres runners tienen que producir la MISMA salida ante un `input()`.

EL REPORTE (un docente, 2026-09-10)
-----------------------------------
"El boton de prueba solo salta como correcto si tienen exactamente las mismas
oraciones, los mismos prints. Me puse a testear por que tenia todo bien y me
daba mal las pruebas."

Tenia razon, y la causa no era el comparador —que esta unificado y bien
documentado en `comparacionSalida.ts`— sino LO QUE SE COMPARA.

EL PROMPT DE `input()` ES SALIDA DEL PROGRAMA
--------------------------------------------
CPython lo escribe a stdout. Con `python p.py < entrada`, un
`input("Nombre: ")` imprime `"Nombre: "`, y el valor tipeado NO se hace eco
(eso lo hace la terminal, no el programa).

De los tres runners de la plataforma, DOS lo replicaban y UNO lo tiraba:

  - `web-teacher/lib/pyodideRunner.ts::_fake_input` — el panel donde el docente
    VALIDA el ejercicio antes de asignarlo — lo escribe, con un comentario que
    explica exactamente por que.
  - El `execution-service` de Java devuelve `result.stdout` crudo del
    contenedor, asi que el `System.out.print(...)` va.
  - `web-student/CodeEditor.tsx::_feed` — el frasco del ALUMNO — lo descartaba.

O sea: el docente validaba en VERDE, el `expected_output` quedaba guardado CON
los prompts, y despues el alumno apretaba el frasco y le daba ROJO con el mismo
codigo correcto. En silencio, porque lo que falta es justo el texto que uno da
por sentado que esta.

Es la MISMA falla que `comparacionSalida.ts` documenta —"Probar da verde, la
cohorte entera recibe WRONG_ANSWER con codigo correcto"— una capa mas arriba.
Ahi se unifico el COMPARADOR; quedo sin unificar lo que se compara.

POR QUE ESTE TEST VIVE ACA Y EN PYTHON
--------------------------------------
Porque EJECUTA de verdad el Python que los dos frontends inyectan en Pyodide,
extrayendolo de sus archivos fuente. Un test que sólo mire el texto ("¿dice
`out.write(prompt)`?") se vacia el dia que alguien lo reescriba distinto pero
equivalente — o peor, pasa mientras el comportamiento cambia.

Mismo criterio que `tests/fixtures/paridad-salida.json`: una regla, verificada
sobre los dos lenguajes que la implementan.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parents[4]
_EDITOR_ALUMNO = _RAIZ / "apps/web-student/src/components/CodeEditor.tsx"
_PANEL_DOCENTE = _RAIZ / "apps/web-teacher/src/lib/pyodideRunner.ts"

# Un programa que pide dos datos, como los del PID.
PROGRAMA = 'a = input("Ingrese A: ")\nb = input("Ingrese B: ")\nprint(f"{a}-{b}")\n'
ENTRADA = "1\n2"


def _cpython_real() -> str:
    """La referencia: lo que el docente ve en su terminal."""
    buf = io.StringIO()
    viejo = sys.stdin
    sys.stdin = io.StringIO(ENTRADA + "\n")
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(PROGRAMA, "<p>", "exec"), {"__name__": "__main__"})  # noqa: S102
    finally:
        sys.stdin = viejo
    return buf.getvalue()


def _extraer(fuente: Path, patron: str) -> str:
    """Saca el cuerpo de la funcion de input del archivo fuente del frontend."""
    texto = fuente.read_text(encoding="utf-8")
    m = re.search(patron, texto, re.S)
    if not m:
        pytest.fail(f"no se encontro la funcion de input en {fuente.name}")
    # El Python vive dentro de un template literal de JS: los backticks y los
    # `\n` van escapados. Se desescapan para poder ejecutarlo.
    return m.group(1).replace("\\`", "`").replace("\\\\n", "\\n")


def _correr_con_feed(cuerpo_feed: str) -> str:
    """Ejecuta PROGRAMA usando el `input` que define `cuerpo_feed`.

    El cuerpo se compila tal cual sale del frontend, con `_out` y `_it` en el
    scope. Si el runner escribe el prompt, aparece en la salida; si lo tira, no.
    """
    out = io.StringIO()
    scope: dict = {"_out": out, "_it": iter(ENTRADA.split("\n")), "EOFError": EOFError}
    exec(compile(cuerpo_feed, "<feed>", "exec"), scope)  # noqa: S102
    fn = scope["_feed"]
    with contextlib.redirect_stdout(out):
        exec(compile(PROGRAMA, "<p>", "exec"), {"__name__": "__main__", "input": fn})  # noqa: S102
    return out.getvalue()


class TestElRunnerDelAlumno:
    """El frasco: `CodeEditor.tsx::_feed`."""

    def _feed_del_alumno(self) -> str:
        cuerpo = _extraer(
            _EDITOR_ALUMNO,
            r"(        def _feed\(prompt=\"\", _it=_lines, _out=buf\):.*?\n)\n",
        )
        # Se desindenta y se renombran los defaults para poder ejecutarlo suelto.
        cuerpo = "\n".join(linea[8:] for linea in cuerpo.split("\n"))
        return cuerpo.replace(
            'def _feed(prompt="", _it=_lines, _out=buf):', 'def _feed(prompt=""):'
        )

    def test_escribe_el_prompt_igual_que_cpython(self) -> None:
        """El corazon del fix.

        Verificado por reversion: sin el `_out.write(prompt)`, esto da
        `'1-2\\n'` en vez de `'Ingrese A: Ingrese B: 1-2\\n'` — le faltan los
        dos prompts, que es exactamente lo que el docente reporto.
        """
        assert _correr_con_feed(self._feed_del_alumno()) == _cpython_real()

    def test_NO_hace_eco_del_valor_tipeado(self) -> None:
        """Eso lo hace la terminal, no el programa.

        Si el runner lo agregara, la salida traeria los datos de entrada y
        volveria a no coincidir — en la direccion opuesta. Es el error que
        comete el modo interactivo (boton Ejecutar), donde SI corresponde
        porque simula una consola.
        """
        salida = _correr_con_feed(self._feed_del_alumno())

        assert "Ingrese A: Ingrese B: 1-2" in salida
        assert "Ingrese A: 1" not in salida


class TestElPanelDelDocente:
    """`pyodideRunner.ts::_fake_input`. Ya lo hacia bien — que siga."""

    def test_escribe_el_prompt_igual_que_cpython(self) -> None:
        texto = _PANEL_DOCENTE.read_text(encoding="utf-8")

        assert "out.write(str(prompt))" in texto, (
            "el panel dejo de escribir el prompt: el docente valida contra una "
            "salida que el alumno nunca va a producir"
        )


class TestLaParidadEsLaPropiedad:
    """Lo que importa no es que cada uno haga algo, sino que hagan LO MISMO."""

    def test_los_dos_runners_de_python_coinciden(self) -> None:
        """Si divergen, el docente valida en verde y el alumno recibe rojo — o
        al reves, que es peor porque nadie lo mira.

        Se compara el comportamiento del runner del alumno contra CPython, y se
        exige que el del docente declare la misma regla. No se ejecuta el del
        docente porque su Python asume `_pr_*` en el scope; su contrato se fija
        con el assert de arriba.
        """
        del_alumno = _correr_con_feed(TestElRunnerDelAlumno()._feed_del_alumno())

        assert del_alumno == _cpython_real()

    def test_java_manda_el_stdout_crudo(self) -> None:
        """El tercer runner. `map_case` pasa `got=result.stdout` sin tocarlo,
        asi que el `System.out.print` del prompt viaja — igual que CPython.

        Si alguien algun dia le mete un filtro, este test lo dice.
        """
        mapper = (
            _RAIZ / "apps/execution-service/src/execution_service/services/result_mapper.py"
        ).read_text(encoding="utf-8")

        assert "got=result.stdout," in mapper
