/**
 * Regresion 2026-07-27: el wizard IA generaba el borrador OK y la vista
 * explotaba al renderizarlo con:
 *
 *   TypeError: u.puntaje_max.trim is not a function
 *
 * Causa: `CriterioRubrica.puntaje_max` esta tipado `string` (Decimal
 * serializado) y el editor de rubricas hace `.trim()`, pero el ejemplo que el
 * propio wizard le pasa al modelo muestra `"puntaje_max": 5` — un NUMERO. El
 * modelo obedecia el ejemplo.
 *
 * TypeScript no lo atrapaba: el borrador viaja como `dict[str, Any]` desde el
 * backend, asi que lo que el modelo escriba entra crudo a componentes tipados.
 * El backend acepta ambos (el contrato es `Decimal`), asi que la unica capa
 * rota era el frontend.
 */
import { afterEach, describe, expect, it, vi } from "vitest"

import { generateEjercicioWithAI } from "../src/lib/api"

const REQ = {
  descripcion_nl: "Ejercicio de listas para principiantes.",
  unidad_tematica: "Estructuras de datos",
}

function mockGenerateResponse(criterios: unknown[]) {
  return {
    borrador: {
      titulo: "Sistema de Control de Inventario",
      enunciado_md: "Una ferreteria necesita digitalizar el control.",
      rubrica: { criterios },
    },
    prompt_version: "v1.0.0",
    model_used: "google/gemini-2.5-flash-lite",
    provider_used: "google",
    tokens_input: 90,
    tokens_output: 4200,
    rag_chunks_used: 0,
    rag_chunks_hash: null,
  }
}

function stubFetch(payload: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => payload,
  })
  globalThis.fetch = fetchMock as unknown as typeof fetch
  return fetchMock
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe("generateEjercicioWithAI — normalizacion del borrador", () => {
  it("convierte puntaje_max numerico a string (el crash de produccion)", async () => {
    stubFetch(
      mockGenerateResponse([
        { nombre: "Correctitud", descripcion: "Resuelve el problema", puntaje_max: 5 },
        { nombre: "Estilo", descripcion: "Codigo legible", puntaje_max: 2.5 },
      ]),
    )

    const resp = await generateEjercicioWithAI(REQ)
    const criterios = (resp.borrador.rubrica as { criterios: { puntaje_max: unknown }[] }).criterios

    expect(criterios.map((c) => c.puntaje_max)).toEqual(["5", "2.5"])
    // Lo que realmente importa: que el editor pueda llamar .trim() sin explotar.
    for (const c of criterios) {
      expect(() => (c.puntaje_max as string).trim()).not.toThrow()
    }
  })

  it("deja intacto el puntaje_max que ya viene como string", async () => {
    stubFetch(
      mockGenerateResponse([
        { nombre: "Correctitud", descripcion: "Resuelve", puntaje_max: "5.00" },
      ]),
    )

    const resp = await generateEjercicioWithAI(REQ)
    const criterios = (resp.borrador.rubrica as { criterios: { puntaje_max: unknown }[] }).criterios

    expect(criterios[0]?.puntaje_max).toBe("5.00")
  })

  it("null/undefined caen a '' para no romper el input controlado", async () => {
    stubFetch(
      mockGenerateResponse([
        { nombre: "A", descripcion: "d", puntaje_max: null },
        { nombre: "B", descripcion: "d" },
      ]),
    )

    const resp = await generateEjercicioWithAI(REQ)
    const criterios = (resp.borrador.rubrica as { criterios: { puntaje_max: unknown }[] }).criterios

    expect(criterios.map((c) => c.puntaje_max)).toEqual(["", ""])
  })

  it("no rompe si el borrador viene sin rubrica", async () => {
    const payload = mockGenerateResponse([])
    // biome-ignore lint/performance/noDelete: se testea justamente la ausencia de la clave
    delete (payload.borrador as Record<string, unknown>).rubrica
    stubFetch(payload)

    const resp = await generateEjercicioWithAI(REQ)

    expect(resp.borrador.titulo).toBe("Sistema de Control de Inventario")
    expect(resp.borrador.rubrica).toBeUndefined()
  })

  it("preserva los campos de metadata de la generacion", async () => {
    stubFetch(mockGenerateResponse([{ nombre: "A", descripcion: "d", puntaje_max: 3 }]))

    const resp = await generateEjercicioWithAI(REQ)

    expect(resp.provider_used).toBe("google")
    expect(resp.tokens_output).toBe(4200)
    expect(resp.prompt_version).toBe("v1.0.0")
  })
})
