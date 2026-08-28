/**
 * JAVA-1 — comparacion de la salida del alumno, lado navegador.
 *
 * La tabla de casos NO vive aca: vive en `tests/fixtures/paridad-salida.json`,
 * en la raiz del monorepo, y la leen tambien
 * `apps/execution-service/tests/unit/test_comparacion_salida.py` y
 * `apps/web-teacher/tests/comparacionSalida.test.ts`. Es a proposito: la
 * paridad entre el corrector del alumno (navegador, Pyodide), el del servidor
 * (contenedor efimero) y el del docente ("Probar ejercicio") es una PROPIEDAD
 * DEL SISTEMA. Con tablas copiadas, la primera correccion que toque una sola
 * las separa y el mismo codigo del alumno empieza a corregirse distinto segun
 * quien lo corra.
 *
 * La implementacion se mudo a `@platform/contracts/comparacion-salida` cuando
 * aparecio el TERCER corrector; este archivo la importa por el re-export de
 * `src/lib/comparacionSalida` para seguir cubriendo el camino real del alumno.
 *
 * Lo que se testea acá y NO en la tabla compartida:
 *  - la semantica de `esperado` nulo, que es DISTINTA a proposito entre los dos
 *    lados (ver el docstring de `salidaCoincide`);
 *  - la forma normalizada concreta, que del lado Python se afirma igual;
 *  - el invariante que gobierna el modulo: la normalizacion NO puede hacer
 *    fallar ningun caso que el `str.strip()` viejo aceptaba.
 */

import { describe, expect, it } from "vitest"
// Import de JSON, no `readFileSync`: bajo Vitest (entorno jsdom) `import.meta.url`
// no es un `file://` y leerlo a mano tira "The URL must be of scheme file". El
// import lo resuelve Vite relativo a ESTE archivo, que es lo que queremos — si
// la tabla se mueve, el test no compila en vez de pasar sin comparar nada.
import tabla from "../../../tests/fixtures/paridad-salida.json"
import { CANTIDAD_BLANCOS_RECORTADOS } from "@platform/contracts/comparacion-salida"
import { normalizarSalida, salidaCoincide } from "../src/lib/comparacionSalida"

interface CasoParidad {
  nombre: string
  actual: string
  esperado: string
  coincide: boolean
  porque: string
}

const casos = tabla.casos as CasoParidad[]

describe("salidaCoincide — tabla compartida con el execution-service", () => {
  it("la tabla se leyo y tiene casos de los dos veredictos", () => {
    // Guarda contra el modo de falla mas tonto de un test parametrizado: la
    // tabla no se encontro / quedo vacia y el `it.each` no corre nada.
    expect(casos.length).toBeGreaterThan(20)
    expect(casos.some((c) => c.coincide)).toBe(true)
    expect(casos.some((c) => !c.coincide)).toBe(true)
  })

  it.each(casos)("$nombre -> $coincide ($porque)", ({ actual, esperado, coincide }) => {
    expect(salidaCoincide(actual, esperado)).toBe(coincide)
  })
})

describe("normalizarSalida — forma concreta", () => {
  // Estos tres son los que el lado Python afirma identicos: si una de las dos
  // implementaciones cambia la FORMA (y no solo el veredicto), se ve aca.
  it("unifica los fines de linea a \\n", () => {
    expect(normalizarSalida("a\r\nb\rc")).toBe("a\nb\nc")
  })

  it("recorta los blancos del final de CADA linea, no solo de la ultima", () => {
    expect(normalizarSalida("a  \nb\t\nc")).toBe("a\nb\nc")
  })

  it("descarta las lineas en blanco de los dos extremos y conserva las del medio", () => {
    expect(normalizarSalida("\n\na\n\nb\n\n")).toBe("a\n\nb")
  })

  it("una salida de solo blancos normaliza a la cadena vacia", () => {
    expect(normalizarSalida("  \n\t\n\r\n")).toBe("")
  })
})

describe("salidaCoincide — bordes con `esperado` nulo (semantica del NAVEGADOR)", () => {
  // Ojo: esta semantica NO se comparte con el servidor y no hay que unificarla.
  // Acá `null` significa "el caso no imprime nada" (era el `expected or ""` del
  // runner de Pyodide). En el execution-service el mismo `None` significa "no
  // hay nada que comparar, con terminar bien alcanza" (caso `junit_assert`), y
  // esa decision se toma ANTES de llamar a `outputs_match`.
  it("esperado null equivale a esperar la cadena vacia", () => {
    expect(salidaCoincide("", null)).toBe(true)
    expect(salidaCoincide("\n\n", null)).toBe(true)
    expect(salidaCoincide("Hola", null)).toBe(false)
  })

  it("esperado undefined se trata igual que null", () => {
    expect(salidaCoincide("", undefined)).toBe(true)
    expect(salidaCoincide("Hola", undefined)).toBe(false)
  })

  it("stdout vacio contra una salida esperada con contenido falla", () => {
    expect(salidaCoincide("", "Hola")).toBe(false)
  })
})

describe("normalizarSalida — invariante del strip() viejo", () => {
  // Los 28 blancos que recorta el corrector, mas el `\n`: exactamente el set de
  // `str.isspace()` de Python, que es lo que el `str.strip()` viejo recortaba.
  const BLANCOS_PYTHON = [
    0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x85, 0xa0, 0x1680, 0x2000, 0x2001,
    0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200a, 0x2028, 0x2029, 0x202f,
    0x205f, 0x3000,
  ]
  const esBlanco = (c: number) => BLANCOS_PYTHON.includes(c)

  /** El `str.strip()` de Python — el corrector ANTERIOR, en los dos runners. */
  function stripPython(s: string): string {
    let i = 0
    let f = s.length
    while (i < f && esBlanco(s.charCodeAt(i))) i++
    while (f > i && esBlanco(s.charCodeAt(f - 1))) f--
    return s.slice(i, f)
  }

  // El invariante: `normalizarSalida(a) === normalizarSalida(a.strip())`.
  //
  // No es cosmetico. Hay conteos `test_count_passed/failed` que YA viajaron al
  // CTR corregidos con `str.strip()`, y son la entrada del labeler N1–N4. Si la
  // normalizacion nueva hace fallar un caso que el strip() aceptaba, re-correr
  // el corpus cambia veredictos historicos: eso es reescribir evidencia de la
  // tesis, no arreglar un bug.
  const afirmarInvariante = (a: string) => {
    expect(normalizarSalida(a)).toBe(normalizarSalida(stripPython(a)))
  }

  it.each([
    ["texto pelado", "Hola"],
    ["blancos en los dos extremos", "   Hola   "],
    ["lineas en blanco en los dos extremos", "\n\n Hola \n\n"],
    ["sangria en una linea posterior", "Hola\n    Chau  "],
    ["linea en blanco intermedia", "  a\n\nb  "],
    ["solo blancos", " \t\n\u00a0 "],
    ["cadena vacia", ""],
    ["nbsp en los dos extremos", "\u00a0Hola\u00a0"],
    ["BOM al principio (NO es blanco de Python: el strip() viejo tampoco lo tocaba)", "\ufeffHola"],
    ["CRLF con blancos", "\r\n  Hola  \r\n"],
  ])("%s", (_n, a) => afirmarInvariante(a))

  it("se sostiene sobre 2000 cadenas generadas al azar", () => {
    // Deterministico a proposito (LCG con semilla fija): un test que falla una
    // vez cada cien corridas no se arregla, se silencia.
    // Lehmer / MINSTD: el producto maximo (2^31 * 48271) entra holgado en el
    // entero exacto de un double, asi que no hay perdida de precision.
    let semilla = 20260827
    const rnd = () => {
      semilla = (semilla * 48271) % 2147483647
      return semilla / 2147483647
    }
    const alfabeto = [
      ...BLANCOS_PYTHON.map((c) => String.fromCharCode(c)),
      "a",
      "b",
      "Z",
      "9",
      "\u200b",
      "\ufeff",
    ]
    for (let i = 0; i < 2000; i++) {
      const largo = Math.floor(rnd() * 12)
      let s = ""
      for (let j = 0; j < largo; j++) {
        s += alfabeto[Math.floor(rnd() * alfabeto.length)] ?? ""
      }
      afirmarInvariante(s)
    }
  })
})

describe("normalizarSalida — costo lineal (no O(n\u00b2))", () => {
  // El recorte del final se escribia `linea.replace(/[blancos]+$/, "")`, SIN
  // ancla izquierda: ante una corrida larga de blancos que no termina la linea,
  // el motor de regex reintenta desde cada indice. Medido en este repo:
  //
  //   `"x" + " "*50000 + "y"`  ->  1.996 ms
  //   `" "*200000 + "fin"`     -> 32.184 ms
  //
  // Y corre en el MAIN THREAD del navegador, despues de Pyodide, FUERA del
  // watchdog de 5 s, sobre `buf.getvalue()` sin tope: un `s += " "` en un bucle
  // —el error clasico del alumno— congelaba el tab medio minuto, multiplicado
  // por cada caso de prueba. `str.rstrip()` de Python siempre fue O(n).
  //
  // El presupuesto es enorme a proposito (250x el costo real medido, 0.1 ms):
  // no mide performance, detecta el retorno del backtracking. Con el regex sin
  // ancla estos casos ni siquiera llegan al assert — revientan el timeout de
  // vitest.
  const PRESUPUESTO_MS = 500

  const medir = (fn: () => void) => {
    const t0 = performance.now()
    fn()
    return performance.now() - t0
  }

  it.each([
    ["blancos en el MEDIO de la linea", `x${" ".repeat(50_000)}y`],
    ["blancos al PRINCIPIO de la linea", `${" ".repeat(200_000)}fin`],
    ["blancos en el medio, mas largo", `x${" ".repeat(200_000)}y`],
    ["blancos al final (el caso feliz)", `fin${" ".repeat(200_000)}`],
  ])("%s se normaliza sin backtracking", (_n, entrada) => {
    expect(medir(() => normalizarSalida(entrada))).toBeLessThan(PRESUPUESTO_MS)
  })

  it("el resultado no cambio: los blancos del medio siguen siendo contenido", () => {
    // La correccion es de costo, no de criterio. Un espacio en el medio de una
    // linea es contenido que el alumno decidio imprimir y sigue contando.
    expect(normalizarSalida("x  y  ")).toBe("x  y")
  })
})

describe("normalizarSalida — tamano del set de blancos", () => {
  it("recorta exactamente 28 code points: isspace() de Python menos el \\n", () => {
    // Numero afirmado y no derivado: recortar MENOS endurece la correccion
    // sobre conteos que ya viajaron al CTR, y recortar MAS agrega tolerancia
    // que el `str.strip()` viejo no tenia. Las dos direcciones son un cambio
    // de veredicto, no un refactor.
    expect(CANTIDAD_BLANCOS_RECORTADOS).toBe(28)
  })

  it("los 5 que separaban al corrector del docente estan adentro", () => {
    // U+001C-U+001F y U+0085: `isspace()` de Python SI, `\s` de JS NO.
    for (const ch of ["\u001c", "\u001d", "\u001e", "\u001f", "\u0085"]) {
      expect(normalizarSalida(`Hola${ch}`)).toBe("Hola")
    }
  })

  it("el que sobraba en el del docente queda afuera", () => {
    // U+FEFF: `\s` de JS SI (y `.trim()` tambien), `isspace()` de Python NO.
    expect(normalizarSalida("\ufeffHola")).toBe("\ufeffHola")
  })
})
