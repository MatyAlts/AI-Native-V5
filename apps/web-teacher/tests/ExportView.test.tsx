/**
 * informe-avance-comisiones — Lote 2, IAC-04 (wiring en ExportView).
 *
 * Cubre SOLO lo agregado (accion "Informe de avance (imprimible)"):
 *  - El boton de export JSON existente sigue presente (no se rompe el flujo).
 *  - Click en "Informe de avance (imprimible)" fetchea progresion/cuartiles/
 *    alertas/perfiles de la comision seleccionada, compone el informe con los
 *    helpers del Lote 1 y lo renderiza (nombre real + rotulo de privacidad).
 *  - Dispara `window.print()` una vez el informe esta en el DOM.
 *  - Si un fetch falla, se muestra un error legible (no rompe la vista).
 *
 * NO cubre: el flujo completo de export JSON (POST /cohort/export + polling),
 * que ya existia antes de este cambio y no se toco.
 */
import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, test, vi } from "vitest"
import { ExportView } from "../src/views/ExportView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

function baseHandlers() {
  return {
    "/comisiones/mis": () => ({
      data: [
        {
          id: COMISION_ID,
          tenant_id: "t1",
          materia_id: "m1",
          periodo_id: "p1",
          codigo: "A",
          nombre: "A-Manana",
          materia_nombre: "Prog 1",
          cupo_maximo: 30,
          horario: {},
          ai_budget_monthly_usd: "0",
          curso_config_hash: null,
          created_at: "2026-01-01T00:00:00Z",
          deleted_at: null,
        },
      ],
      meta: { cursor_next: null },
    }),
    "/progression": () => ({
      comision_id: COMISION_ID,
      n_students: 1,
      n_students_with_enough_data: 1,
      mejorando: 1,
      estable: 0,
      empeorando: 0,
      insuficiente: 0,
      net_progression_ratio: 1,
      trajectories: [
        {
          student_pseudonym: "c1c1c1c1-0001-0001-0001-000000000001",
          n_episodes: 3,
          first_classification: "delegacion_pasiva",
          last_classification: "apropiacion_reflexiva",
          max_appropriation_reached: "apropiacion_reflexiva",
          progression_label: "mejorando",
          tercile_means: [0.1, 0.4, 0.8],
          points: [],
        },
      ],
    }),
    "/cii-quartiles": () => ({
      comision_id: COMISION_ID,
      labeler_version: "1.2.0",
      min_students_for_quartiles: 5,
      n_students_evaluated: 1,
      insufficient_data: true,
      q1: null,
      median: null,
      q3: null,
      min: null,
      max: null,
      mean: null,
      stdev: null,
    }),
    "/alerts-summary": () => ({
      comision_id: COMISION_ID,
      n_students_evaluated: 1,
      min_students_threshold: 5,
      insufficient_data: true,
      alerts_summary: null,
      labeler_version: "1.2.0",
    }),
    "/students/profiles": () => [
      {
        student_pseudonym: "c1c1c1c1-0001-0001-0001-000000000001",
        full_name: "Maria Gomez",
        email: "maria@example.com",
        updated_at: null,
      },
    ],
  }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe("ExportView — informe de avance (imprimible)", () => {
  test("el boton de export JSON existente sigue presente junto al nuevo boton", async () => {
    setupFetchMock(baseHandlers())
    renderWithRouter(
      <ExportView getToken={async () => "tok"} comisionIdDefault={COMISION_ID} />,
    )
    // `renderWithRouter` monta un RouterProvider real: la primera resolucion
    // de ruta es asincrona (aunque no haya loaders), asi que la primera
    // consulta tiene que ser un `findBy*` — un `getBy*` sincrono ve el arbol
    // todavia en su estado "pending" (vacio).
    expect(await screen.findByRole("button", { name: /generar dataset/i })).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /informe de avance \(imprimible\)/i }),
    ).toBeInTheDocument()
  })

  test("genera y muestra el informe con nombre real + rotulo de privacidad, y dispara print", async () => {
    setupFetchMock(baseHandlers())
    const printSpy = vi.spyOn(window, "print").mockImplementation(() => {})
    const user = userEvent.setup()

    renderWithRouter(<ExportView getToken={async () => "tok"} comisionIdDefault={COMISION_ID} />)

    const informeButton = await screen.findByRole("button", {
      name: /informe de avance \(imprimible\)/i,
    })
    await user.click(informeButton)

    expect(await screen.findByText("Maria Gomez")).toBeInTheDocument()
    expect(
      screen.getByText(/uso interno de la c[aá]tedra.*contiene datos personales.*no publicar/i),
    ).toBeInTheDocument()
    // Cuartiles Y alertas vinieron insufficient_data:true -> honestidad
    // tecnica en las dos secciones de la portada, nunca ceros.
    expect(screen.getAllByText(/datos insuficientes por privacidad/i).length).toBeGreaterThanOrEqual(
      2,
    )

    await waitFor(() => expect(printSpy).toHaveBeenCalledTimes(1))
  })

  test("si un fetch del informe falla, muestra error legible sin romper la vista", async () => {
    setupFetchMock({
      ...baseHandlers(),
      "/cii-quartiles": { ok: false, status: 500, body: () => ({ detail: "boom" }) },
    })
    const user = userEvent.setup()

    renderWithRouter(<ExportView getToken={async () => "tok"} comisionIdDefault={COMISION_ID} />)

    const informeButton = await screen.findByRole("button", {
      name: /informe de avance \(imprimible\)/i,
    })
    await user.click(informeButton)

    expect(await screen.findByText(/error/i)).toBeInTheDocument()
    // El form de export JSON sigue intacto tras el error del informe.
    expect(screen.getByRole("button", { name: /generar dataset/i })).toBeInTheDocument()
  })
})
