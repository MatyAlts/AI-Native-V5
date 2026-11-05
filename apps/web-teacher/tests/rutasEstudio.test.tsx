// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
/**
 * Las dos rutas del menu que el change reutiliza (design D13) montan las vistas
 * del estudio y no las del piloto. Router REAL (`routeTree.gen`), modo completo,
 * docente sin membresia: las dos secciones muestran el aviso y el enlace al
 * acuerdo del piloto, y ninguna pide datos del piloto (sample, ratings, eventos
 * crudos del CTR).
 */
import { ConfirmProvider } from "@platform/ui"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router"
import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { routeTree } from "../src/routeTree.gen"
import { setupFetchMock } from "./_mocks"

function montar(ruta: string) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [ruta] }),
    context: { getToken: async () => null, modoAcceso: "completo" },
  })
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <ConfirmProvider>
        <RouterProvider router={router} />
      </ConfirmProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  window.localStorage.setItem("tour:docente-v1", "visto")
  setupFetchMock({
    "/api/v1/interrater/estudios/mis-membresias": () => [],
    "/api/v1/comisiones/mis": () => ({ items: [], next_cursor: null }),
  })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.localStorage.clear()
})

function pedidosDelPiloto(): string[] {
  return vi
    .mocked(fetch)
    .mock.calls.map(([u]) => String(u))
    .filter(
      (u) =>
        u.includes("/api/v1/interrater/sample") ||
        u.includes("/api/v1/interrater/ratings") ||
        u.includes("/api/v1/interrater/my-progress") ||
        u.includes("/api/v1/audit/episodes"),
    )
}

describe("rutas del estudio", () => {
  for (const ruta of ["/interrater", "/entrenamiento-recalibracion"]) {
    it(`${ruta} monta la seccion del estudio (aviso para docente sin membresia)`, async () => {
      montar(ruta)
      expect(
        await screen.findByText(/se usa para un estudio de codificación/, {}, { timeout: 3000 }),
      ).toBeTruthy()
      expect(screen.getByRole("link", { name: /acuerdo del piloto/ })).toBeTruthy()
      expect(pedidosDelPiloto()).toEqual([])
    })
  }
})
