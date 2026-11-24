/**
 * Aceptación HU-030 (orquestador, antes de construir; el constructor no la
 * modifica). Criterios acordados con Juani el 24/11/2026.
 *
 * C02  El editor ofrece PSeInt con su rótulo y su código inicial.
 * C03  Ejecutar corre en el navegador: `Leer` pide el dato en el momento y la
 *      salida llega a la consola. No se llama al servidor.
 * C05  Probar corre los casos visibles en el navegador.
 * C09  La corrida informa su runtime (`pseint-ts-X.Y.Z`) para el CTR.
 * C10  Las descargas de PSeInt salen como `.psc`.
 * N01  Python y Java no cambian en lo que fijan estos tests.
 */
import { VERSION } from "@platform/pseint"
import { act, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import { LANGUAGE_LABELS, LANGUAGE_PLACEHOLDER, type TestCasePublic } from "../src/lib/api"
import { runRemote } from "../src/lib/runRemote"
import { rotuloDescarga } from "../src/utils/descargas"
import { buildEpisodioSourceFile } from "../src/utils/episodioDownload"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

vi.mock("../src/lib/runRemote", () => ({ runRemote: vi.fn() }))

const DOBLE = `Algoritmo doble
	Definir n Como Entero
	Escribir "Ingrese un numero:"
	Leer n
	Escribir "El doble es ", n * 2
FinAlgoritmo
`

const CASOS: TestCasePublic[] = [
  { id: "c1", name: "caso 1", type: "stdin_stdout", code: "3", expected: "Ingrese un numero:\nEl doble es 6", is_public: true },
  { id: "c2", name: "caso 2", type: "stdin_stdout", code: "10", expected: "Ingrese un numero:\nEl doble es 20", is_public: true },
]

let promptOriginal: typeof window.prompt

beforeEach(() => {
  resetMonacoMock()
  vi.mocked(runRemote).mockReset()
  promptOriginal = window.prompt
})

afterEach(() => {
  window.prompt = promptOriginal
})

async function esperarEditor() {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
}

const boton = (re: RegExp) => screen.getByRole("button", { name: re }) as HTMLButtonElement

describe("C02 PSeInt en el editor", () => {
  it("tiene rótulo y código inicial", () => {
    expect((LANGUAGE_LABELS as Record<string, string>).pseint).toBe("PSeInt")
    const inicial = (LANGUAGE_PLACEHOLDER as Record<string, string>).pseint ?? ""
    expect(inicial.trimStart().startsWith("Algoritmo sin_titulo")).toBe(true)
    expect(inicial.trimEnd().endsWith("FinAlgoritmo")).toBe(true)
  })

  it("Monaco recibe el lenguaje pseint", async () => {
    render(<CodeEditor initialCode={DOBLE} language={"pseint" as never} ejercicioId="ej-1" />)
    await esperarEditor()
    expect(editoresCreados[0]?.__opciones?.language).toBe("pseint")
  })
})

describe("C03 Ejecutar en el navegador con Leer interactivo", () => {
  it("pide el dato, muestra la salida y no llama al servidor", async () => {
    const pedidos: string[] = []
    window.prompt = vi.fn((mensaje?: string) => {
      pedidos.push(String(mensaje ?? ""))
      return "21"
    }) as typeof window.prompt
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
    await act(async () => {
      boton(/^Ejecutar/).click()
    })
    await waitFor(() => expect(onCodeExecuted).toHaveBeenCalled())
    expect(pedidos.length).toBe(1)
    expect(pedidos[0]).toContain("Ingrese un numero:")
    const r = onCodeExecuted.mock.calls[0]![0]
    expect(r.output).toContain("El doble es 42")
    expect(r.error).toBeNull()
    expect(runRemote).not.toHaveBeenCalled()
    await waitFor(() => expect(screen.getByText(/El doble es 42/)).toBeTruthy())
  })

  it("C09 la corrida informa el runtime de PSeInt", async () => {
    window.prompt = vi.fn(() => "1") as typeof window.prompt
    const onCodeExecuted = vi.fn()
    render(<CodeEditor initialCode={DOBLE} language={"pseint" as never} onCodeExecuted={onCodeExecuted} />)
    await esperarEditor()
    await act(async () => {
      boton(/^Ejecutar/).click()
    })
    await waitFor(() => expect(onCodeExecuted).toHaveBeenCalled())
    expect(onCodeExecuted.mock.calls[0]![0].runtime).toBe(`pseint-ts-${VERSION}`)
  })

  it("C04 un error de sintaxis se informa con la línea y no pide datos", async () => {
    window.prompt = vi.fn(() => "1") as typeof window.prompt
    const onCodeExecuted = vi.fn()
    const roto = 'Algoritmo roto\n\tEscribir "hola\nFinAlgoritmo\n'
    render(<CodeEditor initialCode={roto} language={"pseint" as never} onCodeExecuted={onCodeExecuted} />)
    await esperarEditor()
    await act(async () => {
      boton(/^Ejecutar/).click()
    })
    await waitFor(() => expect(onCodeExecuted).toHaveBeenCalled())
    const r = onCodeExecuted.mock.calls[0]![0]
    expect(r.error).toMatch(/2/)
    expect(window.prompt).not.toHaveBeenCalled()
  })
})

describe("C05 Probar en el navegador", () => {
  it("corre los casos visibles localmente", async () => {
    const onTestsRun = vi.fn()
    render(
      <CodeEditor
        initialCode={DOBLE}
        language={"pseint" as never}
        ejercicioId="ej-1"
        testCases={CASOS}
        onTestsRun={onTestsRun}
      />,
    )
    await esperarEditor()
    await act(async () => {
      boton(/^Probar/).click()
    })
    await waitFor(() => expect(onTestsRun).toHaveBeenCalled())
    const r = onTestsRun.mock.calls[0]![0]
    expect([r.total, r.passed, r.failed]).toEqual([2, 2, 0])
    expect(runRemote).not.toHaveBeenCalled()
  })

  it("un algoritmo equivocado falla sus casos", async () => {
    const onTestsRun = vi.fn()
    const triple = DOBLE.replace("n * 2", "n * 3")
    render(
      <CodeEditor initialCode={triple} language={"pseint" as never} testCases={CASOS} onTestsRun={onTestsRun} />,
    )
    await esperarEditor()
    await act(async () => {
      boton(/^Probar/).click()
    })
    await waitFor(() => expect(onTestsRun).toHaveBeenCalled())
    const r = onTestsRun.mock.calls[0]![0]
    expect([r.total, r.passed, r.failed]).toEqual([2, 0, 2])
  })
})

describe("C10 descargas", () => {
  it("el rótulo y el archivo usan .psc", () => {
    expect(rotuloDescarga("borrador", "pseint")).toContain(".psc")
    const f = buildEpisodioSourceFile({
      code: DOBLE,
      messages: [],
      language: "pseint",
      meta: { ejercicioTitulo: "Doble", fecha: "24/11/2026" } as never,
    })
    expect(f.filename.endsWith(".psc")).toBe(true)
    expect(f.content).toContain("// ")
  })

  it("N01 Python y Java no cambian", () => {
    expect(rotuloDescarga("borrador", "python")).toContain(".py")
    expect(rotuloDescarga("borrador", "java")).toContain(".java")
  })
})
