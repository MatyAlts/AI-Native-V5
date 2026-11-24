/**
 * Apoyo del constructor (HU-032, no es aceptación): el paso a paso resalta en
 * Monaco la línea de la próxima instrucción y la saca al detenerse.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

vi.mock("../src/lib/runRemote", () => ({ runRemote: vi.fn() }))

const FUENTE = `Algoritmo a
	Definir x Como Entero
	x <- 1
FinAlgoritmo
`

beforeEach(() => resetMonacoMock())

async function click(nombre: RegExp) {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: nombre }))
  })
}

const resaltadas = () =>
  editoresCreados[0]!.__decoraciones
    .filter((d) => d.options.isWholeLine)
    .map((d) => d.range.startLineNumber)

describe("resaltado de la línea en el editor", () => {
  it("sigue a la próxima instrucción y se va al detener", async () => {
    render(<CodeEditor initialCode={FUENTE} language={"pseint" as never} />)
    await waitFor(() => expect(editoresCreados.length).toBe(1))
    await click(/^Paso a paso/)
    await waitFor(() => expect(resaltadas()).toEqual([2]))
    await click(/^Siguiente paso/)
    await waitFor(() => expect(resaltadas()).toEqual([3]))
    expect(editoresCreados[0]!.__lineasReveladas).toEqual([2, 3])
    await click(/^Detener/)
    await waitFor(() => expect(resaltadas()).toEqual([]))
  })

  it("al terminar no queda ninguna línea resaltada", async () => {
    render(<CodeEditor initialCode={FUENTE} language={"pseint" as never} />)
    await waitFor(() => expect(editoresCreados.length).toBe(1))
    await click(/^Paso a paso/)
    await click(/^Continuar/)
    await waitFor(() => expect(screen.getByText(/terminó/i)).toBeTruthy())
    expect(resaltadas()).toEqual([])
  })
})
