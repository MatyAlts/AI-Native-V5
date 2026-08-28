/**
 * JAVA-1 — ATAQUE al corrector del DOCENTE ("Probar ejercicio").
 *
 * `comparacionSalida.test.ts` prueba que `evaluateCase` da el mismo veredicto
 * que la tabla compartida en sus ~32 filas, mas 7 code points sueltos. Eso deja
 * un agujero concreto: una `normalize()` propia que acierte esas 39 entradas y
 * difiera en cualquier otra vuelve a pasar la suite entera. La `normalize()`
 * vieja fallaba SOLO 1 de los 29 casos de entonces — o sea que la tabla, por si
 * sola, ya casi la dejaba pasar.
 *
 * Acá se ataca la delegacion como propiedad, no como tabla: sobre un corpus
 * generado de miles de pares, `evaluateCase` tiene que dar EXACTAMENTE lo que
 * da `salidaCoincide`. Cualquier normalizacion propia que difiera en un solo
 * code point del BMP muere.
 */

import { describe, expect, it } from "vitest"
import { salidaCoincide } from "@platform/contracts/comparacion-salida"
import { type TestCaseLike, evaluateCase } from "../src/lib/pyodideRunner"

function casoDocente(esperado: string | null): TestCaseLike {
  return {
    id: "tc-1",
    name: "caso",
    type: "stdin_stdout",
    code: "",
    expected: esperado,
    is_public: true,
    weight: 1,
  }
}

const pasa = (actual: string, esperado: string | null) =>
  evaluateCase(casoDocente(esperado), { stdout: actual, error: null }).status === "pass"

describe("evaluateCase delega en salidaCoincide — barrido del BMP, no una tabla", () => {
  // El set de blancos es EXACTAMENTE donde el corrector del docente divergia
  // (24 code points contra 28, mas el BOM de mas). Un barrido completo lo fija
  // sin depender de que alguien se acuerde de agregar el code point del dia.
  const BMP = 0x10000

  it("recorte al FINAL: mismo veredicto que el corrector canonico para los 65.536", () => {
    const rotos: string[] = []
    for (let c = 0; c < BMP; c++) {
      if (c >= 0xd800 && c <= 0xdfff) continue
      const ch = String.fromCharCode(c)
      const canonico = salidaCoincide(`Hola${ch}`, "Hola")
      if (pasa(`Hola${ch}`, "Hola") !== canonico) {
        rotos.push(`U+${c.toString(16).toUpperCase().padStart(4, "0")} (canonico=${canonico})`)
      }
    }
    expect(rotos.slice(0, 10)).toEqual([])
  })

  it("recorte al PRINCIPIO: idem para los 65.536", () => {
    const rotos: string[] = []
    for (let c = 0; c < BMP; c++) {
      if (c >= 0xd800 && c <= 0xdfff) continue
      const ch = String.fromCharCode(c)
      const canonico = salidaCoincide(`${ch}Hola`, "Hola")
      if (pasa(`${ch}Hola`, "Hola") !== canonico) {
        rotos.push(`U+${c.toString(16).toUpperCase().padStart(4, "0")} (canonico=${canonico})`)
      }
    }
    expect(rotos.slice(0, 10)).toEqual([])
  })

  it("y el lado ESPERADO tambien: el docente pega el expected_output, no el stdout", () => {
    // El camino del incidente real va por acá: el BOM entra en el `expected`
    // que el docente pega, no en la salida del programa.
    const rotos: string[] = []
    for (let c = 0; c < BMP; c++) {
      if (c >= 0xd800 && c <= 0xdfff) continue
      const ch = String.fromCharCode(c)
      const canonico = salidaCoincide("Hola", `${ch}Hola${ch}`)
      if (pasa("Hola", `${ch}Hola${ch}`) !== canonico) {
        rotos.push(`U+${c.toString(16).toUpperCase().padStart(4, "0")} (canonico=${canonico})`)
      }
    }
    expect(rotos.slice(0, 10)).toEqual([])
  })
})

describe("evaluateCase delega en salidaCoincide — corpus generado de pares", () => {
  // LCG determinista (Lehmer / MINSTD). Un corpus al azar con semilla fija:
  // falla siempre o no falla nunca.
  function corpus(n: number): [string, string][] {
    let semilla = 20260828
    const rnd = () => {
      semilla = (semilla * 48271) % 2147483647
      return semilla / 2147483647
    }
    const alfabeto = [
      "a",
      "b",
      "Z",
      "9",
      " ",
      "\t",
      "\n",
      "\r",
      "\v",
      "\f",
      "",
      "",
      "",
      "",
      "",
      " ",
      " ",
      " ",
      "　",
      " ",
      " ",
      " ",
      "﻿",
      "​",
      "\u{1f642}",
      "é",
      "é",
    ]
    const cadena = () => {
      let s = ""
      const largo = Math.floor(rnd() * 10)
      for (let j = 0; j < largo; j++) s += alfabeto[Math.floor(rnd() * alfabeto.length)] ?? ""
      return s
    }
    return Array.from({ length: n }, () => [cadena(), cadena()] as [string, string])
  }

  const PARES = corpus(6000)

  it("el corpus tiene pares de los dos veredictos (guarda contra el corpus degenerado)", () => {
    const coinciden = PARES.filter(([a, e]) => salidaCoincide(a, e)).length
    expect(coinciden).toBeGreaterThan(50)
    expect(PARES.length - coinciden).toBeGreaterThan(50)
  })

  it("6000 pares: evaluateCase === salidaCoincide, sin excepcion", () => {
    const rotos: string[] = []
    for (const [a, e] of PARES) {
      const canonico = salidaCoincide(a, e)
      if (pasa(a, e) !== canonico) {
        rotos.push(`${JSON.stringify(a)} vs ${JSON.stringify(e)} (canonico=${canonico})`)
      }
    }
    expect(rotos.slice(0, 10)).toEqual([])
  })
})

describe("evaluateCase — el orden de las guardas, que la tabla no puede tocar", () => {
  // La comparacion es lo ULTIMO. Si alguien la adelanta, un caso que reventó
  // pero cuyo stdout truncado casualmente coincide con el esperado se pinta
  // verde, y eso mueve el conteo que alimenta la clasificacion N1-N4.
  it("un error de ejecucion gana aunque la salida coincida EXACTAMENTE", () => {
    const r = evaluateCase(casoDocente("Hola"), { stdout: "Hola", error: "RecursionError" })
    expect(r.status).toBe("error")
  })

  it("un error de ejecucion gana aunque la salida coincida tras normalizar", () => {
    const r = evaluateCase(casoDocente("Hola"), { stdout: "  Hola\r\n", error: "TimeoutError" })
    expect(r.status).toBe("error")
  })

  it("pytest_assert no compara salida ni siquiera cuando difiere del expected", () => {
    const tc: TestCaseLike = { ...casoDocente("Hola"), type: "pytest_assert" }
    expect(evaluateCase(tc, { stdout: "otra cosa", error: null }).status).toBe("pass")
  })

  it("el `got` que ve el docente es el stdout CRUDO, no el normalizado", () => {
    // Si se mostrara el normalizado, el docente veria "Hola" y no entenderia
    // por que un caso que le parece igual da rojo. El diagnostico depende de
    // ver los blancos que sobran.
    const r = evaluateCase(casoDocente("Hola"), { stdout: "Hola  ﻿", error: null })
    expect(r.got).toBe("Hola  ﻿")
    expect(r.status).toBe("fail")
  })
})
