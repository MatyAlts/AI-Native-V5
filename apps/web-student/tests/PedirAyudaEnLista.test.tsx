/**
 * "Pedir ayuda a tu docente" en la lista de ejercicios de la TP
 * (change alumno-pide-ayuda-al-docente). Desde aca el alumno puede pedir
 * aunque no haya episodio (p. ej. el ejercicio no abrio): el modal ofrece
 * elegir el ejercicio, que es opcional.
 */
import { ConfirmProvider } from "@platform/ui"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ExerciseListView } from "../src/components/ExerciseListView"
import type { AvailableTarea, Entrega, TpEjercicio } from "../src/lib/api"

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
      { ejercicio_id: null, orden: 1, completado: false, episode_id: null, completado_at: null },
      { ejercicio_id: null, orden: 2, completado: false, episode_id: null, completado_at: null },
    ],
    submitted_at: null,
    created_at: "2026-05-06T10:00:00Z",
    updated_at: "2026-05-06T10:00:00Z",
    ...overrides,
  }
}

// ADR-047: los ejercicios ya no vienen embebidos en AvailableTarea — la UI
// los resuelve via GET /tareas-practicas/{id}/ejercicios (TpEjercicio[]).
function makePairs(): TpEjercicio[] {
  const base = {
    tarea_practica_id: TAREA_ID,
    peso_en_tp: "0.50",
  }
  return [
    {
      ...base,
      id: "pair-1",
      ejercicio_id: "ejejejej-0001-0001-0001-000000000001",
      orden: 1,
      ejercicio: {
        id: "ejejejej-0001-0001-0001-000000000001",
        titulo: "Suma",
        enunciado_md: "Implementar suma",
        inicial_codigo: null,
        unidad_tematica: "funciones",
        dificultad: "basica",
        test_cases: [],
      },
    },
    {
      ...base,
      id: "pair-2",
      ejercicio_id: "ejejejej-0002-0002-0002-000000000002",
      orden: 2,
      ejercicio: {
        id: "ejejejej-0002-0002-0002-000000000002",
        titulo: "Resta",
        enunciado_md: "Implementar resta",
        inicial_codigo: null,
        unidad_tematica: "funciones",
        dificultad: "basica",
        test_cases: [],
      },
    },
  ]
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
    ...overrides,
  }
}

const llamadas: { url: string; method: string; body: Record<string, unknown> | null }[] = []

function stub() {
  llamadas.length = 0
  const entrega = makeEntrega()
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET"
      llamadas.push({
        url,
        method,
        body: init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null,
      })
      let body: unknown = entrega
      if (url.includes("/pedidos-ayuda/mios")) body = []
      else if (url.includes("/pedidos-ayuda")) body = { id: "p1", estado: "pendiente" }
      else if (url.includes("/ejercicios")) body = makePairs()
      return Promise.resolve({
        ok: true,
        status: method === "POST" && url.includes("/pedidos-ayuda") ? 201 : 200,
        json: () => Promise.resolve(body),
        text: () => Promise.resolve(JSON.stringify(body)),
      } as Response)
    }),
  )
}

function montar() {
  stub()
  render(
    <ExerciseListView
      tarea={makeTarea()}
      comisionId={COMISION_ID}
      onSelectEjercicio={vi.fn()}
      onViewGrade={vi.fn()}
      onBack={vi.fn()}
    />,
    { wrapper: ConfirmProvider },
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("ExerciseListView: pedir ayuda", () => {
  it("el boton esta en el header de la TP", async () => {
    montar()
    await waitFor(() => expect(screen.getByTestId("exercise-list-view")).toBeDefined())
    expect(screen.getByTestId("pedir-ayuda-button")).toBeDefined()
  })

  it("el modal ofrece elegir el ejercicio y el pedido sale con la TP y la entrega", async () => {
    montar()
    await waitFor(() => expect(screen.getByTestId("ejercicios-list")).toBeDefined())

    fireEvent.click(screen.getByTestId("pedir-ayuda-button"))
    const dialogo = within(screen.getByRole("dialog"))
    fireEvent.click(dialogo.getByLabelText(/Error de la plataforma/i))
    fireEvent.change(dialogo.getByLabelText(/En qué ejercicio/i), { target: { value: "2" } })
    fireEvent.click(dialogo.getByRole("button", { name: /^Enviar/i }))

    await waitFor(() => expect(dialogo.getByText(/Tu pedido le llegó a tu docente/i)).toBeDefined())
    const post = llamadas.find((l) => l.method === "POST" && l.url === "/api/v1/pedidos-ayuda")
    expect(post?.body).toMatchObject({
      tarea_practica_id: TAREA_ID,
      entrega_id: ENTREGA_ID,
      ejercicio_orden: 2,
      categoria: "error_plataforma",
      contexto: { pantalla: "lista_ejercicios" },
    })
    expect(post?.body).not.toHaveProperty("episode_id")
  })
})
