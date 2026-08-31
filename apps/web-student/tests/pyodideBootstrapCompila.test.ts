/**
 * El Python que `CodeEditor` le inyecta a Pyodide tiene que ser Python válido.
 *
 * POR QUÉ ESTE TEST EXISTE
 * ------------------------
 * El bootstrap del watchdog y el override de `input()` viven como STRINGS de
 * JavaScript dentro de `CodeEditor.tsx` — uno como template literal, el otro
 * armado con `+` y `\n` a mano. TypeScript no los mira, biome no los mira, y los
 * tests del editor corren contra `_pyodideFake.ts`, que nunca los ejecuta.
 *
 * O sea: hasta acá, un error de indentación en ese Python no lo detectaba NADA.
 * Se descubría en producción, con un alumno mirando cómo el editor no arranca.
 *
 * Este test extrae los dos bloques del archivo y los pasa por un parser. No
 * verifica qué hacen —para eso están los tests de comportamiento— sino que sean
 * parseables, que es la línea que hoy no cubre nadie.
 */
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

const FUENTE = readFileSync(join(__dirname, "../src/components/CodeEditor.tsx"), "utf-8")

/**
 * Chequeo de indentación estructural, que es la clase de error que un string
 * de Python armado a mano produce de verdad. No es un parser de Python
 * completo: verifica que todo bloque abierto con `:` tenga cuerpo indentado y
 * que la indentación cierre contra un nivel que exista.
 */
function erroresDeIndentacion(codigo: string): string[] {
  const errores: string[] = []
  const niveles: number[] = [0]
  let esperaCuerpo = false
  let sangriaDelQueAbrio = 0
  // Profundidad de parentesis/corchetes/llaves. Python une lineas
  // implicitamente mientras hay uno abierto, y ahi la indentacion es libre:
  // los argumentos de un `raise TimeoutError(...)` partido en tres renglones
  // no son un bloque. Sin esto el chequeo denuncia codigo perfectamente valido.
  let profundidad = 0

  const lineas = codigo.split("\n")
  for (let i = 0; i < lineas.length; i++) {
    const linea = lineas[i]
    const sinComillas = linea.replace(/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/g, '""')
    const delta =
      (sinComillas.match(/[([{]/g)?.length ?? 0) - (sinComillas.match(/[)\]}]/g)?.length ?? 0)
    if (profundidad > 0) {
      profundidad += delta
      continue
    }
    if (linea.trim() === "" || linea.trim().startsWith("#")) continue
    const sangria = linea.length - linea.trimStart().length

    if (esperaCuerpo) {
      if (sangria <= sangriaDelQueAbrio) {
        errores.push(`linea ${i + 1}: se esperaba un bloque indentado — ${linea.trim()}`)
      } else {
        niveles.push(sangria)
      }
      esperaCuerpo = false
    } else if (sangria > niveles[niveles.length - 1]) {
      errores.push(`linea ${i + 1}: indentacion inesperada — ${linea.trim()}`)
    } else {
      while (niveles.length > 1 && sangria < niveles[niveles.length - 1]) niveles.pop()
      if (sangria !== niveles[niveles.length - 1]) {
        errores.push(`linea ${i + 1}: la indentacion no cierra contra ningun nivel abierto`)
      }
    }

    if (/:\s*(#.*)?$/.test(sinComillas)) {
      esperaCuerpo = true
      sangriaDelQueAbrio = sangria
    }
    profundidad += delta
  }
  if (esperaCuerpo) errores.push("el archivo termina con un bloque abierto sin cuerpo")
  return errores
}

/** El bootstrap del watchdog: el template literal grande. */
function bloqueDelWatchdog(): string {
  const m = FUENTE.match(/runPythonAsync\(`\n(import sys as _tutor_wd_sys[\s\S]*?)`\)/)
  if (!m) throw new Error("no se encontro el bootstrap del watchdog en CodeEditor.tsx")
  return m[1]
}

/** El override de `input()`: el string armado con `+`. */
function bloqueDelInput(): string {
  const m = FUENTE.match(/"import builtins as __tutor_builtins\\n" \+\n([\s\S]*?)\n\s*\)/)
  if (!m) throw new Error("no se encontro el override de input() en CodeEditor.tsx")
  const trozos = m[1].match(/"((?:[^"\\]|\\.)*)"/g) ?? []
  return `import builtins as __tutor_builtins\n${trozos
    .map((t) => JSON.parse(t) as string)
    .join("")}`
}

/**
 * El chequeo se chequea a si mismo.
 *
 * `erroresDeIndentacion(...)` es una asercion sobre lo NEGATIVO: dice "no hay
 * errores". Esa forma se vacia sola — si la extraccion deja de encontrar el
 * bloque, o el heuristico deja de detectar nada, el test sigue verde diciendo
 * exactamente lo mismo que decia cuando servia.
 *
 * Es la leccion medida en este repo en agosto: de los tests que asertan lo
 * negativo, el CI solo avisa de los que ademas asertan lo positivo.
 */
describe("el chequeo detecta lo que dice detectar", () => {
  it("agarra un bloque sin cuerpo", () => {
    expect(erroresDeIndentacion("def f():\nreturn 1")).not.toEqual([])
  })

  it("agarra una indentacion que no cierra contra ningun nivel", () => {
    expect(erroresDeIndentacion("def f():\n    a = 1\n  b = 2")).not.toEqual([])
  })

  it("agarra una indentacion inesperada", () => {
    expect(erroresDeIndentacion("a = 1\n    b = 2")).not.toEqual([])
  })

  it("NO se queja de una llamada partida en varios renglones", () => {
    // El falso positivo que este heuristico tuvo primero: los argumentos de un
    // `raise X(...)` en tres renglones no son un bloque indentado.
    const codigo = ["def f():", "    raise ValueError(", '        "una",', '        "dos",', "    )"].join(
      "\n",
    )
    expect(erroresDeIndentacion(codigo)).toEqual([])
  })

  it("NO se queja de un dict o una lista multilinea", () => {
    expect(erroresDeIndentacion('d = {\n    "a": 1,\n    "b": 2,\n}')).toEqual([])
  })

  it("NO confunde un ':' adentro de un string con el que abre un bloque", () => {
    expect(erroresDeIndentacion('x = "esto termina en dos puntos:"\ny = 1')).toEqual([])
  })

  it("acepta Python valido con anidamiento", () => {
    const codigo = [
      "def f(x):",
      "    if x:",
      "        return 1",
      "    else:",
      "        return 2",
      "",
      "def g():",
      "    pass",
    ].join("\n")
    expect(erroresDeIndentacion(codigo)).toEqual([])
  })

  it("los dos bloques reales NO son vacios", () => {
    // Si la extraccion se rompe y devuelve "", `erroresDeIndentacion("")` da
    // [] y los dos tests de arriba pasan sin haber mirado nada.
    expect(bloqueDelWatchdog().length).toBeGreaterThan(500)
    expect(bloqueDelInput().length).toBeGreaterThan(100)
  })
})

describe("el Python inyectado a Pyodide", () => {
  it("el bootstrap del watchdog esta bien indentado", () => {
    expect(erroresDeIndentacion(bloqueDelWatchdog())).toEqual([])
  })

  it("el override de input() esta bien indentado", () => {
    // El más frágil de los dos: se arma concatenando strings con `\n` a mano,
    // así que un espacio de menos en un `"    if valor is None:\n"` produce un
    // IndentationError que no se ve leyendo el TSX.
    expect(erroresDeIndentacion(bloqueDelInput())).toEqual([])
  })

  it("declara la excepcion de cancelacion y la usa", () => {
    // Las dos mitades del fix de BUG-2 viven en archivos-dentro-de-strings
    // distintos: la clase en el template literal, el `raise` en el string
    // concatenado. Si alguien toca uno y no el otro, Pyodide tira NameError
    // recién cuando un alumno cancela un input — o sea, en producción.
    const watchdog = bloqueDelWatchdog()
    const input = bloqueDelInput()

    expect(watchdog).toContain("class _TutorCancelado(BaseException)")
    expect(input).toContain("raise _TutorCancelado()")
    expect(watchdog).toContain("except _TutorCancelado:")
  })

  it("_TutorCancelado hereda de BaseException, no de Exception", () => {
    // No es estilo. El patrón que enseña la cátedra envuelve el `input()` en un
    // `try/except` dentro de un `while True`. Con una excepción normal, el
    // `except` la traga, hace `continue`, y cancelar deja de cancelar — que es
    // exactamente el bug que esto viene a cerrar.
    expect(bloqueDelWatchdog()).toMatch(/class _TutorCancelado\(BaseException\)/)
  })

  it("input() devuelve el valor solo cuando NO es None", () => {
    // El `?? ""` de JS ya no está; el chequeo tiene que estar de este lado.
    // Sin él, `None` viajaría a Python como el objeto None y el programa del
    // alumno reventaría con un TypeError incomprensible en vez de detenerse.
    const input = bloqueDelInput()
    expect(input).toContain("if valor is None:")
    expect(input.indexOf("if valor is None:")).toBeLessThan(input.indexOf("return valor"))
  })

  it("el watchdog se sigue pausando durante el input", () => {
    // Regresión que este cambio podía introducir: el `try/finally` se reescribió
    // para poder inspeccionar el valor DESPUÉS de restaurar el deadline. Si el
    // `_tutor_reset_deadline()` se cayera del `finally`, un alumno que tarda en
    // tipear volvería a morir con un falso "bucle infinito".
    const input = bloqueDelInput()
    expect(input).toContain("_tutor_pause_deadline()")
    expect(input).toContain("finally:")
    expect(input).toContain("_tutor_reset_deadline()")
  })
})
