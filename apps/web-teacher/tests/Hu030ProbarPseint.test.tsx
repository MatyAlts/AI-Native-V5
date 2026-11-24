/**
 * Aceptación HU-030 (orquestador, antes de construir; el constructor no la
 * modifica). Criterios acordados con Juani el 24/11/2026.
 *
 * C01  El docente puede elegir PSeInt.
 * C06  El "Probar" del docente corre PSeInt en su navegador.
 * N05  Ese Probar no llama al servidor (antes, todo lo que no era Python iba
 *      al servidor: `esRemoto = lang !== DEFAULT_LANGUAGE`).
 * N01  Java sigue yendo al servidor; Python sigue en Pyodide.
 *
 * Contrato: `ProbarEjercicioPanel` se exporta desde `EjerciciosView`.
 */
import { act, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("../src/lib/api", async (original) => {
  const real = await original<typeof import("../src/lib/api")>()
  return { ...real, runRemoteTestCases: vi.fn() }
})
vi.mock("../src/lib/pyodideRunner", async (original) => {
  const real = await original<typeof import("../src/lib/pyodideRunner")>()
  return { ...real, runTestCases: vi.fn(async () => []), isPyodideRuntimeReady: () => true }
})

import { LANGUAGE_LABELS, type TestCaseEjercicio, runRemoteTestCases } from "../src/lib/api"
import { runTestCases } from "../src/lib/pyodideRunner"
import * as vista from "../src/views/EjerciciosView"

const DOBLE = `Algoritmo doble
	Definir n Como Entero
	Leer n
	Escribir n * 2
FinAlgoritmo
`

const CASOS: TestCaseEjercicio[] = [
  { id: "c1", name: "caso 1", type: "stdin_stdout", code: "3", expected: "6", is_public: true, weight: 1 },
  { id: "c2", name: "caso 2", type: "stdin_stdout", code: "10", expected: "20", is_public: false, weight: 1 },
]

beforeEach(() => {
  vi.mocked(runRemoteTestCases).mockReset()
  vi.mocked(runRemoteTestCases).mockResolvedValue({ outcome: "completed", total: 0, passed: 0, failed: 0, cases: [] } as never)
  vi.mocked(runTestCases).mockClear()
})

function panel() {
  const Panel = (vista as Record<string, unknown>).ProbarEjercicioPanel as
    | ((p: Record<string, unknown>) => JSX.Element)
    | undefined
  expect(Panel, "falta export ProbarEjercicioPanel en EjerciciosView").toBeTypeOf("function")
  return Panel as (p: Record<string, unknown>) => JSX.Element
}

describe("C01 PSeInt en los selectores", () => {
  it("LANGUAGE_LABELS ofrece PSeInt", () => {
    expect((LANGUAGE_LABELS as Record<string, string>).pseint).toBe("PSeInt")
  })
})

describe("C06/N05 Probar del docente en PSeInt", () => {
  it("corre en el navegador, con públicos y ocultos, sin llamar al servidor", async () => {
    const Panel = panel()
    render(<Panel testCases={CASOS} initialCode={DOBLE} collapsible={false} ejercicioId="ej-1" language="pseint" />)
    await act(async () => {
      screen.getByRole("button", { name: /Probar contra 2/ }).click()
    })
    await waitFor(() => expect(screen.getByText(/2\s*\/\s*2 test cases pasan/)).toBeTruthy())
    expect(runRemoteTestCases).not.toHaveBeenCalled()
    expect(runTestCases).not.toHaveBeenCalled()
    expect(screen.queryByText(/Cargando Python/)).toBeNull()
  })

  it("un algoritmo equivocado no pasa", async () => {
    const Panel = panel()
    render(
      <Panel
        testCases={CASOS}
        initialCode={DOBLE.replace("n * 2", "n * 3")}
        collapsible={false}
        ejercicioId="ej-1"
        language="pseint"
      />,
    )
    await act(async () => {
      screen.getByRole("button", { name: /Probar contra 2/ }).click()
    })
    await waitFor(() => expect(screen.getByText(/0\s*\/\s*2 test cases pasan/)).toBeTruthy())
    expect(runRemoteTestCases).not.toHaveBeenCalled()
  })
})

describe("N01 Java sigue en el servidor", () => {
  it("un ejercicio Java con id va al servidor", async () => {
    const Panel = panel()
    render(<Panel testCases={CASOS} initialCode="class Main {}" collapsible={false} ejercicioId="ej-1" language="java" />)
    await act(async () => {
      screen.getByRole("button", { name: /Probar contra 2/ }).click()
    })
    await waitFor(() => expect(runRemoteTestCases).toHaveBeenCalledTimes(1))
  })
})
