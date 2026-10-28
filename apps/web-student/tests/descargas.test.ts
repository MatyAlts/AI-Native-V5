/**
 * Change `descargas-borrador-y-entregado` — logica pura de rotulos y visibilidad.
 */
import { describe, expect, it } from "vitest"
import { botonesDeDescarga, rotuloDescarga } from "../src/utils/descargas"

describe("rotuloDescarga", () => {
  it("borrador en python", () => {
    expect(rotuloDescarga("borrador", "python")).toBe("Descargar borrador (.py)")
  })
  it("entregado en java", () => {
    expect(rotuloDescarga("entregado", "java")).toBe("Descargar lo entregado (.java)")
  })
  it("language desconocido o nulo cae a .py", () => {
    expect(rotuloDescarga("entregado", null)).toBe("Descargar lo entregado (.py)")
    expect(rotuloDescarga("borrador", undefined)).toBe("Descargar borrador (.py)")
    expect(rotuloDescarga("borrador", "ruby")).toBe("Descargar borrador (.py)")
  })
})

const base = { legacy: false, submittedAt: "2026-10-01T10:00:00Z" as string | null }

describe("botonesDeDescarga (design D2)", () => {
  it("draft completado: solo borrador", () => {
    expect(
      botonesDeDescarga({ estado: "draft", ...base, submittedAt: null, completado: true }),
    ).toEqual({ borrador: true, entregado: false })
  })
  it("draft no completado: ninguno", () => {
    expect(
      botonesDeDescarga({ estado: "draft", ...base, submittedAt: null, completado: false }),
    ).toEqual({ borrador: false, entregado: false })
  })
  it("submitted y graded no legacy: solo entregado, completado o no", () => {
    for (const estado of ["submitted", "graded"] as const) {
      for (const completado of [true, false]) {
        expect(botonesDeDescarga({ estado, ...base, completado })).toEqual({
          borrador: false,
          entregado: true,
        })
      }
    }
  })
  it("returned sin re-completar: solo entregado", () => {
    expect(botonesDeDescarga({ estado: "returned", ...base, completado: false })).toEqual({
      borrador: false,
      entregado: true,
    })
  })
  it("returned re-completado: los dos", () => {
    expect(botonesDeDescarga({ estado: "returned", ...base, completado: true })).toEqual({
      borrador: true,
      entregado: true,
    })
  })
  it("legacy completado: solo borrador, en cualquier estado", () => {
    for (const estado of ["draft", "submitted", "graded", "returned"] as const) {
      expect(
        botonesDeDescarga({
          estado,
          legacy: true,
          submittedAt: base.submittedAt,
          completado: true,
        }),
      ).toEqual({
        borrador: true,
        entregado: false,
      })
    }
  })
  it("legacy no completado: ninguno", () => {
    expect(
      botonesDeDescarga({
        estado: "graded",
        legacy: true,
        submittedAt: base.submittedAt,
        completado: false,
      }),
    ).toEqual({ borrador: false, entregado: false })
  })
  it("returned con submittedAt nulo (dato inconsistente): sin entregado", () => {
    expect(
      botonesDeDescarga({ estado: "returned", legacy: false, submittedAt: null, completado: true }),
    ).toEqual({ borrador: true, entregado: false })
  })
})
