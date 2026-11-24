/**
 * Aceptación HU-031 (orquestador, antes de construir; el constructor no la
 * modifica). Criterios acordados el 24/11/2026 (Juani delegó criterios y
 * aceptación).
 *
 * C03  El editor de PSeInt tiene una pestaña "Diagrama" con el diagrama del
 *      código del alumno, que se actualiza mientras escribe.
 * C04  Con un error de sintaxis se conserva el último diagrama válido y se
 *      avisa la línea del error.
 * N02  Python y Java no tienen la pestaña.
 * N03  Mirar el diagrama no emite nada (ni ejecución, ni pruebas).
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

vi.mock("../src/lib/runRemote", () => ({ runRemote: vi.fn() }))

const DOBLE = `Algoritmo doble
	Definir n Como Entero
	Leer n
	Escribir n * 2
FinAlgoritmo
`

beforeEach(() => {
  resetMonacoMock()
})

async function esperarEditor() {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
}

function pestanaDiagrama(): HTMLElement | null {
  return screen.queryByRole("tab", { name: /^Diagrama/ }) ?? screen.queryByRole("button", { name: /^Diagrama/ })
}

async function abrirDiagrama() {
  const p = pestanaDiagrama()
  expect(p, "falta la pestaña Diagrama").not.toBeNull()
  await act(async () => {
    fireEvent.click(p!)
  })
}

describe("C03 diagrama del código del alumno", () => {
  it("la pestaña muestra el diagrama del código", async () => {
    const { container } = render(<CodeEditor initialCode={DOBLE} language={"pseint" as never} />)
    await esperarEditor()
    await abrirDiagrama()
    await waitFor(() => expect(container.querySelectorAll('svg[role="img"]').length).toBe(1))
    expect(container.querySelector('g[data-tipo="entrada"]')).not.toBeNull()
  })

  it("se actualiza mientras escribe", async () => {
    const { container } = render(<CodeEditor initialCode={DOBLE} language={"pseint" as never} />)
    await esperarEditor()
    await abrirDiagrama()
    await waitFor(() => expect(container.querySelectorAll('g[data-tipo="salida"]').length).toBe(1))
    const nuevo = DOBLE.replace("FinAlgoritmo", '\tEscribir "chau"\nFinAlgoritmo')
    await act(async () => {
      editoresCreados[0]!.__tipear(nuevo)
    })
    await waitFor(() => expect(container.querySelectorAll('g[data-tipo="salida"]').length).toBe(2), { timeout: 3000 })
  })
})

describe("C04 error de sintaxis mientras escribe", () => {
  it("conserva el último diagrama válido y avisa la línea", async () => {
    const { container } = render(<CodeEditor initialCode={DOBLE} language={"pseint" as never} />)
    await esperarEditor()
    await abrirDiagrama()
    await waitFor(() => expect(container.querySelectorAll('svg[role="img"]').length).toBe(1))
    await act(async () => {
      editoresCreados[0]!.__tipear(DOBLE.replace("Escribir n * 2", 'Escribir "sin cerrar'))
    })
    await waitFor(() => expect(screen.getByText(/l[ií]nea 4/i)).toBeTruthy(), { timeout: 3000 })
    expect(container.querySelectorAll('svg[role="img"]').length).toBe(1)
    expect(container.querySelector('g[data-tipo="salida"]')).not.toBeNull()
  })
})

describe("N02/N03", () => {
  it("Python no tiene pestaña Diagrama", async () => {
    render(<CodeEditor initialCode="print(1)" language="python" />)
    await esperarEditor()
    expect(pestanaDiagrama()).toBeNull()
  })

  it("Java no tiene pestaña Diagrama", async () => {
    render(<CodeEditor initialCode="class Main {}" language="java" ejercicioId="ej-1" />)
    await esperarEditor()
    expect(pestanaDiagrama()).toBeNull()
  })

  it("mirar el diagrama no ejecuta ni prueba nada", async () => {
    const onCodeExecuted = vi.fn()
    const onTestsRun = vi.fn()
    render(
      <CodeEditor
        initialCode={DOBLE}
        language={"pseint" as never}
        onCodeExecuted={onCodeExecuted}
        onTestsRun={onTestsRun}
      />,
    )
    await esperarEditor()
    await abrirDiagrama()
    await new Promise((r) => setTimeout(r, 1200))
    expect(onCodeExecuted).not.toHaveBeenCalled()
    expect(onTestsRun).not.toHaveBeenCalled()
  })
})
