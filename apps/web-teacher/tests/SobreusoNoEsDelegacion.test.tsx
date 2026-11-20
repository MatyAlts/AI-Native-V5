/**
 * Change `sobreuso-no-es-delegacion` (P1 del plan CIbSE 2027).
 *
 * La pasiva que vino SOLO de la regla de sobreuso (`delegacion_pasiva` +
 * subgrupo `dependiente_sobreuso`) se muestra al docente como "Uso intensivo
 * del tutor", no como delegacion. La etiqueta persistida no cambia.
 */
import { screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"
import {
  USO_INTENSIVO_DOCENTE,
  apropiacionDocenteDePunto,
  esPasivaPorSobreuso,
  explicarEstadoDocente,
} from "../src/utils/docenteLabels"
import { EpisodeNLevelView } from "../src/views/EpisodeNLevelView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const EPISODE_ID = "11111111-2222-3333-4444-555555555555"

const subgrupoSobreuso = {
  key: "dependiente_sobreuso",
  label: "Dependiente (sobreuso)",
  accion_docente: "Intervenir - se apoya de mas en el tutor (overuse)",
  eje: "delegacion_pasiva",
  dimensiones: { autonomia: 0.5, experimentacion: 0.5, persistencia: 0.5, foco: 0.5 },
}

const clasificacionBase = {
  episode_id: EPISODE_ID,
  comision_id: "c1",
  classifier_config_hash: "hash",
  appropriation: "delegacion_pasiva",
  appropriation_reason: "Subgrupo dependiente_sobreuso",
  ct_summary: null,
  ccd_mean: null,
  ccd_orphan_ratio: null,
  cii_stability: null,
  cii_evolution: null,
  is_current: true,
  subgrupo: subgrupoSobreuso,
  regimen_llm: null,
}

const distribucion = {
  episode_id: EPISODE_ID,
  labeler_version: "1.3.0",
  distribution_seconds: { N1: 30, N2: 60, N3: 15, N4: 45, meta: 5 },
  distribution_ratio: { N1: 0.19, N2: 0.39, N3: 0.1, N4: 0.29, meta: 0.03 },
  total_events_per_level: { N1: 2, N2: 3, N3: 1, N4: 4, meta: 2 },
}

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.removeItem("analytics-view-mode")
})

describe("esPasivaPorSobreuso", () => {
  test.each([
    ["delegacion_pasiva", "dependiente_sobreuso", true],
    ["delegacion_pasiva", "dependiente_delegador", false],
    ["delegacion_pasiva", null, false],
    ["delegacion_pasiva", undefined, false],
    // Revision humana cambio la etiqueta: manda la revision.
    ["apropiacion_reflexiva", "dependiente_sobreuso", false],
  ])("(%s, %s) -> %s", (appropriation, subgrupo, esperado) => {
    expect(esPasivaPorSobreuso(appropriation, subgrupo)).toBe(esperado)
  })

  test("label de punto: sobreuso es alerta, delegacion real sigue igual", () => {
    expect(apropiacionDocenteDePunto("delegacion_pasiva", "dependiente_sobreuso")).toBe(
      USO_INTENSIVO_DOCENTE,
    )
    expect(apropiacionDocenteDePunto("delegacion_pasiva", "dependiente_delegador")).toMatch(
      /dependio de la IA/i,
    )
    expect(apropiacionDocenteDePunto("delegacion_pasiva")).toMatch(/dependio de la IA/i)
  })

  test("resumen: sobreuso habla de frecuencia; revisado manda el eje", () => {
    const c = { ...clasificacionBase }
    expect(explicarEstadoDocente(c, 10, "dependiente_sobreuso").resumen).toMatch(
      /alerta de frecuencia/i,
    )
    const revisada = { ...clasificacionBase, appropriation: "apropiacion_reflexiva" }
    expect(explicarEstadoDocente(revisada, 10, "dependiente_sobreuso").resumen).toMatch(
      /trabajo reflexivo/i,
    )
  })
})

describe("veredicto del episodio en vista docente", () => {
  test("pasiva por sobreuso se muestra como Uso intensivo del tutor", async () => {
    localStorage.setItem("analytics-view-mode", "docente")
    setupFetchMock({
      "/n-level-distribution": () => distribucion,
      "/api/v1/classifications/": () => clasificacionBase,
    })
    renderWithRouter(<EpisodeNLevelView getToken={async () => "t"} initialEpisodeId={EPISODE_ID} />)
    await waitFor(() => {
      expect(screen.getByText("Uso intensivo del tutor")).toBeInTheDocument()
    })
    expect(screen.queryByText(/Delegacion pasiva/i)).not.toBeInTheDocument()
    // El label y la accion persistidos del subgrupo tampoco se muestran.
    expect(screen.queryByText("Dependiente (sobreuso)")).not.toBeInTheDocument()
    expect(screen.queryByText(/Intervenir - se apoya/i)).not.toBeInTheDocument()
  })

  test("delegacion real sigue mostrandose como Delegacion pasiva", async () => {
    localStorage.setItem("analytics-view-mode", "docente")
    setupFetchMock({
      "/n-level-distribution": () => distribucion,
      "/api/v1/classifications/": () => ({
        ...clasificacionBase,
        subgrupo: {
          ...subgrupoSobreuso,
          key: "dependiente_delegador",
          label: "Dependiente / delegador",
        },
      }),
    })
    renderWithRouter(<EpisodeNLevelView getToken={async () => "t"} initialEpisodeId={EPISODE_ID} />)
    await waitFor(() => {
      expect(screen.getByText("Delegacion pasiva")).toBeInTheDocument()
    })
    expect(screen.queryByText("Uso intensivo del tutor")).not.toBeInTheDocument()
  })
})
