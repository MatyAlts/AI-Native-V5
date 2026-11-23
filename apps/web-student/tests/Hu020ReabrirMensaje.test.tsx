/**
 * HU-020, prueba de apoyo del constructor (no es la aceptacion).
 *
 * Carrera: la lista se dibujo antes del vencimiento, el alumno toca "Volver a
 * abrir" y el servidor responde 409 por plazo. Antes leia "No se pudo reabrir
 * el ejercicio 1: Error: reabrir ejercicio failed: 409". Tiene que leer el
 * texto del servidor, sin codigos.
 */
import { ConfirmProvider } from "@platform/ui"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ExerciseListView } from "../src/components/ExerciseListView"
import type { AvailableTarea, Entrega, TpEjercicio } from "../src/lib/api"
import { setupFetchMock } from "./_mocks"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const TAREA_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
const IDS = ["ejejejej-0001-0001-0001-000000000001", "ejejejej-0002-0002-0002-000000000002"]
const DETALLE = "Venció el plazo de esta TP: ya no se puede reabrir el ejercicio."
const FUTURO = new Date(Date.now() + 3 * 86400_000).toISOString()

const entrega: Entrega = {
  id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
  tenant_id: "t1",
  tarea_practica_id: TAREA_ID,
  comision_id: COMISION_ID,
  student_pseudonym: "b1b1b1b1-0001-0001-0001-000000000001",
  estado: "draft",
  ejercicio_estados: IDS.map((id, i) => ({
    ejercicio_id: id,
    orden: i + 1,
    completado: true,
    episode_id: `epepepep-000${i + 1}-0001-0001-00000000000${i + 1}`,
    completado_at: null,
  })),
  submitted_at: null,
  created_at: "2026-11-23T10:00:00Z",
  updated_at: "2026-11-23T10:00:00Z",
} as Entrega

const pairs: TpEjercicio[] = IDS.map((id, i) => ({
  id: `pair-${i + 1}`,
  tarea_practica_id: TAREA_ID,
  peso_en_tp: "1.0",
  ejercicio_id: id,
  orden: i + 1,
  ejercicio: {
    id,
    titulo: `Ej ${i + 1}`,
    enunciado_md: "x",
    inicial_codigo: null,
    unidad_tematica: "secuenciales",
    dificultad: "basica" as const,
    test_cases: [],
  },
}))

const tarea: AvailableTarea = {
  id: TAREA_ID,
  codigo: "VERIF",
  titulo: "TP",
  enunciado: "x",
  fecha_inicio: null,
  // La lista se dibuja "dentro del plazo"; el servidor ya lo ve vencido.
  fecha_fin: FUTURO,
  peso: "1.0",
  estado: "published",
  version: 1,
  inicial_codigo: null,
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe("HU-020 · el 409 al reabrir se lee en palabras del servidor", () => {
  it("muestra el detail del servidor, sin codigos ni 'failed'", async () => {
    setupFetchMock({
      "/ejercicio/": { ok: false, status: 409, body: () => ({ detail: DETALLE }) },
      "/ejercicios": () => pairs,
      "/api/v1/entregas": () => entrega,
    })
    render(
      <ExerciseListView
        tarea={tarea}
        comisionId={COMISION_ID}
        onSelectEjercicio={vi.fn()}
        onViewGrade={vi.fn()}
        onBack={vi.fn()}
      />,
      { wrapper: ConfirmProvider },
    )

    await waitFor(() => expect(screen.getByTestId("ejercicio-reabrir-1")).toBeDefined())
    fireEvent.click(screen.getByTestId("ejercicio-reabrir-1"))

    await waitFor(() => expect(screen.getByText(DETALLE)).toBeDefined())
    expect(screen.queryByText(/409|failed|Error:/)).toBeNull()
  })
})
