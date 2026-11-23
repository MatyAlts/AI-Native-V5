/**
 * Apoyo de HU-016: los mensajes de apertura que no cubre la aceptacion
 * (`Hu016AvisoPlazo.test.ts`). Antes estas pistas las agregaba `OpeningStage`
 * buscando el codigo HTTP en el texto crudo.
 */
import { describe, expect, it } from "vitest"
import { ApiError } from "../src/lib/api"
import {
  MENSAJE_NO_EMPEZO,
  MENSAJE_NO_SE_PUDO_ABRIR,
  MENSAJE_NO_SE_PUDO_ENTREGAR,
  MENSAJE_PLAZO_VENCIDO,
  mensajeAlAbrirEpisodio,
  mensajeAlEntregar,
} from "../src/utils/mensajesPlazo"

const CRUDO = /failed|Error:|\b4\d\d\b|\b5\d\d\b/

describe("mensajeAlAbrirEpisodio", () => {
  it("el 403 de TP que no empezo no se confunde con permiso ni con plazo", () => {
    const e = new ApiError("open episode", 403, "Tarea práctica no ha comenzado todavía")
    expect(mensajeAlAbrirEpisodio(e)).toBe(MENSAJE_NO_EMPEZO)
  })

  it("el 403 por plazo es el aviso de plazo", () => {
    const e = new ApiError("open episode", 403, "Tarea práctica fuera de plazo (deadline pasado)")
    expect(mensajeAlAbrirEpisodio(e)).toBe(MENSAJE_PLAZO_VENCIDO)
  })

  it.each([
    [403, /permiso/],
    [404, /no se encontr/],
    [422, /anterior/],
    [429, /segundos/],
  ])("conserva la pista del %i sin mostrar el codigo", (status, pista) => {
    const msg = mensajeAlAbrirEpisodio(new ApiError("open episode", status, "x"))
    expect(msg).toMatch(/no se pudo abrir/i)
    expect(msg).toMatch(pista)
    expect(msg).not.toMatch(CRUDO)
  })

  it("un error que no es del servidor (red) da el generico", () => {
    expect(mensajeAlAbrirEpisodio(new TypeError("Failed to fetch"))).toBe(MENSAJE_NO_SE_PUDO_ABRIR)
  })
})

describe("mensajeAlEntregar", () => {
  it("sin detail legible o con 500 da el generico", () => {
    expect(mensajeAlEntregar(new ApiError("submit entrega", 422, null))).toBe(
      MENSAJE_NO_SE_PUDO_ENTREGAR,
    )
    expect(mensajeAlEntregar(new ApiError("submit entrega", 500, "Internal Server Error"))).toBe(
      MENSAJE_NO_SE_PUDO_ENTREGAR,
    )
    expect(mensajeAlEntregar(new TypeError("Failed to fetch"))).toBe(MENSAJE_NO_SE_PUDO_ENTREGAR)
  })
})
