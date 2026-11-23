/**
 * Aceptacion HU-018, textos que ve el alumno (orquestador, antes de construir;
 * el constructor no la modifica). Juani (22/11): "vos terminas todo entonces".
 *
 * Hallazgos de HU-014:
 *  F09  El cierre contradice al juez: con veredicto REFLEXIVA el alumno leyo
 *       "Buen trabajo... probaste poco por tu cuenta" (mensaje del subgrupo).
 *  F14  La lista de TPs dice "Tu episodio: apropiacion reflexiva/superficial".
 *  F15  Mi progreso usa "Apropiacion reflexiva / superficial / Delegacion".
 *  F05  Un TP de 3 ejercicios iguales dice "Peso: 100%" en cada uno.
 *
 * Contrato nuevo: `src/utils/pesoEjercicio.ts` exporta
 * `porcentajesDePeso(pesos: number[]): number[]`, enteros que suman 100.
 *
 * C01  Con veredicto del juez (`regimen_llm.estado === "ok"`), el mensaje de
 *      cierre sigue a la etiqueta oficial, no al subgrupo.
 * N01  Sin veredicto del juez (o con abstencion), el subgrupo sigue mandando.
 * C02  Ninguna etiqueta de la lista de TPs ni de Mi progreso usa la jerga del
 *      modelo ("apropiacion", "delegacion").
 * C03  El peso de cada ejercicio es su parte del total.
 */
import { describe, expect, it } from "vitest"
import { appropriationLabel } from "../src/components/TareaSelector"
import type { Classification } from "../src/lib/api"
import { buildPedagogicalFeedback } from "../src/pages/EpisodePage"
import { MODOS } from "../src/pages/MiProgresoPage"
import { porcentajesDePeso } from "../src/utils/pesoEjercicio"

function clasif(over: Record<string, unknown>): Classification {
  return {
    episode_id: "e",
    comision_id: "c",
    classifier_config_hash: "h",
    appropriation: "apropiacion_superficial",
    appropriation_reason: "",
    ct_summary: null,
    ccd_mean: null,
    ccd_orphan_ratio: null,
    cii_stability: null,
    cii_evolution: null,
    is_current: true,
    subgrupo: null,
    pasiva_por_sobreuso: false,
    ...over,
  } as unknown as Classification
}

function sg(key: string, eje: string) {
  return {
    key,
    label: key,
    accion_docente: "x",
    eje,
    dimensiones: { autonomia: 0.5, experimentacion: 0.5, persistencia: 0.5, foco: 0.5 },
  }
}

const JERGA = /apropiaci[oó]n|delegaci[oó]n/i

describe("HU-018 · cierre y juez", () => {
  it("C01: juez REFLEXIVA no recibe el mensaje de 'probaste poco'", () => {
    const f = buildPedagogicalFeedback(
      clasif({
        appropriation: "apropiacion_reflexiva",
        subgrupo: sg("colaborador_funcional", "superficial"),
        regimen_llm: { estado: "ok" },
      }),
    )
    expect(f.tono).toBe("positivo")
    expect(f.mensaje).not.toMatch(/probaste poco/i)
  })

  it("C01: juez SUPERFICIAL sobre un subgrupo positivo no felicita de mas", () => {
    const f = buildPedagogicalFeedback(
      clasif({
        appropriation: "apropiacion_superficial",
        subgrupo: sg("colaborador_reflexivo", "reflexiva"),
        regimen_llm: { estado: "ok" },
      }),
    )
    expect(f.tono).not.toBe("positivo")
  })

  it("N01: sin juez, el subgrupo sigue mandando", () => {
    const f = buildPedagogicalFeedback(
      clasif({
        appropriation: "apropiacion_reflexiva",
        subgrupo: sg("colaborador_funcional", "superficial"),
      }),
    )
    expect(f.mensaje).toMatch(/probaste poco/i)
  })

  it("N01: con abstencion del juez, el subgrupo sigue mandando", () => {
    const f = buildPedagogicalFeedback(
      clasif({
        appropriation: "apropiacion_reflexiva",
        subgrupo: sg("colaborador_funcional", "superficial"),
        regimen_llm: { estado: "abstencion_traza_insuficiente" },
      }),
    )
    expect(f.mensaje).toMatch(/probaste poco/i)
  })
})

describe("HU-018 · sin jerga del modelo", () => {
  it("C02: la lista de TPs no dice apropiacion ni delegacion", () => {
    const valores = [
      "apropiacion_reflexiva",
      "apropiacion_superficial",
      "delegacion_pasiva",
      "autonomo",
      "sin_clasificar",
    ] as const
    for (const v of valores) {
      const label = appropriationLabel(v)
      expect(label.trim().length).toBeGreaterThan(0)
      expect(label).not.toMatch(JERGA)
    }
  })

  it("C02: Mi progreso no dice apropiacion ni delegacion", () => {
    for (const modo of Object.values(MODOS)) {
      expect(modo.label).not.toMatch(JERGA)
      expect(modo.short).not.toMatch(JERGA)
    }
  })
})

describe("HU-018 · peso de cada ejercicio", () => {
  const suma = (xs: number[]) => xs.reduce((a, b) => a + b, 0)

  it("C03: tres ejercicios iguales se reparten el 100", () => {
    const p = porcentajesDePeso([1, 1, 1])
    expect(p).toHaveLength(3)
    expect(suma(p)).toBe(100)
    for (const x of p) expect([33, 34]).toContain(x)
  })

  it("C03: pesos distintos respetan la proporcion", () => {
    expect(porcentajesDePeso([1, 3])).toEqual([25, 75])
    expect(porcentajesDePeso([0.5, 0.5])).toEqual([50, 50])
  })

  it("C03: un solo ejercicio vale 100 y sin pesos se reparte igual", () => {
    expect(porcentajesDePeso([1])).toEqual([100])
    expect(suma(porcentajesDePeso([0, 0]))).toBe(100)
  })
})
