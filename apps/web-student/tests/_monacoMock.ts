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
export function resetMonacoMock(): void {
  editoresCreados.length = 0
}

function create(_container: HTMLElement, opciones: Record<string, unknown>): EditorFalso {
  const listeners: (() => void)[] = []
  let valor = String(opciones.value ?? "")
  const editor: EditorFalso = {
    __opciones: opciones,
    __comandos: new Map(),
    __tipear(texto: string) {
      valor = texto
      for (const l of [...listeners]) l()
    },
    getValue: () => valor,
    setValue: (v: string) => {
      valor = v
    },
    onDidPaste: () => {},
    onDidChangeModelContent: (cb: () => void) => {
      listeners.push(cb)
    },
    addCommand: (keybinding: number, cb: () => void) => {
      editor.__comandos.set(keybinding, cb)
    },
    getSelection: () => null,
    getModel: () => ({}),
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
  registerCommand: () => disposable,
}

export const KeyMod = { CtrlCmd: 2048 }
export const KeyCode = { KeyV: 52, KeyC: 33, KeyX: 54, Enter: 3 }
export const MarkerSeverity = { Error: 8 }
export const languages = {
  registerCompletionItemProvider: () => disposable,
  CompletionItemKind: { Snippet: 27 },
  CompletionItemInsertTextRule: { InsertAsSnippet: 4 },
}
