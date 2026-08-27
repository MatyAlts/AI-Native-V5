/**
 * Orden causal de los eventos del editor en la cadena CTR (BUG-11).
 *
 * `codigo_ejecutado` / `tests_ejecutados` salen en el instante en que el alumno
 * aprieta el boton, pero el `edicion_codigo` del MISMO snapshot puede seguir
 * esperando hasta un segundo en el debounce del editor — y llegar despues. La
 * cadena termina entonces afirmando que el alumno ejecuto un codigo antes de
 * escribirlo, que es imposible, y esa linea de tiempo es la que alimenta CCD
 * (codigo-discurso) y CII (inter-iteracion) de la tesis.
 *
 * El orden se observa desde los callbacks del componente: el caller
 * (`EpisodePage`) los encola en la cola durable del CTR, que es FIFO, asi que
 * el orden de estas llamadas ES el orden de la cadena.
 */
import { act, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import type { ExecutionResult, TestCasePublic } from "../src/lib/api"
import { runRemote } from "../src/lib/runRemote"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"
import { type PyodideFake, instalarPyodideFake } from "./_pyodideFake"

vi.mock("../src/lib/runRemote", () => ({ runRemote: vi.fn() }))

const EJECUCION_OK: ExecutionResult = {
  outcome: "completed",
  total: 1,
  passed: 1,
  failed: 0,
  cases: [
    {
      id: "c1",
      name: "caso 1",
      type: "stdin_stdout",
      status: "pass",
      is_public: true,
      input: "",
      expected: "ok",
      got: "ok",
      error: null,
      weight: 1,
    },
  ],
  compile_output: "",
}

const CASOS_PUBLICOS: TestCasePublic[] = [
  { id: "c1", name: "caso 1", type: "stdin_stdout", code: "", expected: "ok", is_public: true },
]

let pyodide: PyodideFake | null = null

beforeEach(() => {
  resetMonacoMock()
  vi.mocked(runRemote).mockResolvedValue(EJECUCION_OK)
})

afterEach(() => {
  pyodide?.desinstalar()
  pyodide = null
})

async function esperarEditor(n: number) {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(n))
  const ed = editoresCreados[n - 1]
  if (!ed) throw new Error(`no hay editor #${n}`)
  return ed
}

describe("orden de eventos: edicion antes que ejecucion (BUG-11)", () => {
  it("'Ejecutar' emite el edicion_codigo pendiente ANTES del codigo_ejecutado", async () => {
    const orden: string[] = []
    render(
      <CodeEditor
        initialCode="class Main {}"
        language="java"
        ejercicioId="ej-1"
        onEditDebounced={() => orden.push("edicion_codigo")}
        onCodeExecuted={() => orden.push("codigo_ejecutado")}
      />,
    )
    const ed = await esperarEditor(1)
    act(() => {
      ed.__tipear("class Main { int x = 1; }")
    })
    // El debounce (1s) sigue corriendo: todavia no salio nada.
    expect(orden).toEqual([])

    await act(async () => {
      screen.getByRole("button", { name: /^Ejecutar codigo/ }).click()
    })
    await waitFor(() => expect(orden).toContain("codigo_ejecutado"))

    expect(orden).toEqual(["edicion_codigo", "codigo_ejecutado"])
  })

  it("'Probar' emite el edicion_codigo pendiente ANTES del tests_ejecutados", async () => {
    pyodide = instalarPyodideFake()
    pyodide.resultadosDeTests = [
      {
        id: "c1",
        name: "caso 1",
        type: "stdin_stdout",
        passed: true,
        expected: "ok",
        actual: "ok",
        stdin: "",
        error: null,
      },
    ]
    const orden: string[] = []
    render(
      <CodeEditor
        initialCode="x = 0"
        language="python"
        testCases={CASOS_PUBLICOS}
        onEditDebounced={() => orden.push("edicion_codigo")}
        onTestsRun={() => orden.push("tests_ejecutados")}
      />,
    )
    const ed = await esperarEditor(1)
    // Esperar a que el runtime quede listo (sino el boton esta deshabilitado).
    await waitFor(() =>
      expect((screen.getByTestId("run-tests-button") as HTMLButtonElement).disabled).toBe(false),
    )
    act(() => {
      ed.__tipear("x = 1")
    })
    expect(orden).toEqual([])

    await act(async () => {
      screen.getByTestId("run-tests-button").click()
    })
    await waitFor(() => expect(orden).toContain("tests_ejecutados"))

    expect(orden).toEqual(["edicion_codigo", "tests_ejecutados"])
  })

  it("el flush no duplica: el debounce vencido despues de la corrida no re-emite", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const onEditDebounced = vi.fn()
      render(
        <CodeEditor
          initialCode="class Main {}"
          language="java"
          ejercicioId="ej-1"
          onEditDebounced={onEditDebounced}
        />,
      )
      const ed = await esperarEditor(1)
      act(() => {
        ed.__tipear("class Main { int x = 1; }")
      })
      await act(async () => {
        screen.getByRole("button", { name: /^Ejecutar codigo/ }).click()
      })
      await vi.advanceTimersByTimeAsync(3000)
      expect(onEditDebounced).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it("sin ediciones pendientes, ejecutar no inventa un edicion_codigo", async () => {
    // El flush no puede convertirse en una fuente de eventos falsos: si el
    // buffer no cambio desde la ultima emision, no hay nada que emitir.
    const onEditDebounced = vi.fn()
    render(
      <CodeEditor
        initialCode="class Main {}"
        language="java"
        ejercicioId="ej-1"
        onEditDebounced={onEditDebounced}
      />,
    )
    await esperarEditor(1)
    await act(async () => {
      screen.getByRole("button", { name: /^Ejecutar codigo/ }).click()
    })
    expect(onEditDebounced).not.toHaveBeenCalled()
  })
})
