/**
 * Vida util de las marcas de origen del `edicion_codigo` (F6).
 *
 * El editor lleva dos banderas —"hubo un pegado" y "se expandio un snippet"—
 * que describen UNA ventana de debounce y deciden el campo `origin` del evento
 * CTR. `pasted_external` es la unica que lleva **override a N4** en el labeler.
 *
 * El bug: `flushEdicionPendiente` las reseteaba SOLO cuando emitia. Un Ctrl+Z
 * dentro del segundo del debounce devuelve el buffer a la ultima emision, no
 * hay nada que emitir, y la marca queda viva indefinidamente. El siguiente
 * tramo —tipeado a mano, sin tocar el clipboard— sale marcado:
 *
 *     PROBE A (tras undo)   -> []
 *     PROBE A (tipeo puro)  -> [{"origin":"snippet_expanded"}]
 *     PROBE B (tipeo puro)  -> [{"origin":"pasted_external"}]
 *
 * O sea: la plataforma afirmando que el alumno pego codigo que en realidad
 * escribio, sobre la señal que decide su nivel de apropiacion. Empeoro cuando
 * "Ejecutar"/"Probar" pasaron a llamar al mismo flush: cada corrida es otra
 * oportunidad de dejar una marca viva.
 *
 * La marca no se resetea al EMITIR: se resetea cuando la ventana se CIERRA.
 */
import { act, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import type { ExecutionResult, TestCasePublic } from "../src/lib/api"
import type { OrigenEdicion } from "../src/lib/edicionPendiente"
import { runRemote } from "../src/lib/runRemote"
import { aceptarSnippet, editoresCreados, resetMonacoMock } from "./_monacoMock"

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

beforeEach(() => {
  resetMonacoMock()
  vi.mocked(runRemote).mockResolvedValue(EJECUCION_OK)
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  vi.useRealTimers()
})

/** Ventana del debounce del editor, con margen. */
const DEBOUNCE_MS = 1500

async function esperarEditor() {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
  const ed = editoresCreados[0]
  if (!ed) throw new Error("no se creo el editor")
  return ed
}

/** Un ejercicio realista tiene al menos un caso publico; sin eso, "Ejecutar"
 * en remoto queda deshabilitado a proposito (ver `CodeEditorSinCasos`). */
const CASOS_PUBLICOS: TestCasePublic[] = [
  { id: "c1", name: "caso 1", type: "stdin_stdout", code: "", expected: "ok", is_public: true },
]

function montar(origenes: OrigenEdicion[], language: "python" | "java" = "python") {
  render(
    <CodeEditor
      initialCode="x = 0"
      language={language}
      ejercicioId="ej-1"
      testCases={CASOS_PUBLICOS}
      onEditDebounced={(_s, _d, origin) => origenes.push(origin)}
    />,
  )
}

describe("marcas de origen: la ventana se cierra emita o no", () => {
  it("un undo tras pegar no contamina el tramo siguiente", async () => {
    const origenes: OrigenEdicion[] = []
    montar(origenes)
    const ed = await esperarEditor()

    // Pega, y deshace ANTES de que venza el debounce.
    act(() => {
      ed.__pegar("x = 0\nprint('pegado')")
    })
    act(() => {
      ed.__tipear("x = 0")
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS)
    })
    // El buffer volvio a la ultima emision: no hay evento, y eso esta bien.
    expect(origenes).toEqual([])

    // Ahora tipea a mano. Sin el reseteo, esto salia `pasted_external`.
    act(() => {
      ed.__tipear("x = 1")
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS)
    })
    expect(origenes).toEqual(["student_typed"])
  })

  it("un undo tras expandir un snippet tampoco contamina", async () => {
    const origenes: OrigenEdicion[] = []
    montar(origenes)
    await esperarEditor()
    const ed = editoresCreados[0]
    if (!ed) throw new Error("no se creo el editor")
    // Los snippets se registran en un effect asincrono (import dinamico).
    await waitFor(() => aceptarSnippet())

    act(() => {
      ed.__tipear("x = 0\nprint()")
    })
    act(() => {
      ed.__tipear("x = 0")
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS)
    })
    expect(origenes).toEqual([])

    act(() => {
      ed.__tipear("x = 2")
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS)
    })
    expect(origenes).toEqual(["student_typed"])
  })

  it("el flush de 'Ejecutar' tampoco deja marcas vivas", async () => {
    // El segundo call-site del flush: cada corrida cierra la ventana. Si no
    // reseteara, una corrida despues de un undo dejaria la marca colgada hasta
    // el proximo evento emitido, que puede ser minutos despues.
    const origenes: OrigenEdicion[] = []
    montar(origenes, "java")
    const ed = await esperarEditor()

    act(() => {
      ed.__pegar("class Main { int x = 1; }")
    })
    act(() => {
      ed.__tipear("x = 0")
    })
    await act(async () => {
      screen.getByRole("button", { name: /^Ejecutar codigo/ }).click()
    })
    expect(origenes).toEqual([])

    act(() => {
      ed.__tipear("x = 3")
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS)
    })
    expect(origenes).toEqual(["student_typed"])
  })
})

describe("marcas de origen: lo que NO cambia", () => {
  it("un pegado que SI llega a emitirse sigue saliendo `pasted_external`", async () => {
    // La direccion inversa —un pegado real degradado a `student_typed`— seria
    // peor que el bug que se arregla: perderia la señal. Esto lo ancla.
    const origenes: OrigenEdicion[] = []
    montar(origenes)
    const ed = await esperarEditor()

    act(() => {
      ed.__pegar("x = 0\nprint('pegado')")
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS)
    })
    expect(origenes).toEqual(["pasted_external"])
  })

  it("un snippet que SI llega a emitirse sigue saliendo `snippet_expanded`", async () => {
    const origenes: OrigenEdicion[] = []
    montar(origenes)
    await esperarEditor()
    const ed = editoresCreados[0]
    if (!ed) throw new Error("no se creo el editor")
    await waitFor(() => aceptarSnippet())

    act(() => {
      ed.__tipear("x = 0\nprint()")
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS)
    })
    expect(origenes).toEqual(["snippet_expanded"])
  })

  it("el pegado gana sobre el snippet en la misma ventana", async () => {
    const origenes: OrigenEdicion[] = []
    montar(origenes)
    await esperarEditor()
    const ed = editoresCreados[0]
    if (!ed) throw new Error("no se creo el editor")
    await waitFor(() => aceptarSnippet())

    act(() => {
      ed.__pegar("x = 0\nprint('pegado')")
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS)
    })
    expect(origenes).toEqual(["pasted_external"])
  })
})
