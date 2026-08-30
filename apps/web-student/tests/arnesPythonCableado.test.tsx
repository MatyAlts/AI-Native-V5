/**
 * El arnes Python sigue enchufado al editor despues de mudarse a su `.py`.
 *
 * El grueso del arnes se prueba con CPython, sin navegador, en
 * `apps/web-student/tests/unit/test_arnes_python.py`. Lo que esos tests NO
 * pueden ver es el cable: que `CodeEditor` le mande a Pyodide EXACTAMENTE ese
 * texto, entero, antes de dejar correr al alumno. Una extraccion que se
 * "olvide" de mandarlo deja los 46 tests de Python en verde y el editor roto —
 * `__tutor_run_student_code is not defined` en la primera corrida.
 *
 * Por eso los asserts son sobre identidad del texto, no sobre pedacitos: si
 * mañana alguien filtra, recorta o interpola el arnes antes de mandarlo, esto
 * cae.
 */
import { render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import { ARNES_PYTHON, TIMEOUT_EJECUCION_SEGUNDOS } from "../src/lib/arnesPython"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"
import { type PyodideFake, instalarPyodideFake } from "./_pyodideFake"

let pyodide: PyodideFake | null = null

beforeEach(() => {
  resetMonacoMock()
  pyodide = instalarPyodideFake()
})

afterEach(() => {
  pyodide?.desinstalar()
  pyodide = null
})

async function montarEditorPython() {
  render(<CodeEditor initialCode="print('hola')" language="python" testCases={[]} />)
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
  await waitFor(() => expect(pyodide?.codigosEjecutados.length).toBeGreaterThan(0))
}

describe("el arnes Python que recibe Pyodide", () => {
  it("es el texto del .py, entero y sin retoques", async () => {
    await montarEditorPython()
    expect(pyodide?.codigosEjecutados).toContain(ARNES_PYTHON)
  })

  it("es lo UNICO que se ejecuta en el bootstrap", async () => {
    // El editor mandaba cuatro bloques; ahora manda uno. Si alguien vuelve a
    // partirlo —o deja un quinto script suelto en el `.tsx`— el arnes deja de
    // estar todo en el archivo que CPython prueba, y esto lo avisa.
    await montarEditorPython()
    expect(pyodide?.codigosEjecutados).toEqual([ARNES_PYTHON])
  })

  it("trae las tres entradas que el editor invoca despues", async () => {
    // El resto del componente llama a estos nombres por string. Que existan en
    // el texto es la unica atadura entre las dos mitades.
    await montarEditorPython()
    expect(ARNES_PYTHON).toContain("def __tutor_run_student_code(")
    expect(ARNES_PYTHON).toContain("def __tutor_run_tests(")
    expect(ARNES_PYTHON).toContain("__tutor_builtins.input = __tutor_input")
  })
})

describe("TIMEOUT_EJECUCION_SEGUNDOS", () => {
  it("sale del .py y no de una copia escrita a mano de este lado", () => {
    expect(TIMEOUT_EJECUCION_SEGUNDOS).toBe(5)
    expect(ARNES_PYTHON).toContain(`_TUTOR_TIMEOUT_SECONDS = ${TIMEOUT_EJECUCION_SEGUNDOS}.0`)
  })

  it("es un numero util, no un NaN silencioso", () => {
    // Un regex que deje de matchear tira al importar; lo que este assert cuida
    // es el escalon de antes: que el grupo capturado sea parseable.
    expect(Number.isFinite(TIMEOUT_EJECUCION_SEGUNDOS)).toBe(true)
    expect(TIMEOUT_EJECUCION_SEGUNDOS).toBeGreaterThan(0)
  })
})
