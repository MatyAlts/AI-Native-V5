/**
 * JAVA-1 — ATAQUE al corrector unificado de salida (`@platform/contracts/comparacion-salida`).
 *
 * Complementa `comparacionSalida.test.ts`, no lo reemplaza. Lo que se agrega es
 * lo que aquel deja abierto, y cada bloque nombra el mutante que lo justifica:
 *
 *  1. El invariante del `strip()` viejo se afirma EXHAUSTIVAMENTE (todas las
 *     cadenas de largo <= 4 sobre un alfabeto elegido) y en su forma FUERTE
 *     —la que de verdad importa al negocio—: dos salidas que el `str.strip()`
 *     viejo consideraba iguales tienen que seguir coincidiendo hoy. La version
 *     que shippeo el fix afirma la forma unaria sobre 2000 cadenas al azar.
 *
 *  2. El set de blancos se barre CODE POINT POR CODE POINT sobre todo el BMP.
 *     `CANTIDAD_BLANCOS_RECORTADOS === 28` no alcanza: cambiar un code point
 *     por otro deja el numero en 28 y el corrector queda roto en silencio.
 *
 *  3. El veredicto del alumno se maneja contra la tabla compartida por el
 *     camino REAL (`resolverVeredictosPython`), no solo por `salidaCoincide`.
 *     Es el equivalente de lo que el web-teacher hace con `evaluateCase`: el
 *     lado del alumno tenia esa prueba solo para la funcion suelta.
 *
 *  4. Formas que la tabla compartida no cubria: NFC/NFD, emoji con ZWJ,
 *     astrales, surrogates sueltos, U+2028/U+2029 (que NO son salto de linea
 *     acá aunque `splitlines()` de Python los partiria), BOM al final, ZWSP al
 *     principio, y la sangria de la primera linea DESPUES de lineas en blanco.
 *
 *  5. El costo lineal, con una entrada lo bastante grande como para que el
 *     regex sin ancla no termine nunca (el bloque que ya existia usa 200k y un
 *     presupuesto de 500 ms; medido en este repo el regex tarda 33 s ahi, pero
 *     su cuarto caso —"blancos al final"— cuesta 0,46 ms con el regex y NO
 *     detecta nada).
 */

import { describe, expect, it } from "vitest"
import { CANTIDAD_BLANCOS_RECORTADOS } from "@platform/contracts/comparacion-salida"
import { normalizarSalida, salidaCoincide } from "../src/lib/comparacionSalida"
import { type TestCaseResult, resolverVeredictosPython } from "../src/lib/veredictoTests"
import tabla from "../../../tests/fixtures/paridad-salida.json"

interface CasoParidad {
  nombre: string
  actual: string
  esperado: string
  coincide: boolean
  porque: string
}
const casos = tabla.casos as CasoParidad[]

/** `str.isspace()` de Python: los 28 que recorta el corrector, mas el `\n`.
 * Verificado contra CPython barriendo los 1.114.112 code points. */
const BLANCOS_PYTHON = [
  0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x85, 0xa0, 0x1680, 0x2000, 0x2001,
  0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200a, 0x2028, 0x2029, 0x202f,
  0x205f, 0x3000,
]
const BLANCOS = new Set(BLANCOS_PYTHON)

/** El `str.strip()` de Python: el corrector ANTERIOR, en los dos runners. */
function stripPython(s: string): string {
  let i = 0
  let f = s.length
  while (i < f && BLANCOS.has(s.charCodeAt(i))) i++
  while (f > i && BLANCOS.has(s.charCodeAt(f - 1))) f--
  return s.slice(i, f)
}

/** Todas las cadenas de largo <= `largo` sobre `alfabeto`. */
function todasLasCadenas(alfabeto: readonly string[], largo: number): string[] {
  const salida: string[] = []
  const rec = (s: string, d: number) => {
    salida.push(s)
    if (d === 0) return
    for (const c of alfabeto) rec(s + c, d - 1)
  }
  rec("", largo)
  return salida
}

describe("invariante del strip() viejo — EXHAUSTIVO, no muestreado", () => {
  // El alfabeto no es decorativo: lleva un representante de cada mecanismo que
  // la normalizacion toca (EOL crudo, EOL de Windows por partes, blanco comun,
  // blanco que solo Python considera blanco, blanco que solo JS considera
  // blanco) mas una letra para que existan lineas con contenido.
  const ALFABETO = ["a", " ", "\n", "\r", "\t", " ", "﻿", " "] as const
  const CADENAS = todasLasCadenas(ALFABETO, 4)

  it("el barrido no quedo vacio (guarda contra el test que no testea nada)", () => {
    // 8^0 + ... + 8^4 = 4681.
    expect(CADENAS.length).toBe(4681)
  })

  it("forma unaria: normalizarSalida(a) === normalizarSalida(strip(a)) para las 4681", () => {
    const rotos: string[] = []
    for (const a of CADENAS) {
      if (normalizarSalida(a) !== normalizarSalida(stripPython(a))) rotos.push(JSON.stringify(a))
    }
    expect(rotos.slice(0, 10)).toEqual([])
  })

  it("forma FUERTE: si el strip() viejo las aceptaba, salidaCoincide las acepta hoy", () => {
    // Este es el invariante de negocio, y no se deduce mirando una cadena sola:
    // `strip(a) === strip(b)` era el criterio ENTERO del corrector anterior, y
    // hay conteos test_count_passed/failed que ya viajaron al CTR con él. Si
    // hoy un par que pasaba falla, re-correr el corpus reescribe evidencia.
    const grupos = new Map<string, string[]>()
    for (const s of CADENAS) {
      const k = stripPython(s)
      const g = grupos.get(k)
      if (g) g.push(s)
      else grupos.set(k, [s])
    }
    expect(grupos.size).toBeGreaterThan(100)

    const rotos: string[] = []
    for (const g of grupos.values()) {
      const cabeza = g[0] ?? ""
      for (const s of g) {
        if (!salidaCoincide(cabeza, s)) rotos.push(`${JSON.stringify(cabeza)} vs ${JSON.stringify(s)}`)
      }
    }
    expect(rotos.slice(0, 10)).toEqual([])
  })

  it("y el invariante NO es trivial: hay pares que el strip() viejo separaba y siguen separados", () => {
    // Sin esto, un `salidaCoincide` que devuelva `true` siempre pasaria el
    // bloque de arriba entero.
    expect(salidaCoincide("a", "b")).toBe(false)
    expect(salidaCoincide("a\nb", "a\n\nb")).toBe(false)
    expect(salidaCoincide("﻿a", "a")).toBe(false)
  })
})

describe("set de blancos — barrido code point por code point del BMP", () => {
  // `CANTIDAD_BLANCOS_RECORTADOS === 28` fija el TAMAÑO del set, no su
  // CONTENIDO: cambiar U+1680 por U+FEFF lo deja en 28 y rompe la paridad con
  // `str.isspace()`. Esto fija el contenido.
  const BMP = 0x10000

  it("se recorta al FINAL exactamente el set de Python (28 blancos + el \\n)", () => {
    const deMas: string[] = []
    const deMenos: string[] = []
    for (let c = 0; c < BMP; c++) {
      // Los surrogates sueltos se saltean: no son un caracter, y `String`
      // los deja pasar tal cual (se cubren aparte, mas abajo).
      if (c >= 0xd800 && c <= 0xdfff) continue
      const recorta = normalizarSalida(`Hola${String.fromCharCode(c)}`) === "Hola"
      const deberia = BLANCOS.has(c)
      if (recorta && !deberia) deMas.push(`U+${c.toString(16).toUpperCase().padStart(4, "0")}`)
      if (!recorta && deberia) deMenos.push(`U+${c.toString(16).toUpperCase().padStart(4, "0")}`)
    }
    expect({ deMas, deMenos }).toEqual({ deMas: [], deMenos: [] })
  })

  it("se recorta al PRINCIPIO de la primera linea exactamente el mismo set", () => {
    const deMas: string[] = []
    const deMenos: string[] = []
    for (let c = 0; c < BMP; c++) {
      if (c >= 0xd800 && c <= 0xdfff) continue
      const recorta = normalizarSalida(`${String.fromCharCode(c)}Hola`) === "Hola"
      const deberia = BLANCOS.has(c)
      if (recorta && !deberia) deMas.push(`U+${c.toString(16).toUpperCase().padStart(4, "0")}`)
      if (!recorta && deberia) deMenos.push(`U+${c.toString(16).toUpperCase().padStart(4, "0")}`)
    }
    expect({ deMas, deMenos }).toEqual({ deMas: [], deMenos: [] })
  })

  it("NINGUN code point del BMP se recorta del MEDIO de una linea", () => {
    // "los espacios INTERNOS son contenido que el alumno decidio imprimir".
    // Un `map(recortarInicio)` sobre todas las lineas, o un `.trim()` que se
    // cuele, muere aca. Se excluyen \n y \r, que si son estructura.
    const rotos: string[] = []
    for (let c = 0; c < BMP; c++) {
      if (c === 0x0a || c === 0x0d) continue
      if (c >= 0xd800 && c <= 0xdfff) continue
      const ch = String.fromCharCode(c)
      if (normalizarSalida(`a${ch}b`) !== `a${ch}b`) {
        rotos.push(`U+${c.toString(16).toUpperCase().padStart(4, "0")}`)
      }
    }
    expect(rotos.slice(0, 10)).toEqual([])
  })

  it("la sangria de una linea POSTERIOR nunca se recorta, para ningun blanco", () => {
    // El perdon de blancos iniciales aplica SOLO a la primera linea (es lo
    // unico que el strip() viejo tocaba). Un `lineas.map(recortarInicio)`
    // pasaria el resto de la suite y moriria aca.
    const rotos: string[] = []
    for (const c of BLANCOS_PYTHON) {
      if (c === 0x0a || c === 0x0d) continue
      const ch = String.fromCharCode(c)
      if (normalizarSalida(`z\n${ch}Hola`) !== `z\n${ch}Hola`) {
        rotos.push(`U+${c.toString(16).toUpperCase().padStart(4, "0")}`)
      }
    }
    expect(rotos).toEqual([])
  })

  it("el tamaño publicado del set coincide con el barrido", () => {
    expect(CANTIDAD_BLANCOS_RECORTADOS).toBe(BLANCOS_PYTHON.length - 1)
  })
})

describe("el camino REAL del veredicto del alumno pasa por el corrector canonico", () => {
  // Espejo de lo que el web-teacher demuestra con `evaluateCase`. `resolverVeredictosPython`
  // es la funcion que pisa el `passed: False` placeholder del runner de Pyodide,
  // o sea la que decide el verde del alumno y de la que sale el conteo que
  // viaja al CTR. Testear `salidaCoincide` suelta no demuestra que ESTE camino
  // la use.
  const caso = (actual: string, expected: string): TestCaseResult => ({
    id: "tc-1",
    name: "caso",
    type: "stdin_stdout",
    passed: false,
    expected,
    actual,
    stdin: "",
    error: null,
  })

  it("la tabla compartida se leyo", () => {
    expect(casos.length).toBeGreaterThan(20)
  })

  it.each(casos)("$nombre -> $coincide", ({ actual, esperado, coincide }) => {
    const [r] = resolverVeredictosPython([caso(actual, esperado)])
    expect(r?.passed).toBe(coincide)
  })
})

describe("formas que la tabla compartida no cubria", () => {
  // Todas verificadas contra el gemelo Python (`normalize_output`) antes de
  // escribirlas: las que entran a la tabla compartida entran con el mismo
  // veredicto en los tres lados.
  it.each([
    // — equivalencia Unicode: NO se normaliza, y esta bien —
    ["NFC vs NFD no se unifican", "café", "café", false],
    // — clusters: nada de esto se recorta ni se parte —
    ["emoji con ZWJ vs sin ZWJ", "\u{1f469}‍\u{1f4bb}", "\u{1f469}\u{1f4bb}", false],
    ["un astral al final NO es blanco", "Hola\u{1f642}", "Hola", false],
    ["un astral se conserva entero", "\u{1f642}", "\u{1f642}", true],
    // — surrogates sueltos: el recorte es por code UNIT, que no puede confundirlos —
    ["surrogate alto suelto no se recorta", "Hola\ud800", "Hola", false],
    ["surrogate bajo suelto no se recorta", "Hola\udc00", "Hola", false],
    // — U+2028/U+2029 se RECORTAN (isspace) pero NO son salto de linea —
    ["U+2028 al final se recorta", "Hola ", "Hola", true],
    ["U+2028 en el medio NO parte la linea", "a b", "a\nb", false],
    ["U+2029 en el medio NO parte la linea", "a b", "a\nb", false],
    // — el BOM por el otro extremo (la tabla solo tenia BOM al principio) —
    ["BOM al FINAL tampoco se recorta", "Hola﻿", "Hola", false],
    ["ZWSP al PRINCIPIO tampoco se recorta", "​Hola", "Hola", false],
    // — blancos Unicode que faltaban como representantes —
    ["U+3000 (ideografico) al final", "Hola　", "Hola", true],
    ["U+202F (nbsp angosto) al final", "Hola ", "Hola", true],
    ["U+1680 (ogham) al final", "Hola ", "Hola", true],
    ["NBSP al PRINCIPIO de la primera linea", " Hola", "Hola", true],
    // — composicion: descartar lineas en blanco y DESPUES recortar la sangria —
    ["sangria de la primera linea DESPUES de lineas en blanco", "\n\n  Hola", "Hola", true],
    ["sangria con nbsp despues de una linea en blanco", "\n  Hola", "Hola", true],
    // — CR suelto en los bordes —
    ["CR suelto al final", "Hola\r", "Hola", true],
    ["CR CR son DOS saltos, no uno", "a\r\rb", "a\n\nb", true],
    ["CR CR no colapsa a un solo salto", "a\r\rb", "a\nb", false],
    // — una linea intermedia hecha de blancos ES una linea en blanco —
    ["linea intermedia de solo blancos == linea vacia", "a\n \t\nb", "a\n\nb", true],
    // — tabs contra espacios: contenido, no formato —
    ["un tab interno no equivale a un espacio", "a\tb", "a b", false],
    ["VT interno es contenido", "ab", "ab", false],
    ["U+001C interno es contenido", "ab", "ab", false],
    ["U+0085 interno es contenido", "ab", "ab", false],
  ] as [string, string, string, boolean][])("%s", (_n, a, e, esperado) => {
    expect(salidaCoincide(a, e)).toBe(esperado)
  })
})

describe("costo lineal — deteccion del backtracking, con margen que no miente", () => {
  // El bloque que ya existia usa 200k y 500 ms. Medido en este repo, el regex
  // sin ancla (`/[blancos]+$/`) sobre esas entradas tarda:
  //
  //   "x" + " "*50000  + "y"  -> 2.054 ms   (detecta)
  //   " "*200000 + "fin"      -> 34.757 ms  (detecta)
  //   "x" + " "*200000 + "y"  -> 33.060 ms  (detecta)
  //   "fin" + " "*200000      ->      0 ms  (NO detecta: la corrida TERMINA la
  //                                          linea, el regex acierta al primer
  //                                          intento — ese caso del it.each
  //                                          existente es decorativo)
  //
  // Los tamaños de acá estan elegidos para que el mutante muera RAPIDO: con
  // 50k blancos el regex tarda 2,1 s y con 150k unos 18 s, los dos muy por
  // encima del presupuesto, mientras que el recorte manual queda debajo de
  // 1 ms. Subirlo a 1.000.000 tambien detecta, pero tarda ~14 minutos en
  // fallar: un detector que cuelga el CI en vez de romperlo no sirve.
  const PRESUPUESTO_MS = 300

  const medir = (fn: () => void) => {
    const t0 = performance.now()
    fn()
    return performance.now() - t0
  }

  it.each([
    // Formas donde la corrida de blancos NO termina la linea: son las unicas
    // que hacen backtrackear al regex sin ancla. Una corrida que SI termina la
    // linea (`"fin" + " "*n`) cuesta 0,46 ms hasta con el regex y no detecta
    // nada — el cuarto caso del it.each que ya existia es de esa forma.
    ["50k blancos en el MEDIO de la linea", `x${" ".repeat(50_000)}y`],
    ["150k blancos en el MEDIO de la linea", `x${" ".repeat(150_000)}y`],
    ["150k blancos al PRINCIPIO de la linea", `${" ".repeat(150_000)}fin`],
    ["150k blancos en una linea INTERMEDIA", `a\nx${" ".repeat(150_000)}y\nb`],
  ])("%s", (_n, entrada) => {
    expect(medir(() => normalizarSalida(entrada))).toBeLessThan(PRESUPUESTO_MS)
  })

  it("y el resultado de esas entradas es el correcto, no solo rapido", () => {
    // Un `recortarFinal` que devuelva la linea sin tocar seria instantaneo y
    // pasaria los cuatro presupuestos de arriba.
    expect(normalizarSalida(`x${" ".repeat(1000)}y`)).toBe(`x${" ".repeat(1000)}y`)
    expect(normalizarSalida(`fin${" ".repeat(1000)}`)).toBe("fin")
    expect(normalizarSalida(`${" ".repeat(1000)}fin`)).toBe("fin")
    expect(normalizarSalida(`a\n${" ".repeat(1000)}\nb`)).toBe("a\n\nb")
  })
})
