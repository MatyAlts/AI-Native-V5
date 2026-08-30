/**
 * Doble de `monaco-editor` para poder testear `CodeEditor` en jsdom.
 *
 * Monaco real no arranca en jsdom (necesita layout, workers y canvas) y ni
 * siquiera resuelve como entry de paquete bajo Vitest, asi que la logica del
 * editor —el debounce de `edicion_codigo`, el reseed del buffer al re-montar,
 * la config de autocompletado— nunca estuvo cubierta por un test. Este modulo
 * se enchufa via `test.alias` en `vite.config.ts` y expone la superficie MINIMA
 * que `CodeEditor` consume, mas dos ganchos para manejarlo desde los tests:
 *
 *   - `__tipear(texto)`  simula que el alumno escribe: cambia el buffer y
 *                        dispara `onDidChangeModelContent`, igual que Monaco.
 *   - `__opciones`       las opciones con las que se llamo a `editor.create`,
 *                        que es donde vive la config de sugerencias.
 *
 * `editoresCreados` acumula un item por cada `create()`: un re-montaje del
 * componente agrega uno nuevo, y comparar el `value` con el que se sembro cada
 * uno es exactamente como se observa la perdida de codigo al cruzar el
 * breakpoint mobile.
 */

export interface EditorFalso {
  /** Opciones con las que `monaco.editor.create` fue invocado. */
  __opciones: Record<string, unknown>
  /** Simula tipeo del alumno: setea el buffer y notifica a los listeners. */
  __tipear(texto: string): void
  /**
   * Simula un pegado: dispara `onDidPaste` y DESPUES cambia el buffer, en ese
   * orden — es el orden de Monaco real, y de el depende que la marca de origen
   * este puesta cuando el debounce arranca. El mock descartaba el callback
   * (`onDidPaste: () => {}`), asi que `origin: "pasted_external"` —la unica
   * marca que lleva override a N4 en el labeler— era inobservable.
   */
  __pegar(texto: string): void
  /** Comandos registrados con `addCommand`, por keybinding. */
  __comandos: Map<number, () => void>
  getValue(): string
  setValue(v: string): void
  onDidPaste(cb: () => void): void
  onDidChangeModelContent(cb: () => void): void
  addCommand(keybinding: number, cb: () => void): void
  getSelection(): null
  getModel(): Record<string, unknown>
  updateOptions(o: Record<string, unknown>): void
  focus(): void
  dispose(): void
}

/** Un item por cada `monaco.editor.create`, en orden de creacion. */
export const editoresCreados: EditorFalso[] = []

/** Limpia el registro entre tests (el modulo es singleton para todo el file). */
/**
 * Lenguajes para los que `CodeEditor` registro un proveedor de completions, en
 * orden de registro.
 *
 * El mock descartaba el registro (`registerCompletionItemProvider: () => disposable`)
 * y con eso el hecho de que `CodeEditor` conecta los snippets quedaba
 * INOBSERVABLE: borrar la linea `registerPythonSnippets(monaco, ...)` desconecta
 * ED-3 entero —el alumno pierde todo el autocompletado de Python— y ningun test
 * se entera. Registrarlo acá abre el unico seam posible: la conexion es un
 * efecto, no hay funcion pura que extraer, asi que lo que se puede anclar es
 * que el efecto ocurrio.
 */
export const lenguajesConSnippets: string[] = []

/**
 * Handlers registrados con `monaco.editor.registerCommand`, por id.
 *
 * El unico que hay es el que los registradores de snippets disparan al ACEPTAR
 * una sugerencia, y es lo que marca la edicion como `snippet_expanded`. El mock
 * lo descartaba (`registerCommand: () => disposable`), asi que la marca era
 * inobservable: una expansion de 8 lineas podia entrar al CTR como tipeada por
 * el alumno y ningun test se enteraba.
 */
export const comandosRegistrados = new Map<string, () => void>()

/** Simula que el alumno acepto una sugerencia de snippet. Hay un id por
 * lenguaje: `aiNative.pythonSnippetAccepted` / `aiNative.javaSnippetAccepted`. */
export function aceptarSnippet(id = "aiNative.pythonSnippetAccepted"): void {
  const handler = comandosRegistrados.get(id)
  if (!handler) throw new Error(`no se registro el comando ${id}`)
  handler()
}

export function resetMonacoMock(): void {
  editoresCreados.length = 0
  lenguajesConSnippets.length = 0
  comandosRegistrados.clear()
}

function create(_container: HTMLElement, opciones: Record<string, unknown>): EditorFalso {
  const listeners: (() => void)[] = []
  const pasteListeners: (() => void)[] = []
  let valor = String(opciones.value ?? "")
  const editor: EditorFalso = {
    __opciones: opciones,
    __comandos: new Map(),
    __tipear(texto: string) {
      valor = texto
      for (const l of [...listeners]) l()
    },
    __pegar(texto: string) {
      // Monaco dispara `onDidPaste` ANTES de `onDidChangeModelContent`.
      for (const l of [...pasteListeners]) l()
      editor.__tipear(texto)
    },
    getValue: () => valor,
    // Monaco real dispara `onDidChangeModelContent` tambien cuando el cambio
    // viene de `setValue` (p.ej. "Restaurar plantilla"): el modelo cambio de
    // verdad. Lo replicamos para no testear un editor mas complaciente que el
    // que corre en produccion.
    setValue: (v: string) => {
      editor.__tipear(v)
    },
    onDidPaste: (cb: () => void) => {
      pasteListeners.push(cb)
    },
    onDidChangeModelContent: (cb: () => void) => {
      listeners.push(cb)
    },
    addCommand: (keybinding: number, cb: () => void) => {
      editor.__comandos.set(keybinding, cb)
    },
    getSelection: () => null,
    // El modelo tiene que saber contar lineas. `setErrorMarkerAtLine` (ED-4)
    // llama a `getLineCount()` / `getLineMaxColumn()` para no marcar una linea
    // que ya no existe, y con un `{}` vacio eso explota con "getLineCount is
    // not a function" — pero SOLO cuando la corrida falla con un traceback que
    // trae numero de linea. Los tests con el doble de Pyodide nunca producian
    // uno, asi que el agujero vivio invisible hasta que los tests de Pyodide
    // real empezaron a generar tracebacks de verdad.
    //
    // Importa mas de lo que parece: en `runCode` el `catch` llama a
    // `setErrorMarker` ANTES de `pushRunHistory` / `onCodeExecuted`. Si esa
    // llamada tira, la corrida fallida nunca llega al historial ni al evento
    // CTR `codigo_ejecutado`. Un mock que no puede reproducirlo tampoco puede
    // avisar si eso se rompe.
    getModel: () => ({
      getLineCount: () => valor.split("\n").length,
      getLineMaxColumn: (linea: number) => (valor.split("\n")[linea - 1] ?? "").length + 1,
    }),
    updateOptions: () => {},
    focus: () => {},
    dispose: () => {},
  }
  editoresCreados.push(editor)
  return editor
}

const disposable = { dispose: () => {} }

export const editor = {
  create,
  setModelMarkers: () => {},
  registerCommand: (id: string, handler: () => void) => {
    comandosRegistrados.set(id, handler)
    return disposable
  },
}

export const KeyMod = { CtrlCmd: 2048 }
export const KeyCode = { KeyV: 52, KeyC: 33, KeyX: 54, Enter: 3 }
export const MarkerSeverity = { Error: 8 }
export const languages = {
  registerCompletionItemProvider: (lenguaje: string) => {
    lenguajesConSnippets.push(lenguaje)
    return disposable
  },
  CompletionItemKind: { Snippet: 27 },
  CompletionItemInsertTextRule: { InsertAsSnippet: 4 },
}
