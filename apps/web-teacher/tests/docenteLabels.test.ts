/**
 * B2b (6.5): `sin_clasificar` es un 5to valor real de `appropriation` desde
 * 6.2. `APPROPRIATION_DOCENTE`/`APPROPRIATION_INVESTIGADOR` no tenían
 * entrada para él — el fallback seguro (`dict[category] ?? category`) de
 * `appropriationWithScope` no rompe, pero muestra la clave cruda
 * ("sin_clasificar (este episodio)") en vez de una frase legible. "Sin
 * clasificar" no es un estado de error: es información sobre el episodio.
 */
import { describe, expect, test } from "vitest"
import {
  APPROPRIATION_DOCENTE,
  SUBGRUPO_DOCENTE,
  appropriationWithScope,
  explicarEstadoDocente,
} from "../src/utils/docenteLabels"

describe("appropriationWithScope — sin_clasificar", () => {
  test("audiencia docente: frase legible, no la clave cruda", () => {
    const label = appropriationWithScope("sin_clasificar", "docente")
    expect(label).not.toContain("sin_clasificar")
    expect(label.toLowerCase()).toContain("sin clasificar")
  })

  test("audiencia investigador: frase legible propia, distinta de la docente", () => {
    const label = appropriationWithScope("sin_clasificar", "investigador")
    expect(label).not.toContain("sin_clasificar")
    expect(label.toLowerCase()).toContain("sin clasificar")
  })

  test("triangulación: un valor conocido (apropiacion_reflexiva) sigue con su label de siempre", () => {
    expect(appropriationWithScope("apropiacion_reflexiva", "docente")).toBe(
      "En este episodio: trabajo de forma reflexiva (se apropio de la solucion) (este episodio)",
    )
  })
})

/**
 * Hallazgo #3: `desenganchado` = SI uso el tutor (prompts > 0) pero casi no
 * trabajo el codigo. El texto decia "ni dialogo con el tutor" (falso por
 * construccion) y faltaba `autonomo_desenganchado` (poco trabajo SIN tutor,
 * classifier-service/subgrupo.py).
 */

const metricas = {
  appropriation: "apropiacion_superficial",
  ct_summary: 0.8,
  ccd_mean: 0.8,
  ccd_orphan_ratio: 0,
  cii_stability: 0.8,
}

describe("hallazgo #8: reflexiva no se confunde con el eje autonomo", () => {
  const m = {
    appropriation: "apropiacion_reflexiva",
    ct_summary: 0.8,
    ccd_mean: 0.8,
    ccd_orphan_ratio: 0.1,
    cii_stability: 0.8,
  }

  test("label de apropiacion_reflexiva dice 'reflexiva' y no 'autonoma'", () => {
    expect(APPROPRIATION_DOCENTE.apropiacion_reflexiva.toLowerCase()).toContain("reflexiv")
    expect(APPROPRIATION_DOCENTE.apropiacion_reflexiva.toLowerCase()).not.toContain("autonom")
  })

  test("el eje autonomo conserva su texto 'sin usar el tutor' (distinto del reflexivo)", () => {
    expect(APPROPRIATION_DOCENTE.autonomo).toContain("sin usar el tutor")
    expect(APPROPRIATION_DOCENTE.autonomo).not.toBe(APPROPRIATION_DOCENTE.apropiacion_reflexiva)
  })

  test("el resumen del macro reflexivo no dice 'autonomo'", () => {
    const { resumen } = explicarEstadoDocente(m, 10)
    expect(resumen.toLowerCase()).toContain("reflexivo")
    expect(resumen.toLowerCase()).not.toContain("autonom")
  })
})

describe("subgrupos desenganchado / autonomo_desenganchado", () => {
  test("desenganchado (con tutor) no dice que no hubo dialogo con el tutor", () => {
    const { resumen } = explicarEstadoDocente(metricas, 10, "desenganchado")
    expect(resumen).not.toMatch(/ni dialogo con el tutor/i)
    expect(resumen.toLowerCase()).toContain("tutor")
    expect(resumen.toLowerCase()).toContain("codigo")
  })

  test("autonomo_desenganchado tiene resumen propio: poca actividad y sin tutor", () => {
    const { resumen } = explicarEstadoDocente(metricas, 10, "autonomo_desenganchado")
    expect(resumen).not.toBe(explicarEstadoDocente(metricas, 10, "desenganchado").resumen)
    expect(resumen.toLowerCase()).toMatch(/sin (usar|consultar|recurrir)/)
  })

  test("autonomo_desenganchado no sugiere 'dialogar mas con el tutor' (trabajar sin tutor es el perfil)", () => {
    const { acciones } = explicarEstadoDocente(
      { ...metricas, ccd_mean: 0.1 },
      10,
      "autonomo_desenganchado",
    )
    expect(acciones.join(" ")).not.toMatch(/dialogar/i)
    // contraste: con tutor la misma metrica si sugiere dialogar
    expect(
      explicarEstadoDocente({ ...metricas, ccd_mean: 0.1 }, 10, "desenganchado").acciones.join(" "),
    ).toMatch(/dialogar/i)
  })

  test("SUBGRUPO_DOCENTE tiene etiqueta legible para autonomo_desenganchado", () => {
    expect(SUBGRUPO_DOCENTE.autonomo_desenganchado).toBeTruthy()
    expect(SUBGRUPO_DOCENTE.autonomo_desenganchado).not.toBe(SUBGRUPO_DOCENTE.desenganchado)
  })
})
