/**
 * Tests E2E del ComisionDelDocenteCard (shape docente).
 *
 * Cubre:
 *  - Render con 4 KPIs + display name + CTA "Abrir cohorte".
 *  - "datos insuf." cuando un KPI viene null (honestidad tecnica).
 *  - Drill-down: link "Abrir cohorte" -> /progression?comisionId=X.
 */
import { screen } from "@testing-library/react"
import { describe, expect, test } from "vitest"
import {
  ComisionDelDocenteCard,
  type ComisionKpis,
} from "../src/components/ComisionDelDocenteCard"
import type { Comision } from "../src/lib/api"
import { renderWithRouter } from "./_mocks"

function makeComision(overrides: Partial<Comision> = {}): Comision {
  return {
    id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
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
    ...overrides,
  }
}

const fullKpis: ComisionKpis = {
  alumnos: 6,
  episodiosSemana: 12,
  alertas: 2,
  adversosSemana: 0,
}

const partialKpis: ComisionKpis = {
  alumnos: 6,
  episodiosSemana: null,
  alertas: null,
  adversosSemana: 0,
}

describe("ComisionDelDocenteCard", () => {
  test("renderiza kicker + headline + 4 KPIs + CTA", async () => {
    renderWithRouter(
      <ComisionDelDocenteCard
        comision={makeComision()}
        displayName="A-Manana"
        kpis={fullKpis}
      />,
    )
    expect(await screen.findByTestId("comision-card-kicker")).toHaveTextContent(/A/)
    // El horario vive en un span hermano del kicker dentro de la misma card
    expect(screen.getByTestId("comision-card")).toHaveTextContent(/Lun\/Mie 8-12/)
    expect(screen.getByText("A-Manana")).toBeInTheDocument()
    const kpis = screen.getByTestId("comision-card-kpis")
    expect(kpis).toHaveTextContent(/alumnos/)
    expect(kpis).toHaveTextContent("6")
    expect(kpis).toHaveTextContent(/episodios sem\./)
    expect(kpis).toHaveTextContent("12")
    expect(kpis).toHaveTextContent(/alertas/)
    expect(kpis).toHaveTextContent("2")
    expect(kpis).toHaveTextContent(/adversos sem\./)
    expect(screen.getByTestId("comision-card-cohort-link")).toHaveTextContent(/Ver cohorte/i)
  })

  test("kpi null se renderiza como '—' (no 0 ambiguo)", async () => {
    renderWithRouter(
      <ComisionDelDocenteCard
        comision={makeComision()}
        displayName="A-Manana"
        kpis={partialKpis}
      />,
    )
    const kpis = await screen.findByTestId("comision-card-kpis")
    // alumnos=6 visible
    expect(kpis).toHaveTextContent("6")
    // episodios + alertas son "—" (guion largo, honestidad tecnica).
    // El layout actual no usa <dd>; cada celda es un div con span value + span label.
    // Buscamos spans cuyo texto sea exactamente "—" (los valores nulos).
    const valueSpans = kpis.querySelectorAll("span")
    const dashCount = Array.from(valueSpans).filter(
      (s) => (s.textContent ?? "").trim() === "—",
    ).length
    expect(dashCount).toBeGreaterThanOrEqual(2)
  })

  test("CTA 'Abrir cohorte' apunta a /progression con comisionId", async () => {
    const c = makeComision()
    renderWithRouter(
      <ComisionDelDocenteCard comision={c} displayName="A-Manana" kpis={fullKpis} />,
    )
    const link = (await screen.findByTestId("comision-card-cohort-link")) as HTMLAnchorElement
    expect(link.getAttribute("href")).toMatch(/progression/)
    expect(link.getAttribute("href")).toContain(c.id)
  })
})
