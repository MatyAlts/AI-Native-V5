/**
 * Aceptación HU-030 (orquestador, antes de construir; el constructor no la
 * modifica). Criterios acordados con Juani el 24/11/2026.
 *
 * C11  Paridad: cada algoritmo de `paridad/casos/` da, en nuestro intérprete,
 *      lo mismo que PSeInt oficial (`paridad/esperados.json`, generado con
 *      `paridad/generar_esperados.py` y PSeInt 20250314, perfil por defecto).
 *      - `ok`: la salida es idéntica, byte a byte.
 *      - `error_ejecucion`: misma salida previa y misma línea del error.
 *      - `error_sintaxis`: no se ejecuta nada (salida vacía) y misma línea.
 * C12  El perfil es el de PSeInt oficial por defecto: lo fijan estos mismos
 *      casos (arreglos desde 1, `=` no asigna, `y`/`o` reservadas, `Para`
 *      descendente implícito, `Escribir a, b` sin separador, etc.).
 */
import { readFileSync, readdirSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { ejecutarConEntrada } from "../src/index"

const DIR = join(__dirname, "paridad")
const CASOS = join(DIR, "casos")

interface Esperado {
  tipo: "ok" | "error_sintaxis" | "error_ejecucion"
  linea: number | null
  codigo_pseint: number | null
  salida: string
}

const esperados = JSON.parse(readFileSync(join(DIR, "esperados.json"), "utf-8")) as Record<string, Esperado>

function entradaDe(nombre: string): string {
  try {
    return readFileSync(join(CASOS, `${nombre}.entrada`), "utf-8")
  } catch {
    return ""
  }
}

const nombres = readdirSync(CASOS)
  .filter((f) => f.endsWith(".psc"))
  .map((f) => f.replace(/\.psc$/, ""))
  .sort()

describe("C11 paridad con PSeInt oficial", () => {
  it("el corpus está completo: cada caso tiene su esperado", () => {
    expect(nombres.length).toBeGreaterThanOrEqual(36)
    for (const n of nombres) expect(esperados[n], n).toBeDefined()
  })

  it("cubre los tres resultados posibles", () => {
    const tipos = new Set(Object.values(esperados).map((e) => e.tipo))
    expect(tipos).toEqual(new Set(["ok", "error_sintaxis", "error_ejecucion"]))
  })

  for (const nombre of nombres) {
    it(nombre, async () => {
      const esperado = esperados[nombre]!
      const fuente = readFileSync(join(CASOS, `${nombre}.psc`), "utf-8")
      const r = await ejecutarConEntrada(fuente, entradaDe(nombre))

      expect(r.estado, `estado de ${nombre}`).toBe(esperado.tipo)
      expect(r.salida, `salida de ${nombre}`).toBe(esperado.salida)
      if (esperado.tipo === "ok") {
        expect(r.error).toBeNull()
      } else {
        expect(r.error, `error de ${nombre}`).not.toBeNull()
        expect(r.error!.linea, `línea del error de ${nombre}`).toBe(esperado.linea)
        expect(r.error!.mensaje.trim().length).toBeGreaterThan(0)
      }
    })
  }
})
