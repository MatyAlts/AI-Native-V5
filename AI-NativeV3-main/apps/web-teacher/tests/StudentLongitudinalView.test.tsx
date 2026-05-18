/**
 * Tests E2E de StudentLongitudinalView (ADR-018 + ADR-022).
 *
 * Cubre:
 * - drill-down con initialComisionId+initialStudentId: 2 fetches (evolution + alerts)
 * - Render de evolución per-template + sparkline
 * - Render de alertas cuando hay (vs cohorte)
 * - Render de "sin alertas" cuando el estudiante está OK
 */
import { screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"
import { StudentLongitudinalView } from "../src/views/StudentLongitudinalView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const fakeGetToken = async () => "test-token"
const COMISION = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
const STUDENT = "11111111-2222-3333-4444-555555555555"

const evolutionResponse = {
  student_pseudonym: STUDENT,
  comision_id: COMISION,
  n_groups_evaluated: 2,
  n_groups_insufficient: 0,
  n_episodes_total: 6,
  evolution_per_template: [
    {
      template_id: "tpl-1",
      n_episodes: 3,
      scores_ordinal: [0, 1, 2],
      slope: 1.0,
      insufficient_data: false,
    },
    {
      template_id: "tpl-2",
      n_episodes: 3,
      scores_ordinal: [2, 1, 0],
      slope: -1.0,
      insufficient_data: false,
    },
  ],
  // Sin agrupacion por Unidad en este fixture; la view cae al render
  // per_template cuando este array esta vacio.
  evolution_per_unidad: [],
  mean_slope: 0.0,
  sufficient_data: true,
  labeler_version: "1.0.0",
}

const alertsResponseWithAlerts = {
  student_pseudonym: STUDENT,
  comision_id: COMISION,
  labeler_version: "1.0.0",
  student_slope: -1.5,
  cohort_stats: {
    comision_id: COMISION,
    labeler_version: "1.0.0",
    min_students_for_quartiles: 5,
    n_students_evaluated: 8,
    insufficient_data: false,
    q1: -0.5,
    median: 0.0,
    q3: 0.5,
    min: -1.5,
    max: 1.0,
    mean: 0.0,
    stdev: 0.6,
  },
  quartile: "Q1" as const,
  alerts: [
    {
      code: "regresion_vs_cohorte",
      severity: "high" as const,
      title: "Regresión severa vs. cohorte",
      detail: "z=-2.5",
      threshold_used: "-2σ",
      z_score: -2.5,
    },
  ],
  n_alerts: 1,
  highest_severity: "high" as const,
}

const alertsResponseEmpty = {
  ...alertsResponseWithAlerts,
  student_slope: 0.0,
  quartile: "Q2" as const,
  alerts: [],
  n_alerts: 0,
  highest_severity: null,
}

function mockTwoFetches(evo: object, alerts: object) {
  setupFetchMock({
    "/cii-evolution-longitudinal": () => evo,
    "/alerts": () => alerts,
  })
}

beforeEach(() => {
  localStorage.setItem("analytics-view-mode", "investigador")
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("StudentLongitudinalView", () => {
  test("drill-down autocarga evolution + alerts", async () => {
    mockTwoFetches(evolutionResponse, alertsResponseWithAlerts)
    renderWithRouter(
      <StudentLongitudinalView
        getToken={fakeGetToken}
        initialComisionId={COMISION}
        initialStudentId={STUDENT}
      />,
    )
    await waitFor(() => {
      // Resumen denso: numero de episodios en el strip de stats (texto exacto del span)
      expect(screen.getByText("episodios")).toBeInTheDocument()
      expect(screen.getByText("6")).toBeInTheDocument()
    })
  })

  test("alertas con severity high se renderizan en panel ámbar", async () => {
    mockTwoFetches(evolutionResponse, alertsResponseWithAlerts)
    renderWithRouter(
      <StudentLongitudinalView
        getToken={fakeGetToken}
        initialComisionId={COMISION}
        initialStudentId={STUDENT}
      />,
    )
    await waitFor(() => {
      expect(screen.getByText(/1 alerta/i)).toBeInTheDocument()
    })
    expect(screen.getByText(/Regresión severa vs\. cohorte/i)).toBeInTheDocument()
    expect(screen.getByText(/Q1 \(peor 25%\)/i)).toBeInTheDocument()
  })

  test("sin alertas: panel emerald 'dentro del rango esperado'", async () => {
    mockTwoFetches(evolutionResponse, alertsResponseEmpty)
    renderWithRouter(
      <StudentLongitudinalView
        getToken={fakeGetToken}
        initialComisionId={COMISION}
        initialStudentId={STUDENT}
      />,
    )
    await waitFor(() => {
      expect(screen.getByText(/Sin alertas/i)).toBeInTheDocument()
    })
    expect(screen.getByText(/dentro del rango esperado/i)).toBeInTheDocument()
  })

  test("renderiza tabla con un row por template + slopes", async () => {
    mockTwoFetches(evolutionResponse, alertsResponseEmpty)
    renderWithRouter(
      <StudentLongitudinalView
        getToken={fakeGetToken}
        initialComisionId={COMISION}
        initialStudentId={STUDENT}
      />,
    )
    await waitFor(() => {
      // Slope positivo (template 1) y negativo (template 2)
      expect(screen.getByText(/\+1\.000/)).toBeInTheDocument()
      expect(screen.getByText(/-1\.000/)).toBeInTheDocument()
    })
    // Etiquetas de tendencia
    expect(screen.getByText(/mejorando/i)).toBeInTheDocument()
    expect(screen.getByText(/empeorando/i)).toBeInTheDocument()
  })
})
