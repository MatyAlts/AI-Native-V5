/**
 * Aceptación HU-030 (orquestador, antes de construir; el constructor no la
 * modifica).
 *
 * C13  Los tres ejercicios de prueba (`scripts/data/pseint-prueba/*.json`)
 *      son resolubles: su solución de referencia pasa TODOS sus casos en el
 *      intérprete, con la misma comparación de salida que usa la plataforma.
 *      Y un algoritmo vacío no pasa ninguno (los casos discriminan).
 */
import { readFileSync, readdirSync } from "node:fs"
import { join } from "node:path"
import { salidaCoincide } from "@platform/contracts/comparacion-salida"
import { describe, expect, it } from "vitest"
import { ejecutarConEntrada } from "../src/index"

const DIR = join(__dirname, "..", "..", "..", "scripts", "data", "pseint-prueba")

interface Caso {
  name: string
  type: string
  code: string
  expected: string
  is_public: boolean
}

interface EjercicioPrueba {
  titulo: string
  tema: string
  language: string
  solucion_referencia: string
  test_cases: Caso[]
}

const archivos = (() => {
  try {
    return readdirSync(DIR).filter((f) => f.endsWith(".json"))
  } catch {
    return []
  }
})()

describe("C13 ejercicios de prueba de PSeInt", () => {
  it("son tres", () => {
    expect(archivos.length).toBe(3)
  })

  for (const archivo of archivos) {
    const ej = JSON.parse(readFileSync(join(DIR, archivo), "utf-8")) as EjercicioPrueba

    it(`${archivo}: la solución de referencia pasa todos los casos`, async () => {
      for (const c of ej.test_cases) {
        const r = await ejecutarConEntrada(ej.solucion_referencia, c.code)
        expect(r.estado, `${archivo} / ${c.name}`).toBe("ok")
        expect(salidaCoincide(r.salida, c.expected), `${archivo} / ${c.name}: ${JSON.stringify(r.salida)}`).toBe(true)
      }
    })

    it(`${archivo}: un algoritmo vacío no pasa ninguno`, async () => {
      const vacio = "Algoritmo vacio\nFinAlgoritmo\n"
      for (const c of ej.test_cases) {
        const r = await ejecutarConEntrada(vacio, c.code)
        expect(salidaCoincide(r.salida, c.expected), `${archivo} / ${c.name}`).toBe(false)
      }
    })
  }
})
