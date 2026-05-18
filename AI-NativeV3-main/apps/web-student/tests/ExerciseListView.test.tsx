/**
 * Tests para ExerciseListView (tp-entregas-correccion).
 *
 * Cubre:
 *   - Render de la lista de ejercicios con estados lock/unlock/complete
 *   - Barra de progreso con X/N ejercicios completados
 *   - Boton "Entregar TP" visible solo cuando todos completos
 *   - Badge de estado de entrega (draft/submitted/graded/returned)
 *   - Boton "Ver calificacion" visible cuando graded/returned
 *   - Click en ejercicio disponible llama onSelectEjercicio
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ExerciseListView } from "../src/components/ExerciseListView"
import type { AvailableTarea, Entrega } from "../src/lib/api"
import { setupFetchMock } from "./_mocks"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const TAREA_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
const ENTREGA_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"

function makeEntrega(overrides: Partial<Entrega> = {}): Entrega {
  return {
    id: ENTREGA_ID,
    tenant_id: "t1",
    tarea_practica_id: TAREA_ID,
    comision_id: COMISION_ID,
    student_pseudonym: "b1b1b1b1-0001-0001-0001-000000000001",
    estado: "draft",
    ejercicio_estados: [
      { orden: 1, completado: false, episode_id: null, completado_at: null },
      { orden: 2, completado: false, episode_id: null, completado_at: null },
    ],
    submitted_at: null,
    created_at: "2026-05-06T10:00:00Z",
    updated_at: "2026-05-06T10:00:00Z",
    ...overrides,
  }
}

function makeTarea(overrides: Partial<AvailableTarea> = {}): AvailableTarea {
  return {
    id: TAREA_ID,
    codigo: "TP01",
    titulo: "Funciones basicas",
    enunciado: "Implementar funciones basicas en Python.",
    fecha_inicio: null,
    fecha_fin: null,
    peso: "1.0",
    estado: "published",
    version: 1,
    inicial_codigo: null,
    ejercicios: [
      {
        orden: 1,
        titulo: "Suma",
        enunciado_md: "Implementar suma",
        inicial_codigo: null,
        peso: 0.5,
      },
      {
        orden: 2,
        titulo: "Resta",
        enunciado_md: "Implementar resta",
        inicial_codigo: null,
        peso: 0.5,
      },
    ],
    ...overrides,
  }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("ExerciseListView", () => {
  describe("render inicial", () => {
    beforeEach(() => {
      const entrega = makeEntrega()
      setupFetchMock({
        "/api/v1/entregas": () => ({ data: [entrega], meta: { cursor_next: null } }),
      })
    })

    it("muestra el titulo de la TP", async () => {
      const tarea = makeTarea()
      render(
        <ExerciseListView
          tarea={tarea}
          comisionId={COMISION_ID}
          onSelectEjercicio={vi.fn()}
          onViewGrade={vi.fn()}
          onBack={vi.fn()}
        />,
      )
      await waitFor(() => {
        expect(screen.getByTestId("exercise-list-view")).toBeDefined()
      })
      expect(screen.getByText("Funciones basicas")).toBeDefined()
    })

    it("muestra la lista de ejercicios ordenada", async () => {
      const tarea = makeTarea()
      render(
        <ExerciseListView
          tarea={tarea}
          comisionId={COMISION_ID}
          onSelectEjercicio={vi.fn()}
          onViewGrade={vi.fn()}
          onBack={vi.fn()}
        />,
      )
      await waitFor(() => {
        expect(screen.getByTestId("ejercicios-list")).toBeDefined()
      })
      expect(screen.getByTestId("ejercicio-item-1")).toBeDefined()
      expect(screen.getByTestId("ejercicio-item-2")).toBeDefined()
    })
  })

  describe("progreso de ejercicios", () => {
    it("muestra barra de progreso con 0/2 completados", async () => {
      const entrega = makeEntrega()
      setupFetchMock({
        "/api/v1/entregas": () => entrega,
      })
      const tarea = makeTarea()
      render(
        <ExerciseListView
          tarea={tarea}
          comisionId={COMISION_ID}
          onSelectEjercicio={vi.fn()}
          onViewGrade={vi.fn()}
          onBack={vi.fn()}
        />,
      )
      await waitFor(() => {
        expect(screen.getByTestId("entrega-progress")).toBeDefined()
      })
      expect(screen.getByText("0/2")).toBeDefined()
    })

    it("muestra barra de progreso con 1/2 completados", async () => {
      const entrega = makeEntrega({
        ejercicio_estados: [
          { orden: 1, completado: true, episode_id: "ep-1", completado_at: "2026-05-06T11:00:00Z" },
          { orden: 2, completado: false, episode_id: null, completado_at: null },
        ],
      })
      setupFetchMock({
        "/api/v1/entregas": () => entrega,
      })
      const tarea = makeTarea()
      render(
        <ExerciseListView
          tarea={tarea}
          comisionId={COMISION_ID}
          onSelectEjercicio={vi.fn()}
          onViewGrade={vi.fn()}
          onBack={vi.fn()}
        />,
      )
      await waitFor(() => {
        expect(screen.getByText("1/2")).toBeDefined()
      })
    })
  })

  describe("secuencialidad de ejercicios", () => {
    it("el ejercicio 2 esta bloqueado cuando el 1 no esta completado", async () => {
      const entrega = makeEntrega()
      setupFetchMock({
        "/api/v1/entregas": () => entrega,
      })
      const tarea = makeTarea()
      render(
        <ExerciseListView
          tarea={tarea}
          comisionId={COMISION_ID}
          onSelectEjercicio={vi.fn()}
          onViewGrade={vi.fn()}
          onBack={vi.fn()}
        />,
      )
      await waitFor(() => {
        expect(screen.getByTestId("ejercicios-list")).toBeDefined()
      })
      // Ejercicio 2 bloqueado — no debe tener boton de start
      expect(screen.queryByTestId("ejercicio-start-2")).toBeNull()
    })

    it("muestra boton de empezar en ejercicio 1", async () => {
      const entrega = makeEntrega()
      setupFetchMock({
        "/api/v1/entregas": () => entrega,
      })
      const tarea = makeTarea()
      render(
        <ExerciseListView
          tarea={tarea}
          comisionId={COMISION_ID}
          onSelectEjercicio={vi.fn()}
          onViewGrade={vi.fn()}
          onBack={vi.fn()}
        />,
      )
      await waitFor(() => {
        expect(screen.getByTestId("ejercicio-start-1")).toBeDefined()
      })
    })

    it("click en ejercicio disponible llama onSelectEjercicio con el orden correcto", async () => {
      const entrega = makeEntrega()
      setupFetchMock({
        "/api/v1/entregas": () => entrega,
      })
      const tarea = makeTarea()
      const onSelectEjercicio = vi.fn()
      render(
        <ExerciseListView
          tarea={tarea}
          comisionId={COMISION_ID}
          onSelectEjercicio={onSelectEjercicio}
          onViewGrade={vi.fn()}
          onBack={vi.fn()}
        />,
      )
      await waitFor(() => {
        expect(screen.getByTestId("ejercicio-start-1")).toBeDefined()
      })
      fireEvent.click(screen.getByTestId("ejercicio-start-1"))
      expect(onSelectEjercicio).toHaveBeenCalledWith(tarea, 1, ENTREGA_ID)
    })
  })

  describe("boton Entregar TP", () => {
    it("NO muestra el boton cuando hay ejercicios incompletos", async () => {
      const entrega = makeEntrega()
      setupFetchMock({
        "/api/v1/entregas": () => entrega,
      })
      const tarea = makeTarea()
      render(
        <ExerciseListView
          tarea={tarea}
          comisionId={COMISION_ID}
          onSelectEjercicio={vi.fn()}
          onViewGrade={vi.fn()}
          onBack={vi.fn()}
        />,
      )
      await waitFor(() => {
        expect(screen.getByTestId("ejercicios-list")).toBeDefined()
      })
      expect(screen.queryByTestId("submit-entrega-btn")).toBeNull()
    })

    it("muestra el boton cuando todos los ejercicios estan completados y estado=draft", async () => {
      const entrega = makeEntrega({
        ejercicio_estados: [
          { orden: 1, completado: true, episode_id: "ep-1", completado_at: "2026-05-06T11:00:00Z" },
          { orden: 2, completado: true, episode_id: "ep-2", completado_at: "2026-05-06T11:30:00Z" },
        ],
      })
      setupFetchMock({
        "/api/v1/entregas": () => entrega,
      })
      const tarea = makeTarea()
      render(
        <ExerciseListView
          tarea={tarea}
          comisionId={COMISION_ID}
          onSelectEjercicio={vi.fn()}
          onViewGrade={vi.fn()}
          onBack={vi.fn()}
        />,
      )
      await waitFor(() => {
        expect(screen.getByTestId("submit-entrega-btn")).toBeDefined()
      })
    })
  })

  describe("badges de estado de entrega", () => {
    it("muestra badge 'Entregada' cuando estado=submitted", async () => {
      const entrega = makeEntrega({ estado: "submitted" })
      setupFetchMock({
        "/api/v1/entregas": () => entrega,
      })
      const tarea = makeTarea()
      render(
        <ExerciseListView
          tarea={tarea}
          comisionId={COMISION_ID}
          onSelectEjercicio={vi.fn()}
          onViewGrade={vi.fn()}
          onBack={vi.fn()}
        />,
      )
      await waitFor(() => {
        expect(screen.getByTestId("entrega-estado-badge")).toBeDefined()
      })
      expect(screen.getByText("Entregada")).toBeDefined()
    })

    it("muestra boton Ver calificacion cuando estado=graded", async () => {
      const entrega = makeEntrega({
        estado: "graded",
        ejercicio_estados: [
          { orden: 1, completado: true, episode_id: "ep-1", completado_at: "2026-05-06T11:00:00Z" },
          { orden: 2, completado: true, episode_id: "ep-2", completado_at: "2026-05-06T11:30:00Z" },
        ],
      })
      setupFetchMock({
        "/api/v1/entregas": () => entrega,
      })
      const tarea = makeTarea()
      const onViewGrade = vi.fn()
      render(
        <ExerciseListView
          tarea={tarea}
          comisionId={COMISION_ID}
          onSelectEjercicio={vi.fn()}
          onViewGrade={onViewGrade}
          onBack={vi.fn()}
        />,
      )
      await waitFor(() => {
        expect(screen.getByTestId("ver-calificacion-btn")).toBeDefined()
      })
      fireEvent.click(screen.getByTestId("ver-calificacion-btn"))
      expect(onViewGrade).toHaveBeenCalledWith(entrega)
    })
  })
})
