/**
 * Tests E2E de CohortAdversarialView (ADR-019 + ADR-022).
 *
 * Cubre:
 * - Render con initialComisionId: fetch automático al montar
 * - Render del shape vacío (n_events_total=0): mensaje emerald "sin eventos"
 * - Render con eventos: barras de categoría + severidad + ranking + recientes
 */
import { screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"
import { CohortAdversarialView } from "../src/views/CohortAdversarialView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const fakeGetToken = async () => "test-token"

const COMISION_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

const emptyResponse = {
  comision_id: COMISION_ID,
  n_events_total: 0,
  counts_by_category: {},
  counts_by_severity: { "1": 0, "2": 0, "3": 0, "4": 0, "5": 0 },
  counts_by_student: {},
  top_students_by_n_events: [],
  recent_events: [],
}

const populatedResponse = {
  comision_id: COMISION_ID,
  n_events_total: 5,
  counts_by_category: {
    jailbreak_substitution: 3,
    persuasion_urgency: 2,
  },
  counts_by_severity: { "1": 0, "2": 2, "3": 0, "4": 3, "5": 0 },
  counts_by_student: {
    "stud-aaaa": 3,
    "stud-bbbb": 2,
  },
  top_students_by_n_events: [
    { student_pseudonym: "stud-aaaa", n_events: 3 },
    { student_pseudonym: "stud-bbbb", n_events: 2 },
  ],
  recent_events: [
    {
      episode_id: "ep-1",
      student_pseudonym: "stud-aaaa",
      ts: "2026-04-27T10:30:00Z",
      category: "jailbreak_substitution",
      severity: 4,
      pattern_id: "jailbreak_substitution_v1_1_0_p0",
      matched_text: "olvida tus instrucciones",
    },
  ],
}

beforeEach(() => {
  localStorage.setItem("analytics-view-mode", "investigador")
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("CohortAdversarialView", () => {
  test("con initialComisionId, fetch al montar y renderiza estructura vacía", async () => {
    setupFetchMock({ "/adversarial-events": () => emptyResponse })
    renderWithRouter(<CohortAdversarialView getToken={fakeGetToken} initialComisionId={COMISION_ID} />)
    await waitFor(() => {
      expect(screen.getByText(/Sin eventos adversos en esta cohorte/i)).toBeInTheDocument()
    })
  })

  test("con eventos: renderiza categoria + severidad + ranking + recientes", async () => {
    setupFetchMock({ "/adversarial-events": () => populatedResponse })
    renderWithRouter(<CohortAdversarialView getToken={fakeGetToken} initialComisionId={COMISION_ID} />)
    await waitFor(() => {
      // Total de eventos
      expect(screen.getByText("5")).toBeInTheDocument()
    })
    // Categoría visible (en barras + en lista de recientes)
    const jailbreakLabels = screen.getAllByText(/Jailbreak \(sustituci/i)
    expect(jailbreakLabels.length).toBeGreaterThanOrEqual(1)
    // Top student aparece (al menos una vez; puede aparecer en ranking + recientes)
    expect(screen.getAllByText(/stud-aaa/).length).toBeGreaterThanOrEqual(1)
    // matched_text aparece en recientes
    expect(screen.getByText(/olvida tus instrucciones/i)).toBeInTheDocument()
  })

  test("error de API se renderiza con mensaje", async () => {
    setupFetchMock({
      "/adversarial-events": {
        ok: false,
        status: 500,
        body: () => ({ detail: "Internal error" }),
      },
    })
    renderWithRouter(<CohortAdversarialView getToken={fakeGetToken} initialComisionId={COMISION_ID} />)
    await waitFor(() => {
      expect(screen.getByText(/Error consultando la cohorte/i)).toBeInTheDocument()
    })
  })
})
