/**
 * Tests para CorreccionesView (EntregasListView + GradingFormView).
 * tp-entregas-correccion, task 12.2.
 *
 * Cubre:
 *   - EntregasListView: muestra tabla con filas de entregas
 *   - EntregasListView: filtra por estado
 *   - EntregasListView: click en fila abre GradingFormView
 *   - GradingFormView: muestra cabecera y ejercicios de la entrega
 *   - GradingFormView: muestra formulario para entregas submitted
 *   - GradingFormView: muestra boton Devolver para entregas graded
 *   - GradingFormView: no muestra boton Calificar para entregas graded
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { CorreccionesView } from "../src/views/CorreccionesView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const TAREA_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
const ENTREGA_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
const STUDENT_ID = "b1b1b1b1-0001-0001-0001-000000000001"

const mockEntregaSubmitted = {
  id: ENTREGA_ID,
  tenant_id: "t1",
  tarea_practica_id: TAREA_ID,
  comision_id: COMISION_ID,
  student_pseudonym: STUDENT_ID,
  estado: "submitted",
  ejercicio_estados: [
    { orden: 1, completado: true, episode_id: "ep-0000001-abcd", completado_at: "2026-05-06T11:00:00Z" },
    { orden: 2, completado: true, episode_id: "ep-0000002-abcd", completado_at: "2026-05-06T11:30:00Z" },
  ],
  submitted_at: "2026-05-06T12:00:00Z",
  created_at: "2026-05-06T10:00:00Z",
  updated_at: "2026-05-06T12:00:00Z",
}

const mockEntregaGraded = {
  ...mockEntregaSubmitted,
  estado: "graded",
}

const mockTarea = {
  id: TAREA_ID,
  tenant_id: "t1",
  comision_id: COMISION_ID,
  codigo: "TP01",
  titulo: "Funciones basicas",
  enunciado: "Implementar funciones",
  fecha_inicio: null,
  fecha_fin: null,
  peso: "1.0",
  rubrica: null,
  estado: "published",
  version: 1,
  parent_tarea_id: null,
  template_id: null,
  has_drift: false,
  created_by: "u1",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
}

const getToken = () => Promise.resolve("dev-token")

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("CorreccionesView — EntregasListView", () => {
  it("muestra la tabla con una entrega submitted", async () => {
    setupFetchMock({
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(
      <CorreccionesView comisionId={COMISION_ID} getToken={getToken} />,
    )
    await waitFor(() => {
      expect(screen.getByTestId("entregas-list-view")).toBeDefined()
    })
    expect(screen.getByTestId("entregas-table")).toBeDefined()
    const rows = screen.getAllByTestId("entrega-row")
    expect(rows.length).toBe(1)
  })

  it("muestra badge de estado 'Enviada' para submitted", async () => {
    setupFetchMock({
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(
      <CorreccionesView comisionId={COMISION_ID} getToken={getToken} />,
    )
    await waitFor(() => {
      expect(screen.getByTestId("entrega-estado-submitted")).toBeDefined()
    })
    // "Enviada" aparece en 2 lugares: el badge de estado y el label del timestamp
    // de submitted_at. Asertamos que el badge contiene la etiqueta correcta.
    expect(screen.getByTestId("entrega-estado-submitted")).toHaveTextContent("Enviada")
  })

  it("muestra mensaje cuando no hay entregas", async () => {
    setupFetchMock({
      "/api/v1/entregas": () => ({ data: [], meta: { cursor_next: null } }),
    })
    renderWithRouter(
      <CorreccionesView comisionId={COMISION_ID} getToken={getToken} />,
    )
    await waitFor(() => {
      expect(screen.getByTestId("entregas-list-view")).toBeDefined()
    })
    expect(screen.getByText(/aun no tiene entregas/i)).toBeDefined()
  })

  it("click en Corregir abre el GradingFormView", async () => {
    setupFetchMock({
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(
      <CorreccionesView comisionId={COMISION_ID} getToken={getToken} />,
    )
    await waitFor(() => {
      expect(screen.getByTestId("entrega-drill-btn")).toBeDefined()
    })
    fireEvent.click(screen.getByTestId("entrega-drill-btn"))
    await waitFor(() => {
      expect(screen.getByTestId("grading-form-view")).toBeDefined()
    })
  })
})

describe("CorreccionesView — GradingFormView", () => {
  it("muestra los ejercicios completados en la entrega", async () => {
    setupFetchMock({
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(
      <CorreccionesView comisionId={COMISION_ID} getToken={getToken} />,
    )
    await waitFor(() => {
      expect(screen.getByTestId("entrega-drill-btn")).toBeDefined()
    })
    fireEvent.click(screen.getByTestId("entrega-drill-btn"))
    await waitFor(() => {
      expect(screen.getByTestId("ejercicios-estados-list")).toBeDefined()
    })
    expect(screen.getByTestId("ej-estado-1")).toBeDefined()
    expect(screen.getByTestId("ej-estado-2")).toBeDefined()
  })

  it("muestra el formulario de calificacion para entrega submitted", async () => {
    setupFetchMock({
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(
      <CorreccionesView comisionId={COMISION_ID} getToken={getToken} />,
    )
    await waitFor(() => {
      expect(screen.getByTestId("entrega-drill-btn")).toBeDefined()
    })
    fireEvent.click(screen.getByTestId("entrega-drill-btn"))
    await waitFor(() => {
      expect(screen.getByTestId("calificar-btn")).toBeDefined()
    })
    expect(screen.getByTestId("nota-final-input")).toBeDefined()
    expect(screen.getByTestId("feedback-input")).toBeDefined()
  })

  it("muestra boton Devolver para entrega graded", async () => {
    const calificacion = {
      id: "d1",
      entrega_id: ENTREGA_ID,
      nota_final: 8,
      feedback_general: "Buen trabajo",
      detalle_criterios: [],
      calificado_at: "2026-05-06T13:00:00Z",
      calificador_id: "docente-1",
    }
    setupFetchMock({
      "/api/v1/entregas": () => ({ data: [mockEntregaGraded], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
      "/calificacion": () => calificacion,
    })
    renderWithRouter(
      <CorreccionesView comisionId={COMISION_ID} getToken={getToken} />,
    )
    await waitFor(() => {
      expect(screen.getByTestId("entrega-drill-btn")).toBeDefined()
    })
    fireEvent.click(screen.getByTestId("entrega-drill-btn"))
    await waitFor(() => {
      expect(screen.getByTestId("devolver-btn")).toBeDefined()
    })
    expect(screen.queryByTestId("calificar-btn")).toBeNull()
  })

  it("boton Volver regresa a la lista", async () => {
    setupFetchMock({
      "/api/v1/entregas": () => ({ data: [mockEntregaSubmitted], meta: { cursor_next: null } }),
      "/api/v1/tareas-practicas/": () => mockTarea,
    })
    renderWithRouter(
      <CorreccionesView comisionId={COMISION_ID} getToken={getToken} />,
    )
    await waitFor(() => {
      expect(screen.getByTestId("entrega-drill-btn")).toBeDefined()
    })
    fireEvent.click(screen.getByTestId("entrega-drill-btn"))
    await waitFor(() => {
      expect(screen.getByTestId("grading-form-view")).toBeDefined()
    })
    // Click en Volver
    const backBtn = screen.getByText(/Volver a entregas/i)
    fireEvent.click(backBtn)
    await waitFor(() => {
      expect(screen.getByTestId("entregas-list-view")).toBeDefined()
    })
  })
})
