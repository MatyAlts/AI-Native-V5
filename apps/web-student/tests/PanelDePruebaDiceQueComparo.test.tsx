/**
 * El panel de pruebas muestra lo que SE COMPARO, no lo que se vio en pantalla.
 *
 * EL CASO REAL (2026-10-02, en produccion)
 * ------------------------------------------
 * Un alumno con el `input()` puesto pero sin el `print()` vio esto:
 *
 *     Esperado   Desaprobado
 *     Obtenido   Ingrese su edad
 *
 * y concluyo —razonablemente— que la plataforma estaba rota. No lo estaba: lo
 * que se comparo fue la cadena VACIA, porque su programa no imprimio nada. El
 * `"Ingrese su edad"` es el prompt de `input()`, que desde la change
 * `comparacion-ignora-el-prompt-del-input` va al buffer de PANTALLA y no al de
 * comparacion.
 *
 * O sea: el panel exhibia `actual` (pantalla) mientras el veredicto se decidia
 * contra `comparacion`. Dos cosas distintas con la misma etiqueta, y el alumno
 * leyendo la que no explica nada.
 *
 * Y el mismo alumno ya habia reportado el sintoma en la encuesta del piloto,
 * antes de que existiera el buffer doble: *"no entiendo que es lo que muestra
 * la parte de prueba"*.
 *
 * POR QUE ESTE TEST EXISTE Y NO SOLO EL FIX
 * -------------------------------------------
 * Porque la revision de esa change declaro exactamente este hueco: *"ningun
 * test ejecuta la separacion real `buf`/`buf_comparacion` del lado alumno"* —
 * lo que habia era un test estructural, por regex sobre el codigo fuente del
 * harness de Pyodide. El hueco estaba escrito y mordio once dias despues.
 *
 * Este archivo SI ejecuta: monta el `CodeEditor` real, le inyecta por el fake
 * de Pyodide un resultado con los dos buffers distintos, aprieta "Probar", y
 * afirma sobre el DOM que el alumno termina viendo.
 */
import { act, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import type { TestCasePublic } from "../src/lib/api"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"
import { type PyodideFake, instalarPyodideFake } from "./_pyodideFake"

const CASOS: TestCasePublic[] = [
  {
    id: "c1",
    name: "desaprobado",
    type: "stdin_stdout",
    code: "4",
    expected: "Desaprobado",
    is_public: true,
  },
]

let pyodide: PyodideFake | null = null

beforeEach(() => {
  resetMonacoMock()
})

afterEach(() => {
  pyodide?.desinstalar()
  pyodide = null
  vi.restoreAllMocks()
})

/** Monta el editor, corre "Probar", y deja el panel de resultados en el DOM. */
async function correrPruebas(resultado: {
  actual: string
  comparacion: string
  passed: boolean
}): Promise<void> {
  pyodide = instalarPyodideFake()
  pyodide.resultadosDeTests = [
    {
      id: "c1",
      name: "desaprobado",
      type: "stdin_stdout",
      passed: resultado.passed,
      expected: "Desaprobado",
      actual: resultado.actual,
      comparacion: resultado.comparacion,
      stdin: "4",
      error: null,
    },
  ]

  render(<CodeEditor initialCode="x = 0" language="python" testCases={CASOS} />)
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
  await waitFor(() =>
    expect((screen.getByTestId("run-tests-button") as HTMLButtonElement).disabled).toBe(false),
  )
  await act(async () => {
    screen.getByTestId("run-tests-button").click()
  })
  await waitFor(() => expect(screen.getByText(/Esperado/i)).toBeTruthy())
}

describe("el caso real: input() sin print()", () => {
  const CASO_REAL = {
    actual: "Ingrese su edad: ",
    comparacion: "",
    passed: false,
  }

  it("dice que el programa no imprimio nada, en vez de mostrar el prompt como obtenido", async () => {
    await correrPruebas(CASO_REAL)
    // Esto es lo que explica el veredicto: se comparo la cadena vacia.
    expect(screen.getByText(/tu programa no imprimio nada/i)).toBeTruthy()
  })

  it("el prompt NO aparece como el valor obtenido", async () => {
    await correrPruebas(CASO_REAL)
    // El prompt sigue visible (abajo), pero no en la fila que el alumno lee
    // como "esto es lo que produjo mi programa".
    const obtenido = screen.getByText(/^Obtenido$/i).closest("div")
    expect(obtenido).toBeTruthy()
    expect(obtenido?.textContent ?? "").not.toContain("Ingrese su edad")
  })

  it("muestra la pantalla aparte, aclarando que el input() no se compara", async () => {
    await correrPruebas(CASO_REAL)
    expect(screen.getByText(/^En pantalla$/i)).toBeTruthy()
    expect(screen.getByText(/Ingrese su edad/)).toBeTruthy()
    expect(screen.getByText(/el texto de input\(\) no se compara/i)).toBeTruthy()
  })
})

describe("sin prompt, la fila de pantalla no aparece", () => {
  it("si lo comparado y la pantalla coinciden, no se muestra 'En pantalla'", async () => {
    // Un ejercicio sin `input()`: los dos buffers son iguales, asi que la fila
    // extra solo seria ruido. Mostrarla siempre es tan malo como no mostrarla
    // nunca — por eso el fix la condiciona a que difieran.
    await correrPruebas({ actual: "Aprobado", comparacion: "Aprobado", passed: false })
    expect(screen.queryByText(/^En pantalla$/i)).toBeNull()
    expect(screen.queryByText(/no se compara/i)).toBeNull()
  })

  it("un caso que pasa no muestra ni obtenido ni pantalla", async () => {
    // El detalle del fallo no tiene nada que explicar cuando no hubo fallo.
    await correrPruebas({ actual: "Desaprobado", comparacion: "Desaprobado", passed: true })
    expect(screen.queryByText(/^Obtenido$/i)).toBeNull()
    expect(screen.queryByText(/^En pantalla$/i)).toBeNull()
    // Lo esperado SI se sigue mostrando: es util ver contra que se compara
    // incluso cuando el caso anda.
    expect(screen.getByText(/^Esperado$/i)).toBeTruthy()
  })
})
