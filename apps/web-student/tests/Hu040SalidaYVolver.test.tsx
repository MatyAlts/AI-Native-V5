/**
 * Aceptacion HU-040 (orquestador, antes de construir; el constructor no la
 * modifica). Observaciones de la recorrida como alumno del 25/11 (vienen de
 * `main`), que Juani pidio arreglar en una historia nueva.
 *
 * 1. Despues de salir de un ejercicio, "atras" en el navegador volvia al
 *    episodio pausado y lo reanudaba. Y al salir de nuevo (sin el contexto
 *    del ejercicio en sessionStorage) iba a la home en vez de al TP.
 * 2. "Mis notas" y "Mi progreso" tenian "Volver a mis materias" a la home y
 *    el ancho angosto viejo (`max-w-3xl`).
 *
 * Contrato:
 *  - `destinoSalidaEjercicio(ctx, estado, materias)` en
 *    `src/lib/entregaAlSalir.ts`, pura:
 *      ctx = { materiaId, tareaId } | null  (contexto del ejercicio)
 *      estado = { tarea_practica_id, comision_id, ejercicio_orden } | null
 *      materias = [{ materia_id, comision_id }]
 *    Con ctx -> { to: "/materia/$id", params: { id: ctx.materiaId },
 *    search: { tareaId: ctx.tareaId }, replace: true }.
 *    Sin ctx pero con un episodio de ejercicio (`ejercicio_orden` no null) y
 *    su materia encontrada por `comision_id` -> lo mismo con
 *    `estado.tarea_practica_id`. Si no (TP de un solo ejercicio, o sin datos)
 *    -> null (sigue el camino de la entrega de siempre).
 *  - `routes/episodio.$id.tsx` la usa al salir y navega con `replace: true`
 *    (la salida reemplaza la entrada del episodio en el historial).
 *  - `/mis-notas` y `/progreso`: con `?comisionId=` el link de volver dice
 *    "Volver al curso" y va a `/curso/<comisionId>`; sin comisionId dice
 *    "Volver a Mis cursos" y va a `/`. Sin contenedor `max-w-3xl`.
 *
 * C17  Salir de un ejercicio vuelve a su TP y no deja el episodio en el
 *      historial.
 * N17  Entrar al episodio sin contexto y salir no manda a la home si el
 *      episodio es de un ejercicio.
 * C18  Mis notas y Mi progreso vuelven al curso y usan todo el ancho.
 */
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router"
import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { destinoSalidaEjercicio } from "../src/lib/entregaAlSalir"
import { setupFetchMock } from "./_mocks"

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..")
const COM = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const MAT = "99999999-9999-9999-9999-999999999999"
const TP = "77777777-7777-7777-7777-777777777777"
const materias = [{ materia_id: MAT, comision_id: COM }]

describe("HU-040 · a donde vuelve el alumno al salir de un ejercicio", () => {
  it("C17: con el contexto del ejercicio vuelve a su TP, reemplazando el historial", () => {
    expect(destinoSalidaEjercicio({ materiaId: MAT, tareaId: TP }, null, materias)).toEqual({
      to: "/materia/$id",
      params: { id: MAT },
      search: { tareaId: TP },
      replace: true,
    })
  })

  it("N17: sin contexto, si el episodio es de un ejercicio, vuelve a su TP", () => {
    const estado = { tarea_practica_id: TP, comision_id: COM, ejercicio_orden: 101 }
    expect(destinoSalidaEjercicio(null, estado, materias)).toEqual({
      to: "/materia/$id",
      params: { id: MAT },
      search: { tareaId: TP },
      replace: true,
    })
  })

  it("N17: un TP de un solo ejercicio o sin datos sigue el camino de siempre", () => {
    const monolitico = { tarea_practica_id: TP, comision_id: COM, ejercicio_orden: null }
    expect(destinoSalidaEjercicio(null, monolitico, materias)).toBeNull()
    expect(destinoSalidaEjercicio(null, null, materias)).toBeNull()
    const otraComision = { tarea_practica_id: TP, comision_id: "x", ejercicio_orden: 1 }
    expect(destinoSalidaEjercicio(null, otraComision, materias)).toBeNull()
  })

  it("C17: la ruta del episodio usa la regla y reemplaza el historial al salir", () => {
    const ruta = readFileSync(join(RAIZ, "src/routes/episodio.$id.tsx"), "utf-8")
    expect(ruta).toContain("destinoSalidaEjercicio(")
    // Toda navegacion de salida reemplaza la entrada del episodio.
    const navegaciones = ruta.match(/navigate\(/g) ?? []
    const conReplace = ruta.match(/replace:\s*true/g) ?? []
    expect(navegaciones.length).toBeGreaterThan(0)
    expect(conReplace.length).toBeGreaterThanOrEqual(navegaciones.length)
  })
})

// ── Mis notas y Mi progreso ─────────────────────────────────────────────

function datos() {
  setupFetchMock({
    "/api/v1/users/me/profile": () => ({ ok: true }),
    "/api/v1/analytics/student/me/episodes": () => ({ episodes: [] }),
    "/api/v1/comisiones/mis": () => ({ data: [] }),
    "/api/v1/materias/mias": () => ({
      data: [
        {
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
        },
      ],
    }),
    "/api/v1/entregas": () => ({ data: [], meta: { cursor_next: null } }),
  })
}

async function montar(inicial: string) {
  vi.resetModules()
  vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "")
  const { routeTree } = await import("../src/routeTree.gen")
  const { ConfirmProvider } = await import("@platform/ui")
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [inicial] }),
    context: { getToken: async () => null },
  })
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const r = render(
    <QueryClientProvider client={qc}>
      <ConfirmProvider>
        <RouterProvider router={router} />
      </ConfirmProvider>
    </QueryClientProvider>,
  )
  return r
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

describe("HU-040 · Mis notas y Mi progreso vuelven al curso", () => {
  for (const ruta of ["/mis-notas", "/progreso"]) {
    it(`C18: ${ruta} con curso vuelve al curso y usa todo el ancho`, async () => {
      const { container } = await montar(`${ruta}?comisionId=${COM}`)
      const volver = await screen.findByRole("link", { name: /Volver al curso/ }, { timeout: 4000 })
      expect(volver.getAttribute("href")).toBe(`/curso/${COM}`)
      expect(screen.queryByText(/Volver a mis materias/)).toBeNull()
      expect(container.querySelector(".max-w-3xl")).toBeNull()
    })

    it(`C18: ${ruta} sin curso vuelve a Mis cursos`, async () => {
      await montar(ruta)
      const volver = await screen.findByRole(
        "link",
        { name: /Volver a Mis cursos/ },
        { timeout: 4000 },
      )
      expect(volver.getAttribute("href")).toBe("/")
    })
  }
})
