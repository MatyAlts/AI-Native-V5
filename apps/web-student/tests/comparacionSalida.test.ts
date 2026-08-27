/**
 * JAVA-1 — comparacion de la salida del alumno, lado navegador.
 *
 * La tabla de casos NO vive aca: vive en `tests/fixtures/paridad-salida.json`,
 * en la raiz del monorepo, y la lee tambien
 * `apps/execution-service/tests/unit/test_comparacion_salida.py`. Es a
 * proposito: la paridad entre el corrector de Python (navegador, Pyodide) y el
 * de Java (servidor, contenedor efimero) es una PROPIEDAD DEL SISTEMA. Con dos
 * tablas copiadas, la primera correccion que toque una sola las separa y el
 * mismo codigo del alumno empieza a corregirse distinto segun el lenguaje.
 *
 * Lo que se testea acá y NO en la tabla compartida:
 *  - la semantica de `esperado` nulo, que es DISTINTA a proposito entre los dos
 *    lados (ver el docstring de `salidaCoincide`);
 *  - la forma normalizada concreta, que del lado Python se afirma igual.
 */

import { describe, expect, it } from "vitest"
// Import de JSON, no `readFileSync`: bajo Vitest (entorno jsdom) `import.meta.url`
// no es un `file://` y leerlo a mano tira "The URL must be of scheme file". El
// import lo resuelve Vite relativo a ESTE archivo, que es lo que queremos — si
// la tabla se mueve, el test no compila en vez de pasar sin comparar nada.
import tabla from "../../../tests/fixtures/paridad-salida.json"
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
