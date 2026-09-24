/**
 * BUG-19 (QA 2026-09-23): "Ver calificacion" mostraba
 * "CRITERIOS DE EVALUACION -> 0 / NaN".
 *
 * `GradeDetailView` leia `criterio.nombre` y `criterio.peso`, campos que no
 * existen en el contrato real (`{criterio, puntaje, max_puntaje, comentario}`
 * — `CriterioCalificacion` de evaluation-service). El nombre salia vacio y
 * `Math.round(criterio.peso * 10)` daba `NaN` con la autoridad de un numero
 * real.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { GradeDetailView } from "../src/components/GradeDetailView"
import type { Entrega } from "../src/lib/api"
import { setupFetchMock } from "./_mocks"

const ENTREGA_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"

function makeEntregaGraded(): Entrega {
  return {
    id: ENTREGA_ID,
    tenant_id: "t1",
    tarea_practica_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    comision_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    student_pseudonym: "b1b1b1b1-0001-0001-0001-000000000001",
    estado: "graded",
    ejercicio_estados: [],
    submitted_at: "2026-09-20T10:00:00Z",
    created_at: "2026-09-20T09:00:00Z",
    updated_at: "2026-09-23T12:00:00Z",
  }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("GradeDetailView — BUG-19", () => {
  it("muestra el criterio real y el puntaje sobre max_puntaje, sin NaN", async () => {
    setupFetchMock({
      "/calificacion": () => ({
        id: "califid-1",
        entrega_id: ENTREGA_ID,
        nota_final: 7,
        feedback_general: "Buen trabajo",
        detalle_criterios: [
          { criterio: "Usa la interfaz", puntaje: 3, max_puntaje: 5, comentario: null },
        ],
        graded_at: "2026-09-23T12:00:00Z",
        graded_by: "docente-1",
      }),
    })

    render(<GradeDetailView entrega={makeEntregaGraded()} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByTestId("criterio-item")).toBeInTheDocument()
    })
    expect(screen.getByText("Usa la interfaz")).toBeInTheDocument()
    expect(screen.getByText("3 / 5")).toBeInTheDocument()
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument()
  })

  it("un max_puntaje ausente muestra '—', nunca NaN", async () => {
    setupFetchMock({
      "/calificacion": () => ({
        id: "califid-2",
        entrega_id: ENTREGA_ID,
        nota_final: 5,
        feedback_general: "",
        // Shape legacy/roto: sin max_puntaje. Es exactamente el caso que
        // producia "0 / NaN" en produccion.
        detalle_criterios: [{ criterio: "Sin maximo", puntaje: 0, comentario: null }],
        graded_at: "2026-09-23T12:00:00Z",
        graded_by: "docente-1",
      }),
    })

    render(<GradeDetailView entrega={makeEntregaGraded()} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByTestId("criterio-item")).toBeInTheDocument()
    })
    expect(screen.getByText("0 / —")).toBeInTheDocument()
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument()
  })
})
