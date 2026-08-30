/**
 * El panel del admin ofrece los MISMOS providers que acepta el backend.
 *
 * Hay cuatro lugares que enumeran esto:
 *
 *   1. `ai-gateway/services/byok.py::PROVIDERS_VALIDOS`
 *   2. `ai-gateway/routes/byok.py` — el `Literal` del endpoint
 *   3. el check `ck_byok_provider` de `byok_keys`
 *   4. este panel — el tipo de `api.ts` y el `<select>` de `ByokPage`
 *
 * Los tres primeros los compara `test_providers_sincronizados.py` del lado
 * Python. Este archivo cierra el cuarto, que es el unico que el usuario ve.
 *
 * Por que importa: el 2026-08-28 se arreglo el constraint para que aceptara
 * `openrouter`, y el panel quedo con cuatro opciones. El fix funcionaba solo
 * por el camino del env fallback: un admin seguia sin poder cargar una key de
 * OpenRouter desde la UI, sin ningun error que lo explicara — la opcion
 * simplemente no estaba en la lista.
 *
 * Un desfasaje de este tipo no rompe nada visible, y por eso dura. El de
 * `openrouter` en el constraint estuvo CUATRO MESES.
 */
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const AQUI = dirname(fileURLToPath(import.meta.url))
const RAIZ = join(AQUI, "../../..")

const API_TS = join(AQUI, "../src/lib/api.ts")
const BYOK_PAGE = join(AQUI, "../src/pages/ByokPage.tsx")
const BYOK_PY = join(RAIZ, "apps/ai-gateway/src/ai_gateway/services/byok.py")

/** Los del backend, leidos de `PROVIDERS_VALIDOS`. Es la fuente de verdad. */
function providersDelBackend(): string[] {
  const texto = readFileSync(BYOK_PY, "utf-8")
  const m = texto.match(/PROVIDERS_VALIDOS\s*=\s*\(([^)]*)\)/)
  if (!m?.[1]) throw new Error(`no se encontro PROVIDERS_VALIDOS en ${BYOK_PY}`)
  return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1] as string).sort()
}

/** Los del tipo `ByokKeyCreate["provider"]`. */
function providersDelTipo(): string[] {
  const texto = readFileSync(API_TS, "utf-8")
  const m = texto.match(/provider:\s*((?:"[a-z]+"\s*\|\s*)*"[a-z]+")/)
  if (!m?.[1]) throw new Error(`no se encontro el tipo de provider en ${API_TS}`)
  return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1] as string).sort()
}

/** Los que el ADMIN ve en el desplegable de proveedores.
 *
 * La pagina tiene VARIOS `<select>` (scope, filtros), asi que no alcanza con
 * juntar todos los `<option>` del archivo: eso trae "tenant", "materia" y
 * "facultad" y el test compara peras con manzanas. Se acota al bloque del
 * `<select>` cuyo `onChange` escribe `provider`. */
function providersDelSelect(): string[] {
  const texto = readFileSync(BYOK_PAGE, "utf-8")
  const i = texto.indexOf("provider: e.target.value")
  if (i === -1) throw new Error(`no se encontro el <select> de provider en ${BYOK_PAGE}`)
  const cierre = texto.indexOf("</select>", i)
  if (cierre === -1) throw new Error("el <select> de provider no cierra")
  return [...texto.slice(i, cierre).matchAll(/<option value="([a-z]+)">/g)]
    .map((x) => x[1] as string)
    .sort()
}

describe("los providers de BYOK estan sincronizados", () => {
  it("el tipo del panel ofrece los mismos que acepta el backend", () => {
    expect(providersDelTipo()).toEqual(providersDelBackend())
  })

  it("el desplegable ofrece los mismos que el tipo", () => {
    // Si el tipo los tiene y el `<select>` no, el admin no puede elegirlo
    // aunque el backend lo acepte: la opcion no existe en la pantalla.
    expect(providersDelSelect()).toEqual(providersDelTipo())
  })

  it("openrouter esta en los tres — la regresion que origino este archivo", () => {
    expect(providersDelBackend()).toContain("openrouter")
    expect(providersDelTipo()).toContain("openrouter")
    expect(providersDelSelect()).toContain("openrouter")
  })

  it("las tres lecturas encuentran algo", () => {
    // Guarda anti-vacuidad: si un regex deja de matchear y devuelve [], los
    // tests de arriba compararian nada contra nada y pasarian contentos.
    expect(providersDelBackend().length).toBeGreaterThanOrEqual(4)
    expect(providersDelTipo().length).toBeGreaterThanOrEqual(4)
    expect(providersDelSelect().length).toBeGreaterThanOrEqual(4)
  })
})
