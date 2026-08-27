/**
 * Doble de `monaco-editor` para ejercitar los REGISTRADORES de snippets.
 *
 * `_monacoMock.ts` (el que `vite.config.ts` aliasea sobre el import real) sirve
 * para montar `CodeEditor`: devuelve un disposable compartido y descarta el
 * proveedor de completions. Eso alcanza para testear el editor, pero no para
 * testear `registerJavaSnippets` / `registerPythonSnippets`, donde lo que
 * importa es justamente lo que se le pasa a Monaco:
 *
 *   - las sugerencias que devuelve `provideCompletionItems` (¿llevan `command`?
 *     ¿qué `insertText` tienen? ¿cuántos `additionalTextEdits`?);
 *   - que `dispose()` dé de baja el proveedor Y el comando, no uno solo.
 *
 * Los dos registradores reciben el módulo `monaco` por parámetro, así que no
 * hace falta ningún alias: se les inyecta este objeto directo.
 */

import type * as Monaco from "monaco-editor"

/** Un `registerCompletionItemProvider` observado. */
export interface ProveedorRegistrado {
  lenguaje: string
  provider: Monaco.languages.CompletionItemProvider
  disposed: boolean
}

/** Un `editor.registerCommand` observado. */
export interface ComandoRegistrado {
  id: string
  handler: () => void
  disposed: boolean
}

export interface MonacoFalso {
  /** El objeto que se le pasa a `registerXSnippets`. */
  monaco: typeof Monaco
  proveedores: ProveedorRegistrado[]
  comandos: ComandoRegistrado[]
  /** Pide las sugerencias al último proveedor registrado, con `source` como
   * contenido del modelo. Devuelve la lista tal cual la arma el registrador. */
  sugerencias(source: string): Monaco.languages.CompletionItem[]
}

/** Posición fija: los registradores solo la usan para armar el `range`, que no
 * es lo que estos tests miran. */
const POSICION = { lineNumber: 1, column: 1 } as Monaco.Position

export function crearMonacoFalso(): MonacoFalso {
  const proveedores: ProveedorRegistrado[] = []
  const comandos: ComandoRegistrado[] = []

  const monaco = {
    editor: {
      registerCommand(id: string, handler: () => void) {
        const entrada: ComandoRegistrado = { id, handler, disposed: false }
        comandos.push(entrada)
        return {
          dispose: () => {
            entrada.disposed = true
          },
        }
      },
    },
    languages: {
      registerCompletionItemProvider(
        lenguaje: string,
        provider: Monaco.languages.CompletionItemProvider,
      ) {
        const entrada: ProveedorRegistrado = { lenguaje, provider, disposed: false }
        proveedores.push(entrada)
        return {
          dispose: () => {
            entrada.disposed = true
          },
        }
      },
      CompletionItemKind: { Snippet: 27 },
      CompletionItemInsertTextRule: { InsertAsSnippet: 4 },
    },
  } as unknown as typeof Monaco

  return {
    monaco,
    proveedores,
    comandos,
    sugerencias(source: string) {
      const ultimo = proveedores[proveedores.length - 1]
      if (!ultimo) throw new Error("no se registro ningun proveedor de completions")
      const model = {
        getValue: () => source,
        getWordUntilPosition: () => ({ word: "", startColumn: 1, endColumn: 1 }),
      } as unknown as Monaco.editor.ITextModel
      const resultado = ultimo.provider.provideCompletionItems(
        model,
        POSICION,
        {} as Monaco.languages.CompletionContext,
        {} as Monaco.CancellationToken,
      )
      if (!resultado || !("suggestions" in resultado)) {
        throw new Error("el proveedor no devolvio sugerencias")
      }
      return resultado.suggestions as Monaco.languages.CompletionItem[]
    },
  }
}
