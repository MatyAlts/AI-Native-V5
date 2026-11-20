import { describe, expect, test } from "vitest"
import type { RegimenLLM } from "../src/lib/api"
import { lecturaJuez } from "../src/utils/lecturaJuez"

function v(regimen: string | null, raw: unknown, estado = "ok"): RegimenLLM {
  return {
    estado,
    regimen,
    confianza: 0.8,
    raw,
    razon: "",
    model_used: "m",
    prompt_version: "p",
  } as RegimenLLM
}

const dim = (valor: string, cita = "") => ({ valor, localizador: cita ? "mensaje 1" : "", cita })

const mtac = (extra: Record<string, unknown> = {}) => ({
  d1_verbalizacion: dim("presente", "pienso"),
  d2_verificacion: dim("no_evaluable"),
  d3_justificacion: dim("ausente"),
  d4_autonomia: dim("oraculo", "decime"),
  regimen: "SUPERFICIAL",
  confianza: 0.8,
  justificacion_global: "g",
  ...extra,
})

describe("lecturaJuez", () => {
  test("v1: misma lectura que la vista armaba antes de HU-008", () => {
    const l = lecturaJuez(
      v("SUPERFICIAL", {
        verbalizacion: { presente: true, evidencia: "a" },
        verificacion: { presente: "no_evaluable", evidencia: "" },
        justificacion: { presente: false, evidencia: "" },
        autonomia: { presente: "ausente", evidencia: "b" },
        regimen: "SUPERFICIAL",
        confianza: 0.8,
        justificacion_global: "g",
      }),
    )
    expect(l?.label).toBe("Superficial")
    expect(l?.frontera).toBeNull()
    expect(l?.dims.map((d) => [d.estado, d.on, d.ev])).toEqual([
      ["presente", true, "a"],
      ["no evaluable", false, ""],
      ["ausente", false, ""],
      ["oraculo", false, "b"],
    ])
  })

  test("v2/v3: valores MTAC, cita y localizador", () => {
    const l = lecturaJuez(v("SUPERFICIAL", mtac()))
    expect(l?.dims.map((d) => [d.estado, d.on, d.ev, d.localizador])).toEqual([
      ["presente", true, "pienso", "mensaje 1"],
      ["no evaluable", false, "", ""],
      ["ausente", false, "", ""],
      ["oraculo", false, "decime", "mensaje 1"],
    ])
  })

  test("frontera: nombra los dos regimenes si vienen, si no marca generica", () => {
    expect(
      lecturaJuez(
        v("SUPERFICIAL", mtac({ es_frontera: true, frontera_entre: ["SUPERFICIAL", "PASIVA"] })),
      )?.frontera,
    ).toBe("Caso de frontera entre Superficial y Pasiva")
    expect(
      lecturaJuez(v("SUPERFICIAL", mtac({ es_frontera: true, frontera_entre: [] })))?.frontera,
    ).toBe("Caso de frontera")
    expect(lecturaJuez(v("SUPERFICIAL", mtac({ es_frontera: false })))?.frontera).toBeNull()
  })

  test("sin lectura: estado no ok, raw desconocido o regimen desconocido", () => {
    expect(lecturaJuez(v(null, null, "salida_invalida"))).toBeNull()
    expect(lecturaJuez(v("REFLEXIVA", { otra: 1 }))).toBeNull()
    expect(lecturaJuez(v("REFLEXIVA", "texto"))).toBeNull()
    expect(lecturaJuez(v("OTRO", mtac()))).toBeNull()
  })
})
