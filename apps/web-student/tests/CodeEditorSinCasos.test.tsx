/**
 * "Ejecutar" sobre un ejercicio remoto SIN casos de prueba.
 *
 * En un lenguaje remoto (Java, ADR-060) "Ejecutar" y "Probar" son la MISMA
 * llamada: las dos postean a `/executions` con `{ejercicio_id, source_code}` y
 * el servidor corre los casos. "Probar" tenia el guard `hasTests`; "Ejecutar"
 * no. Con `test_cases: []` —que el contrato admite— la corrida no ejecuta nada
 * (el servidor itera sobre la lista de casos) y devuelve
 * `total=0, passed=0, failed=0`. El labeler lee `failed == 0` como "paso todo"
 * y etiqueta N4 un episodio donde el codigo del alumno nunca corrio.
 *
 * El alumno no pierde nada: hoy apretar el boton le devuelve la consola vacia,
 * porque no hay ningun caso cuyo stdout mostrar. Lo unico que producia era el
 * evento.
 *
 * El backend cierra el mismo agujero del lado del servidor. Esto evita que la
 * peticion salga siquiera — y que consuma cuota, que en remoto se cobra.
 */
import { act, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import type { ExecutionResult, TestCasePublic } from "../src/lib/api"
import { runRemote } from "../src/lib/runRemote"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"
import { type PyodideFake, instalarPyodideFake } from "./_pyodideFake"

vi.mock("../src/lib/runRemote", () => ({ runRemote: vi.fn() }))

/** Lo que devuelve el servidor cuando el ejercicio no tiene ni un caso. */
const EJECUCION_SIN_CASOS: ExecutionResult = {
  outcome: "completed",
  total: 0,
  passed: 0,
  failed: 0,
  cases: [],
  compile_output: "",
}

const UN_CASO: TestCasePublic[] = [
  { id: "c1", name: "caso 1", type: "stdin_stdout", code: "", expected: "ok", is_public: true },
]

let pyodide: PyodideFake | null = null

beforeEach(() => {
  resetMonacoMock()
  // Los contadores del mock NO se limpian solos entre tests. Sin esto, si el
  // primer test empieza a llamar a `runRemote` (o sea: si el guard se rompe),
  // el `toHaveBeenCalledTimes(1)` del tercero tambien falla — y el rojo
  // aparecerja en el test equivocado.
  vi.mocked(runRemote).mockReset()
  vi.mocked(runRemote).mockResolvedValue(EJECUCION_SIN_CASOS)
})

afterEach(() => {
  pyodide?.desinstalar()
  pyodide = null
})

async function esperarEditor() {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
}

const botonEjecutar = () =>
  screen.getByRole("button", { name: /^Ejecutar/ }) as HTMLButtonElement

describe("Ejecutar en remoto sin casos de prueba", () => {
  it("no manda la corrida (ni con el boton ni con el atajo)", async () => {
    const onCodeExecuted = vi.fn()
    render(
      <CodeEditor
        initialCode="class Main {}"
        language="java"
        ejercicioId="ej-1"
        testCases={[]}
        onCodeExecuted={onCodeExecuted}
      />,
    )
    await esperarEditor()

    await act(async () => {
      botonEjecutar().click()
    })
    // El atajo de teclado NO pasa por el boton deshabilitado: es el camino que
    // se cuela si el guard vive solo en el `disabled`.
    const ed = editoresCreados[0]
    if (!ed) throw new Error("no se creo el editor")
    const atajo = ed.__comandos.get(2048 | 3) // CtrlCmd | Enter
    if (!atajo) throw new Error("no se registro Ctrl+Enter")
    await act(async () => {
      atajo()
    })

    expect(runRemote).not.toHaveBeenCalled()
    expect(onCodeExecuted).not.toHaveBeenCalled()
  })

  it("el boton queda deshabilitado y dice por que", async () => {
    render(
      <CodeEditor initialCode="class Main {}" language="java" ejercicioId="ej-1" testCases={[]} />,
    )
    await esperarEditor()
    expect(botonEjecutar().disabled).toBe(true)
    expect(botonEjecutar().title).toMatch(/no tiene casos de prueba/i)
  })

  it("con al menos un caso publico, 'Ejecutar' vuelve a andar", async () => {
    // El guard no puede cerrarle la puerta al ejercicio normal.
    const onCodeExecuted = vi.fn()
    render(
      <CodeEditor
        initialCode="class Main {}"
        language="java"
        ejercicioId="ej-1"
        testCases={UN_CASO}
        onCodeExecuted={onCodeExecuted}
      />,
    )
    await esperarEditor()
    expect(botonEjecutar().disabled).toBe(false)
    await act(async () => {
      botonEjecutar().click()
    })
    expect(runRemote).toHaveBeenCalledTimes(1)
  })
})

describe("Ejecutar en local sigue sin pedir casos", () => {
  it("Python sin test_cases ejecuta igual: no hay tests de por medio", async () => {
    // En Pyodide "Ejecutar" corre el codigo suelto del alumno y le muestra su
    // stdout. No emite conteo de tests, asi que no puede inventar un "paso
    // todo". Pedirle casos seria romperle la herramienta principal al alumno.
    pyodide = instalarPyodideFake()
    const onCodeExecuted = vi.fn()
    render(
      <CodeEditor
        initialCode="print('hola')"
        language="python"
        testCases={[]}
        onCodeExecuted={onCodeExecuted}
      />,
    )
    await esperarEditor()
    await waitFor(() => expect(botonEjecutar().disabled).toBe(false))
    await act(async () => {
      botonEjecutar().click()
    })
    await waitFor(() => expect(onCodeExecuted).toHaveBeenCalledTimes(1))
  })
})
