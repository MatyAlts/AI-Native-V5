/**
 * Aceptación HU-032 (orquestador, antes de construir; el constructor no la
 * modifica). Juani: "empeza con la proxima vos tranquilo" (24/11).
 *
 * C07  El editor de PSeInt tiene "Paso a paso": controles Siguiente paso,
 *      Continuar y Detener, y un indicador de la línea que sigue.
 * C08  La prueba de escritorio se ve como tabla: una columna por variable y
 *      una fila por paso.
 * C09  `Leer` pide el dato en su paso, con el mismo diálogo que Ejecutar.
 * C10  Al terminar, la salida queda en la consola.
 * N02  Python y Java no tienen paso a paso.
 * N03  El paso a paso no emite codigo_ejecutado ni tests (decisión: no se
 *      mezcla con los datos del estudio hasta que Alberto decida medirlo).
 * N04  Editar el código durante el paso a paso lo detiene (no se sigue con un
 *      código que ya no es el que se ve).
 */
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

vi.mock("../src/lib/runRemote", () => ({ runRemote: vi.fn() }))

const ACUMULA = `Algoritmo acumula
	Definir i, s Como Entero
	s <- 0
	Para i <- 1 Hasta 3 Hacer
		s <- s + i
	FinPara
	Escribir "s = ", s
FinAlgoritmo
`

const DOBLE = `Algoritmo doble
	Definir n Como Entero
	Escribir "Ingrese un numero:"
	Leer n
	Escribir "El doble es ", n * 2
FinAlgoritmo
`

let promptOriginal: typeof window.prompt

beforeEach(() => {
  resetMonacoMock()
  promptOriginal = window.prompt
})

afterEach(() => {
  window.prompt = promptOriginal
})

async function esperarEditor() {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
}

const boton = (re: RegExp) => screen.queryByRole("button", { name: re }) as HTMLButtonElement | null

async function click(re: RegExp) {
  const b = boton(re)
  expect(b, `falta el botón ${re}`).not.toBeNull()
  await act(async () => {
    fireEvent.click(b!)
  })
}

function tabla(): HTMLElement {
  return screen.getByRole("table", { name: /prueba de escritorio/i })
}

describe("C07/C08 paso a paso con prueba de escritorio", () => {
  it("avanza de a una instrucción y muestra la línea que sigue", async () => {
    render(<CodeEditor initialCode={ACUMULA} language={"pseint" as never} />)
    await esperarEditor()
    await click(/^Paso a paso/)
    await waitFor(() => expect(screen.getByText(/l[ií]nea 2\b/i)).toBeTruthy())
    expect(boton(/^Siguiente paso/)).not.toBeNull()
    expect(boton(/^Continuar/)).not.toBeNull()
    expect(boton(/^Detener/)).not.toBeNull()
    await click(/^Siguiente paso/)
    await waitFor(() => expect(screen.getByText(/l[ií]nea 3\b/i)).toBeTruthy())
  })

  it("la tabla tiene una columna por variable y una fila por paso", async () => {
    render(<CodeEditor initialCode={ACUMULA} language={"pseint" as never} />)
    await esperarEditor()
    await click(/^Paso a paso/)
    for (let k = 0; k < 4; k++) await click(/^Siguiente paso/)
    const t = tabla()
    const encabezados = within(t)
      .getAllByRole("columnheader")
      .map((c) => c.textContent?.trim())
    expect(encabezados).toEqual(expect.arrayContaining(["i", "s"]))
    const filas = within(t).getAllByRole("row").slice(1)
    expect(filas.length).toBe(4)
    // Después del paso 4 (s <- s + i con i = 1), s vale 1.
    const ultima = filas.at(-1)!
    const celdas = within(ultima)
      .getAllByRole("cell")
      .map((c) => c.textContent?.trim())
    const iCol = encabezados.indexOf("i")
    const sCol = encabezados.indexOf("s")
    expect(celdas[iCol]).toBe("1")
    expect(celdas[sCol]).toBe("1")
  })

  it("C10 Continuar llega al final y deja la salida en la consola", async () => {
    render(<CodeEditor initialCode={ACUMULA} language={"pseint" as never} />)
    await esperarEditor()
    await click(/^Paso a paso/)
    await click(/^Continuar/)
    await waitFor(() => expect(screen.getAllByText(/s = 6/).length).toBeGreaterThan(0))
    expect(boton(/^Siguiente paso/)?.disabled ?? true).toBe(true)
  })
})

describe("C09 Leer en el paso a paso", () => {
  it("pide el dato recién en el paso del Leer, mostrando la salida previa", async () => {
    const pedidos: string[] = []
    window.prompt = vi.fn((m?: string) => {
      pedidos.push(String(m ?? ""))
      return "21"
    }) as typeof window.prompt
    render(<CodeEditor initialCode={DOBLE} language={"pseint" as never} />)
    await esperarEditor()
    await click(/^Paso a paso/)
    await click(/^Siguiente paso/) // Definir
    await click(/^Siguiente paso/) // Escribir
    expect(pedidos.length).toBe(0)
    await click(/^Siguiente paso/) // Leer
    await waitFor(() => expect(pedidos.length).toBe(1))
    expect(pedidos[0]).toContain("Ingrese un numero:")
    const celdas = within(tabla())
      .getAllByRole("cell")
      .map((c) => c.textContent?.trim())
    expect(celdas).toContain("21")
  })
})

describe("N02/N03/N04", () => {
  it("Python y Java no tienen paso a paso", async () => {
    render(<CodeEditor initialCode="print(1)" language="python" />)
    await esperarEditor()
    expect(boton(/^Paso a paso/)).toBeNull()
  })

  it("Java tampoco", async () => {
    render(<CodeEditor initialCode="class Main {}" language="java" ejercicioId="ej-1" />)
    await esperarEditor()
    expect(boton(/^Paso a paso/)).toBeNull()
  })

  it("el paso a paso no emite ejecución ni pruebas", async () => {
    const onCodeExecuted = vi.fn()
    const onTestsRun = vi.fn()
    render(
      <CodeEditor
        initialCode={ACUMULA}
        language={"pseint" as never}
        onCodeExecuted={onCodeExecuted}
        onTestsRun={onTestsRun}
      />,
    )
    await esperarEditor()
    await click(/^Paso a paso/)
    await click(/^Continuar/)
    await waitFor(() => expect(screen.getAllByText(/s = 6/).length).toBeGreaterThan(0))
    expect(onCodeExecuted).not.toHaveBeenCalled()
    expect(onTestsRun).not.toHaveBeenCalled()
  })

  it("editar el código detiene el paso a paso", async () => {
    render(<CodeEditor initialCode={ACUMULA} language={"pseint" as never} />)
    await esperarEditor()
    await click(/^Paso a paso/)
    await click(/^Siguiente paso/)
    expect(boton(/^Siguiente paso/)).not.toBeNull()
    await act(async () => {
      editoresCreados[0]!.__tipear(ACUMULA.replace("s <- 0", "s <- 10"))
    })
    await waitFor(() => expect(boton(/^Siguiente paso/)).toBeNull())
    expect(boton(/^Paso a paso/)).not.toBeNull()
  })

  it("con un error de sintaxis no arranca y avisa la línea", async () => {
    render(
      <CodeEditor
        initialCode={'Algoritmo roto\n\tEscribir "hola\nFinAlgoritmo\n'}
        language={"pseint" as never}
      />,
    )
    await esperarEditor()
    await click(/^Paso a paso/)
    await waitFor(() => expect(screen.getAllByText(/l[ií]nea 2/i).length).toBeGreaterThan(0))
    expect(boton(/^Siguiente paso/)).toBeNull()
  })
})
