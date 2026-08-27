/**
 * Snippets de ceremonia para Python en el editor del alumno.
 *
 * Espejo de `javaSnippets.ts`. Mismo alcance deliberado y, sobre todo, la
 * MISMA trazabilidad: sin el comando de aceptacion, el codigo que inserta el
 * editor entra a la cadena CTR como `student_typed`.
 *
 * ALCANCE DELIBERADO — solo ceremonia, nunca logica
 * -------------------------------------------------
 * Python casi no tiene ceremonia: por eso esta lista es corta y va a seguir
 * siendo corta. Entra unicamente lo que el alumno tipea igual en todos los
 * ejercicios sin que eso sea lo evaluado:
 *
 *   - `print` / `input`: los dos unicos puntos de E/S de la consola de la
 *     cursada. Son el equivalente exacto de `sout` y `sysin` del lado Java.
 *   - `if __name__ == "__main__":`: guarda de modulo. Es literalmente la misma
 *     linea siempre y no expresa ninguna decision del alumno — el gemelo de
 *     `psvm`.
 *
 * Lo que NO entra aca: estructuras de control (`for`, `while`, `if`). En
 * Programacion 1 pre-universitario escribir el `for` ES el objetivo de
 * aprendizaje; un snippet que lo resuelve no ahorra ceremonia, resuelve el
 * ejercicio. Tampoco entran colecciones (`list`, `dict`, `set`, comprehensions):
 * el ejercicio integrador E3 del banco PID-UTN ("Agenda de Turnos") las prohibe
 * explicitamente, asi que ofrecerlas seria trabajar en contra del enunciado.
 *
 * Trazabilidad
 * ------------
 * Cada aceptacion dispara `SNIPPET_ACCEPTED_COMMAND_ID`, que el `CodeEditor`
 * usa para emitir la edicion con `origin="snippet_expanded"` en vez de
 * `student_typed`. Sin eso, la plataforma afirma que el alumno tipeo algo que
 * le puso el editor — evidencia falsa en una tesis sobre trazabilidad, y de la
 * peor clase: invisible, porque el evento se ve identico a uno legitimo.
 *
 * El id del comando es PROPIO de Python y no se comparte con Java a proposito:
 * `monaco.editor.registerCommand` sobre un id ya registrado deja los dos
 * handlers encadenados, y dar de baja uno restauraria el otro. Dos ids, dos
 * ciclos de vida independientes.
 *
 * `snippet_expanded` NO se etiqueta N4: en este modelo N4 es "interaccion con
 * IA" (ver docstring de `event_labeler.py`), y un snippet no es IA. Cae a N2
 * (elaboracion estrategica), igual que `student_typed`, y la distincion queda
 * guardada en el payload para el analisis posterior.
 */

import type * as Monaco from "monaco-editor"

/** Comando que Monaco ejecuta al aceptar cualquiera de estos snippets. */
export const SNIPPET_ACCEPTED_COMMAND_ID = "aiNative.pythonSnippetAccepted"

export interface PythonSnippetSpec {
  label: string
  detail: string
  documentation: string
  insertText: string
}

/**
 * Ceremonia pura, independiente del contenido del archivo.
 *
 * Exportado para que se pueda auditar la lista sin levantar Monaco: la
 * propiedad que importa no es que el snippet funcione, es que NINGUNO de estos
 * resuelva logica del ejercicio.
 */
export const PYTHON_SNIPPETS: readonly PythonSnippetSpec[] = [
  {
    label: "print",
    detail: "print(...)",
    documentation: "Imprime una linea por salida estandar.",
    insertText: "print($0)",
  },
  {
    label: "input",
    detail: 'input("mensaje")',
    documentation: "Lee una linea de teclado, mostrando antes un mensaje.",
    insertText: 'input("${1:Ingresa un valor: }")$0',
  },
  {
    label: "main",
    detail: 'if __name__ == "__main__":',
    documentation: "Guarda de modulo: el bloque corre solo si el archivo se ejecuta directamente.",
    insertText: 'if __name__ == "__main__":\n    $0',
  },
]

/**
 * Registra el proveedor de snippets de Python y el comando de trazabilidad.
 *
 * @param monaco   modulo `monaco-editor` ya importado.
 * @param onAccept se invoca al aceptar un snippet, antes del proximo flush de
 *                 `edicion_codigo`. El `CodeEditor` lo usa para marcar el
 *                 origin de la ventana de debounce en curso.
 * @returns disposable que da de baja proveedor y comando.
 */
export function registerPythonSnippets(
  monaco: typeof Monaco,
  onAccept: () => void,
): Monaco.IDisposable {
  const commandDisposable = monaco.editor.registerCommand(SNIPPET_ACCEPTED_COMMAND_ID, () => {
    onAccept()
  })

  const acceptCommand = {
    id: SNIPPET_ACCEPTED_COMMAND_ID,
    title: "Registrar expansion de snippet",
  }

  const providerDisposable = monaco.languages.registerCompletionItemProvider("python", {
    provideCompletionItems: (model, position) => {
      const word = model.getWordUntilPosition(position)
      const range: Monaco.IRange = {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: word.startColumn,
        endColumn: word.endColumn,
      }

      const suggestions: Monaco.languages.CompletionItem[] = PYTHON_SNIPPETS.map((spec) => ({
        label: spec.label,
        kind: monaco.languages.CompletionItemKind.Snippet,
        detail: spec.detail,
        documentation: spec.documentation,
        insertText: spec.insertText,
        insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
        range,
        // Sin este `command` la expansion entra al CTR como `student_typed`.
        command: acceptCommand,
      }))

      return { suggestions }
    },
  })

  return {
    dispose: () => {
      providerDisposable.dispose()
      commandDisposable.dispose()
    },
  }
}
