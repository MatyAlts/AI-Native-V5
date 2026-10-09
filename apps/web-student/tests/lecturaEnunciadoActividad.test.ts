import { beforeEach, describe, expect, it } from "vitest"
import {
  ACTIVIDAD_QUIETA_MS,
  marcarActividad,
  msDeLecturaContables,
  resetActividad,
  ultimaActividadMs,
} from "../src/lib/lecturaEnunciadoActividad"

describe("msDeLecturaContables", () => {
  it("cuenta el tramo entero si nunca hubo actividad", () => {
    expect(msDeLecturaContables(1000, 100_000, null)).toBe(1000)
  })

  it("no cuenta nada si la ultima actividad cae dentro de la ventana", () => {
    const ahora = 100_000
    expect(msDeLecturaContables(1000, ahora, ahora - 1000)).toBe(0)
    expect(msDeLecturaContables(1000, ahora, ahora - (ACTIVIDAD_QUIETA_MS - 1))).toBe(0)
  })

  it("vuelve a contar una vez pasada la ventana de quietud", () => {
    const ahora = 100_000
    expect(msDeLecturaContables(1000, ahora, ahora - ACTIVIDAD_QUIETA_MS)).toBe(1000)
    expect(msDeLecturaContables(1000, ahora, ahora - 60_000)).toBe(1000)
  })

  it("no devuelve negativos", () => {
    expect(msDeLecturaContables(-5, 1000, null)).toBe(0)
  })
})

describe("marcarActividad / ultimaActividadMs", () => {
  beforeEach(() => resetActividad())

  it("parte sin actividad", () => {
    expect(ultimaActividadMs()).toBeNull()
  })

  it("recuerda el ultimo instante marcado", () => {
    marcarActividad(5000)
    expect(ultimaActividadMs()).toBe(5000)
    marcarActividad(9000)
    expect(ultimaActividadMs()).toBe(9000)
  })
})
