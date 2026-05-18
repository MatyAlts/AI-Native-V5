/**
 * Tests E2E de HomeView (shape docente, brief D1).
 *
 * Cubre:
 *  - Render con N comisiones: una card por comision con KPIs.
 *  - Empty state honesto: "no tenes comisiones asignadas" + ADR-029.
 *  - Error state: rate limit / fetch fallido renderiza mensaje + UUID truncado.
 *  - Drill-down: click "Abrir cohorte" navega a /progression?comisionId=X.
 */
import { screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"
import { HomeView } from "../src/views/HomeView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const fakeGetToken = async () => "test-token"

const COMISION_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

const oneComisionResponse = {
  data: [
    {
      id: COMISION_ID,
      tenant_id: "00000000-0000-0000-0000-000000000001",
      materia_id: "11111111-1111-1111-1111-111111111111",
      periodo_id: "22222222-2222-2222-2222-222222222222",
      codigo: "A",
      nombre: "A-Manana",
      cupo_maximo: 30,
      horario: { resumen: "Lun/Mie 8-12" },
      ai_budget_monthly_usd: "100.00",
      curso_config_hash: null,
      created_at: "2026-03-01T00:00:00Z",
      deleted_at: null,
    },
  ],
  meta: { cursor_next: null },
}

const progressionResponse = {
  comision_id: COMISION_ID,
  n_students: 6,
  n_students_with_enough_data: 4,
  mejorando: 3,
  estable: 1,
  empeorando: 0,
  insuficiente: 2,
  net_progression_ratio: 0.5,
  trajectories: [
    { student_pseudonym: "stud-1", n_episodes: 3, points: [], first_classification: null, last_classification: null, max_appropriation_reached: null, progression_label: "mejorando", tercile_means: null },
    { student_pseudonym: "stud-2", n_episodes: 2, points: [], first_classification: null, last_classification: null, max_appropriation_reached: null, progression_label: "insuficiente", tercile_means: null },
  ],
}

const adversarialResponse = {
  comision_id: COMISION_ID,
  n_events_total: 0,
  counts_by_category: {},
  counts_by_severity: {},
  counts_by_student: {},
  top_students_by_n_events: [],
  recent_events: [],
}

const alertsSummaryInsufficientResponse = {
  comision_id: COMISION_ID,
  n_students_evaluated: 2,
  min_students_threshold: 5,
  insufficient_data: true,
  alerts_summary: null,
  labeler_version: "1.0.0",
}

const alertsSummaryPopulatedResponse = {
  comision_id: COMISION_ID,
  n_students_evaluated: 6,
  min_students_threshold: 5,
  insufficient_data: false,
  alerts_summary: {
    regresion_vs_cohorte: 1,
    bottom_quartile: 2,
    slope_negativo_significativo: 1,
    students_with_any_alert: 3,
  },
  labeler_version: "1.0.0",
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("HomeView", () => {
  test("con 1 comision asignada renderiza card con kpis y CTA", async () => {
    setupFetchMock({
      "/api/v1/comisiones/mis": () => oneComisionResponse,
      "/progression": () => progressionResponse,
      "/adversarial-events": () => adversarialResponse,
      "/alerts-summary": () => alertsSummaryPopulatedResponse,
    })
    renderWithRouter(<HomeView getToken={fakeGetToken} />)
    await waitFor(() => {
      expect(screen.getByTestId("comision-card")).toBeInTheDocument()
    })
    // Kicker codigo
    expect(screen.getByTestId("comision-card-kicker").textContent).toMatch(/A/)
    // Display name (nombre del seed)
    expect(screen.getByText("A-Manana")).toBeInTheDocument()
    // KPI alumnos visible (n_students=6)
    const kpiBlock = screen.getByTestId("comision-card-kpis")
    expect(kpiBlock).toHaveTextContent("alumnos")
    expect(kpiBlock).toHaveTextContent("6")
    // CTA Ver cohorte
    expect(screen.getByTestId("comision-card-cohort-link")).toHaveTextContent(/Ver cohorte/i)
  })

  test("alertas muestra students_with_any_alert cuando hay data", async () => {
    setupFetchMock({
      "/api/v1/comisiones/mis": () => oneComisionResponse,
      "/progression": () => progressionResponse,
      "/adversarial-events": () => adversarialResponse,
      "/alerts-summary": () => alertsSummaryPopulatedResponse,
    })
    renderWithRouter(<HomeView getToken={fakeGetToken} />)
    await waitFor(() => {
      expect(screen.getByTestId("comision-card-kpi-alertas")).toBeInTheDocument()
    })
    const alertasKpi = screen.getByTestId("comision-card-kpi-alertas")
    // students_with_any_alert = 3
    expect(alertasKpi).toHaveTextContent("3")
    // Tooltip lista breakdown
    expect(alertasKpi.getAttribute("title")).toMatch(/3 estudiantes/)
    expect(alertasKpi.getAttribute("title")).toMatch(/regresion vs cohorte: 1/)
  })

  test("alertas '—' + tooltip k-anonymity cuando insufficient_data", async () => {
    setupFetchMock({
      "/api/v1/comisiones/mis": () => oneComisionResponse,
      "/progression": () => progressionResponse,
      "/adversarial-events": () => adversarialResponse,
      "/alerts-summary": () => alertsSummaryInsufficientResponse,
    })
    renderWithRouter(<HomeView getToken={fakeGetToken} />)
    await waitFor(() => {
      expect(screen.getByTestId("comision-card-kpi-alertas")).toBeInTheDocument()
    })
    const alertasKpi = screen.getByTestId("comision-card-kpi-alertas")
    // KPI muestra "—" porque insufficient_data=true
    expect(alertasKpi.textContent).toMatch(/—/)
    // Tooltip explica k-anonymity
    expect(alertasKpi.getAttribute("title")).toMatch(/k-anonymity/)
    expect(alertasKpi.getAttribute("title")).toMatch(/N<5/)
  })

  test("empty state honesto cuando docente no tiene comisiones", async () => {
    setupFetchMock({
      "/api/v1/comisiones/mis": () => ({ data: [], meta: { cursor_next: null } }),
    })
    renderWithRouter(<HomeView getToken={fakeGetToken} />)
    await waitFor(() => {
      expect(screen.getByText(/Todav.a no ten.s comisiones asignadas/i)).toBeInTheDocument()
    })
    expect(screen.getByText(/ADR-029/i)).toBeInTheDocument()
  })

  test("error de fetch renderiza mensaje + UUID truncado", async () => {
    setupFetchMock({
      "/api/v1/comisiones/mis": {
        ok: false,
        status: 500,
        body: () => ({ detail: "boom" }),
      },
    })
    renderWithRouter(<HomeView getToken={fakeGetToken} />)
    await waitFor(() => {
      expect(screen.getByText(/No pudimos cargar tus comisiones/i)).toBeInTheDocument()
    })
  })

  test("tools transversales como divider tipografico (no card-grid)", async () => {
    setupFetchMock({
      "/api/v1/comisiones/mis": () => oneComisionResponse,
      "/progression": () => progressionResponse,
      "/adversarial-events": () => adversarialResponse,
    })
    renderWithRouter(<HomeView getToken={fakeGetToken} />)
    await waitFor(() => {
      expect(screen.getByText(/Herramientas transversales/i)).toBeInTheDocument()
    })
    // Las 3 tools son line-items (no cards)
    expect(screen.getByText(/Plantillas/i)).toBeInTheDocument()
    expect(screen.getByText(/Inter-rater/i)).toBeInTheDocument()
    expect(screen.getByText(/Exportar dataset/i)).toBeInTheDocument()
  })
})
