/**
 * Change `sobreuso-no-es-delegacion` (P1 del plan CIbSE 2027), lado alumno.
 *
 * Cuando la pasiva vino SOLO de la regla de sobreuso, al alumno no se le dice
 * que el tutor hizo el trabajo: se le habla del ritmo de consultas. Lo decide
 * el backend con `pasiva_por_sobreuso` (HU-007); la UI no recalcula la regla.
 */
import { describe, expect, it } from "vitest"
import type { Classification } from "../src/lib/api"
import { buildPedagogicalFeedback } from "../src/pages/EpisodePage"
import { MODOS, modoDeEpisodio } from "../src/pages/MiProgresoPage"

const MENSAJE =
  "Consultaste al tutor muy seguido. Proba dar un paso propio entre consulta y consulta."

function clasificacion(
  appropriation: Classification["appropriation"],
  key: string | null,
  pasivaPorSobreuso?: boolean,
) {
  return {
    episode_id: "e",
    comision_id: "c",
    classifier_config_hash: "h",
    appropriation,
    appropriation_reason: "",
    ct_summary: null,
    ccd_mean: null,
    ccd_orphan_ratio: null,
    cii_stability: null,
    cii_evolution: null,
    is_current: true,
    subgrupo: key
      ? {
          key,
          label: "x",
          accion_docente: "x",
          eje: "delegacion_pasiva",
          dimensiones: { autonomia: 0.5, experimentacion: 0.5, persistencia: 0.5, foco: 0.5 },
        }
      : null,
    ...(pasivaPorSobreuso === undefined ? {} : { pasiva_por_sobreuso: pasivaPorSobreuso }),
  } as Classification
}

describe("feedback del episodio", () => {
  it("pasiva por sobreuso: mensaje de ritmo, sin atribuir el trabajo al tutor", () => {
    const fb = buildPedagogicalFeedback(
      clasificacion("delegacion_pasiva", "dependiente_sobreuso", true),
    )
    expect(fb.mensaje).toBe(MENSAJE)
    expect(fb.tono).toBe("neutro")
    expect(fb.mensaje).not.toMatch(/lo hizo el tutor/i)
  })

  it("delegacion real sigue con su mensaje", () => {
    const fb = buildPedagogicalFeedback(clasificacion("delegacion_pasiva", "dependiente_delegador"))
    expect(fb.mensaje).toMatch(/lo hizo el tutor/i)
  })

  it("backend viejo sin el booleano: el subgrupo de sobreuso se ve como delegacion", () => {
    const fb = buildPedagogicalFeedback(clasificacion("delegacion_pasiva", "dependiente_sobreuso"))
    expect(fb.mensaje).toMatch(/lo hizo el tutor/i)
  })

  it("si una revision cambio la etiqueta, manda el eje revisado", () => {
    const fb = buildPedagogicalFeedback(
      clasificacion("apropiacion_reflexiva", "dependiente_sobreuso", false),
    )
    expect(fb.mensaje).not.toBe(MENSAJE)
    expect(fb.tono).toBe("positivo")
  })
})

describe("chip de Mi progreso", () => {
  it("pasiva por sobreuso no se muestra como Delegacion", () => {
    const modo = modoDeEpisodio({
      appropriation: "delegacion_pasiva",
      pasiva_por_sobreuso: true,
    })
    expect(modo?.short).toBe("Muchas consultas")
    expect(modo?.color).toBe("var(--color-warning)")
  })

  it("delegacion real y backends viejos sin el booleano siguen como Delegacion", () => {
    expect(modoDeEpisodio({ appropriation: "delegacion_pasiva", pasiva_por_sobreuso: false })).toBe(
      MODOS[0],
    )
    expect(modoDeEpisodio({ appropriation: "delegacion_pasiva" })).toBe(MODOS[0])
  })
})
