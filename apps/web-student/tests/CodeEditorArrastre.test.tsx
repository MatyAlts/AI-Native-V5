/**
 * Arrastrar-y-soltar codigo al editor (decision del equipo, 2026-08-28).
 *
 * El editor no TRACKEA el pegado: lo PROHIBE. Ctrl+V, el menu contextual y
 * los atajos de copiar/cortar estan todos bloqueados y emiten `pega_intentada`
 * en su lugar. Pero el arrastrar-y-soltar entraba por una puerta distinta:
 * `dropIntoEditor` (default `true` en Monaco) no pasa por `onDidPaste` ni por
 * ningun listener de clipboard, asi que el texto soltado desde otra ventana
 * caia en el buffer y salia rotulado `origin: "student_typed"`.
 *
 * O sea: la plataforma afirmando que el alumno tipeo codigo que no tipeo,
 * sobre la misma señal que decide su nivel de apropiacion. Es el mismo defecto
 * que el override de `pasted_external`, por el canal de al lado.
 *
 * Se cerro con el criterio del clipboard —bloquear y registrar el intento— y
 * NO agrega un tipo de evento nuevo a la cadena: `drag_drop` ya estaba
 * declarado en el `metodo` de `pega_intentada` (contrato, ruta del tutor y
 * cliente del CTR) y simplemente no lo emitia nadie.
 *
 * Son DOS mitades y las dos hacen falta: apagar `dropIntoEditor` desactiva el
 * widget de Monaco, pero el navegador inserta el texto igual si nadie cancela
 * el `dragover`. Cada test de aca abajo mata una mitad distinta.
 */
import { render, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import type { TestCasePublic } from "../src/lib/api"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

vi.mock("../src/lib/runRemote", () => ({ runRemote: vi.fn() }))

const CASOS_PUBLICOS: TestCasePublic[] = [
  { id: "c1", name: "caso 1", type: "stdin_stdout", code: "", expected: "ok", is_public: true },
]

type IntentoPegado = {
  contenidoLongitud: number
  contenidoPreview: string
  metodo: string
}

beforeEach(() => {
  resetMonacoMock()
})

function montar(intentos: IntentoPegado[]) {
  const { container } = render(
    <CodeEditor
      initialCode="x = 0"
      language="python"
      ejercicioId="ej-1"
      testCases={CASOS_PUBLICOS}
      onPasteAttempt={(p) => intentos.push(p as IntentoPegado)}
    />,
  )
  return container
}

/** El div que recibe los listeners es el ultimo del arbol del editor. */
async function contenedorDelEditor(container: HTMLElement) {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
  const el = container.querySelector("div.flex-1.min-h-\\[140px\\]")
  if (!el) throw new Error("no se encontro el contenedor del editor")
  return el as HTMLElement
}

/** `DataTransfer` no existe en jsdom: alcanza con el `getData` que se usa. */
function eventoDeArrastre(tipo: "dragover" | "drop", texto: string) {
  const ev = new Event(tipo, { bubbles: true, cancelable: true })
  Object.defineProperty(ev, "dataTransfer", {
    value: { getData: () => texto, dropEffect: "copy" },
  })
  return ev
}

describe("arrastrar codigo al editor esta bloqueado y queda registrado", () => {
  it("el drop se cancela y emite pega_intentada con metodo drag_drop", async () => {
    const intentos: IntentoPegado[] = []
    const container = montar(intentos)
    const el = await contenedorDelEditor(container)

    const soltado = "import os\nos.system('rm -rf /')"
    const ev = eventoDeArrastre("drop", soltado)
    el.dispatchEvent(ev)

    // Cancelado: el navegador no inserta el texto en el buffer.
    expect(ev.defaultPrevented).toBe(true)
    // Y el intento queda en la cadena, con el metodo que lo distingue del
    // clipboard. Sin esto el arrastre seria invisible, que es peor que
    // bloquearlo: el alumno igual consiguio el codigo de algun lado.
    expect(intentos).toEqual([
      {
        contenidoLongitud: soltado.length,
        contenidoPreview: soltado,
        metodo: "drag_drop",
      },
    ])
  })

  it("el dragover se cancela: sin eso el drop no llega a dispararse", async () => {
    const intentos: IntentoPegado[] = []
    const container = montar(intentos)
    const el = await contenedorDelEditor(container)

    const ev = eventoDeArrastre("dragover", "x = 1")
    el.dispatchEvent(ev)

    // Es el `dragover` cancelado lo que le dice al navegador "aca no se
    // suelta". Si esto pasara a `false`, el texto entraria por la via nativa
    // sin tocar nunca nuestro handler de `drop`.
    expect(ev.defaultPrevented).toBe(true)
    // Moverse por encima del editor no es un intento: no se emite nada hasta
    // que efectivamente suelta. Si no, un arrastre deja decenas de eventos.
    expect(intentos).toEqual([])
  })

  it("el preview del contenido se trunca a 200 chars como el del clipboard", async () => {
    const intentos: IntentoPegado[] = []
    const container = montar(intentos)
    const el = await contenedorDelEditor(container)

    const largo = "a".repeat(500)
    el.dispatchEvent(eventoDeArrastre("drop", largo))

    // El contrato declara `max_length=200` en `contenido_preview`: mandarlo
    // entero lo rechaza el backend y se pierde el registro del intento.
    expect(intentos[0]?.contenidoLongitud).toBe(500)
    expect(intentos[0]?.contenidoPreview).toHaveLength(200)
  })

  it("Monaco se crea con dropIntoEditor apagado", async () => {
    const intentos: IntentoPegado[] = []
    montar(intentos)
    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))

    // La otra mitad del cierre. Los listeners cubren el camino del navegador;
    // esto apaga el widget propio de Monaco, que inserta sin pasar por el DOM
    // del contenedor.
    expect(editoresCreados[0]?.__opciones.dropIntoEditor).toEqual({ enabled: false })
  })
})
