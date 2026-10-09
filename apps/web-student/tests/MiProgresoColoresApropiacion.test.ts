/**
 * QA 08/10 #14: los tres modos de apropiacion usan los tokens canonicos
 * `--color-appropriation-*` (los mismos que el panel docente), no `level-n4`
 * (terracota, que es el nivel N4 y no una categoria de apropiacion).
 */
import { describe, expect, it } from "vitest"
import { MODOS } from "../src/pages/MiProgresoPage"

describe("MODOS de apropiacion", () => {
  it("delegacion usa el token de delegacion", () => {
    expect(MODOS[0]?.color).toBe("var(--color-appropriation-delegacion)")
  })
  it("superficial usa el token de superficial", () => {
    expect(MODOS[1]?.color).toBe("var(--color-appropriation-superficial)")
  })
  it("reflexiva usa el token de reflexiva (verde), no level-n4", () => {
    expect(MODOS[2]?.color).toBe("var(--color-appropriation-reflexiva)")
    for (const m of Object.values(MODOS)) expect(m.color).not.toContain("level-n4")
  })
})
