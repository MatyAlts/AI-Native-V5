/**
 * Reproduccion de la auditoria del panel del docente (rama `audita/docente`).
 *
 * El docente corrige por criterio; el alumno lee lo que el docente puso. Este
 * test documenta que ese ultimo tramo esta cortado: `GradeDetailView` lee
 * `criterio.nombre` y `criterio.peso`, y el backend
 * (`evaluation_service.schemas.entrega.CriterioCalificacion`) persiste y
 * devuelve `criterio` y `max_puntaje`. La asercion esta escrita sobre el
 * comportamiento ACTUAL (roto).
 */
import { cleanup, screen, waitFor } from "@testing-library/react"
import { render } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { GradeDetailView } from "../src/components/GradeDetailView"

const ENTREGA_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"

const entregaGraded = {
  id: ENTREGA_ID,
  tenant_id: "t1",
  tarea_practica_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  comision_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  student_pseudonym: "b1b1b1b1-0001-0001-0001-000000000001",
  estado: "graded" as const,
  ejercicio_estados: [],
  submitted_at: "2026-05-06T12:00:00Z",
  created_at: "2026-05-06T10:00:00Z",
  updated_at: "2026-05-06T12:00:00Z",
}

// Exactamente lo que devuelve `GET /entregas/{id}/calificacion`: el shape del
// schema `CriterioCalificacion` del evaluation-service.
const calificacionDelBackend = {
  id: "cal-1",
  entrega_id: ENTREGA_ID,
  nota_final: 8,
  feedback_general: "Buen trabajo",
  detalle_criterios: [
    { criterio: "Correctitud", puntaje: "4.00", max_puntaje: "5.00", comentario: null },
    { criterio: "Legibilidad", puntaje: "3.00", max_puntaje: "3.00", comentario: null },
  ],
  graded_at: "2026-05-06T13:00:00Z",
  graded_by: "docente-1",
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("La devolucion por criterio que ve el alumno", () => {
  it("muestra el criterio sin nombre y el maximo como NaN", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(calificacionDelBackend),
          text: () => Promise.resolve(JSON.stringify(calificacionDelBackend)),
        } as Response),
      ),
    )

    render(<GradeDetailView entrega={entregaGraded} onBack={() => {}} />)

    await waitFor(() => {
      expect(screen.getByTestId("criterios-list")).toBeDefined()
    })

    const items = screen.getAllByTestId("criterio-item")
    expect(items.length).toBe(2)

    // El nombre del criterio sale vacio: la vista lee `.nombre`, el backend
    // manda `.criterio`.
    expect(items[0]?.textContent).not.toContain("Correctitud")

    // Y el denominador sale NaN: la vista hace `Math.round(criterio.peso * 10)`
    // y el backend manda `max_puntaje`. El alumno lee "4.00 / NaN".
    expect(items[0]?.textContent).toContain("NaN")
    expect(items[1]?.textContent).toContain("NaN")
  })
})
