/**
 * Test de coverage anti-regresion del helpContent (D.1 / 2026-04-29).
 *
 * Garantiza que TODA key `helpContent.X` referenciada en `apps/web-teacher/src/views/`
 * exista en el modulo `apps/web-teacher/src/utils/helpContent.tsx`. Previene el
 * fallo silencioso en el que una view referencia una key inexistente y el
 * Modal del HelpButton renderea undefined (modal vacio, sin error visible).
 *
 * Si este test falla:
 *   - Agregaste una view nueva con `helpContent={helpContent.NUEVA}` pero
 *     no creaste la entrada `NUEVA: ( ... )` en helpContent.tsx, O
 *   - Renombraste una entrada de helpContent sin actualizar las views.
 */
import * as fs from "node:fs"
import * as path from "node:path"
import { describe, expect, test } from "vitest"
import { helpContent } from "../src/utils/helpContent"

const VIEWS_DIR = path.resolve(__dirname, "../src/views")

function listViewFiles(): string[] {
  return fs
    .readdirSync(VIEWS_DIR)
    .filter((f) => f.endsWith(".tsx"))
    .map((f) => path.join(VIEWS_DIR, f))
}

function extractHelpContentKeys(content: string): string[] {
  // Match `helpContent.someKey` — solo tokens validos (letras, digitos, _, $)
  const matches = content.matchAll(/helpContent\.([a-zA-Z_$][a-zA-Z0-9_$]*)/g)
  return Array.from(matches, (m) => m[1] as string)
}

describe("helpContent coverage", () => {
  test("todas las keys referenciadas en views existen en helpContent.tsx", () => {
    const referenced = new Set<string>()
    const filesByKey = new Map<string, string[]>()
    for (const file of listViewFiles()) {
      const content = fs.readFileSync(file, "utf-8")
      const keys = extractHelpContentKeys(content)
      for (const key of keys) {
        referenced.add(key)
        const list = filesByKey.get(key) ?? []
        list.push(path.basename(file))
        filesByKey.set(key, list)
      }
    }

    const available = new Set(Object.keys(helpContent))
    const missing: { key: string; referencedIn: string[] }[] = []
    for (const key of referenced) {
      if (!available.has(key)) {
        missing.push({ key, referencedIn: filesByKey.get(key) ?? [] })
      }
    }

    expect(missing).toEqual([])
  })

  test("helpContent.tsx exporta el shape esperado por consumers", () => {
    // Sanity: el modulo expone un objeto con keys string y values ReactNode.
    // No iteramos los values (son JSX renderable solo en runtime React);
    // verificamos que tiene al menos las 9 keys vigentes del piloto.
    const expected = [
      "export",
      "kappaRating",
      "materiales",
      "progression",
      "tareasPracticas",
      "templates",
      "episodeNLevel",
      "studentLongitudinal",
      "cohortAdversarial",
    ]
    for (const key of expected) {
      expect(Object.keys(helpContent)).toContain(key)
    }
  })
})
