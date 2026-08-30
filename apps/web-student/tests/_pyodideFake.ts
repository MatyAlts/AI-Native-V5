/**
 * Doble de Pyodide para los tests del editor.
 *
 * `CodeEditor` carga Pyodide del CDN y, si no lo consigue, deja los controles
 * deshabilitados para siempre — con lo cual en jsdom no se puede apretar
 * "Ejecutar" ni "Probar". Instalando `window.loadPyodide` ANTES del render, el
 * componente toma este doble y salta la inyeccion del script.
 *
 * El doble ignora todos los scripts de bootstrap (watchdog, sandbox de
 * imports, runner de tests) y solo responde a la llamada real:
 * `__tutor_run_tests(...)` devuelve el JSON de resultados que se le configuro.
 * No ejecuta Python: lo que estos tests observan es el cableado del componente
 * (orden de los eventos, conteos que viajan al CTR), no la corrida.
 */

export interface ResultadoCasoFalso {
  id: string | null
  name: string | null
  type: "stdin_stdout" | "pytest_assert"
  passed: boolean
  expected: string | null
  actual: string
  stdin: string
  error: string | null
}

export interface PyodideFake {
  /** Resultados que devolvera la proxima llamada a `__tutor_run_tests`. */
  resultadosDeTests: ResultadoCasoFalso[]
  /** Todo lo que el componente le mando a `runPythonAsync`, en orden.
   * Lo usa `arnesPythonCableado.test.tsx` para verificar que al editor le
   * sigue llegando el arnes entero despues de que se mudo a su `.py`. */
  codigosEjecutados: string[]
  /** Deshace el parcheo de `window.loadPyodide`. */
  desinstalar(): void
}

export function instalarPyodideFake(): PyodideFake {
  const anterior = window.loadPyodide
  const control: PyodideFake = {
    resultadosDeTests: [],
    codigosEjecutados: [],
    desinstalar() {
      if (anterior) {
        window.loadPyodide = anterior
        return
      }
      // `exactOptionalPropertyTypes` no deja asignar `undefined` a una prop
      // opcional: hay que sacarla, que es justo el estado previo (no existia).
      window.loadPyodide = undefined as unknown as NonNullable<typeof window.loadPyodide>
    },
  }

  const api = {
    runPythonAsync: async (code: string): Promise<unknown> => {
      control.codigosEjecutados.push(code)
      if (code.includes("__tutor_run_tests(")) {
        return JSON.stringify(control.resultadosDeTests)
      }
      return undefined
    },
    setStdout: () => {},
    setStderr: () => {},
    setStdin: () => {},
    globals: { set: () => {} },
  }

  window.loadPyodide = async () =>
    api as unknown as Awaited<ReturnType<NonNullable<typeof window.loadPyodide>>>

  return control
}
