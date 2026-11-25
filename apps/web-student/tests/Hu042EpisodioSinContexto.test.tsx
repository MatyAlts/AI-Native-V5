/**
 * Aceptación HU-042 (orquestador, antes de construir; el constructor no la
 * modifica). Un episodio de ejercicio retomado SIN contexto local.
 *
 * Hoy el contexto del ejercicio (entrega, ejercicio, orden) vive solo en
 * sessionStorage (`active-exercise-context`). Si el alumno retoma el episodio
 * en otra pestaña o después de reiniciar el navegador, ese contexto no está y
 * `EpisodePage.markEjercicioCompletedOnce` hace `if (!ejercicioContext) return`:
 * el ejercicio NO queda completado al cerrar; la consigna muestra el enunciado
 * del TP y no el del ejercicio; y la pantalla de cierre dice "Volver a mis
 * materias". El servidor SÍ lo sabe: `GET /api/v1/episodes/{id}` devuelve
 * `ejercicio_id`, `ejercicio_orden` y `tarea_practica_id`, y la entrega propia
 * del alumno sale de `GET /api/v1/entregas?...&propias=true`.
 *
 * Se monta la RUTA real `/episodio/<id>` (router en memoria, como Hu040/Hu041)
 * con sessionStorage vacío, así el arreglo puede vivir en la ruta o en
 * `EpisodeView`, indistinto.
 *
 * C03  Sin contexto local, con el estado del episodio diciendo el ejercicio y
 *      una entrega propia en `draft`:
 *      - al cerrar el episodio (con código escrito) se llama UNA vez a
 *        `PATCH /api/v1/entregas/<entregaId>/ejercicio/<orden>` con
 *        `completado: true`, `episode_id` y `ejercicio_id` del episodio;
 *      - la consigna muestra el enunciado del EJERCICIO, no el del TP.
 * C05  La pantalla de cierre (después de saltear la reflexión) ofrece volver
 *      al TP ("Volver al TP" o "Siguiente ejercicio") y nunca "Volver a mis
 *      materias". También si la clasificación falla (pantalla de respaldo).
 *
 * Mocks de fetch por prefijo (`setupFetchMock`): la entrega se sirve tanto
 * por la lista (`/api/v1/entregas?`) como por id (`/api/v1/entregas/<id>`).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router"
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { setupFetchMock } from "./_mocks"

// La ruta entera hidrata, cierra y clasifica: más que los 5 s por omisión.
vi.setConfig({ testTimeout: 20000 })

const COM = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const MAT = "99999999-9999-9999-9999-999999999999"
const TP = "77777777-7777-7777-7777-777777777777"
const EP = "55555555-5555-5555-5555-555555555555"
const ENT = "44444444-4444-4444-4444-444444444444"
const EJ1 = "11111111-0000-0000-0000-000000000001"
const EJ2 = "11111111-0000-0000-0000-000000000002"
const ORDEN = 1

const ENUNCIADO_TP = "Consigna general del TP de secuenciales zq."
const ENUNCIADO_EJ = "Leé dos números y mostrá su suma kx."

const materia = {
  materia_id: MAT,
  codigo: "P1",
  nombre: "Programación 1",
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
  codigo: "TP-01",
  titulo: "Secuenciales",
  enunciado: ENUNCIADO_TP,
  fecha_inicio: null,
  fecha_fin: null,
  peso: "1.00",
  estado: "published",
  unidad_id: null,
  version: 1,
  inicial_codigo: null,
  language: "pseint",
  permite_pausa: true,
  test_cases: [],
}

const ejercicio = (id: string, orden: number, titulo: string, enunciado: string) => ({
  id: `tpe-${orden}`,
  tarea_practica_id: TP,
  ejercicio_id: id,
  orden,
  peso_en_tp: "1.00",
  ejercicio: {
    id,
    titulo,
    enunciado_md: enunciado,
    enunciado,
    language: "pseint",
    inicial_codigo: null,
    test_cases: [],
  },
})

const entregaDraft = {
  id: ENT,
  tarea_practica_id: TP,
  comision_id: COM,
  student_pseudonym: "yo",
  estado: "draft",
  ejercicio_estados: [],
  submitted_at: null,
  nota_final: null,
}

// Editores creados por el doble de Monaco de la ruta montada (ver `montar`).
let editores: { __tipear(texto: string): void }[] = []

type Llamada = { url: string; method: string; body: string }

function datos(opciones: { classifyFalla?: boolean } = {}): Llamada[] {
  setupFetchMock({
    "/api/v1/users/me/profile": () => ({ ok: true }),
    "/api/v1/analytics/student/me/episodes": () => ({ episodes: [] }),
    "/api/v1/comisiones/mis": () => ({ data: [] }),
    "/api/v1/materias/mias": () => ({ data: [materia] }),
    [`/api/v1/entregas/${ENT}/ejercicio/`]: () => ({ ...entregaDraft }),
    [`/api/v1/entregas/${ENT}`]: () => ({ ...entregaDraft }),
    "/api/v1/entregas": () => ({ data: [{ ...entregaDraft }], meta: { cursor_next: null } }),
    [`/api/v1/episodes/${EP}/close`]: () => ({ ok: true }),
    [`/api/v1/episodes/${EP}/resume`]: () => ({ ok: true, episode_id: EP }),
    [`/api/v1/classify_episode/${EP}`]: () => {
      if (opciones.classifyFalla) throw new Error("classifier caido")
      return { appropriation: "apropiacion_reflexiva", features: {} }
    },
    [`/api/v1/episodes/${EP}`]: () => ({
      episode_id: EP,
      tarea_practica_id: TP,
      comision_id: COM,
      estado: "open",
      opened_at: "2026-11-25T10:00:00Z",
      closed_at: null,
      last_code_snapshot: null,
      messages: [],
      notes: [],
      ejercicio_id: EJ1,
      ejercicio_orden: ORDEN,
    }),
    [`/api/v1/tareas-practicas/${TP}/ejercicios`]: () => [
      ejercicio(EJ1, 1, "Suma", ENUNCIADO_EJ),
      ejercicio(EJ2, 2, "Resta", "Leé dos números y mostrá su resta."),
    ],
    [`/api/v1/tareas-practicas/${TP}`]: () => tarea,
  })
  const llamadas: Llamada[] = []
  const stub = globalThis.fetch
  vi.stubGlobal("fetch", (url: string | URL | Request, init?: RequestInit) => {
    llamadas.push({
      url: typeof url === "string" ? url : url.toString(),
      method: (init?.method ?? "GET").toUpperCase(),
      body: String(init?.body ?? ""),
    })
    return (stub as typeof fetch)(url as never, init)
  })
  return llamadas
}

async function montar() {
  vi.resetModules()
  vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "")
  const { routeTree } = await import("../src/routeTree.gen")
  const { ConfirmProvider } = await import("@platform/ui")
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [`/episodio/${EP}`] }),
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
  // `vi.resetModules()` deja una instancia nueva del doble de Monaco: la que
  // usa la ruta montada es la que se importa DESPUES de montar.
  const monaco = await import("./_monacoMock")
  editores = monaco.editoresCreados
  return router
}

const patches = (ll: Llamada[]) =>
  ll.filter((l) => l.method === "PATCH" && l.url.includes("/ejercicio/"))

async function escribirYCerrar() {
  await waitFor(() => expect(editores.length).toBeGreaterThanOrEqual(1), { timeout: 4000 })
  // Esperar a que termine la hidratación (el botón de cerrar habilitado).
  const cerrar = await screen.findByTestId("close-episode-button", {}, { timeout: 4000 })
  await waitFor(() => expect((cerrar as HTMLButtonElement).disabled).toBe(false))
  await act(async () => {
    editores[editores.length - 1]?.__tipear('Algoritmo suma\n\tEscribir "hola"\nFinAlgoritmo')
  })
  await act(async () => {
    fireEvent.click(cerrar)
  })
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn()
  editores = []
  // Sin contexto local: otra pestaña o navegador reiniciado.
  window.sessionStorage.clear()
  window.localStorage.clear()
  window.localStorage.setItem("onboarding-alumno-visto", "1")
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  window.localStorage.clear()
  window.sessionStorage.clear()
})

describe("HU-042 C03 · episodio de ejercicio retomado sin contexto local", () => {
  it("al cerrar marca el ejercicio completado en la entrega propia", async () => {
    const llamadas = datos()
    await montar()
    await escribirYCerrar()
    await waitFor(
      () => expect(llamadas.some((l) => l.url.includes(`/classify_episode/${EP}`))).toBe(true),
      { timeout: 4000 },
    )
    await waitFor(() => expect(patches(llamadas)).toHaveLength(1), { timeout: 4000 })
    const p = patches(llamadas)[0]!
    expect(p.url).toContain(`/api/v1/entregas/${ENT}/ejercicio/${ORDEN}`)
    expect(JSON.parse(p.body)).toMatchObject({
      completado: true,
      episode_id: EP,
      ejercicio_id: EJ1,
    })
  })

  it("la consigna muestra el enunciado del ejercicio, no el del TP", async () => {
    datos()
    await montar()
    expect(await screen.findByText(/mostrá su suma kx/, {}, { timeout: 4000 })).toBeTruthy()
    expect(screen.queryByText(/Consigna general del TP de secuenciales zq/)).toBeNull()
  })
})

describe("HU-042 C05 · el cierre ofrece volver al TP, nunca a mis materias", () => {
  it("con clasificación: Volver al TP / Siguiente ejercicio", async () => {
    datos()
    await montar()
    await escribirYCerrar()
    const saltar = await screen.findByRole(
      "button",
      { name: /no quiero reflexionar/i },
      { timeout: 4000 },
    )
    await act(async () => {
      fireEvent.click(saltar)
    })
    // Primero llegar a la pantalla de cierre; recién ahí se mira el botón.
    expect(
      (await screen.findAllByText(/Cierre del ejercicio/, {}, { timeout: 4000 })).length,
    ).toBeGreaterThan(0)
    expect(
      await screen.findByRole(
        "button",
        { name: /Volver al TP|Siguiente ejercicio/ },
        { timeout: 4000 },
      ),
    ).toBeTruthy()
    expect(screen.queryByText(/Volver a mis materias/)).toBeNull()
  })

  it("si la clasificación falla, la pantalla de respaldo tampoco manda a mis materias", async () => {
    datos({ classifyFalla: true })
    await montar()
    await escribirYCerrar()
    const saltar = await screen.findByRole(
      "button",
      { name: /no quiero reflexionar/i },
      { timeout: 4000 },
    )
    await act(async () => {
      fireEvent.click(saltar)
    })
    // Primero llegar a la pantalla de cierre; recién ahí se mira el botón.
    expect(
      (await screen.findAllByText(/Cierre del ejercicio/, {}, { timeout: 4000 })).length,
    ).toBeGreaterThan(0)
    expect(
      await screen.findByRole(
        "button",
        { name: /Volver al TP|Siguiente ejercicio/ },
        { timeout: 4000 },
      ),
    ).toBeTruthy()
    expect(screen.queryByText(/Volver a mis materias/)).toBeNull()
  })
})
