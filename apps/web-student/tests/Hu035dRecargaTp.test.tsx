/**
 * Aceptacion HU-035, regresion (orquestador, antes de arreglar; el constructor
 * no la modifica). Bug que encontro Juani el 25/11.
 *
 * Desde el campus, cada TP lleva a `/materia/<materia>?tareaId=<tp>`. La
 * pagina abria el TP y SACABA `tareaId` de la URL; al recargar quedaba
 * `/materia/<materia>` sola y el alumno caia en la pantalla vieja de la
 * materia (selector de unidades con "#0", "#1"), que con el campus no tiene
 * que verse.
 *
 * Contrato:
 *  - Con `?tareaId=` de un TP CON ejercicios, la URL conserva `tareaId`
 *    mientras se ve la lista de ejercicios: recargar vuelve al mismo TP.
 *    (Para un TP de un solo ejercicio, que abre el episodio enseguida, se
 *    puede sacar antes de ir al episodio, como hoy.)
 *  - `/materia/<materia>` sin `tareaId` ni `returnToExercise` lleva al campus
 *    del curso: `/curso/<comision_id>` (replace). La pantalla vieja de
 *    unidades no se muestra.
 *
 * N15  Recargar un TP abierto desde el campus vuelve al mismo TP.
 * N16  La materia sola no muestra la pantalla vieja: va al campus.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { setupFetchMock } from "./_mocks"

const COM = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const MAT = "99999999-9999-9999-9999-999999999999"
const TP = "77777777-7777-7777-7777-777777777777"
const U1 = "11111111-1111-1111-1111-111111111111"

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
  codigo: "SEC-2027",
  titulo: "Secuenciales 2027",
  enunciado: "x",
  fecha_inicio: null,
  fecha_fin: null,
  estado: "published",
  unidad_id: U1,
  version: 1,
  language: "python",
}

const ejercicioTp = (id: string, orden: number, titulo: string) => ({
  id,
  tarea_practica_id: TP,
  ejercicio_id: `x${orden}`,
  orden,
  peso_en_tp: "0.5",
  ejercicio: {
    id: `x${orden}`,
    titulo,
    enunciado_md: "x",
    inicial_codigo: null,
    test_cases: [],
    tags: [],
    language: "python",
    unidad_tematica: null,
    dificultad: null,
  },
})

function datos() {
  setupFetchMock({
    "/api/v1/users/me/profile": () => ({ ok: true }),
    "/api/v1/analytics/student/me/episodes": () => ({ episodes: [] }),
    "/api/v1/comisiones/mis": () => ({ data: [] }),
    "/api/v1/materias/mias": () => ({ data: [materia] }),
    [`/api/v1/tareas-practicas/${TP}/ejercicios`]: () => [
      ejercicioTp("e1", 1, "Hola"),
      ejercicioTp("e2", 2, "Chau"),
    ],
    [`/api/v1/tareas-practicas/${TP}`]: () => tarea,
    "/api/v1/tareas-practicas": () => ({ data: [tarea], meta: { cursor_next: null } }),
    "/api/v1/unidades": () => ({
      data: [{ id: U1, comision_id: COM, nombre: "Unidad 1", descripcion: null, orden: 0 }],
      meta: { cursor_next: null },
    }),
    "/api/v1/entregas": () => ({
      id: "ent",
      tarea_practica_id: TP,
      comision_id: COM,
      estado: "draft",
      ejercicio_estados: [
        { orden: 1, completado: false },
        { orden: 2, completado: false },
      ],
      nota_final: null,
      data: [],
      meta: { cursor_next: null },
    }),
  })
}

async function montar(inicial: string) {
  vi.resetModules()
  vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "")
  const { routeTree } = await import("../src/routeTree.gen")
  // Despues de resetModules: el provider tiene que ser de la misma copia de
  // @platform/ui que usan las paginas.
  const { ConfirmProvider } = await import("@platform/ui")
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [inicial] }),
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
  datos()
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  window.localStorage.clear()
})

describe("HU-035 · recargar un TP abierto desde el campus", () => {
  it("N15: la URL conserva tareaId mientras se ve el TP", async () => {
    const router = await montar(`/materia/${MAT}?tareaId=${TP}`)
    expect(await screen.findByText(/Ejercicios completados/, {}, { timeout: 4000 })).toBeTruthy()
    // Dejamos correr efectos: la URL no tiene que perder el TP.
    await new Promise((r) => setTimeout(r, 300))
    expect(router.state.location.pathname).toBe(`/materia/${MAT}`)
    expect((router.state.location.search as { tareaId?: string }).tareaId).toBe(TP)
  })

  it("N16: la materia sola lleva al campus y no muestra la pantalla vieja", async () => {
    const router = await montar(`/materia/${MAT}`)
    await waitFor(() => expect(router.state.location.pathname).toBe(`/curso/${COM}`), {
      timeout: 4000,
    })
    expect(screen.queryByText(/Elegí una unidad para ver los trabajos prácticos/)).toBeNull()
  })
})
