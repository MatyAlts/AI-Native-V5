/**
 * Devolucion PARCIAL ("Pedir corrección"): el docente reabre solo algunos
 * ejercicios (change publicar-nota-y-pedir-correccion, D5/D6).
 */
import { ConfirmProvider } from "@platform/ui"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ExerciseListView } from "../src/components/ExerciseListView"
import type { AvailableTarea, Entrega, TpEjercicio } from "../src/lib/api"
import { setupFetchMock } from "./_mocks"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const TAREA_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
const IDS = [
  "ejejejej-0001-0001-0001-000000000001",
  "ejejejej-0002-0002-0002-000000000002",
  "ejejejej-0003-0003-0003-000000000003",
]

function estados(spec: Array<{ c: boolean; marca?: boolean }>) {
  return spec.map((s, i) => ({
    ejercicio_id: IDS[i] ?? null,
    orden: i + 1,
    completado: s.c,
    episode_id: `epepepep-000${i + 1}-0001-0001-00000000000${i + 1}`,
    completado_at: null,
    ...(s.marca === undefined ? {} : { reabierto_por_docente: s.marca }),
  }))
}

function makeEntrega(spec: Array<{ c: boolean; marca?: boolean }>): Entrega {
  return {
    id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
    tenant_id: "t1",
    tarea_practica_id: TAREA_ID,
    comision_id: COMISION_ID,
    student_pseudonym: "b1b1b1b1-0001-0001-0001-000000000001",
    estado: "returned",
    ejercicio_estados: estados(spec),
    submitted_at: null,
    created_at: "2026-05-06T10:00:00Z",
    updated_at: "2026-05-06T10:00:00Z",
  }
}

function makePairs(): TpEjercicio[] {
  return IDS.map((id, i) => ({
    id: `pair-${i + 1}`,
    tarea_practica_id: TAREA_ID,
    peso_en_tp: "0.33",
    ejercicio_id: id,
    orden: i + 1,
    ejercicio: {
      id,
      titulo: `Ej ${i + 1}`,
      enunciado_md: "x",
      inicial_codigo: null,
      unidad_tematica: "funciones",
      dificultad: "basica" as const,
      test_cases: [],
    },
  }))
}

const tarea: AvailableTarea = {
  id: TAREA_ID,
  codigo: "TP01",
  titulo: "TP",
  enunciado: "x",
  fecha_inicio: null,
  fecha_fin: null,
  peso: "1.0",
  estado: "published",
  version: 1,
  inicial_codigo: null,
}

function montar(entrega: Entrega) {
  setupFetchMock({
    "/ejercicios": () => makePairs(),
    "/api/v1/entregas": () => entrega,
  })
  return render(
    <ExerciseListView
      tarea={tarea}
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
  vi.restoreAllMocks()
})

describe("devolucion parcial en la lista de ejercicios", () => {
  it("el reabierto tiene badge 'A corregir' y empezar; los demas no tienen 'Volver a abrir'", async () => {
    montar(
      makeEntrega([
        { c: true, marca: false },
        { c: false, marca: true },
        { c: true, marca: false },
      ]),
    )
    await waitFor(() => expect(screen.getByTestId("ejercicios-list")).toBeDefined())

    expect(screen.getByTestId("ejercicio-a-corregir-2")).toBeDefined()
    expect(screen.queryByTestId("ejercicio-a-corregir-1")).toBeNull()
    expect(screen.queryByTestId("ejercicio-a-corregir-3")).toBeNull()
    expect(screen.getByTestId("ejercicio-start-2")).toBeDefined()
    expect(screen.queryByTestId("ejercicio-reabrir-1")).toBeNull()
    expect(screen.queryByTestId("ejercicio-reabrir-3")).toBeNull()
  })

  it("los completados quedan sin bloqueo visible aunque el 2 este pendiente", async () => {
    montar(
      makeEntrega([
        { c: true, marca: false },
        { c: false, marca: true },
        { c: true, marca: false },
      ]),
    )
    await waitFor(() => expect(screen.getByTestId("ejercicios-list")).toBeDefined())
    expect(screen.queryByText(/Completar ejercicio anterior primero/)).toBeNull()
  })

  it("un reabierto posterior espera al reabierto anterior", async () => {
    montar(
      makeEntrega([
        { c: false, marca: true },
        { c: true, marca: false },
        { c: false, marca: true },
      ]),
    )
    await waitFor(() => expect(screen.getByTestId("ejercicios-list")).toBeDefined())
    expect(screen.getByTestId("ejercicio-start-1")).toBeDefined()
    expect(screen.queryByTestId("ejercicio-start-3")).toBeNull()
    expect(screen.getByText(/Completar ejercicio anterior primero/)).toBeDefined()
  })

  it("legacy sin marcas: como hoy (Volver a abrir en completados, sin badge)", async () => {
    montar(makeEntrega([{ c: true }, { c: true }, { c: false }]))
    await waitFor(() => expect(screen.getByTestId("ejercicios-list")).toBeDefined())
    expect(screen.getByTestId("ejercicio-reabrir-1")).toBeDefined()
    expect(screen.getByTestId("ejercicio-reabrir-2")).toBeDefined()
    expect(screen.queryByTestId("ejercicio-a-corregir-3")).toBeNull()
  })
})
