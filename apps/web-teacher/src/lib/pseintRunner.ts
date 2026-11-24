/**
 * "Probar ejercicio" del docente para PSeInt (HU-030, C06): corre TODOS los
 * casos (publicos y ocultos) en el navegador, con el mismo interprete que usa
 * el alumno (`@platform/pseint`). No llama al servidor (N05) y no carga
 * Pyodide.
 *
 * Devuelve la misma forma que `pyodideRunner.runTestCases`, asi el panel no
 * distingue de donde vino el resultado. La comparacion es `salidaCoincide`,
 * la misma normalizacion que usan Python y el execution-service.
 */
import { salidaCoincide } from "@platform/contracts/comparacion-salida"
import { ejecutarConEntrada } from "@platform/pseint"
import type { TestCaseEjercicio } from "./api"
import type { TestCaseRunResult } from "./pyodideRunner"

const TIPO_NO_EJECUTABLE = "PSeInt solo tiene casos de entrada y salida (stdin_stdout)."

export async function runTestCasesPseint(
  code: string,
  testCases: TestCaseEjercicio[],
): Promise<TestCaseRunResult[]> {
  const resultados: TestCaseRunResult[] = []
  for (const tc of testCases) {
    const base = {
      id: tc.id,
      name: tc.name,
      type: tc.type,
      input: tc.code ?? "",
      expected: tc.expected ?? null,
      weight: tc.weight,
    }
    if (tc.type !== "stdin_stdout") {
      resultados.push({
        ...base,
        status: "skipped",
        got: "",
        comparacion: "",
        error: TIPO_NO_EJECUTABLE,
      })
      continue
    }
    const r = await ejecutarConEntrada(code, tc.code ?? "")
    if (r.estado !== "ok") {
      resultados.push({
        ...base,
        status: "error",
        got: r.salida,
        comparacion: r.salida,
        error: r.error ? `Línea ${r.error.linea}: ${r.error.mensaje}` : "Error de ejecución.",
      })
      continue
    }
    resultados.push({
      ...base,
      status: salidaCoincide(r.salida, tc.expected) ? "pass" : "fail",
      got: r.salida,
      comparacion: r.salida,
      error: null,
    })
  }
  return resultados
}
