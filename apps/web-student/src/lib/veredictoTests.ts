/**
 * JAVA-1 / H2: quien decide si un caso de prueba de Python PASA.
 *
 * Por que esto vive acá y no inline en `CodeEditor`
 * ------------------------------------------------
 * El runner Pyodide (`__tutor_run_tests`, embebido en `CodeEditor`) devuelve
 * `passed: False` FIJO para los casos `stdin_stdout` — es un placeholder
 * deliberado: el runner corre el codigo y captura la salida, pero la
 * comparacion la hace el lado JS con `salidaCoincide`, que es la MISMA
 * normalizacion que el execution-service aplica a Java. Tener una sola
 * implementacion del criterio es lo que mantiene a los dos lenguajes en
 * paridad.
 *
 * Consecuencia: el veredicto REAL de todos los casos de Python lo pone esta
 * funcion. Y de acá sale el conteo que `onTestsRun` manda al CTR como
 * `tests_ejecutados` — el evento del que el labeler deriva N3 vs N4. Si esto
 * se rompe, cada caso de Python reporta fallado y la evidencia del piloto
 * queda mal etiquetada, sin que nada explote.
 *
 * Mientras la logica vivia dentro del `.map()` del componente no habia forma
 * de ejercitarla sin montar Monaco + Pyodide, y de hecho no la ejercitaba
 * nadie: reemplazar el map por la identidad dejaba los 274 tests en verde.
 * Sacarla a una funcion PURA exportada es lo que permite anclarla.
 */

import { salidaCoincide } from "./comparacionSalida"

/** Resultado por caso de una corrida de tests (F1). Espejo del dict que arma
 * el runner Python `__tutor_run_tests`. */
export interface TestCaseResult {
  id: string | null
  name: string | null
  type: "stdin_stdout" | "pytest_assert"
  passed: boolean
  expected: string | null
  actual: string
  stdin: string
  error: string | null
}

/**
 * Aplica el veredicto local a lo que devolvio el runner Pyodide. Funcion PURA:
 * no muta la entrada, devuelve una lista nueva.
 *
 * Solo se re-evaluan los casos `stdin_stdout` que terminaron SIN error. Los
 * dos recortes importan:
 *
 *  - `pytest_assert` ya trae su veredicto del runner (lo da el `assert` de
 *    Python, no una comparacion de salida). Pisarlo seria inventar.
 *  - un caso que murio con excepcion, timeout o EOF fallo por otra razon y su
 *    `actual` esta truncado; compararlo contra `expected` daria un veredicto
 *    derivado de una salida incompleta.
 */
export function resolverVeredictosPython(resultados: readonly TestCaseResult[]): TestCaseResult[] {
  return resultados.map((r) =>
    r.type === "stdin_stdout" && r.error === null
      ? { ...r, passed: salidaCoincide(r.actual, r.expected) }
      : r,
  )
}

/** Conteos que viajan al CTR en `tests_ejecutados`. Funcion PURA. */
export interface ConteoTests {
  total: number
  passed: number
  failed: number
  failedNames: string[]
}

/**
 * Deriva los conteos del evento a partir de los resultados YA veredictados.
 *
 * Va junto al veredicto a proposito: `total`/`passed`/`failed` es lo que el
 * labeler lee, y separarlo del criterio que lo produce es como se termina con
 * dos definiciones de "paso".
 */
export function contarTests(resultados: readonly TestCaseResult[]): ConteoTests {
  const passed = resultados.filter((r) => r.passed).length
  return {
    total: resultados.length,
    passed,
    failed: resultados.length - passed,
    failedNames: resultados.filter((r) => !r.passed).map((r) => r.name ?? r.id ?? "test"),
  }
}
