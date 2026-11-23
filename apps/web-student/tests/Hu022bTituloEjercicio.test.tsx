/**
 * HU-022 (vuelta 2), C05 d (F30): en una re-entrega cada ejercicio puede
 * tener tres botones (descargar borrador, descargar lo entregado, volver a
 * abrir) y el título quedaba cortado en "E…". El título no se trunca y la fila
 * deja que los botones bajen a otra línea cuando no entran.
 *
 * jsdom no mide layout: se afirma la estructura que lo permite (sin
 * `truncate`, fila con `flex-wrap` y un ancho mínimo para el título). El corte
 * real se mira en navegador en la demo.
 * Prueba propia del constructor (sin aceptación congelada para este punto).
 */
import { ConfirmProvider } from "@platform/ui"
import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ExerciseListView } from "../src/components/ExerciseListView"
import type { AvailableTarea, Entrega, TpEjercicio } from "../src/lib/api"
import { setupFetchMock } from "./_mocks"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const TAREA_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
const EJ1 = "ejejejej-0001-0001-0001-000000000001"

const ENTREGA: Entrega = {
  id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
  tenant_id: "t1",
  tarea_practica_id: TAREA_ID,
  comision_id: COMISION_ID,
  student_pseudonym: "b1b1b1b1-0001-0001-0001-000000000001",
  estado: "returned",
  ejercicio_estados: [
    { ejercicio_id: EJ1, orden: 1, completado: true, episode_id: "ep-1", completado_at: null },
  ],
  submitted_at: "2026-11-20T10:00:00Z",
  created_at: "2026-11-20T09:00:00Z",
  updated_at: "2026-11-21T09:00:00Z",
}

const PARES = [
  {
    id: "pair-1",
    tarea_practica_id: TAREA_ID,
    peso_en_tp: "1.0",
    ejercicio_id: EJ1,
    orden: 1,
    ejercicio: {
      id: EJ1,
      titulo: "Calculadora de presupuesto de hardware",
      enunciado_md: "x",
      inicial_codigo: null,
      unidad_tematica: "secuenciales",
      dificultad: "basica",
      test_cases: [],
    },
  },
] as TpEjercicio[]

const TAREA: AvailableTarea = {
  id: TAREA_ID,
  codigo: "TP01",
  titulo: "Secuenciales",
  enunciado: "x",
  fecha_inicio: null,
  fecha_fin: null,
  peso: "1.0",
  estado: "published",
  version: 1,
  inicial_codigo: null,
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("C05 d · el título del ejercicio no se corta con tres botones", () => {
  it("con los tres botones de la re-entrega, el título queda entero y la fila hace wrap", async () => {
    setupFetchMock({ "/ejercicios": () => PARES, "/api/v1/entregas": () => ENTREGA })
    render(
      <ExerciseListView
        tarea={TAREA}
        comisionId={COMISION_ID}
        onSelectEjercicio={vi.fn()}
        onViewGrade={vi.fn()}
        onBack={vi.fn()}
      />,
      { wrapper: ConfirmProvider },
    )
    const item = await waitFor(() => screen.getByTestId("ejercicio-item-1"))
    // Guarda: el caso es el de los tres botones.
    await waitFor(() => expect(within(item).getAllByRole("button").length).toBe(3))
    const titulo = within(item).getByText(/Calculadora de presupuesto de hardware/)
    expect(titulo.className).not.toMatch(/\btruncate\b/)
    const fila = item.firstElementChild as HTMLElement
    expect(fila.className).toMatch(/\bflex-wrap\b/)
    const bloqueTitulo = titulo.parentElement as HTMLElement
    expect(bloqueTitulo.className).toMatch(/\bbasis-/)
  })
})
