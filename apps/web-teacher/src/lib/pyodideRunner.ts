/**
 * Harness Pyodide para "Probar ejercicio" (F1, lado DOCENTE).
 *
 * Corre el codigo solucion (o un codigo de prueba) del docente contra los
 * test_cases de un ejercicio, dentro del navegador via WebAssembly. Es una
 * verificacion de autoria: el docente confirma que el ejercicio funciona ANTES
 * de asignarlo. NO emite eventos CTR — eso es exclusivo del alumno dentro de un
 * episodio (write-only al CTR desde tutor-service, ADR-010).
 *
 * Reusa el patron del `web-student/CodeEditor.tsx` (mismo CDN, misma version de
 * Pyodide, mismo watchdog por sys.settrace). NO importa de web-student: replica
 * lo minimo aca para no acoplar los frontends. La diferencia con el editor del
 * alumno es que aca corremos N test_cases en namespaces frescos y comparamos el
 * resultado contra el `expected` — el alumno solo corre su propio codigo suelto.
 *
 * Semantica de los dos tipos de test_case (contrato TestCaseSchema, ADR-034):
 *  - "pytest_assert": `code` son lineas de assert que referencian las
 *    clases/funciones definidas por la solucion (mismo archivo). Se ejecuta
 *    exec(solucion) y despues exec(asserts) en el MISMO namespace. Pasa si no
 *    salta ninguna excepcion. `expected` es null.
 *  - "stdin_stdout": `code` es la entrada (stdin, una linea por renglon) que se
 *    inyecta al programa; `expected` es la salida exacta esperada. Se ejecuta la
 *    solucion capturando stdout y se compara normalizado contra `expected`.
 *
 * Limitacion heredada del harness del alumno: el watchdog corta bucles a nivel
 * Python (sys.settrace por opcode), pero una unica llamada C larga no es
 * interrumpible. Aceptable para un preview del docente.
 */

const PYODIDE_VERSION = "0.26.3"
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`
// Presupuesto de computo por test_case (no de tiempo real: no hay input humano
// aca). Protege el tab del docente contra un bucle infinito en la solucion.
const CASE_TIMEOUT_SECONDS = 5

type PyodideAPI = {
  runPythonAsync(code: string): Promise<unknown>
  globals: { set(name: string, value: unknown): void }
}

type PyodideLoader = (options?: { indexURL?: string }) => Promise<PyodideAPI>

declare global {
  interface Window {
    loadPyodide?: PyodideLoader
  }
}

// Import del tipo del contrato de la vista (no hay dependencia de runtime con
// lib/api.ts — solo el shape del test_case).
export interface TestCaseLike {
  id: string
  name: string
  type: "stdin_stdout" | "pytest_assert" | "junit_assert"
  code: string
  expected: string | null
  is_public: boolean
  weight: number
}

/**
 * `skipped`: el caso no se corrio porque este runner es de Python y el tipo del
 * caso pertenece a otro lenguaje. Es un estado explicito y no un `fail`: un
 * caso que no se ejecuto no reprobo. Sin este estado, un `junit_assert` caia en
 * la rama de `stdin_stdout` y se comparaba su codigo de asserts contra el stdout
 * del programa, produciendo verdes y rojos que no significaban nada.
 */
export type TestCaseStatus = "pass" | "fail" | "error" | "skipped"

export interface TestCaseRunResult {
  id: string
  name: string
  type: "stdin_stdout" | "pytest_assert" | "junit_assert"
  status: TestCaseStatus
  /** entrada del caso: stdin (stdin_stdout) o los asserts (pytest_assert). */
  input: string
  /** salida esperada (solo stdin_stdout). */
  expected: string | null
  /** lo que efectivamente imprimio el programa (stdout capturado). */
  got: string
  /** mensaje de error/excepcion (ultima linea) si status === "error". */
  error: string | null
  weight: number
}

// Harness Python: define la funcion que corre UN caso y devuelve un JSON con
// {stdout, error}. Se ejecuta una sola vez al cargar el runtime.
const HARNESS_PY = `
import io as _pr_io
import sys as _pr_sys
import time as _pr_time
import json as _pr_json
import builtins as _pr_builtins
import traceback as _pr_tb

_PR_TIMEOUT = ${CASE_TIMEOUT_SECONDS}.0


class _PrTimeout(BaseException):
    pass


_pr_deadline = {"t": None}


def _pr_trace(frame, event, arg):
    # Tracing por opcode: dispara en cada bytecode para cortar tambien loops
    # apretados de una sola linea (ej. while True: pass).
    frame.f_trace_opcodes = True
    d = _pr_deadline["t"]
    if d is not None and _pr_time.monotonic() > d:
        raise _PrTimeout()
    return _pr_trace


def _pr_last_line(exc):
    parts = _pr_tb.format_exception_only(type(exc), exc)
    return parts[-1].strip() if parts else repr(exc)


def __probar_run_case(solution_code, test_code, stdin_text, mode):
    # Namespace fresco por caso (aislamiento entre tests). __name__ == __main__
    # para que el bloque if __name__ == "__main__": de la solucion corra.
    ns = {"__name__": "__main__"}
    out = _pr_io.StringIO()
    lines = stdin_text.split("\\n") if stdin_text else []
    pos = {"i": 0}

    def _fake_input(prompt=""):
        # CPython escribe el prompt a stdout (es salida del programa); el valor
        # tipeado NO va a stdout (seria echo de terminal). Replicamos eso.
        if prompt:
            out.write(str(prompt))
        if pos["i"] < len(lines):
            v = lines[pos["i"]]
            pos["i"] += 1
            return v
        raise EOFError(
            "El programa pidio mas entradas de las que provee el test (stdin agotado)"
        )

    real_stdout = _pr_sys.stdout
    real_input = _pr_builtins.input
    _pr_sys.stdout = out
    _pr_builtins.input = _fake_input
    _pr_deadline["t"] = _pr_time.monotonic() + _PR_TIMEOUT
    _pr_sys.settrace(_pr_trace)
    exc_msg = None
    try:
        exec(compile(solution_code, "<solucion>", "exec"), ns)
        if mode == "pytest_assert" and test_code.strip():
            exec(compile(test_code, "<test>", "exec"), ns)
    except _PrTimeout:
        exc_msg = (
            "TimeoutError: la ejecucion supero los %d segundos y fue interrumpida "
            "(posible bucle infinito)" % int(_PR_TIMEOUT)
        )
    except AssertionError as e:
        msg = str(e)
        exc_msg = "AssertionError: " + msg if msg else "AssertionError (un assert del test fallo)"
    except BaseException as e:  # noqa: BLE001 — el docente necesita ver cualquier error
        exc_msg = _pr_last_line(e)
    finally:
        _pr_sys.settrace(None)
        _pr_deadline["t"] = None
        _pr_sys.stdout = real_stdout
        _pr_builtins.input = real_input
    return _pr_json.dumps({"stdout": out.getvalue(), "error": exc_msg})
`

let runtimePromise: Promise<PyodideAPI> | null = null
let runtimeReady = false

/** True si Pyodide ya termino de cargar (para no mostrar "cargando" de mas). */
export function isPyodideRuntimeReady(): boolean {
  return runtimeReady
}

/**
 * Carga Pyodide desde el CDN una sola vez (singleton). Reintenta si fallo la
 * carga previa (deja runtimePromise en null en el catch).
 */
export function loadPyodideRuntime(): Promise<PyodideAPI> {
  if (runtimePromise) return runtimePromise
  runtimePromise = (async () => {
    if (!window.loadPyodide) {
      await new Promise<void>((resolve, reject) => {
        const script = document.createElement("script")
        script.src = `${PYODIDE_URL}pyodide.js`
        script.onload = () => resolve()
        script.onerror = () => reject(new Error("No se pudo cargar Pyodide desde el CDN"))
        document.head.appendChild(script)
      })
    }
    if (!window.loadPyodide) {
      throw new Error("Pyodide no quedo disponible tras cargar el script del CDN")
    }
    const py = await window.loadPyodide({ indexURL: PYODIDE_URL })
    await py.runPythonAsync(HARNESS_PY)
    runtimeReady = true
    return py
  })()
  runtimePromise.catch(() => {
    // Permitir un reintento en la proxima llamada.
    runtimePromise = null
    runtimeReady = false
  })
  return runtimePromise
}

// Normaliza salida para comparar: line endings, trailing whitespace por linea y
// bordes. Un espacio final o un \r\n no deberian marcar un test como fallado.
function normalize(s: string): string {
  return s
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((l) => l.replace(/\s+$/g, ""))
    .join("\n")
    .trim()
}

function evaluateCase(
  tc: TestCaseLike,
  parsed: { stdout: string; error: string | null },
): TestCaseRunResult {
  const base = {
    id: tc.id,
    name: tc.name,
    type: tc.type,
    input: tc.code,
    expected: tc.expected,
    weight: tc.weight,
  }
  if (parsed.error) {
    return { ...base, status: "error", got: parsed.stdout, error: parsed.error }
  }
  if (tc.type === "pytest_assert") {
    // Sin excepcion => todos los asserts pasaron.
    return { ...base, status: "pass", got: parsed.stdout, error: null }
  }
  // stdin_stdout: comparar stdout normalizado contra expected.
  const pass = normalize(parsed.stdout) === normalize(tc.expected ?? "")
  return { ...base, status: pass ? "pass" : "fail", got: parsed.stdout, error: null }
}

/**
 * Corre `solutionCode` contra cada test_case (secuencial, namespace fresco por
 * caso) y devuelve el resultado por caso. Carga Pyodide en la primera llamada.
 */
export async function runTestCases(
  solutionCode: string,
  testCases: TestCaseLike[],
): Promise<TestCaseRunResult[]> {
  const py = await loadPyodideRuntime()
  const results: TestCaseRunResult[] = []
  for (const tc of testCases) {
    // Este runner es Pyodide. Un caso de otro lenguaje NO se ejecuta ni se
    // aproxima: se declara no ejecutado. Correrlo por la rama de stdin_stdout
    // daria un veredicto que el docente leeria como valido.
    if (tc.type === "junit_assert") {
      results.push({
        id: tc.id,
        name: tc.name,
        type: tc.type,
        status: "skipped",
        input: tc.code,
        expected: tc.expected,
        got: "",
        error: "No hay entorno de ejecucion de Java todavia: este caso no se corrio.",
        weight: tc.weight,
      })
      continue
    }
    py.globals.set("__pr_solution", solutionCode)
    py.globals.set("__pr_test", tc.type === "pytest_assert" ? tc.code : "")
    py.globals.set("__pr_stdin", tc.type === "stdin_stdout" ? tc.code : "")
    py.globals.set("__pr_mode", tc.type)
    const raw = await py.runPythonAsync(
      "__probar_run_case(__pr_solution, __pr_test, __pr_stdin, __pr_mode)",
    )
    let parsed: { stdout: string; error: string | null }
    try {
      parsed = JSON.parse(String(raw)) as { stdout: string; error: string | null }
    } catch {
      parsed = { stdout: "", error: "No se pudo leer el resultado del runtime" }
    }
    results.push(evaluateCase(tc, parsed))
  }
  return results
}
