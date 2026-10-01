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
  /**
   * Marca un fragmento del buffer como seleccionado.
   *
   * Hace falta porque el portapapeles interno se llena con
   * `getModel().getValueInRange(getSelection())` y NO con
   * `window.getSelection()`: Monaco mantiene la seleccion en un textarea
   * oculto, y en Chrome y Firefox `window.getSelection().toString()` devuelve
   * "" cuando la seleccion vive adentro de un control de formulario. Con el
   * lector equivocado "copiar adentro del editor" queda roto en produccion y
   * verde en los tests, asi que el mock modela el lector correcto.
   *
   * Pasar `null` deselecciona.
   */
  __seleccionar(texto: string | null): void
  /** Dispara el handler que `CodeEditor` registro para ese keybinding. */
  __comando(keybinding: number): void
  getValue(): string
  setValue(v: string): void
  onDidPaste(cb: () => void): void
  onDidChangeModelContent(cb: () => void): void
  addCommand(keybinding: number, cb: () => void): void
  getSelection(): SeleccionFalsa | null
  getModel(): ModeloFalso
  executeEdits(fuente: string, ediciones: EdicionFalsa[]): boolean
  updateOptions(o: Record<string, unknown>): void
  focus(): void
  dispose(): void
}

/** Lo que `getSelection()` devuelve. Monaco entrega un `Selection` con
 * coordenadas; acá alcanza con el texto, porque es lo unico que el componente
 * hace con el (leerlo, y usarlo como rango de `executeEdits`). */
export interface SeleccionFalsa {
  texto: string
}

export interface ModeloFalso {
  getValueInRange(sel: SeleccionFalsa | null): string
  getFullModelRange(): SeleccionFalsa
}

export interface EdicionFalsa {
  range: SeleccionFalsa | null
  text: string
  forceMoveMarkers?: boolean
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
  let seleccion: SeleccionFalsa | null = null
  const editor: EditorFalso = {
    __opciones: opciones,
    __comandos: new Map(),
    __seleccionar(texto: string | null) {
      if (texto !== null && !valor.includes(texto)) {
        // Sin esto un test podria "seleccionar" algo que no esta en el buffer
        // y seguir en verde midiendo una situacion que no existe.
        throw new Error(`no se puede seleccionar ${JSON.stringify(texto)}: no esta en el buffer`)
      }
      seleccion = texto === null ? null : { texto }
    },
    __comando(keybinding: number) {
      const cb = editor.__comandos.get(keybinding)
      if (!cb) throw new Error(`no hay comando registrado para el keybinding ${keybinding}`)
      cb()
    },
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
    getSelection: () => seleccion,
    getModel: () => ({
      getValueInRange: (sel: SeleccionFalsa | null) => sel?.texto ?? "",
      getFullModelRange: () => ({ texto: valor }),
    }),
    /**
     * Aplica la edicion al buffer y notifica, como hace Monaco real.
     *
     * Simplificacion deliberada: el rango se modela por TEXTO, asi que se
     * reemplaza la primera ocurrencia de lo seleccionado. Alcanza para lo que
     * el componente hace (reemplazar la seleccion, o insertar si no hay) y
     * deja observable lo que importa: que el pegado interno entra al buffer y
     * dispara el debounce.
     */
    executeEdits: (_fuente: string, ediciones: EdicionFalsa[]) => {
      let siguiente = valor
      for (const ed of ediciones) {
        const sel = ed.range
        siguiente =
          sel && sel.texto !== "" ? siguiente.replace(sel.texto, ed.text) : siguiente + ed.text
      }
      // La seleccion COLAPSA a vacia (el cursor queda donde termino la
      // edicion). NO queda en `null`: Monaco real devuelve un `Selection`
      // vacio en la posicion del cursor, y solo da `null` si no hay modelo ni
      // view state. Modelarlo como `null` hacia que un Ctrl+V despues de un
      // Ctrl+X no encontrara donde insertar — un fallo del doble, no del
      // componente.
      seleccion = { texto: "" }
      editor.__tipear(siguiente)
      return true
    },
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
