/**
 * Los textos de ayuda/tour/onboarding dejan de prometer una liberacion diferida
 * de las notas: el alumno ve la nota apenas el docente la guarda.
 */
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

const ARCHIVOS = [
  "src/tour/vistas.tsx",
  "src/utils/helpContent.tsx",
  "src/onboarding/docenteOnboarding.tsx",
]
const leer = (rel: string) =>
  readFileSync(resolve(__dirname, "..", rel), "utf-8").replace(/\s+/g, " ")

describe("textos de Correcciones", () => {
  for (const rel of ARCHIVOS) {
    it(`${rel} ya no promete 'liberarlas'`, () => {
      expect(leer(rel)).not.toMatch(/liberarlas|liberar las notas/i)
    })
  }

  it("el tour explica 'Publicar nota' y 'Pedir correccion'", () => {
    const t = leer("src/tour/vistas.tsx")
    expect(t).toContain("Publicar nota")
    expect(t).toContain("Pedir correccion")
  })

  it("la ayuda de la vista ya no dice 'Devolver al estudiante' y explica Pedir correccion", () => {
    const h = leer("src/utils/helpContent.tsx")
    expect(h).not.toContain("Devolver al estudiante")
    expect(h).toContain("Pedir correccion")
  })

  it("el onboarding dice que el alumno ve la nota al guardarla", () => {
    expect(leer("src/onboarding/docenteOnboarding.tsx")).toContain("Publicar nota")
  })
})
