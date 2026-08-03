import { describe, expect, it } from "vitest"
import { extractJavaErrorLineNumber, parseJavaError } from "../src/lib/javaError"

// Salidas reales de javac y de la JVM, no inventadas.
const COMPILE_ERROR = `Main.java:5: error: ';' expected
        System.out.println("hola")
                                  ^
1 error`

const RUNTIME_DIVISION = `Exception in thread "main" java.lang.ArithmeticException: / by zero
\tat Main.dividir(Main.java:9)
\tat Main.main(Main.java:4)`

const RUNTIME_INDICE = `Exception in thread "main" java.lang.ArrayIndexOutOfBoundsException: Index 5 out of bounds for length 3
\tat Main.main(Main.java:7)`

describe("parseJavaError — compilacion", () => {
  it("extrae el mensaje y la linea de un error de javac", () => {
    const err = parseJavaError(COMPILE_ERROR, "")
    expect(err?.kind).toBe("compilation")
    expect(err?.message).toBe("';' expected")
    expect(err?.line).toBe(5)
  })

  it("no devuelve el bloque entero ni el cursor de posicion", () => {
    // El `^` y el conteo "1 error" son ruido para el alumno.
    const err = parseJavaError(COMPILE_ERROR, "")
    expect(err?.message).not.toContain("^")
    expect(err?.message).not.toContain("1 error")
  })
})

describe("parseJavaError — ejecucion", () => {
  it("traduce una excepcion frecuente a lenguaje entendible", () => {
    const err = parseJavaError("", RUNTIME_DIVISION)
    expect(err?.kind).toBe("runtime")
    expect(err?.message).toContain("division por cero")
  })

  it("usa el PRIMER frame, que es donde reventó y no quien lo llamó", () => {
    // La traza tiene Main.java:9 (donde falla) y Main.java:4 (quien llama).
    const err = parseJavaError("", RUNTIME_DIVISION)
    expect(err?.line).toBe(9)
  })

  it("explica el indice fuera de rango sin perder el detalle", () => {
    const err = parseJavaError("", RUNTIME_INDICE)
    expect(err?.message).toContain("no existe en el arreglo")
    expect(err?.message).toContain("Index 5 out of bounds")
    expect(err?.line).toBe(7)
  })

  it("una excepcion sin traduccion conserva su nombre corto", () => {
    const err = parseJavaError(
      "",
      'Exception in thread "main" java.lang.IllegalStateException: roto',
    )
    expect(err?.message).toBe("IllegalStateException: roto")
  })
})

describe("parseJavaError — bordes", () => {
  it("sin errores devuelve null", () => {
    expect(parseJavaError("", "")).toBeNull()
  })

  it("una salida desconocida se muestra cruda antes que tragarsela", () => {
    const err = parseJavaError("", "algo raro paso aca")
    expect(err?.kind).toBe("unknown")
    expect(err?.message).toBe("algo raro paso aca")
  })

  it("la compilacion tiene prioridad sobre el runtime", () => {
    // Si no compiló, no llegó a ejecutarse: el error relevante es el primero.
    const err = parseJavaError(COMPILE_ERROR, RUNTIME_DIVISION)
    expect(err?.kind).toBe("compilation")
  })
})

describe("extractJavaErrorLineNumber", () => {
  it("NO inventa una linea cuando no hay frame reconocible", () => {
    // Un marcador en la linea equivocada manda al alumno a buscar el error
    // donde no esta. Peor que no marcar nada.
    expect(extractJavaErrorLineNumber('Exception in thread "main" java.lang.Error')).toBeNull()
    expect(extractJavaErrorLineNumber("")).toBeNull()
  })

  it("ignora los frames internos de la JVM y toma el del alumno", () => {
    const traza = `Exception in thread "main" java.lang.NullPointerException
\tat java.base/java.util.Objects.requireNonNull(Objects.java:233)
\tat Main.main(Main.java:12)`
    // El primer frame es interno de la JVM: `java.base/java.util.Objects...`.
    // Se descarta porque la notacion de modulo lleva una barra, que el patron
    // de la clase invocante no cruza. Al alumno no le sirve que le marquemos la
    // linea 233 de un archivo del JDK que no puede ver ni editar.
    expect(extractJavaErrorLineNumber(traza)).toBe(12)
  })
})
