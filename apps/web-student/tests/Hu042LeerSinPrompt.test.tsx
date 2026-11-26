/**
 * Aceptación HU-042 (orquestador, antes de construir; el constructor no la
 * modifica). `Leer` de PSeInt sin `window.prompt`.
 *
 * Hoy "Ejecutar" y "Paso a paso" de PSeInt piden cada `Leer` con
 * `window.prompt` (`CodeEditor.tsx`, `entradaSalidaPseint().leer`): el diálogo
 * nativo congela la página entera mientras espera.
 *
 * C04  Correr un programa PSeInt con `Leer`:
 *      - NO llama a `window.prompt` (ni en Ejecutar ni en Paso a paso).
 *      - Aparece en el panel de salida (dentro de `code-editor-root` y FUERA
 *        del contenedor de Monaco `code-editor-container`) un campo de
 *        entrada con `aria-label="Dato para Leer"`.
 *      - Mientras espera, la consola ya muestra lo que el programa escribió
 *        antes del `Leer`.
 *      - Escribir un valor y apretar Enter hace que el programa siga: la
 *        salida (la que llega a `onCodeExecuted` y la que se ve) tiene el eco
 *        del valor y el resultado; el campo deja de pedir dato (desaparece o
 *        queda deshabilitado).
 *      - En Paso a paso: no llama a `window.prompt`, pide el dato con el
 *        mismo campo y el valor llega a la prueba de escritorio.
 *
 * Contrato: input accesible por `getByLabelText("Dato para Leer")`; Enter
 * (keyDown key="Enter") confirma el valor escrito.
 *
 * Python queda como está: no se afirma nada sobre su `input()`.
 *
 * Ojo: `hu030Pseint.test.tsx` (C03) y `hu032PasoAPaso.test.tsx` (C09) afirman
 * hoy que `Leer` usa `window.prompt`; esta historia los contradice y el
 * orquestador decide cómo actualizarlos (el constructor no los toca).
 */
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

vi.mock("../src/lib/runRemote", () => ({ runRemote: vi.fn() }))

const DOBLE = `Algoritmo doble
	Definir n Como Entero
	Escribir "Ingrese un numero:"
	Leer n
	Escribir "El doble es ", n * 2
FinAlgoritmo
`

const ROTULO = "Dato para Leer"

let promptOriginal: typeof window.prompt
let promptEspia: ReturnType<typeof vi.fn>

beforeEach(() => {
  resetMonacoMock()
  promptOriginal = window.prompt
  // Si la implementación siguiera usando el diálogo nativo, este espía lo
  // registra (y contesta otra cosa, para que el resultado no coincida).
  promptEspia = vi.fn(() => "99")
  window.prompt = promptEspia as unknown as typeof window.prompt
})

afterEach(() => {
  window.prompt = promptOriginal
})

async function esperarEditor() {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
}

async function click(re: RegExp) {
  const b = screen.queryByRole("button", { name: re }) as HTMLButtonElement | null
  expect(b, `falta el botón ${re}`).not.toBeNull()
  await act(async () => {
    fireEvent.click(b!)
  })
}

async function campoDeLeer(): Promise<HTMLInputElement> {
  await waitFor(
    () => {
      expect(promptEspia).not.toHaveBeenCalled()
      expect(screen.queryByLabelText(ROTULO)).not.toBeNull()
    },
    { timeout: 2000 },
  )
  const campo = screen.getByLabelText(ROTULO) as HTMLInputElement
  // En el panel de salida: adentro del editor, afuera de Monaco.
  const raiz = screen.getByTestId("code-editor-root")
  expect(raiz.contains(campo)).toBe(true)
  expect(screen.getByTestId("code-editor-container").contains(campo)).toBe(false)
  return campo
}

async function responder(campo: HTMLInputElement, valor: string) {
  await act(async () => {
    fireEvent.change(campo, { target: { value: valor } })
  })
  await act(async () => {
    fireEvent.keyDown(campo, { key: "Enter", code: "Enter" })
  })
}

function yaNoPideDato() {
  const campo = screen.queryByLabelText(ROTULO) as HTMLInputElement | null
  expect(campo === null || campo.disabled).toBe(true)
}

describe("HU-042 C04 · Ejecutar PSeInt pide el Leer en el panel, sin window.prompt", () => {
  it("muestra el campo, sigue al apretar Enter y la salida tiene el eco y el resultado", async () => {
    const onCodeExecuted = vi.fn()
    render(
      <CodeEditor
        initialCode={DOBLE}
        language={"pseint" as never}
        ejercicioId="ej-1"
        testCases={[]}
        onCodeExecuted={onCodeExecuted}
      />,
    )
    await esperarEditor()
    await click(/^Ejecutar/)

    const campo = await campoDeLeer()
    // Esperando el dato: lo escrito antes del Leer ya está en la consola, y el
    // programa todavía no terminó.
    expect(
      within(screen.getByTestId("code-editor-root")).getAllByText(/Ingrese un numero:/).length,
    ).toBeGreaterThan(0)
    expect(onCodeExecuted).not.toHaveBeenCalled()

    await responder(campo, "21")

    await waitFor(() => expect(onCodeExecuted).toHaveBeenCalledTimes(1))
    const r = onCodeExecuted.mock.calls[0]![0]
    expect(r.error).toBeNull()
    // Eco del valor en su propia línea, antes del resultado.
    expect(r.output).toMatch(/Ingrese un numero:\s*\n?21\n[\s\S]*El doble es 42/)
    await waitFor(() => expect(screen.getAllByText(/El doble es 42/).length).toBeGreaterThan(0))
    yaNoPideDato()
    expect(promptEspia).not.toHaveBeenCalled()
  })
})

describe("HU-042 C04 · Paso a paso pide el Leer en el panel, sin window.prompt", () => {
  it("en el paso del Leer aparece el campo y el valor llega a la prueba de escritorio", async () => {
    render(<CodeEditor initialCode={DOBLE} language={"pseint" as never} />)
    await esperarEditor()
    await click(/^Paso a paso/)
    await click(/^Siguiente paso/) // Definir
    await click(/^Siguiente paso/) // Escribir
    expect(screen.queryByLabelText(ROTULO)).toBeNull()
    // El click no se espera entero: el paso queda colgado esperando el dato.
    const siguiente = screen.getByRole("button", { name: /^Siguiente paso/ })
    act(() => {
      fireEvent.click(siguiente)
    }) // Leer

    const campo = await campoDeLeer()
    await responder(campo, "21")

    await waitFor(() => {
      const celdas = within(screen.getByRole("table", { name: /prueba de escritorio/i }))
        .getAllByRole("cell")
        .map((c) => c.textContent?.trim())
      expect(celdas).toContain("21")
    })
    expect(promptEspia).not.toHaveBeenCalled()
  })
})
