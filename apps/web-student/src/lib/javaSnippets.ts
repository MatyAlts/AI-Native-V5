/**
 * Snippets de ceremonia para Java en el editor del alumno.
 *
 * ALCANCE DELIBERADO — solo ceremonia, nunca logica
 * -------------------------------------------------
 * Java obliga al alumno a escribir andamiaje que no es lo que se esta
 * evaluando: `System.out.println`, getters/setters, el `import` del Scanner,
 * los constructores que repiten `this.x = x` una vez por campo y los overrides
 * canonicos (`toString`, `equals`, `hashCode`), cuyo cuerpo queda determinado
 * por los campos y no admite decision del alumno.
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

/** Imports que necesitan los overrides de igualdad (JAVA-2). */
const OBJECTS_IMPORT = "import java.util.Objects;"
const ARRAYS_IMPORT = "import java.util.Arrays;"

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

// ── JAVA-2: constructores y overrides ────────────────────────────────────────
//
// Todo lo de abajo es ceremonia canonica: dado el conjunto de campos, el cuerpo
// del constructor, del `toString`, del `equals` y del `hashCode` no admite
// decision del alumno — se escriben SIEMPRE igual. Es exactamente el andamiaje
// que Java exige y que no es lo que la materia evalua.

/** Una clase declarada en el archivo, con el fuente que le corresponde. */
export interface ClassBlock {
  name: string
  /** Fuente desde su `class X` hasta la declaracion de la clase siguiente (o
   * el fin del archivo). Sirve para atribuirle SUS campos y SUS metodos. */
  source: string
}

const CLASS_DECL_RE =
  /^[ \t]*(?:(?:public|final|abstract|static|private|protected)[ \t]+)*class[ \t]+([A-Za-z_$][\w$]*)/gm

/**
 * Parte el archivo por declaracion de clase.
 *
 * Regex y no parser, igual que `parseFields`: el codigo de Programacion 1 es un
 * archivo con la clase `Main` y, a lo sumo, una clase auxiliar plana al lado.
 *
 * El corte es por declaracion, NO por llaves balanceadas: una clase anidada
 * quedaria como un bloque hermano y le robaria el resto del fuente a la que la
 * contiene. Es la misma aproximacion (y la misma limitacion) que ya tenia
 * `parseFields`, que mira el archivo entero.
 */
export function parseClassBlocks(source: string): ClassBlock[] {
  const marcas: { name: string; index: number }[] = []
  CLASS_DECL_RE.lastIndex = 0
  let m: RegExpExecArray | null = CLASS_DECL_RE.exec(source)
  while (m !== null) {
    const name = m[1]
    if (name) marcas.push({ name, index: m.index })
    m = CLASS_DECL_RE.exec(source)
  }
  return marcas.map((marca, i) => ({
    name: marca.name,
    source: source.slice(marca.index, marcas[i + 1]?.index ?? source.length),
  }))
}

/**
 * Listas de parametros (crudas, sin parsear) de los constructores ya
 * declarados en la clase. `[""]` significa "hay un constructor sin argumentos".
 *
 * Existe para no ofrecer dos veces lo mismo: si el alumno ya escribio el
 * constructor completo, el snippet desaparece.
 */
export function declaredConstructorParams(classSource: string, className: string): string[] {
  // `$` es legal en un identificador Java y significa "fin de input" en una
  // regex: sin escaparlo, una clase `A$B` construiria un patron que no matchea
  // nada (o peor, matchea de mas).
  const re = new RegExp(
    `^[ \\t]*(?:(?:public|protected|private)[ \\t]+)?${className.replace(/\$/g, "\\$")}[ \\t]*\\(([^)\\n]*)\\)`,
    "gm",
  )
  const out: string[] = []
  let m: RegExpExecArray | null = re.exec(classSource)
  while (m !== null) {
    out.push(m[1] ?? "")
    m = re.exec(classSource)
  }
  return out
}

const PRIMITIVOS = new Set(["boolean", "byte", "char", "short", "int", "long", "float", "double"])

function esArray(field: FieldDecl): boolean {
  return field.type.endsWith("[]")
}

/** Constructor con TODOS los campos, en el orden en que estan declarados. */
export function constructorSource(className: string, fields: readonly FieldDecl[]): string {
  const params = fields.map((f) => `${f.type} ${f.name}`).join(", ")
  const cuerpo = fields.map((f) => `    this.${f.name} = ${f.name};`)
  return [`public ${className}(${params}) {`, ...cuerpo, "}"].join("\n")
}

/** Constructor sin argumentos. Java lo deja de dar gratis apenas escribis otro. */
export function emptyConstructorSource(className: string): string {
  return [`public ${className}() {`, "}"].join("\n")
}

/**
 * `toString` con todos los campos. Concatenacion con `+` a proposito: es lo que
 * se ensena en la cursada, y `String.format` agregaria una sintaxis nueva.
 *
 * Los arrays van por `Arrays.toString`: concatenar un array con `+` imprime su
 * referencia (`[D@1b6d3586`), que es exactamente el tipo de "anda pero esta
 * mal" que un snippet no puede regalar.
 */
export function toStringSource(className: string, fields: readonly FieldDecl[]): string {
  if (fields.length === 0) {
    return ["@Override", "public String toString() {", `    return "${className}{}";`, "}"].join(
      "\n",
    )
  }
  const partes = fields.map((f, i) => {
    const valor = esArray(f) ? `Arrays.toString(${f.name})` : f.name
    return `"${i === 0 ? "" : ", "}${f.name}=" + ${valor}`
  })
  return [
    "@Override",
    "public String toString() {",
    `    return "${className}{" + ${partes.join(" + ")} + "}";`,
    "}",
  ].join("\n")
}

/** Comparacion de UN campo dentro de `equals`, segun su tipo. */
function equalsCampo(field: FieldDecl): string {
  if (esArray(field)) return `Arrays.equals(this.${field.name}, otro.${field.name})`
  if (field.type === "float") return `Float.compare(this.${field.name}, otro.${field.name}) == 0`
  if (field.type === "double") return `Double.compare(this.${field.name}, otro.${field.name}) == 0`
  if (PRIMITIVOS.has(field.type)) return `this.${field.name} == otro.${field.name}`
  return `Objects.equals(this.${field.name}, otro.${field.name})`
}

/**
 * `equals` canonico: identidad, null + clase, cast, campo por campo.
 *
 * `float`/`double` van por `compare` y no por `==` porque `NaN != NaN` y
 * `0.0 == -0.0`, que rompen el contrato de `equals`. Los arrays van por
 * `Arrays.equals` porque el `==` de un array compara referencias.
 */
export function equalsSource(className: string, fields: readonly FieldDecl[]): string {
  // Sin campos no hay comparacion que hacer: dos instancias de una clase sin
  // estado son iguales si son de la misma clase, y con eso alcanzan las dos
  // guardas de arriba. El caso NO llega desde el proveedor (que saltea las
  // clases sin campos), pero esta funcion es exportada y `toStringSource` si
  // maneja su caso vacio — dejar el hueco solo acá seria una trampa: el `join`
  // de una lista vacia produce `return ;`, que no compila.
  if (fields.length === 0) {
    return [
      "@Override",
      "public boolean equals(Object o) {",
      "    if (this == o) return true;",
      "    return o != null && getClass() == o.getClass();",
      "}",
    ].join("\n")
  }
  return [
    "@Override",
    "public boolean equals(Object o) {",
    "    if (this == o) return true;",
    "    if (o == null || getClass() != o.getClass()) return false;",
    `    ${className} otro = (${className}) o;`,
    `    return ${fields.map(equalsCampo).join(" && ")};`,
    "}",
  ].join("\n")
}

/** `hashCode` consistente con el `equals` de arriba (mismos campos, mismo trato). */
export function hashCodeSource(fields: readonly FieldDecl[]): string {
  const args = fields.map((f) => (esArray(f) ? `Arrays.hashCode(${f.name})` : f.name))
  return [
    "@Override",
    "public int hashCode() {",
    `    return Objects.hash(${args.join(", ")});`,
    "}",
  ].join("\n")
}

/** Imports que `equals`/`hashCode` necesitan segun los campos involucrados. */
export function importsParaIgualdad(fields: readonly FieldDecl[]): string[] {
  const imports = [OBJECTS_IMPORT]
  if (fields.some(esArray)) imports.push(ARRAYS_IMPORT)
  return imports
}

/** Import que `toString` necesita: solo si hay algun campo array. */
export function importsParaToString(fields: readonly FieldDecl[]): string[] {
  return fields.some(esArray) ? [ARRAYS_IMPORT] : []
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

      /** Edit que agrega los imports faltantes arriba del archivo.
       *
       * Un SOLO edit con todos: dos edits en el mismo rango se pisan entre si
       * al aplicarse (`equals` con un campo array necesita `Objects` y
       * `Arrays` a la vez). */
      const importEdits = (
        ...requeridos: (string | undefined)[]
      ): Monaco.editor.ISingleEditOperation[] | undefined => {
        const faltantes = requeridos.filter(
          (imp): imp is string => Boolean(imp) && !source.includes(imp as string),
        )
        if (faltantes.length === 0) return undefined
        const line = importInsertLine(lines)
        return [
          {
            range: {
              startLineNumber: line,
              endLineNumber: line,
              startColumn: 1,
              endColumn: 1,
            },
            text: `${faltantes.join("\n")}\n`,
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

      // ── JAVA-2: constructores y overrides, por clase declarada ────────────
      // Se resuelven POR BLOQUE de clase (a diferencia de los accesores, que
      // miran el archivo entero): un constructor de `Main` con los campos de
      // `Persona` no seria ceremonia, seria basura.
      for (const bloque of parseClassBlocks(source)) {
        const camposClase = parseFields(bloque.source)
        // Sin campos no hay ceremonia que ahorrar: un `ctorvacio` o un
        // `toString` de la clase `Main` (que nunca tiene estado) es ruido en la
        // lista de sugerencias, no ayuda.
        if (camposClase.length === 0) continue
        const ctorParams = declaredConstructorParams(bloque.source, bloque.name)
        const tieneCtorVacio = ctorParams.some((p) => p.trim() === "")
        const tieneCtorConArgs = ctorParams.some((p) => p.trim() !== "")

        if (!tieneCtorConArgs) {
          suggestions.push({
            label: "ctor",
            kind: monaco.languages.CompletionItemKind.Snippet,
            detail: `Constructor completo de ${bloque.name} (${camposClase.length} campos)`,
            documentation: `Recibe todos los campos de ${bloque.name} y los asigna.`,
            insertText: constructorSource(bloque.name, camposClase),
            insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
            range,
            command: acceptCommand,
          })
        }

        if (!tieneCtorVacio) {
          suggestions.push({
            label: "ctorvacio",
            kind: monaco.languages.CompletionItemKind.Snippet,
            detail: `Constructor sin argumentos de ${bloque.name}`,
            // Java deja de dar el constructor por omision apenas escribis otro:
            // el vacio hay que volver a declararlo a mano, y eso sorprende.
            documentation: `Constructor vacio de ${bloque.name}.`,
            insertText: emptyConstructorSource(bloque.name),
            insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
            range,
            command: acceptCommand,
          })
        }

        if (!hasMethod(bloque.source, "toString")) {
          const extra = importEdits(...importsParaToString(camposClase))
          suggestions.push({
            label: "tostring",
            kind: monaco.languages.CompletionItemKind.Snippet,
            detail: `toString() de ${bloque.name}`,
            documentation: `Representacion en texto de ${bloque.name} con todos sus campos.`,
            insertText: toStringSource(bloque.name, camposClase),
            insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
            range,
            command: acceptCommand,
            ...(extra ? { additionalTextEdits: extra } : {}),
          })
        }

        const importsIgualdad = importsParaIgualdad(camposClase)
        if (!hasMethod(bloque.source, "equals")) {
          const extra = importEdits(...importsIgualdad)
          suggestions.push({
            label: "equals",
            kind: monaco.languages.CompletionItemKind.Snippet,
            detail: `equals(Object) de ${bloque.name}`,
            documentation: "Igualdad por valor, campo por campo. Agrega los imports si faltan.",
            insertText: equalsSource(bloque.name, camposClase),
            insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
            range,
            command: acceptCommand,
            ...(extra ? { additionalTextEdits: extra } : {}),
          })
        }
        if (!hasMethod(bloque.source, "hashCode")) {
          const extra = importEdits(...importsIgualdad)
          suggestions.push({
            label: "hashCode",
            kind: monaco.languages.CompletionItemKind.Snippet,
            detail: `hashCode() de ${bloque.name}`,
            documentation:
              "Hash consistente con equals (mismos campos). Agrega los imports si faltan.",
            insertText: hashCodeSource(camposClase),
            insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
            range,
            command: acceptCommand,
            ...(extra ? { additionalTextEdits: extra } : {}),
          })
        }
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
