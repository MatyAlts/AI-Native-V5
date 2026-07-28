/**
 * Analisis de errores de Java: compilacion y excepciones en ejecucion.
 *
 * Modulo HERMANO de `pyodideError.ts`, no una extension suya (D6 del design de
 * `java-execution-engine`). Ese usa expresiones regulares del traceback de
 * CPython (`File "<editor>", line N`, `NombreError:`) y Java no se parece a
 * ninguna de las dos. No hay nada que parametrizar cuando el formato entero es
 * otro.
 *
 * Java tiene DOS formatos distintos, y hay que reconocer los dos:
 *
 * 1. Error de compilacion (javac). Puede traer varios errores y un conteo:
 *
 *      Main.java:5: error: ';' expected
 *              System.out.println("hola")
 *                                        ^
 *      1 error
 *
 * 2. Excepcion en ejecucion, con la traza de llamadas:
 *
 *      Exception in thread "main" java.lang.ArithmeticException: / by zero
 *          at Main.main(Main.java:5)
 *
 * Al alumno le sirve la linea del error y el numero de linea, no la traza
 * entera ni el `at ...` de frames internos de la JVM.
 */

/** Formato del error, para que la UI pueda rotularlo distinto. */
export type JavaErrorKind = "compilation" | "runtime" | "unknown"

export interface JavaError {
  kind: JavaErrorKind
  /** Mensaje corto y accionable para mostrarle al alumno. */
  message: string
  /** Linea 1-based del codigo del alumno, o null si no se puede saber. */
  line: number | null
}

// `Main.java:5: error: ';' expected`
const COMPILE_RE = /^(?:[\w/.]*?)\.java:(\d+):\s*error:\s*(.+)$/
// `at Main.main(Main.java:5)` — solo frames del archivo del alumno.
const STACK_FRAME_RE = /\bat\s+[\w.$]+\((\w+)\.java:(\d+)\)/
// `Exception in thread "main" java.lang.ArithmeticException: / by zero`
const EXCEPTION_RE =
  /^(?:Exception in thread\s+"[^"]*"\s+)?((?:[\w.]+\.)?\w*(?:Exception|Error))(?::\s*(.*))?$/

/**
 * Nombres de excepcion que conviene traducir: son las que un alumno de primer
 * año se come seguido y cuyo nombre no le dice nada.
 */
const EXPLICACIONES: Record<string, string> = {
  ArithmeticException: "Error aritmetico (por ejemplo, division por cero)",
  ArrayIndexOutOfBoundsException: "Accediste a una posicion que no existe en el arreglo",
  StringIndexOutOfBoundsException: "Accediste a una posicion que no existe en el texto",
  NullPointerException: "Usaste una variable que todavia no apunta a ningun objeto",
  NumberFormatException: "Intentaste convertir a numero un texto que no lo es",
  InputMismatchException: "La entrada leida no tiene el tipo que el programa esperaba",
  NoSuchElementException: "El programa pidio mas entradas de las que hay disponibles",
  StackOverflowError: "Recursion sin caso base: el programa se llamo a si mismo sin parar",
}

function nombreCorto(fqn: string): string {
  const partes = fqn.split(".")
  return partes[partes.length - 1] ?? fqn
}

/**
 * Analiza la salida cruda de una corrida Java.
 *
 * @param compileOutput salida de javac (vacia si compilo bien)
 * @param stderr salida de error del programa (vacia si no reventó)
 */
export function parseJavaError(compileOutput: string, stderr: string): JavaError | null {
  const compilacion = parseCompilation(compileOutput)
  if (compilacion) return compilacion

  const runtime = parseRuntime(stderr)
  if (runtime) return runtime

  // Hay salida de error pero no matchea ningun formato conocido: se muestra
  // cruda antes que tragarsela. Un error sin explicacion es mejor que ninguno.
  const resto = (stderr || compileOutput).trim()
  if (!resto) return null
  return { kind: "unknown", message: resto.split("\n")[0] ?? resto, line: null }
}

function parseCompilation(compileOutput: string): JavaError | null {
  if (!compileOutput.trim()) return null

  for (const linea of compileOutput.split("\n")) {
    const match = COMPILE_RE.exec(linea.trim())
    if (match) {
      const numero = Number.parseInt(match[1] ?? "", 10)
      return {
        kind: "compilation",
        message: match[2]?.trim() ?? "Error de compilacion",
        line: Number.isFinite(numero) && numero > 0 ? numero : null,
      }
    }
  }

  return {
    kind: "compilation",
    message: compileOutput.trim().split("\n")[0] ?? "Error de compilacion",
    line: null,
  }
}

function parseRuntime(stderr: string): JavaError | null {
  if (!stderr.trim()) return null

  const lineas = stderr.split("\n").filter((l) => l.trim() !== "")

  let message: string | null = null
  for (const linea of lineas) {
    const match = EXCEPTION_RE.exec(linea.trim())
    if (match) {
      const corto = nombreCorto(match[1] ?? "")
      const detalle = match[2]?.trim()
      const explicacion = EXPLICACIONES[corto]
      message = explicacion
        ? `${explicacion}${detalle ? ` (${detalle})` : ""}`
        : `${corto}${detalle ? `: ${detalle}` : ""}`
      break
    }
  }

  if (message === null) return null

  return { kind: "runtime", message, line: extractJavaErrorLineNumber(stderr) }
}

/**
 * Numero de linea del codigo del alumno donde reventó.
 *
 * Se queda con el PRIMER frame de la traza, que es el mas cercano al fallo. Los
 * frames posteriores son quien lo llamo, y los de la JVM no interesan.
 *
 * Devuelve null cuando no hay frame reconocible: **no se inventa una linea**. Un
 * marcador en la linea equivocada es peor que ninguno — manda al alumno a
 * buscar el error donde no esta.
 */
export function extractJavaErrorLineNumber(raw: string): number | null {
  const match = STACK_FRAME_RE.exec(raw)
  if (!match) return null
  const numero = Number.parseInt(match[2] ?? "", 10)
  return Number.isFinite(numero) && numero > 0 ? numero : null
}
