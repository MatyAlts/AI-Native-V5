/**
 * Aceptacion HU-007, lado alumno (orquestador, antes de construir).
 *
 * El alumno ve "Muchas consultas" solo cuando el backend manda
 * `pasiva_por_sobreuso: true`. Una pasiva confirmada (por un docente o por el
 * juez) llega con `false` y se muestra como delegacion, aunque el subgrupo
 * siga siendo `dependiente_sobreuso` (N01, N02).
 */
import { describe, expect, it } from "vitest"
import type { Classification } from "../src/lib/api"
import { buildPedagogicalFeedback } from "../src/pages/EpisodePage"
import { MODOS, modoDeEpisodio } from "../src/pages/MiProgresoPage"

const MENSAJE =
  "Consultaste al tutor muy seguido. Proba dar un paso propio entre consulta y consulta."

function clasificacion(pasivaPorSobreuso: boolean) {
  return {
    episode_id: "e",
    comision_id: "c",
    classifier_config_hash: "h",
    appropriation: "delegacion_pasiva",
    appropriation_reason: "",
    ct_summary: null,
    ccd_mean: null,
    ccd_orphan_ratio: null,
    cii_stability: null,
    cii_evolution: null,
    is_current: true,
    subgrupo: {
      key: "dependiente_sobreuso",
      label: "x",
      accion_docente: "x",
      eje: "delegacion_pasiva",
      dimensiones: { autonomia: 0.5, experimentacion: 0.5, persistencia: 0.5, foco: 0.5 },
    },
    pasiva_por_sobreuso: pasivaPorSobreuso,
  } as unknown as Classification
}

describe("HU-007 · feedback del episodio", () => {
  it("C02: pasiva_por_sobreuso=true da el mensaje de ritmo", () => {
    expect(buildPedagogicalFeedback(clasificacion(true)).mensaje).toBe(MENSAJE)
  })

  it("N01/N02: confirmada da el mensaje de delegacion", () => {
    const fb = buildPedagogicalFeedback(clasificacion(false))
    expect(fb.mensaje).not.toBe(MENSAJE)
    expect(fb.mensaje).toMatch(/lo hizo el tutor/i)
  })
})

describe("HU-007 · chip de Mi progreso", () => {
  it("C02: pasiva_por_sobreuso=true da Muchas consultas", () => {
    const modo = modoDeEpisodio({
      appropriation: "delegacion_pasiva",
      subgrupo_key: "dependiente_sobreuso",
      pasiva_por_sobreuso: true,
    } as never)
    expect(modo?.short).toBe("Muchas consultas")
  })

  it("N01/N02: confirmada sigue como Delegacion aunque el subgrupo sea de sobreuso", () => {
    const modo = modoDeEpisodio({
      appropriation: "delegacion_pasiva",
      subgrupo_key: "dependiente_sobreuso",
      pasiva_por_sobreuso: false,
    } as never)
    expect(modo).toBe(MODOS[0])
  })
})
