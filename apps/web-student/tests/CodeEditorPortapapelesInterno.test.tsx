/**
 * Portapapeles interno del editor (change `portapapeles-interno-editor`).
 *
 * El alumno puede copiar y pegar SU PROPIO codigo adentro del editor. Todo lo
 * demas sigue bloqueado — y, sobre todo, el codigo sigue sin poder SALIR de la
 * plataforma.
 *
 * El mecanismo es el que ya bloqueaba el pegado desde hace meses: los
 * `addCommand` de Monaco, que reemplazan el keybinding ANTES de que el
 * navegador genere un evento de clipboard. Lo unico que cambia es que ahora
 * tienen una rama mas: si hay algo copiado adentro, se inserta; si no, se
 * bloquea como siempre.
 *
 * Por que NO se usa el portapapeles del sistema operativo, que seria lo obvio:
 * para pegar hace falta leer el clipboard, para leerlo hace falta el evento
 * `paste` nativo, y para que ese evento exista hay que sacar el
 * `addCommand(Ctrl+V)`. Medido en Chrome el 2026-10-01: sacandolo, el listener
 * DOM en captura sobre el contenedor NO recibe el evento (si lo recibe uno a
 * nivel `document`), con lo cual el `preventDefault()` nunca corre y el pegado
 * externo entra al buffer sin cartel y sin `pega_intentada`. Guardando el texto
 * en memoria no hace falta leer el clipboard nunca, y el bloqueo se queda donde
 * se sabe que funciona.
 *
 * Efecto lateral buscado: Ctrl+C no escribe al clipboard del SO, asi que el
 * alumno sigue sin poder llevarse el codigo a VS Code o a ChatGPT. El enunciado
 * del prompt del tutor ("copiar y pegar esta bloqueado... no se puede
 * ejecutar") sigue siendo verdadero.
 */
import { act, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import type { TestCasePublic } from "../src/lib/api"
import type { OrigenEdicion } from "../src/lib/edicionPendiente"
import { KeyCode, KeyMod, editoresCreados, resetMonacoMock } from "./_monacoMock"

// El editor importa `runRemote` al montar; sin el doble, el test sale a la red.
vi.mock("../src/lib/runRemote", () => ({ runRemote: vi.fn() }))

const COPIAR = KeyMod.CtrlCmd | KeyCode.KeyC
const CORTAR = KeyMod.CtrlCmd | KeyCode.KeyX
const PEGAR = KeyMod.CtrlCmd | KeyCode.KeyV

const DEBOUNCE_MS = 1500

const CASOS_PUBLICOS: TestCasePublic[] = [
  { id: "c1", name: "caso 1", type: "stdin_stdout", code: "", expected: "ok", is_public: true },
]

beforeEach(() => {
  resetMonacoMock()
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  vi.useRealTimers()
})

interface Registro {
  origenes: OrigenEdicion[]
  pegados: { contenidoLongitud: number; metodo: string }[]
  copiados: { seleccionChars: number; metodo: string }[]
}

function montar(): Registro {
  const reg: Registro = { origenes: [], pegados: [], copiados: [] }
  render(
    <CodeEditor
      initialCode={"a = 1\nb = 2\n"}
      language="python"
      ejercicioId="ej-1"
      testCases={CASOS_PUBLICOS}
      onEditDebounced={(_s, _d, origin) => reg.origenes.push(origin)}
      onPasteAttempt={(p) => reg.pegados.push({ ...p })}
      onCopyAttempt={(p) => reg.copiados.push({ ...p })}
    />,
  )
  return reg
}

async function esperarEditor() {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
  const ed = editoresCreados[0]
  if (!ed) throw new Error("no se creo el editor")
  return ed
}

describe("copiar y pegar adentro del editor", () => {
  it("Ctrl+C guarda la seleccion y deja el buffer intacto", async () => {
    const reg = montar()
    const ed = await esperarEditor()

    ed.__seleccionar("a = 1")
    act(() => ed.__comando(COPIAR))

    expect(ed.getValue()).toBe("a = 1\nb = 2\n")
    // El rastro de auditoria del copiado NO puede desaparecer: es lo que deja
    // constancia de que el alumno movio codigo, aunque sea el suyo.
    expect(reg.copiados).toEqual([{ seleccionChars: 5, metodo: "shortcut" }])
  })

  it("Ctrl+C y despues Ctrl+V pega, y el evento sale como pasted_internal", async () => {
    const reg = montar()
    const ed = await esperarEditor()

    ed.__seleccionar("a = 1")
    act(() => ed.__comando(COPIAR))
    // Mover el cursor sin resaltar nada deja una seleccion VACIA, no `null`:
    // Monaco solo devuelve `null` si no hay modelo ni view state. Modelarlo
    // al reves haria pasar un test sobre una situacion que no ocurre.
    ed.__seleccionar("")
    act(() => ed.__comando(PEGAR))

    expect(ed.getValue()).toBe("a = 1\nb = 2\na = 1")

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS)
    })
    // NO `student_typed`: el alumno no tipeo esos caracteres, los movio.
    // NO `pasted_external`: no vinieron de afuera, y esa marca lleva override
    // a N4 — etiquetaria como dependencia de la IA un reordenamiento propio.
    expect(reg.origenes).toEqual(["pasted_internal"])
  })

  it("Ctrl+V sin nada copiado adentro sigue bloqueado y queda registrado", async () => {
    const reg = montar()
    const ed = await esperarEditor()

    act(() => ed.__comando(PEGAR))

    expect(ed.getValue()).toBe("a = 1\nb = 2\n")
    expect(reg.pegados).toHaveLength(1)
    expect(reg.pegados[0]?.metodo).toBe("shortcut")
    expect(screen.getByTestId("clipboard-blocked-toast")).toBeTruthy()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS)
    })
    // Un pegado bloqueado no cambia el buffer, asi que no hay nada que emitir.
    expect(reg.origenes).toEqual([])
  })

  it("Ctrl+X guarda la seleccion y la borra del buffer", async () => {
    const reg = montar()
    const ed = await esperarEditor()

    ed.__seleccionar("b = 2")
    act(() => ed.__comando(CORTAR))

    expect(ed.getValue()).toBe("a = 1\n\n")
    expect(reg.copiados).toEqual([{ seleccionChars: 5, metodo: "shortcut" }])

    // Y lo cortado se puede volver a pegar: es el caso de uso entero.
    act(() => ed.__comando(PEGAR))
    expect(ed.getValue()).toBe("a = 1\n\nb = 2")
  })

  it("Ctrl+C sin seleccion no deja un portapapeles vacio que habilite el pegado", async () => {
    const reg = montar()
    const ed = await esperarEditor()

    ed.__seleccionar("")
    act(() => ed.__comando(COPIAR))
    act(() => ed.__comando(PEGAR))

    // Si una copia vacia contara como "hay algo copiado", el Ctrl+V siguiente
    // pegaria "" y el bloqueo quedaria desactivado por una tecla de mas.
    expect(ed.getValue()).toBe("a = 1\nb = 2\n")
    expect(reg.pegados).toHaveLength(1)
  })

  it("sin view state (getSelection null) no pega ni inventa un intento fallido", async () => {
    const reg = montar()
    const ed = await esperarEditor()

    ed.__seleccionar("a = 1")
    act(() => ed.__comando(COPIAR))
    // `null` = el editor no tiene modelo ni view state. No es "el alumno no
    // seleccionó nada" (eso es una seleccion vacia, ver el test de arriba).
    ed.__seleccionar(null)
    act(() => ed.__comando(PEGAR))

    expect(ed.getValue()).toBe("a = 1\nb = 2\n")
    // Y sobre todo: NO sale `pega_intentada`. El alumno tenia algo copiado y
    // la regla se lo permitia — registrar un intento bloqueado seria meter en
    // la serie un evento que describe una decision que nadie tomo.
    expect(reg.pegados).toEqual([])

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS)
    })
    expect(reg.origenes).toEqual([])
  })
})

describe("el codigo no sale de la plataforma", () => {
  it("el evento copy del DOM se cancela: nada llega al clipboard del SO", async () => {
    montar()
    await esperarEditor()
    const contenedor = document.querySelector("[data-testid='code-editor-container']")
    expect(contenedor).toBeTruthy()

    const ev = new Event("copy", { bubbles: true, cancelable: true })
    act(() => {
      contenedor?.dispatchEvent(ev)
    })

    // Si esto deja de cancelarse, el alumno puede copiar su codigo y pegarlo
    // en ChatGPT. Es la propiedad que sostiene la trazabilidad, no un detalle.
    expect(ev.defaultPrevented).toBe(true)
  })

  it("el evento paste del DOM se cancela y queda registrado", async () => {
    const reg = montar()
    await esperarEditor()
    const contenedor = document.querySelector("[data-testid='code-editor-container']")

    const ev = new Event("paste", { bubbles: true, cancelable: true })
    act(() => {
      contenedor?.dispatchEvent(ev)
    })

    expect(ev.defaultPrevented).toBe(true)
    expect(reg.pegados).toHaveLength(1)
  })
})

describe("la costura de los pegados imprevistos sigue en pie", () => {
  it("un pegado nativo que llegue al modelo cae como pasted_external", async () => {
    const reg = montar()
    const ed = await esperarEditor()

    // `__pegar` simula el camino de Monaco real: onDidPaste y despues el
    // cambio de buffer. Con el bloqueo puesto no deberia ocurrir nunca, pero
    // si algun camino imprevisto lo logra, tiene que caer del lado que SI
    // lleva override a N4 — nunca perderse como tipeo del alumno.
    act(() => {
      ed.__pegar("a = 1\nb = 2\nfoo_de_afuera()")
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS)
    })

    expect(reg.origenes).toEqual(["pasted_external"])
  })
})
