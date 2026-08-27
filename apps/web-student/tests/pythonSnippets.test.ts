/**
 * ED-3 — snippets de ceremonia para Python.
 *
 * Los dos invariantes que este archivo protege NO son de UX:
 *
 *  1. **Trazabilidad**: toda sugerencia tiene que llevar su `command`. Sin él,
 *     `CodeEditor` nunca marca `snippetSinceLastFlushRef` y el código que
 *     INSERTA EL EDITOR entra a la cadena CTR con `origin="student_typed"` — la
 *     plataforma afirmando que el alumno escribió algo que le puso el editor.
 *     Es evidencia falsa en una tesis sobre trazabilidad, y de la peor clase:
 *     invisible, porque el evento se ve idéntico a uno legítimo.
 *
 *  2. **Alcance pedagógico**: ningún `insertText` puede resolver lógica. En
 *     Programación 1 escribir el `for` ES el objetivo de aprendizaje, y el
 *     integrador E3 del banco PID-UTN prohíbe explícitamente las colecciones.
 *
 * El id del comando de Python tiene que ser DISTINTO del de Java:
 * `registerCommand` sobre un id ya registrado deja los dos handlers
 * encadenados y dar de baja uno restauraría el otro.
 */

import { describe, expect, it, vi } from "vitest"
import { SNIPPET_ACCEPTED_COMMAND_ID as JAVA_COMMAND_ID } from "../src/lib/javaSnippets"
import {
  PYTHON_SNIPPETS,
  SNIPPET_ACCEPTED_COMMAND_ID,
  registerPythonSnippets,
} from "../src/lib/pythonSnippets"
import { crearMonacoFalso } from "./_monacoSnippetsFake"

/**
 * Saca la sintaxis de placeholders de Monaco (`${1:texto}`, `$0`) para poder
 * mirar el código Python que queda. Sin esto, `input("${1:Ingresa un valor: }")`
 * dispararía cualquier chequeo de llaves y el test se volvería ruido.
 */
function codigoPlano(insertText: string): string {
  return insertText
    .replace(/\$\{\d+:[^}]*\}/g, "X")
    .replace(/\$\{\d+\}/g, "X")
    .replace(/\$\d+/g, "")
}

/**
 * La guarda de módulo es ceremonia declarada: es literalmente la misma línea
 * siempre y no expresa ninguna decisión del alumno. Se la exceptúa del chequeo
 * de estructuras de control POR SU TEXTO EXACTO — un `if ${1:cond}:` genérico
 * no matchea y sigue estando prohibido.
 */
const GUARDA_DE_MODULO = 'if __name__ == "__main__":'

describe("PYTHON_SNIPPETS — alcance pedagogico", () => {
  it("no ofrece ninguna estructura de control", () => {
    // El `for`/`while`/`if` los escribe el alumno: son lo evaluado, no
    // ceremonia. Un snippet que los resuelve no ahorra andamiaje, resuelve el
    // ejercicio.
    const PROHIBIDAS = /\b(for|while|if|elif|else|def|class|lambda|return)\b/
    for (const spec of PYTHON_SNIPPETS) {
      const sinGuarda = codigoPlano(spec.insertText).split(GUARDA_DE_MODULO).join("")
      expect(sinGuarda, `snippet "${spec.label}" ofrece una estructura de control`).not.toMatch(
        PROHIBIDAS,
      )
    }
  })

  it("no ofrece colecciones (el integrador E3 del banco PID-UTN las prohibe)", () => {
    const COLECCIONES = /\b(list|dict|set|tuple|append|range|enumerate|zip|sorted|len)\b|\[\]|\{\}/
    for (const spec of PYTHON_SNIPPETS) {
      expect(
        codigoPlano(spec.insertText),
        `snippet "${spec.label}" ofrece una coleccion`,
      ).not.toMatch(COLECCIONES)
    }
  })

  it("la lista es corta y es la declarada: print, input y la guarda de modulo", () => {
    // No es un snapshot decorativo: fija el ALCANCE. Agregar un snippet nuevo
    // obliga a pasar por acá y justificar que es ceremonia y no logica.
    expect(PYTHON_SNIPPETS.map((s) => s.label)).toEqual(["print", "input", "main"])
  })

  it("la guarda de modulo se inserta con su cuerpo indentado", () => {
    // En Python la indentacion es sintaxis: una guarda sin cuerpo indentado
    // deja el archivo con un IndentationError apenas se acepta el snippet.
    const main = PYTHON_SNIPPETS.find((s) => s.label === "main")
    expect(main?.insertText).toBe('if __name__ == "__main__":\n    $0')
  })
})

describe("registerPythonSnippets — trazabilidad", () => {
  it("TODAS las sugerencias llevan el command de aceptacion", () => {
    const fake = crearMonacoFalso()
    registerPythonSnippets(fake.monaco, () => {})
    const sugerencias = fake.sugerencias("x = 1")

    expect(sugerencias.length).toBe(PYTHON_SNIPPETS.length)
    for (const s of sugerencias) {
      // Sin `command`, la expansion entra al CTR como `student_typed`.
      expect(s.command, `la sugerencia "${String(s.label)}" no lleva command`).toBeDefined()
      expect(s.command?.id).toBe(SNIPPET_ACCEPTED_COMMAND_ID)
    }
  })

  it("el command registrado invoca el onAccept que le pasa el CodeEditor", () => {
    // El handler es lo que setea `snippetSinceLastFlushRef`: si se registra un
    // comando que no llama a `onAccept`, el `command` de la sugerencia existe
    // pero no marca nada, y el origin sigue siendo `student_typed`.
    const fake = crearMonacoFalso()
    const onAccept = vi.fn()
    registerPythonSnippets(fake.monaco, onAccept)

    const comando = fake.comandos.find((c) => c.id === SNIPPET_ACCEPTED_COMMAND_ID)
    expect(comando).toBeDefined()
    comando?.handler()
    expect(onAccept).toHaveBeenCalledTimes(1)
  })

  it("se registra sobre el lenguaje python, no sobre otro", () => {
    const fake = crearMonacoFalso()
    registerPythonSnippets(fake.monaco, () => {})
    expect(fake.proveedores.map((p) => p.lenguaje)).toEqual(["python"])
  })

  it("el command id de Python es DISTINTO del de Java", () => {
    // `monaco.editor.registerCommand` sobre un id ya registrado encadena los
    // handlers: con un id compartido, dar de baja el proveedor de un lenguaje
    // restauraria el handler del otro. Dos ids, dos ciclos de vida.
    expect(SNIPPET_ACCEPTED_COMMAND_ID).not.toBe(JAVA_COMMAND_ID)
  })
})

describe("registerPythonSnippets — ciclo de vida", () => {
  it("dispose() da de baja el proveedor Y el comando", () => {
    // Dar de baja solo el proveedor deja el comando colgado: al re-montar el
    // editor se registra otro handler sobre el mismo id y una sola aceptacion
    // marca el flag N veces.
    const fake = crearMonacoFalso()
    const disposable = registerPythonSnippets(fake.monaco, () => {})

    expect(fake.proveedores.every((p) => p.disposed)).toBe(false)
    expect(fake.comandos.every((c) => c.disposed)).toBe(false)

    disposable.dispose()

    expect(
      fake.proveedores.every((p) => p.disposed),
      "el proveedor quedo vivo",
    ).toBe(true)
    expect(
      fake.comandos.every((c) => c.disposed),
      "el comando quedo vivo",
    ).toBe(true)
  })
})
