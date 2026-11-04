// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
/**
 * Centinela del retiro del entrenamiento del piloto (change cibse-codificacion-ciega,
 * tarea 11.9; spec codebook-versionado, "Sin contenido de codebook en el codigo", y
 * entrenamiento-calibracion, "Retiro del entrenamiento del piloto").
 *
 * El entrenamiento viejo ensenaba la regla que el paper evalua ("el sobreuso manda,
 * pasiva") con 7 episodios reales hardcodeados. Si cualquiera de esos textos o ids
 * vuelve al panel, la referencia humana del estudio queda contaminada otra vez. Este
 * test recorre TODO `src/` (no una lista de archivos) para que ningun lugar nuevo
 * se escape.
 */
import { readFileSync, readdirSync, statSync } from "node:fs"
import { dirname, join, relative } from "node:path"
import { fileURLToPath } from "node:url"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { helpContent } from "../src/utils/helpContent"

const SRC = join(dirname(fileURLToPath(import.meta.url)), "../src")

const TEXTOS_PROHIBIDOS = ["la trampa", "sobreuso manda", "si ves que sobreusa"]

const ANCLAS_DEL_PILOTO = [
  "02205295-67ab-45d5-a07e-22be5585cf2a",
  "a8150302-988b-4313-921d-49c672301b59",
  "2b083646-c873-4323-8bd9-cd674273fee8",
  "06ddbc14-d1f1-42cf-a128-201dce7d9c2c",
  "079dede6-32f9-4d73-aa85-91d1cb83f01c",
  "2df3242f-512a-4a17-a562-2bda4fc66fdb",
  "0a3d4388-c4e1-4333-b495-7e7e889d48dd",
]

function archivos(dir: string): string[] {
  return readdirSync(dir).flatMap((nombre) => {
    const ruta = join(dir, nombre)
    return statSync(ruta).isDirectory() ? archivos(ruta) : [ruta]
  })
}

function hallazgos(): string[] {
  const encontrados: string[] = []
  for (const ruta of archivos(SRC)) {
    const contenido = readFileSync(ruta, "utf-8").toLowerCase()
    for (const prohibido of [...TEXTOS_PROHIBIDOS, ...ANCLAS_DEL_PILOTO]) {
      if (contenido.includes(prohibido)) encontrados.push(`${relative(SRC, ruta)}: "${prohibido}"`)
    }
  }
  return encontrados
}

describe("sin entrenamiento del piloto en el panel", () => {
  it("ningun archivo de src/ contiene los textos ni los episode_id de las anclas del piloto", () => {
    expect(hallazgos()).toEqual([])
  })

  it("la ayuda de Codificacion no ensena reglas de clasificacion del piloto", () => {
    const html = renderToStaticMarkup(helpContent.interraterCoding as React.ReactElement)
      .toLowerCase()
    for (const regla of [
      "delegacion pasiva",
      "apropiacion superficial",
      "apropiacion reflexiva",
      "perfiles (3 ejes)",
      "sobreuso",
    ]) {
      expect(html, `la ayuda menciona "${regla}"`).not.toContain(regla)
    }
  })

  it("el recorrido de src/ de verdad mira archivos (no pasa por vacio)", () => {
    const todos = archivos(SRC)
    expect(todos.length).toBeGreaterThan(20)
    expect(todos.some((r) => r.endsWith("helpContent.tsx"))).toBe(true)
  })
})
