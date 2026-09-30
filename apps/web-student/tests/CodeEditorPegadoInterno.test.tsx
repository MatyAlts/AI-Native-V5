/**
 * Portapapeles interno (change `copiar-pegar-interno-en-el-episodio`).
 *
 * El portapapeles del SO no guarda procedencia. Pero el editor SI puede
 * saber otra cosa: "¿eso lo puse yo aca?". Al copiar/cortar dentro de la
 * pagina se guarda `{texto, origen}` en memoria (ver `lib/portapapelesInterno`).
 * Al pegar se compara el contenido real del clipboard contra lo guardado:
 * coincide -> se permite y el evento `edicion_codigo` sale con
 * `origin: "pasted_internal"`; no coincide -> se bloquea, como siempre.
 *
 * ADR-026: el panel del tutor queda AFUERA del portapapeles interno. Un
 * copiado hecho ahi (identificado por `[data-tour="tutor-chat"]`, el mismo
 * atributo que ya usa el tour de onboarding) NUNCA se registra, asi que
 * cualquier pegado de ese texto cae por "no coincide" y se bloquea solo —
 * sin necesidad de una regla aparte.
 *
 * Los dos bloqueos de HOY (`addCommand(Ctrl+V)` y el listener DOM de
 * `paste` en captura) pasan de CORTAR a VALIDAR: el segundo sigue siendo el
 * unico punto de decision (addCommand se saca — sin el, el Ctrl+V nativo SI
 * genera el evento `paste` del DOM, que es lo que el listener necesita para
 * leer `clipboardData` de verdad. Ver el comentario en `CodeEditor.tsx`).
 */
import { act, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CodeEditor } from "../src/components/CodeEditor"
import type { TestCasePublic } from "../src/lib/api"
import type { OrigenEdicion } from "../src/lib/edicionPendiente"
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

afterEach(() => {
  vi.restoreAllMocks()
})

/**
 * Monta el editor junto a DOS vecinos que representan el resto de la pagina:
 * un stub de la consigna (permitido: lleva `data-copiable-interno`, el mismo
 * atributo que el panel real en `EpisodePage.tsx`) y un stub del panel del
 * tutor (prohibido, ADR-026: NO lo lleva).
 *
 * La regla es ALLOWLIST, asi que el stub del tutor no necesita ninguna marca
 * especial — le alcanza con no tener la del permitido. Esa es exactamente la
 * propiedad que se quiere: lo que no se habilita explicitamente, no entra.
 */
function montar(origenes: OrigenEdicion[], intentos: IntentoPegado[]) {
  const { container } = render(
    <div>
      <div data-copiable-interno data-testid="consigna-stub">
        de la consigna
      </div>
      <div data-testid="tutor-stub">del tutor</div>
      <CodeEditor
        initialCode="x = 0"
        language="python"
        ejercicioId="ej-1"
        testCases={CASOS_PUBLICOS}
        onEditDebounced={(_s, _d, origin) => origenes.push(origin)}
        onPasteAttempt={(p) => intentos.push(p as IntentoPegado)}
      />
    </div>,
  )
  return container
}

async function contenedorDelEditor(container: HTMLElement) {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
  const el = container.querySelector("div.flex-1.min-h-\\[140px\\]")
  if (!el) throw new Error("no se encontro el contenedor del editor")
  return el as HTMLElement
}

/**
 * Simula "el alumno selecciono y copio ESTE texto".
 *
 * jsdom no implementa seleccion real, asi que se mockea `window.getSelection`.
 * Pero NO alcanza con `toString()`: el portapapeles interno tambien exige que
 * la seleccion este CONTENIDA en la region permitida, y eso se comprueba con
 * `getRangeAt(0).commonAncestorContainer`. Un doble sin `Range` hace que ese
 * chequeo falle siempre y esconde justo la proteccion que cierra la fuga de
 * Ctrl+A. Por eso se construye un `Range` de verdad.
 *
 * `hasta` permite simular una seleccion que ARRANCA en un nodo y se EXTIENDE
 * hasta otro — el caso Ctrl+A, que es la fuga que este chequeo existe para
 * cerrar.
 */
function copiar(nodo: HTMLElement, texto: string, hasta?: HTMLElement) {
  const rango = document.createRange()
  rango.setStart(nodo, 0)
  rango.setEnd(hasta ?? nodo, (hasta ?? nodo).childNodes.length)
  vi.spyOn(window, "getSelection").mockReturnValue({
    toString: () => texto,
    rangeCount: 1,
    getRangeAt: () => rango,
  } as unknown as Selection)
  const ev = new Event("copy", { bubbles: true, cancelable: true })
  nodo.dispatchEvent(ev)
}

/** `clipboardData` no existe en el `ClipboardEvent` de jsdom por defecto —
 * se define a mano, igual que `dataTransfer` en `CodeEditorArrastre.test.tsx`. */
function eventoDePegado(texto: string): ClipboardEvent {
  const ev = new Event("paste", { bubbles: true, cancelable: true }) as ClipboardEvent
  Object.defineProperty(ev, "clipboardData", {
    value: { getData: () => texto },
  })
  return ev
}

const DEBOUNCE_MS = 1500

describe("pegado interno permitido", () => {
  it("1.1 — texto copiado de la consigna se puede pegar, y sale origin pasted_internal", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const origenes: OrigenEdicion[] = []
    const intentos: IntentoPegado[] = []
    const container = montar(origenes, intentos)
    const editorEl = await contenedorDelEditor(container)
    const ed = editoresCreados[0]
    if (!ed) throw new Error("no se creo el editor")

    const consigna = container.querySelector('[data-testid="consigna-stub"]')
    if (!consigna) throw new Error("no se encontro el stub de la consigna")
    const texto = "nombre_variable_exacto = 42"

    act(() => {
      copiar(consigna as HTMLElement, texto)
    })

    const ev = eventoDePegado(texto)
    act(() => {
      editorEl.dispatchEvent(ev)
    })
    // Coincide: se deja pasar. El navegador (Monaco, en produccion) es quien
    // inserta el texto — acá se simula esa continuacion con `__pegar`, igual
    // que el resto de la suite simula "Monaco aplico un paste".
    expect(ev.defaultPrevented).toBe(false)
    act(() => {
      ed.__pegar(texto)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS)
    })

    expect(origenes).toEqual(["pasted_internal"])
    expect(intentos).toEqual([])
    vi.useRealTimers()
  })

  it("editor -> editor (codigo propio) tambien se permite", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const origenes: OrigenEdicion[] = []
    const intentos: IntentoPegado[] = []
    const container = montar(origenes, intentos)
    const editorEl = await contenedorDelEditor(container)
    const ed = editoresCreados[0]
    if (!ed) throw new Error("no se creo el editor")

    const texto = "def resolver(): pass"
    // El copiado DESDE el editor lee la seleccion por la API de MONACO
    // (`getSelection()` + `getModel().getValueInRange()`), no por
    // `window.getSelection()`, porque esa ultima devuelve "" cuando la
    // seleccion vive adentro del textarea oculto de Monaco. Por eso acá se
    // arma el doble por el lado de Monaco.
    ed.__setSeleccion(texto)
    // Copiar DESDE el propio contenedor del editor (selecciono su propio
    // codigo y lo copia — no es "tomar nada de nadie").
    act(() => {
      copiar(editorEl, texto)
    })

    const ev = eventoDePegado(texto)
    act(() => {
      editorEl.dispatchEvent(ev)
    })
    expect(ev.defaultPrevented).toBe(false)
    act(() => {
      ed.__pegar(texto)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS)
    })

    expect(origenes).toEqual(["pasted_internal"])
    vi.useRealTimers()
  })
})

describe("ADR-026: el panel del tutor queda afuera", () => {
  it("1.2 — texto copiado del panel del tutor NO se puede pegar", async () => {
    const origenes: OrigenEdicion[] = []
    const intentos: IntentoPegado[] = []
    const container = montar(origenes, intentos)
    const editorEl = await contenedorDelEditor(container)

    const tutor = container.querySelector('[data-testid="tutor-stub"]')
    if (!tutor) throw new Error("no se encontro el stub del tutor")
    const texto = "solucion_completa_del_tutor()"

    act(() => {
      copiar(tutor as HTMLElement, texto)
    })

    const ev = eventoDePegado(texto)
    act(() => {
      editorEl.dispatchEvent(ev)
    })

    // Nunca se registro: el "no coincide" bloquea solo, sin regla aparte
    // para el tutor.
    expect(ev.defaultPrevented).toBe(true)
    expect(intentos).toEqual([
      {
        contenidoLongitud: texto.length,
        contenidoPreview: texto,
        // `shortcut`, no `menu_contextual`. Hasta el 2026-09-30 este campo
        // salia fijo en "menu_contextual" porque los dos caminos habian
        // quedado colapsados en un listener nativo — o sea que un Ctrl+V, el
        // camino MAS comun, se registraba como el menos comun, y estos tests
        // lo tenian cementado. Ahora `metodoDeClipboard` distingue: si no
        // hubo un `contextmenu` reciente, fue atajo.
        metodo: "shortcut",
      },
    ])
    expect(origenes).toEqual([])
  })
})

describe("pegado bloqueado (comportamiento que no cambia)", () => {
  it("1.3 — texto que no esta en el portapapeles interno se bloquea y emite pega_intentada", async () => {
    const origenes: OrigenEdicion[] = []
    const intentos: IntentoPegado[] = []
    const container = montar(origenes, intentos)
    const editorEl = await contenedorDelEditor(container)

    // Nunca se copio nada dentro de la pagina: esto es "pegue algo de
    // ChatGPT", el caso que el change NO toca.
    const externo = "import antigravity"
    const ev = eventoDePegado(externo)
    act(() => {
      editorEl.dispatchEvent(ev)
    })

    expect(ev.defaultPrevented).toBe(true)
    expect(intentos).toEqual([
      {
        contenidoLongitud: externo.length,
        contenidoPreview: externo,
        // `shortcut`, no `menu_contextual`. Hasta el 2026-09-30 este campo
        // salia fijo en "menu_contextual" porque los dos caminos habian
        // quedado colapsados en un listener nativo — o sea que un Ctrl+V, el
        // camino MAS comun, se registraba como el menos comun, y estos tests
        // lo tenian cementado. Ahora `metodoDeClipboard` distingue: si no
        // hubo un `contextmenu` reciente, fue atajo.
        metodo: "shortcut",
      },
    ])
    expect(origenes).toEqual([])
  })

  it("1.4 — copiar interno, despues un pegado con contenido distinto: el interno quedo viejo y se bloquea", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const origenes: OrigenEdicion[] = []
    const intentos: IntentoPegado[] = []
    const container = montar(origenes, intentos)
    const editorEl = await contenedorDelEditor(container)
    const ed = editoresCreados[0]
    if (!ed) throw new Error("no se creo el editor")
    const consigna = container.querySelector('[data-testid="consigna-stub"]')
    if (!consigna) throw new Error("no se encontro el stub de la consigna")

    const textoInterno = "variable_de_la_consigna"
    act(() => {
      copiar(consigna as HTMLElement, textoInterno)
    })

    // Primero se prueba que el mecanismo FUNCIONA (si no, el test de abajo
    // seria trivial: cualquier cosa "quedaria vieja" porque nunca hubo nada
    // vigente).
    const evValido = eventoDePegado(textoInterno)
    act(() => {
      editorEl.dispatchEvent(evValido)
    })
    expect(evValido.defaultPrevented).toBe(false)
    act(() => {
      ed.__pegar(textoInterno)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS)
    })
    expect(origenes).toEqual(["pasted_internal"])

    // Ahora el alumno fue a otra pestana, copio algo de ChatGPT (ese copiado
    // NUNCA pasa por esta pagina, asi que el portapapeles interno sigue
    // apuntando al texto de la consigna) y vuelve a pegar.
    const textoExterno = "solucion_completa_de_chatgpt()"
    const evInvalido = eventoDePegado(textoExterno)
    act(() => {
      editorEl.dispatchEvent(evInvalido)
    })

    expect(evInvalido.defaultPrevented).toBe(true)
    expect(intentos).toEqual([
      {
        contenidoLongitud: textoExterno.length,
        contenidoPreview: textoExterno,
        // `shortcut`, no `menu_contextual`. Hasta el 2026-09-30 este campo
        // salia fijo en "menu_contextual" porque los dos caminos habian
        // quedado colapsados en un listener nativo — o sea que un Ctrl+V, el
        // camino MAS comun, se registraba como el menos comun, y estos tests
        // lo tenian cementado. Ahora `metodoDeClipboard` distingue: si no
        // hubo un `contextmenu` reciente, fue atajo.
        metodo: "shortcut",
      },
    ])
    vi.useRealTimers()
  })
})

describe("los agujeros que encontro QA el 2026-09-30", () => {
  it("FUGA A: una seleccion que ARRANCA permitida y se EXTIENDE al tutor se bloquea", async () => {
    // El vector real es Ctrl+A. La primera version chequeaba con `closest()`,
    // que mira donde EMPEZO la seleccion y no que CONTIENE: el target quedaba
    // afuera del panel del tutor, entraba por la puerta permitida, y el blob
    // completo —con el codigo del tutor adentro— se volvia pegable.
    //
    // Cuatro gestos y el alumno tenia la solucion. Y peor: el evento salia
    // `pasted_internal` -> N2, o sea que la cadena registraba apropiacion de
    // bajo nivel sobre lo que era una delegacion.
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const origenes: OrigenEdicion[] = []
    const intentos: IntentoPegado[] = []
    const container = montar(origenes, intentos)
    const editorEl = await contenedorDelEditor(container)

    const consigna = container.querySelector<HTMLElement>('[data-testid="consigna-stub"]')
    const tutor = container.querySelector<HTMLElement>('[data-testid="tutor-stub"]')
    if (!consigna || !tutor) throw new Error("faltan los stubs")

    const blob = "de la consigna\ndel tutor: def resolver(): return 42"
    copiar(consigna, blob, tutor) // arranca en la consigna, termina en el tutor

    const ev = eventoDePegado(blob)
    editorEl.dispatchEvent(ev)
    expect(ev.defaultPrevented).toBe(true)
  })

  it("el rastro de auditoria del copiado no puede desaparecer en silencio", async () => {
    // QA borro entera la emision de `copia_intentada` y los 548 tests siguieron
    // verdes: `montar()` nunca pasaba `onCopyAttempt`. Hasta este change ese
    // evento registraba un intento FALLIDO; ahora el copiado funciona, asi que
    // es el UNICO registro de que el alumno copio algo.
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const copias: { seleccionChars: number; metodo: string }[] = []
    const { container } = render(
      <div>
        <CodeEditor
          initialCode="x = 0"
          language="python"
          ejercicioId="ej-1"
          testCases={CASOS_PUBLICOS}
          onEditDebounced={() => {}}
          onCopyAttempt={(p) => copias.push(p)}
        />
      </div>,
    )
    const editorEl = await contenedorDelEditor(container)
    const ed = editoresCreados[0]
    if (!ed) throw new Error("no se creo el editor")

    ed.__setSeleccion("x = 0")
    editorEl.dispatchEvent(new Event("copy", { bubbles: true, cancelable: true }))

    expect(copias.length).toBe(1)
    expect(copias[0]?.seleccionChars).toBe(5)
  })

  it("metodo distingue el menu contextual del atajo, en vez de mentir fijo", async () => {
    // Al unificar los dos caminos en un listener nativo el campo quedo en un
    // valor fijo — plausible y falso. `metodoDeClipboard` lo recupera mirando
    // si hubo un `contextmenu` reciente.
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const copias: { seleccionChars: number; metodo: string }[] = []
    const { container } = render(
      <div>
        <CodeEditor
          initialCode="x = 0"
          language="python"
          ejercicioId="ej-1"
          testCases={CASOS_PUBLICOS}
          onEditDebounced={() => {}}
          onCopyAttempt={(p) => copias.push(p)}
        />
      </div>,
    )
    const editorEl = await contenedorDelEditor(container)
    const ed = editoresCreados[0]
    if (!ed) throw new Error("no se creo el editor")
    ed.__setSeleccion("x = 0")

    // Sin menu previo -> atajo
    editorEl.dispatchEvent(new Event("copy", { bubbles: true, cancelable: true }))
    expect(copias[0]?.metodo).toBe("shortcut")

    // Con menu justo antes -> menu contextual
    editorEl.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true }))
    editorEl.dispatchEvent(new Event("copy", { bubbles: true, cancelable: true }))
    expect(copias[1]?.metodo).toBe("menu_contextual")
  })
})
