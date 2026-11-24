/**
 * PSeInt en el editor del alumno (HU-030): el lenguaje para Monaco (resaltado
 * de sintaxis) y sus snippets de ceremonia.
 *
 * Monaco no trae PSeInt, así que se registra un lenguaje `pseint` con un
 * tokenizador Monarch: palabras clave, textos, comentarios `//` y números. Las
 * palabras clave no distinguen mayúsculas, igual que en PSeInt.
 *
 * Los snippets siguen el mismo criterio que `pythonSnippets.ts` y
 * `javaSnippets.ts`: SOLO ceremonia, nunca lógica. Entra el esqueleto
 * `Algoritmo … FinAlgoritmo` y la E/S (`Escribir`, `Leer`, `Definir`), que el
 * alumno tipea igual en todos los ejercicios. Las estructuras de control
 * (`Si`, `Mientras`, `Para`) NO entran: en Programación 1 escribirlas es el
 * objetivo de aprendizaje.
 *
 * Trazabilidad: cada aceptación dispara un comando PROPIO de PSeInt (no se
 * comparte con Python ni Java: `registerCommand` sobre un id ya registrado
 * encadena handlers) que el `CodeEditor` usa para emitir la edición con
 * `origin="snippet_expanded"` en vez de `student_typed`.
 */

import type * as Monaco from "monaco-editor"

/** Id del lenguaje en Monaco. Coincide con el `Language` del contrato. */
export const PSEINT_LANGUAGE_ID = "pseint"

/** Comando que Monaco ejecuta al aceptar cualquiera de estos snippets. */
export const PSEINT_SNIPPET_ACCEPTED_COMMAND_ID = "aiNative.pseintSnippetAccepted"

const PALABRAS_CLAVE = [
  "Algoritmo",
  "FinAlgoritmo",
  "Proceso",
  "FinProceso",
  "Funcion",
  "FinFuncion",
  "SubProceso",
  "FinSubProceso",
  "SubAlgoritmo",
  "FinSubAlgoritmo",
  "Definir",
  "Como",
  "Dimension",
  "Leer",
  "Escribir",
  "Imprimir",
  "Mostrar",
  "Sin",
  "Saltar",
  "Bajar",
  "Si",
  "Entonces",
  "SiNo",
  "FinSi",
  "Segun",
  "Hacer",
  "De",
  "Otro",
  "Modo",
  "FinSegun",
  "Mientras",
  "FinMientras",
  "Repetir",
  "Hasta",
  "Que",
  "Para",
  "Con",
  "Paso",
  "FinPara",
  "Fin",
  "Por",
  "Referencia",
  "Valor",
]

const TIPOS = ["Entero", "Real", "Numero", "Numerico", "Caracter", "Texto", "Cadena", "Logico"]

const OPERADORES_PALABRA = ["Y", "O", "NO", "MOD"]

const CONSTANTES = ["Verdadero", "Falso", "PI"]

/** Tokenizador Monarch. Exportado para auditarlo sin levantar Monaco. */
export const PSEINT_MONARCH: Monaco.languages.IMonarchLanguage = {
  ignoreCase: true,
  defaultToken: "",
  keywords: PALABRAS_CLAVE,
  typeKeywords: TIPOS,
  operatorWords: OPERADORES_PALABRA,
  constants: CONSTANTES,
  tokenizer: {
    root: [
      [/\/\/.*$/, "comment"],
      [/"[^"]*"/, "string"],
      [/'[^']*'/, "string"],
      [/"[^"]*$/, "string.invalid"],
      [/\d+(\.\d+)?/, "number"],
      [
        /[a-zA-ZáéíóúÁÉÍÓÚñÑ_][\wáéíóúÁÉÍÓÚñÑ]*/,
        {
          cases: {
            "@keywords": "keyword",
            "@typeKeywords": "type",
            "@operatorWords": "operator",
            "@constants": "constant",
            "@default": "identifier",
          },
        },
      ],
      [/<-|<=|>=|<>|[=<>+\-*/^%&|~]/, "operator"],
      [/[()[\],;:]/, "delimiter"],
    ],
  },
}

export interface PseintSnippetSpec {
  label: string
  detail: string
  documentation: string
  insertText: string
}

/** Ceremonia pura, independiente del contenido del archivo. */
export const PSEINT_SNIPPETS: readonly PseintSnippetSpec[] = [
  {
    label: "Algoritmo",
    detail: "Algoritmo … FinAlgoritmo",
    documentation: "Esqueleto de un algoritmo de PSeInt.",
    insertText: "Algoritmo ${1:sin_titulo}\n\t$0\nFinAlgoritmo",
  },
  {
    label: "Escribir",
    detail: 'Escribir "..."',
    documentation: "Muestra un mensaje o un valor por pantalla.",
    insertText: "Escribir $0",
  },
  {
    label: "Leer",
    detail: "Leer variable",
    documentation: "Lee un dato del teclado y lo guarda en una variable.",
    insertText: "Leer $0",
  },
  {
    label: "Definir",
    detail: "Definir variable Como Tipo",
    documentation: "Declara una variable con su tipo (Entero, Real, Caracter o Logico).",
    insertText: "Definir ${1:variable} Como ${2|Entero,Real,Caracter,Logico|}$0",
  },
]

const registrados = new WeakSet<object>()

/**
 * Registra el lenguaje `pseint` en Monaco. Idempotente: el `CodeEditor` lo
 * llama antes de cada `editor.create`, y un segundo registro duplicaría el
 * tokenizador.
 */
export function registrarLenguajePseint(monaco: typeof Monaco): void {
  if (registrados.has(monaco)) return
  registrados.add(monaco)
  monaco.languages.register({ id: PSEINT_LANGUAGE_ID, extensions: [".psc"], aliases: ["PSeInt"] })
  monaco.languages.setMonarchTokensProvider(PSEINT_LANGUAGE_ID, PSEINT_MONARCH)
  monaco.languages.setLanguageConfiguration(PSEINT_LANGUAGE_ID, {
    comments: { lineComment: "//" },
    brackets: [
      ["(", ")"],
      ["[", "]"],
    ],
    autoClosingPairs: [
      { open: "(", close: ")" },
      { open: "[", close: "]" },
      { open: '"', close: '"' },
    ],
  })
}

/**
 * Registra el proveedor de snippets de PSeInt y el comando de trazabilidad.
 *
 * @returns disposable que da de baja proveedor y comando.
 */
export function registerPseintSnippets(
  monaco: typeof Monaco,
  onAccept: () => void,
): Monaco.IDisposable {
  const commandDisposable = monaco.editor.registerCommand(
    PSEINT_SNIPPET_ACCEPTED_COMMAND_ID,
    () => {
      onAccept()
    },
  )
  const acceptCommand = {
    id: PSEINT_SNIPPET_ACCEPTED_COMMAND_ID,
    title: "Registrar expansion de snippet",
  }
  const providerDisposable = monaco.languages.registerCompletionItemProvider(PSEINT_LANGUAGE_ID, {
    provideCompletionItems: (model, position) => {
      const word = model.getWordUntilPosition(position)
      const range: Monaco.IRange = {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: word.startColumn,
        endColumn: word.endColumn,
      }
      const suggestions: Monaco.languages.CompletionItem[] = PSEINT_SNIPPETS.map((spec) => ({
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
