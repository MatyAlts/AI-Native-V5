/**
 * Aceptacion HU-041 (orquestador, antes de construir; el constructor no la
 * modifica). Bug que encontro Juani el 25/11.
 *
 * Al tocar desde el campus un TP de un solo ejercicio YA CALIFICADO, se abria
 * un episodio nuevo sobre ese TP (`POST /episodes` 201) y al salir el alumno
 * caia en la home. Tambien pasa en `main`: el "Ver calificacion" del selector
 * viejo llamaba a la misma funcion que abrir el TP. El campus lo dejo a un
 * click: cada tarjeta de TP lleva a abrirlo.
 *
 * Regla: al abrir un TP SIN ejercicios (monolitico) por `/materia/<m>?tareaId=`,
 * se mira la entrega propia del alumno (`GET /entregas?tarea_practica_id=&propias=true`):
 *  - `graded` o `submitted` -> se muestra `GradeDetailView`
 *    (`data-testid="grade-detail-view"`) y NO se abre ningun episodio.
 *  - sin entrega, `draft` o `returned` -> se abre el episodio como siempre.
 *
 * N18  Un TP calificado no abre un episodio nuevo: muestra la calificacion.
 * N19  Un TP entregado y sin corregir tampoco: muestra que espera correccion.
 * C19  Un TP pendiente sigue abriendo su episodio.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { setupFetchMock } from "./_mocks"

const COM = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const MAT = "99999999-9999-9999-9999-999999999999"
const TP = "77777777-7777-7777-7777-777777777777"
const EP = "55555555-5555-5555-5555-555555555555"

const materia = {
  materia_id: MAT,
  codigo: "P2",
  nombre: "Programación 2",
  comision_id: COM,
  comision_codigo: "A",
  comision_nombre: "A",
  horario_resumen: null,
  periodo_id: "p",
  periodo_codigo: "2027-1",
  inscripcion_id: "i",
  fecha_inscripcion: "2027-03-01",
}

const tarea = {
  id: TP,
  comision_id: COM,
  codigo: "TP-02",
  titulo: "Listas enlazadas simples",
  enunciado: "x",
  fecha_inicio: null,
  fecha_fin: null,
  estado: "published",
  unidad_id: null,
  version: 1,
  language: "python",
}

const entrega = (estado: string | null) =>
  estado === null
    ? []
    : [
        {
          id: "ent-1",
          tarea_practica_id: TP,
          comision_id: COM,
          student_pseudonym: "yo",
          estado,
          ejercicio_estados: [],
          submitted_at: "2026-11-25T12:00:00Z",
          nota_final: estado === "graded" ? 8.5 : null,
        },
      ]

function datos(estado: string | null) {
  setupFetchMock({
    "/api/v1/users/me/profile": () => ({ ok: true }),
    "/api/v1/analytics/student/me/episodes": () => ({ episodes: [] }),
    "/api/v1/comisiones/mis": () => ({ data: [] }),
    [`/api/v1/comisiones/${COM}/config-hashes`]: () => ({
      prompt_hash: "p",
      classifier_config_hash: "c",
    }),
    "/api/v1/materias/mias": () => ({ data: [materia] }),
    [`/api/v1/tareas-practicas/${TP}/ejercicios`]: () => [],
    [`/api/v1/tareas-practicas/${TP}`]: () => tarea,
    "/api/v1/tareas-practicas": () => ({ data: [tarea], meta: { cursor_next: null } }),
    "/calificacion": () => ({
      id: "cal",
      entrega_id: "ent-1",
      nota_final: 8.5,
      feedback_general: "Bien",
      detalle_criterios: [],
      graded_at: "2026-11-25T13:00:00Z",
    }),
    "/api/v1/entregas": () => ({ data: entrega(estado), meta: { cursor_next: null } }),
    "/api/v1/episodes": () => ({ episode_id: EP, id: EP }),
  })
}

function abrioEpisodio(): boolean {
  return vi
    .mocked(fetch)
    .mock.calls.some(
      ([u, init]) =>
        String(u).endsWith("/api/v1/episodes") &&
        ((init as RequestInit | undefined)?.method ?? "GET").toUpperCase() === "POST",
    )
}

async function montar() {
  vi.resetModules()
  vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "")
  const { routeTree } = await import("../src/routeTree.gen")
  const { ConfirmProvider } = await import("@platform/ui")
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [`/materia/${MAT}?tareaId=${TP}`] }),
    context: { getToken: async () => null },
  })
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <ConfirmProvider>
        <RouterProvider router={router} />
      </ConfirmProvider>
    </QueryClientProvider>,
  )
  return router
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn()
  window.sessionStorage.clear()
  window.localStorage.setItem("onboarding-alumno-visto", "1")
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  window.localStorage.clear()
})

describe("HU-041 · un TP ya entregado no se vuelve a abrir", () => {
  it("N18: calificado -> muestra la calificacion y no abre episodio", async () => {
    datos("graded")
    await montar()
    expect(await screen.findByTestId("grade-detail-view", {}, { timeout: 4000 })).toBeTruthy()
    await new Promise((r) => setTimeout(r, 300))
    expect(abrioEpisodio()).toBe(false)
  })

  it("N19: entregado sin corregir -> muestra que espera correccion y no abre episodio", async () => {
    datos("submitted")
    await montar()
    expect(await screen.findByTestId("grade-detail-view", {}, { timeout: 4000 })).toBeTruthy()
    await new Promise((r) => setTimeout(r, 300))
    expect(abrioEpisodio()).toBe(false)
  })

  it("C19: pendiente -> abre el episodio como siempre", async () => {
    datos(null)
    await montar()
    await waitFor(() => expect(abrioEpisodio()).toBe(true), { timeout: 4000 })
  })
})
