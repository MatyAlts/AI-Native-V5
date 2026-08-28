/**
 * El editor pierde el codigo al cruzar el breakpoint mobile (Monaco doblado —
 * ver `_monacoMock.ts`).
 *
 * `EpisodePage` renderiza el panel del editor en dos subarboles distintos
 * (`{isMobile ? <div>{editorPanel}</div> : <PanelGroup>{editorPanel}</...>}`),
 * asi que cruzar el breakpoint DESMONTA y vuelve a montar `CodeEditor`. Monaco
 * posee el buffer y se siembra una sola vez con `initialCode`, asi que el
 * editor nuevo revive el codigo con el que se lo sembro — que hasta ahora solo
 * se actualizaba al hidratar y al Ejecutar.
 *
 * El otro invariante que estos tests protegen es igual de importante: el
 * re-montaje NO debe emitir un `edicion_codigo` que el alumno no hizo. Un
 * evento falso en la cadena CTR es peor que perder el codigo — la cadena
 * sostiene la tesis.
 *
 * Los casos usan `language="java"` para que el componente no intente cargar
 * Pyodide (que en jsdom nunca resuelve y deja los controles deshabilitados).
 * El re-montaje es identico en cualquier lenguaje.
 */
import { act, render, waitFor } from "@testing-library/react"
import { useState } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
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

function Contenedor({
  onEditDebounced,
  seguirCodigo,
}: {
  onEditDebounced?: (s: string, d: number, o: string) => void
  seguirCodigo: boolean
}) {
  const [code, setCode] = useState("class Main {}")
  const [mobile, setMobile] = useState(false)
  const editor = (
    <CodeEditor
      initialCode={code}
      language="java"
      ejercicioId="ej-1"
      {...(onEditDebounced ? { onEditDebounced } : {})}
      // `seguirCodigo=false` reproduce el estado ANTES del fix: el padre no se
      // entera de lo que el alumno tipea.
      {...(seguirCodigo ? { onCodeChange: setCode } : {})}
    />
  )
  return (
    <div>
      <button type="button" data-testid="cruzar-breakpoint" onClick={() => setMobile((m) => !m)}>
        cruzar
      </button>
      {mobile ? <section>{editor}</section> : <main>{editor}</main>}
    </div>
  )
}

describe("CodeEditor — codigo tipeado vs. re-montaje (BUG-4)", () => {
  it("al cruzar el breakpoint, el editor se re-siembra con lo que el alumno tipeo", async () => {
    const { getByTestId } = render(<Contenedor seguirCodigo={true} />)
    const ed1 = await esperarEditor(1)
    expect(ed1.__opciones.value).toBe("class Main {}")

    act(() => {
      ed1.__tipear("class Main { int x = 1; }")
    })

    act(() => {
      getByTestId("cruzar-breakpoint").click()
    })
    const ed2 = await esperarEditor(2)
    expect(ed2.__opciones.value).toBe("class Main { int x = 1; }")
  })

  it("el re-montaje NO emite un edicion_codigo fantasma", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const onEditDebounced = vi.fn()
      const { getByTestId } = render(
        <Contenedor seguirCodigo={true} onEditDebounced={onEditDebounced} />,
      )
      const ed1 = await esperarEditor(1)
      act(() => {
        ed1.__tipear("class Main { int x = 1; }")
      })
      await vi.advanceTimersByTimeAsync(1500)
      expect(onEditDebounced).toHaveBeenCalledTimes(1)

      act(() => {
        getByTestId("cruzar-breakpoint").click()
      })
      await esperarEditor(2)
      await vi.advanceTimersByTimeAsync(3000)
      // Ni uno mas: el re-seed pasa por `editor.create`, no por
      // `onDidChangeModelContent`.
      expect(onEditDebounced).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it("el diff del edicion_codigo posterior al re-montaje se mide contra lo tipeado", async () => {
    // Si el re-seed reiniciara el baseline al codigo viejo, el `diff_chars` del
    // siguiente evento contaria de nuevo lo que el alumno ya habia escrito.
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const onEditDebounced = vi.fn()
      const { getByTestId } = render(
        <Contenedor seguirCodigo={true} onEditDebounced={onEditDebounced} />,
      )
      const ed1 = await esperarEditor(1)
      act(() => {
        ed1.__tipear("abcdefghij") // 10 chars
      })
      await vi.advanceTimersByTimeAsync(1500)

      act(() => {
        getByTestId("cruzar-breakpoint").click()
      })
      const ed2 = await esperarEditor(2)
      onEditDebounced.mockClear()
      act(() => {
        ed2.__tipear("abcdefghijkl") // +2
      })
      await vi.advanceTimersByTimeAsync(1500)

      expect(onEditDebounced).toHaveBeenCalledTimes(1)
      expect(onEditDebounced.mock.calls[0]?.[1]).toBe(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it("'Restaurar plantilla' vuelve a la plantilla, no a lo ultimo tipeado", async () => {
    // Consecuencia directa de que el padre ahora sigue el buffer: sin guardar
    // la plantilla aparte, `initialCode` seria el codigo del alumno y el boton
    // quedaria en no-op.
    const { getByTestId } = render(<Contenedor seguirCodigo={true} />)
    const ed1 = await esperarEditor(1)
    act(() => {
      ed1.__tipear("codigo del alumno")
    })

    act(() => {
      getByTestId("restore-template-button").click()
    })
    act(() => {
      getByTestId("confirm-restore-template").click()
    })

    expect(ed1.getValue()).toBe("class Main {}")
  })
})
