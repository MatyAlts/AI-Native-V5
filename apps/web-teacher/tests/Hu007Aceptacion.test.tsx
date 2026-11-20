/**
 * Aceptacion HU-007 (orquestador, antes de construir; el constructor no la modifica).
 *
 * La UI no recalcula "pasiva por sobreuso": usa el booleano `pasiva_por_sobreuso`
 * que manda el backend. Una pasiva con subgrupo de sobreuso que confirmo un
 * docente o decidio el juez llega con `pasiva_por_sobreuso: false` y se muestra
 * como delegacion (N01, N02).
 */
import { screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"
import {
  USO_INTENSIVO_DOCENTE,
  apropiacionDocenteDePunto,
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

function clasificacion(pasivaPorSobreuso: boolean) {
  return {
    episode_id: EPISODE_ID,
    comision_id: "c1",
    classifier_config_hash: "hash",
    appropriation: "delegacion_pasiva",
    appropriation_reason: "x",
    ct_summary: null,
    ccd_mean: null,
    ccd_orphan_ratio: null,
    cii_stability: null,
    cii_evolution: null,
    is_current: true,
    subgrupo: subgrupoSobreuso,
    regimen_llm: null,
    pasiva_por_sobreuso: pasivaPorSobreuso,
  }
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

describe("HU-007 · veredicto del episodio usa el dato del backend", () => {
  test("C02: pasiva_por_sobreuso=true se muestra como Uso intensivo", async () => {
    localStorage.setItem("analytics-view-mode", "docente")
    setupFetchMock({
      "/n-level-distribution": () => distribucion,
      "/api/v1/classifications/": () => clasificacion(true),
    })
    renderWithRouter(<EpisodeNLevelView getToken={async () => "t"} initialEpisodeId={EPISODE_ID} />)
    await waitFor(() => {
      expect(screen.getByText("Uso intensivo del tutor")).toBeInTheDocument()
    })
  })

  test("N01/N02: confirmada (pasiva_por_sobreuso=false) se muestra como Delegacion pasiva", async () => {
    localStorage.setItem("analytics-view-mode", "docente")
    setupFetchMock({
      "/n-level-distribution": () => distribucion,
      "/api/v1/classifications/": () => clasificacion(false),
    })
    renderWithRouter(<EpisodeNLevelView getToken={async () => "t"} initialEpisodeId={EPISODE_ID} />)
    await waitFor(() => {
      expect(screen.getByText("Delegacion pasiva")).toBeInTheDocument()
    })
    expect(screen.queryByText("Uso intensivo del tutor")).not.toBeInTheDocument()
  })

  test("N01/N02: el resumen de una confirmada no habla de alerta de frecuencia", () => {
    const r = explicarEstadoDocente(clasificacion(false), 10, "dependiente_sobreuso")
    expect(r.resumen).not.toMatch(/alerta de frecuencia/i)
    const s = explicarEstadoDocente(clasificacion(true), 10, "dependiente_sobreuso")
    expect(s.resumen).toMatch(/alerta de frecuencia/i)
  })
})

describe("HU-007 · puntos de progresion y trayectoria", () => {
  test("C02: el label del punto sale del booleano del backend", () => {
    expect(apropiacionDocenteDePunto("delegacion_pasiva", true)).toBe(USO_INTENSIVO_DOCENTE)
    expect(apropiacionDocenteDePunto("delegacion_pasiva", false)).toMatch(/dependio de la IA/i)
    expect(apropiacionDocenteDePunto("delegacion_pasiva")).toMatch(/dependio de la IA/i)
  })
})
