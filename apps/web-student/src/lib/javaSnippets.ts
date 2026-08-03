/**
 * Snippets de ceremonia para Java en el editor del alumno.
 *
 * ALCANCE DELIBERADO — solo ceremonia, nunca logica
 * -------------------------------------------------
 * Java obliga al alumno a escribir andamiaje que no es lo que se esta
 * evaluando: `System.out.println`, getters/setters, el `import` del Scanner.
 * Eso es ruido de sintaxis, no elaboracion. El editor ya asume esa postura en
 * otro lado: `LANGUAGE_PLACEHOLDER.java` (ver `api.ts`) abre el archivo con la
 * clase `Main` y su `main` ya escritos, porque el runner corre literalmente
 * `javac Main.java && java Main` — la ceremonia es un requisito de la
 * infraestructura, no una decision del alumno.
 *
 * Lo que NO entra aca: estructuras de control (`for`, `while`, `if`). En
 * Programacion 1 pre-universitario escribir el `for` ES el objetivo de
 * aprendizaje; un snippet que lo resuelve no ahorra ceremonia, resuelve el
 * ejercicio.
 *
 * Tampoco entran colecciones (`ArrayList`, `HashMap`): el ejercicio integrador
 * E3 del banco PID-UTN ("Agenda de Turnos") prohibe explicitamente listas,
 * dicts, sets y tuplas. Ofrecer un snippet que sirve en bandeja justo lo que
 * la consigna veda seria trabajar en contra del enunciado.
 *
 * Trazabilidad
 * ------------
 * Cada aceptacion dispara `SNIPPET_ACCEPTED_COMMAND_ID`, que el `CodeEditor`
 * usa para emitir la edicion con `origin="snippet_expanded"` en vez de
 * `student_typed`. Sin eso, una expansion de 8 lineas entra al CTR como si el
 * alumno las hubiera tipeado — una mentira que no se nota, porque el evento se
 * ve igual y el diff grande no llama la atencion.
 *
 * `snippet_expanded` NO se etiqueta N4: en este modelo N4 es "interaccion con
 * IA" (ver docstring de `event_labeler.py`), y un snippet no es IA. Mandarlo a
 * N4 inflaria la metrica de dependencia del tutor cada vez que alguien escribe
 * `sout`. Cae a N2 (elaboracion estrategica), igual que `student_typed`, y la
 * distincion queda guardada en el payload para el analisis posterior.
 */

import type * as Monaco from "monaco-editor"

/** Comando que Monaco ejecuta al aceptar cualquiera de estos snippets. */
export const SNIPPET_ACCEPTED_COMMAND_ID = "aiNative.javaSnippetAccepted"

/** Import que el snippet `scanner` necesita tener arriba del archivo. */
const SCANNER_IMPORT = "import java.util.Scanner;"

export interface FieldDecl {
  /** Tipo declarado, tal cual aparece en el fuente (`int`, `String`, `double`). */
  type: string
  /** Nombre del campo. */
  name: string
}

/**
 * Campos de instancia declarados `private`. Regex a proposito, no un parser:
 * el codigo de Programacion 1 es una clase plana y un parser de Java entero
 * seria un language server, que es exactamente lo que este archivo evita.
 *
 * Acepta modificadores en cualquier orden (`private static final`), tipos
 * genericos (`List<String>`) y arrays (`int[]`), con o sin inicializador.
 */
const FIELD_RE =
  /^[ \t]*private[ \t]+(?:(?:static|final|transient|volatile)[ \t]+)*([A-Za-z_$][\w$.]*(?:<[^>\n]*>)?(?:\[\])*)[ \t]+([a-zA-Z_$][\w$]*)[ \t]*(?:=[^;\n]*)?;/gm

export function parseFields(source: string): FieldDecl[] {
  const out: FieldDecl[] = []
  const seen = new Set<string>()
  // `lastIndex` es estado mutable de la regex global — la reseteamos para que
  // dos llamadas seguidas no arranquen desde donde quedo la anterior.
  FIELD_RE.lastIndex = 0
  let m: RegExpExecArray | null = FIELD_RE.exec(source)
  while (m !== null) {
    const type = m[1]
    const name = m[2]
    if (type && name && !seen.has(name)) {
      seen.add(name)
      out.push({ type, name })
    }
    m = FIELD_RE.exec(source)
  }
  return out
}

/** `precioUnitario` -> `PrecioUnitario`, para armar `getPrecioUnitario`. */
export function capitalize(name: string): string {
  // `charAt` en vez de `name[0]` porque devuelve "" en el string vacio en vez
  // de `undefined` — sin non-null assertion.
  return name.charAt(0).toUpperCase() + name.slice(1)
}

/**
 * Los `boolean` llevan `isX()` por convencion JavaBeans, no `getX()`.
 * Si el campo ya se llama `isActivo`, no duplicamos el prefijo.
 */
export function getterName(field: FieldDecl): string {
  if (field.type === "boolean") {
    return /^is[A-Z]/.test(field.name) ? field.name : `is${capitalize(field.name)}`
  }
  return `get${capitalize(field.name)}`
}

export function setterName(field: FieldDecl): string {
  return `set${capitalize(field.name)}`
}

export function getterSource(field: FieldDecl): string {
  return [`public ${field.type} ${getterName(field)}() {`, `    return ${field.name};`, "}"].join(
    "\n",
  )
}

export function setterSource(field: FieldDecl): string {
  return [
    `public void ${setterName(field)}(${field.type} ${field.name}) {`,
    `    this.${field.name} = ${field.name};`,
    "}",
  ].join("\n")
}

/** Un accesor ya definido no se vuelve a ofrecer. */
function hasMethod(source: string, method: string): boolean {
  return new RegExp(`\\b${method}\\s*\\(`).test(source)
}

/**
 * Donde insertar un `import`: despues del ultimo import existente, o arriba de
 * todo si no hay ninguno (respetando la linea `package` si esta).
 *
 * Devuelve el numero de linea (1-based) *antes* de la cual insertar.
 */
export function importInsertLine(lines: readonly string[]): number {
  let lastImport = 0
  let packageLine = 0
  for (let i = 0; i < lines.length; i++) {
    const line = (lines[i] ?? "").trim()
    if (line.startsWith("import ")) lastImport = i + 1
    else if (line.startsWith("package ")) packageLine = i + 1
  }
  if (lastImport > 0) return lastImport + 1
  if (packageLine > 0) return packageLine + 1
  return 1
}

interface SnippetSpec {
  label: string
  detail: string
  documentation: string
  insertText: string
  /** Import que hay que garantizar arriba del archivo, si aplica. */
  requiresImport?: string
}

/** Ceremonia pura, independiente del contenido del archivo. */
const STATIC_SNIPPETS: readonly SnippetSpec[] = [
  {
    label: "sout",
    detail: "System.out.println(...)",
    documentation: "Imprime una linea por salida estandar.",
    insertText: "System.out.println($0);",
  },
  {
    label: "serr",
    detail: "System.err.println(...)",
    documentation: "Imprime una linea por salida de error.",
    insertText: "System.err.println($0);",
  },
  {
    label: "sysin",
    detail: "Scanner sobre System.in",
    documentation: "Declara un Scanner para leer de teclado y agrega el import si falta.",
    insertText: "Scanner ${1:sc} = new Scanner(System.in);\n$0",
    requiresImport: SCANNER_IMPORT,
  },
  {
    label: "psvm",
    detail: "public static void main(String[] args)",
    documentation: "Metodo main. El runner ejecuta `java Main`, asi que la clase debe tenerlo.",
    insertText: "public static void main(String[] args) {\n    $0\n}",
  },
  {
    label: "class",
    detail: "class Nombre { ... }",
    documentation: "Clase auxiliar dentro del archivo.",
    insertText: "class ${1:Nombre} {\n    $0\n}",
  },
]

/**
 * Registra el proveedor de snippets de Java y el comando de trazabilidad.
 *
 * @param monaco   modulo `monaco-editor` ya importado.
 * @param onAccept se invoca al aceptar un snippet, antes del proximo flush de
 *                 `edicion_codigo`. El `CodeEditor` lo usa para marcar el
 *                 origin de la ventana de debounce en curso.
 * @returns disposable que da de baja proveedor y comando.
 */
export function registerJavaSnippets(
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

  const providerDisposable = monaco.languages.registerCompletionItemProvider("java", {
    provideCompletionItems: (model, position) => {
      const word = model.getWordUntilPosition(position)
      const range: Monaco.IRange = {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: word.startColumn,
        endColumn: word.endColumn,
      }

      const source = model.getValue()
      const lines = source.split("\n")
      const suggestions: Monaco.languages.CompletionItem[] = []

      /** Edit que agrega el import arriba del archivo, si todavia no esta. */
      const importEdits = (
        importStmt: string | undefined,
      ): Monaco.editor.ISingleEditOperation[] | undefined => {
        if (!importStmt) return undefined
        if (source.includes(importStmt)) return undefined
        const line = importInsertLine(lines)
        return [
          {
            range: {
              startLineNumber: line,
              endLineNumber: line,
              startColumn: 1,
              endColumn: 1,
            },
            text: `${importStmt}\n`,
          },
        ]
      }

      for (const spec of STATIC_SNIPPETS) {
        const extra = importEdits(spec.requiresImport)
        suggestions.push({
          label: spec.label,
          kind: monaco.languages.CompletionItemKind.Snippet,
          detail: spec.detail,
          documentation: spec.documentation,
          insertText: spec.insertText,
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          range,
          command: acceptCommand,
          ...(extra ? { additionalTextEdits: extra } : {}),
        })
      }

      // ── Accesores derivados de los campos declarados en el archivo ────────
      const fields = parseFields(source)
      const missingGetters = fields.filter((f) => !hasMethod(source, getterName(f)))
      const missingSetters = fields.filter((f) => !hasMethod(source, setterName(f)))

      for (const field of missingGetters) {
        suggestions.push({
          label: getterName(field),
          kind: monaco.languages.CompletionItemKind.Snippet,
          detail: `Getter de ${field.name}`,
          documentation: `Devuelve ${field.name} (${field.type}).`,
          insertText: getterSource(field),
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          range,
          command: acceptCommand,
        })
      }

      for (const field of missingSetters) {
        suggestions.push({
          label: setterName(field),
          kind: monaco.languages.CompletionItemKind.Snippet,
          detail: `Setter de ${field.name}`,
          documentation: `Asigna ${field.name} (${field.type}).`,
          insertText: setterSource(field),
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          range,
          command: acceptCommand,
        })
      }

      // Un solo item que completa TODO lo que falta — el caso real de una clase
      // con varios campos, donde ir uno por uno es justamente la ceremonia.
      if (missingGetters.length + missingSetters.length > 1) {
        const body = [
          ...missingGetters.map(getterSource),
          ...missingSetters.map(setterSource),
        ].join("\n\n")
        suggestions.push({
          label: "getset",
          kind: monaco.languages.CompletionItemKind.Snippet,
          detail: `Getters y setters faltantes (${missingGetters.length + missingSetters.length})`,
          documentation: "Genera de una todos los accesores que faltan para los campos privados.",
          insertText: body,
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          range,
          command: acceptCommand,
        })
      }

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
