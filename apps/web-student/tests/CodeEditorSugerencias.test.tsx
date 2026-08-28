/**
 * Config de autocompletado del editor (Monaco doblado — ver `_monacoMock.ts`).
 *
 * Con los defaults de Monaco no se puede escribir un f-string de Python: la
 * comilla que sigue a la `f` commitea la sugerencia resaltada y se come el
 * prefijo. Es el primer formateo de strings de la cursada.
 */
import { render, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

beforeEach(() => {
  resetMonacoMock()
})

/** Espera a que el enesimo `monaco.editor.create` haya ocurrido. */
async function esperarEditor(n: number) {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(n))
  const ed = editoresCreados[n - 1]
  if (!ed) throw new Error(`no hay editor #${n}`)
  return ed
}

describe("CodeEditor — autocompletado (BUG-3: la 'f' de los f-strings)", () => {
  it("crea Monaco sin acceptSuggestionOnCommitCharacter", async () => {
    render(<CodeEditor initialCode="x = 1" language="python" />)
    const ed = await esperarEditor(1)
    // Con el default (true) la comilla de `f"..."` commitea la sugerencia
    // resaltada y se come la `f`.
    expect(ed.__opciones.acceptSuggestionOnCommitCharacter).toBe(false)
  })

  it("no dispara sugerencias dentro de strings ni comentarios, si en codigo", async () => {
    render(<CodeEditor initialCode="x = 1" language="python" />)
    const ed = await esperarEditor(1)
    expect(ed.__opciones.quickSuggestions).toEqual({
      other: true,
      comments: false,
      strings: false,
    })
  })

  it("conserva el autocompletado por caracter disparador", async () => {
    // El fix no es "apagar IntelliSense": tiene que seguir ayudando donde ayuda.
    render(<CodeEditor initialCode="x = 1" language="python" />)
    const ed = await esperarEditor(1)
    expect(ed.__opciones.suggestOnTriggerCharacters).toBe(true)
  })
})
