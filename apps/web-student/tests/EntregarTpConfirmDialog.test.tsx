/**
 * QA 08/10 #15: "Entregar TP" confirma con el ConfirmDialog del DS, no con
 * window.confirm nativo.
 */
import { ConfirmProvider } from "@platform/ui"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ExerciseListView } from "../src/components/ExerciseListView"
import type { AvailableTarea, Entrega, TpEjercicio } from "../src/lib/api"

const TAREA_ID = "tarea-cf"
const ENTREGA_ID = "entrega-cf"
const estados = [1, 2].map((orden) => ({
  ejercicio_id: null,
  orden,
  completado: true,
  episode_id: `ep-${orden}`,
  completado_at: "2026-05-06T11:00:00Z",
}))
const entrega = {
  id: ENTREGA_ID,
  tenant_id: "t1",
  tarea_practica_id: TAREA_ID,
  comision_id: "com",
  student_pseudonym: "p",
  estado: "draft",
  ejercicio_estados: estados,
  submitted_at: null,
  created_at: "2026-05-06T10:00:00Z",
  updated_at: "2026-05-06T10:00:00Z",
} as unknown as Entrega
const pairs = [1, 2].map((orden) => ({
  id: `pair-${orden}`,
  tarea_practica_id: TAREA_ID,
  ejercicio_id: `ej-${orden}`,
  orden,
  peso_en_tp: "0.50",
  ejercicio: {
    id: `ej-${orden}`,
    titulo: `E${orden}`,
    enunciado_md: "x",
    inicial_codigo: null,
    unidad_tematica: "u",
    dificultad: "basica",
    test_cases: [],
  },
})) as unknown as TpEjercicio[]
const tarea = {
  id: TAREA_ID,
  codigo: "TP",
  titulo: "TP",
  enunciado: "x",
  fecha_inicio: null,
  fecha_fin: null,
  peso: "1.0",
  estado: "published",
  version: 1,
  inicial_codigo: null,
} as AvailableTarea

type Llamada = { url: string; method: string }

function montar() {
  const llamadas: Llamada[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string | URL | Request, init?: RequestInit) => {
      const u = typeof url === "string" ? url : url.toString()
      llamadas.push({ url: u, method: init?.method ?? "GET" })
      const body = u.includes("/ejercicios") ? pairs : entrega
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(body),
        text: () => Promise.resolve(JSON.stringify(body)),
      } as Response)
    }),
  )
  render(
    <ConfirmProvider>
      <ExerciseListView
        tarea={tarea}
        comisionId="com"
        onSelectEjercicio={vi.fn()}
        onViewGrade={vi.fn()}
        onBack={vi.fn()}
      />
    </ConfirmProvider>,
  )
  return llamadas
}
const submits = (ll: Llamada[]) =>
  ll.filter((l) => l.method === "POST" && l.url.includes("/submit"))

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("Entregar TP usa ConfirmDialog", () => {
  it("abre el dialogo del DS y NO llama a window.confirm; cancelar no entrega", async () => {
    const nativo = vi.spyOn(window, "confirm").mockReturnValue(true)
    const ll = montar()
    fireEvent.click(await screen.findByTestId("submit-entrega-btn"))
    expect(await screen.findByText(/tu docente sera notificado/)).toBeDefined()
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }))
    await waitFor(() => expect(screen.queryByText(/tu docente sera notificado/)).toBeNull())
    expect(nativo).not.toHaveBeenCalled()
    expect(submits(ll)).toHaveLength(0)
  })

  it("confirmar en el dialogo dispara el submit", async () => {
    const nativo = vi.spyOn(window, "confirm").mockReturnValue(false)
    const ll = montar()
    fireEvent.click(await screen.findByTestId("submit-entrega-btn"))
    await screen.findByText(/tu docente sera notificado/)
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }))
    await waitFor(() => expect(submits(ll)).toHaveLength(1))
    expect(nativo).not.toHaveBeenCalled()
  })
})
