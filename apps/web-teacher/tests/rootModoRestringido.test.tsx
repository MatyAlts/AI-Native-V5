// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
/**
 * Layout raiz en MODO RESTRINGIDO (design D13; spec estudio-codificacion-acceso,
 * "Entrada al panel docente para miembros sin comisiones").
 *
 * Un codificador externo entra al panel docente sin tener comisiones. Ahi el
 * panel tiene que ser solo las dos secciones del estudio: sin tour docente, sin
 * carteles de onboarding, sin selectores de comision ni de tenant, y sin pedir
 * comisiones (que ademas le darian 403 o vacio). Cualquier otra ruta lo devuelve
 * a Codificacion.
 *
 * Se monta el router REAL (`routeTree.gen`) con memory history: lo que se
 * prueba es el ruteo y el layout que de verdad corren, no una copia.
 *
 * Cada ausencia tiene su control en modo completo (mismo montaje, otro modo):
 * sin el control, "no aparece el tour" pasaria tambien si el tour estuviera roto.
 */
import { ConfirmProvider } from "@platform/ui"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { routeTree } from "../src/routeTree.gen"
import { setupFetchMock } from "./_mocks"

type Modo = "completo" | "restringido"

function montar(ruta: string, modoAcceso: Modo) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [ruta] }),
    context: { getToken: async () => null, modoAcceso },
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
  return router
}

function urlsPedidas(): string[] {
  return vi.mocked(fetch).mock.calls.map(([u]) => String(u))
}

const TEXTO_TOUR = "Esta plataforma registra el camino"
const TEXTO_ONBOARDING = "Todavia no figuras en ninguna comision"

beforeEach(() => {
  window.localStorage.clear()
  setupFetchMock({
    "/api/v1/interrater/estudios/mis-membresias": () => [
      { clave: "cibse-2027", titulo: "CIbSE", rol: "codificador", cerrada: false },
    ],
    "/api/v1/comisiones/mis": () => ({ items: [], next_cursor: null }),
  })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("root en modo restringido", () => {
  // Con `comisionId` para que el `beforeLoad` propio de Progresion no redirija al
  // home: lo que se prueba es que el ROOT redirige antes.
  it("otra ruta (Progresion) redirige a Codificacion", async () => {
    const router = montar("/progression?comisionId=11111111-1111-4111-8111-111111111111", "restringido")
    await waitFor(() => expect(router.state.location.pathname).toBe("/interrater"))
  })

  it("Entrenamiento-Recalibracion es alcanzable sin redirigir", async () => {
    const router = montar("/entrenamiento-recalibracion", "restringido")
    await screen.findAllByText("Codificación (inter-jueces)")
    expect(router.state.location.pathname).toBe("/entrenamiento-recalibracion")
  })

  it("el menu tiene solo las dos secciones del estudio", async () => {
    montar("/interrater", "restringido")
    const nav = await screen.findByRole("navigation")
    const botones = Array.from(nav.querySelectorAll("button")).map((b) => b.textContent?.trim())
    const conEtiqueta = botones.filter((t) => t && t.length > 0)
    expect(conEtiqueta).toEqual(
      expect.arrayContaining(["Entrenamiento-Recalibración", "Codificación (inter-jueces)"]),
    )
    expect(nav.textContent).not.toContain("Progresión")
    expect(nav.textContent).not.toContain("Mis comisiones")
    expect(nav.textContent).not.toContain("Trabajos Prácticos")
  })

  it("no arranca el tour, no muestra onboarding, no monta selectores ni pide comisiones", async () => {
    montar("/interrater", "restringido")
    await screen.findByRole("navigation")
    // Dar tiempo a efectos y queries que dispararian el tour o los fetch.
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByText(TEXTO_TOUR, { exact: false })).toBeNull()
    expect(screen.queryByText(TEXTO_ONBOARDING, { exact: false })).toBeNull()
    expect(screen.queryByRole("radiogroup", { name: "Modo de visualizacion", hidden: true })).toBeNull()
    const urls = urlsPedidas()
    expect(urls.filter((u) => u.includes("/api/v1/comisiones"))).toEqual([])
    expect(urls.filter((u) => u.includes("/api/v1/universidades/mine"))).toEqual([])
  })
})

describe("control: el mismo montaje en modo completo", () => {
  it("no redirige, muestra el menu entero y pide comisiones (las aserciones de arriba discriminan)", async () => {
    // `/interrater-admin` y no Progresion: con el mock generico, ProgressionView se
    // cae y tumba el arbol entero, y el control no mediria nada.
    const router = montar("/interrater-admin", "completo")
    const nav = await screen.findByRole("navigation")
    expect(router.state.location.pathname).toBe("/interrater-admin")
    expect(nav.textContent).toContain("Progresión")
    await waitFor(() =>
      expect(urlsPedidas().some((u) => u.includes("/api/v1/comisiones/mis"))).toBe(true),
    )
    await waitFor(() =>
      expect(urlsPedidas().some((u) => u.includes("/api/v1/universidades/mine"))).toBe(true),
    )
    expect(screen.getByRole("radiogroup", { name: "Modo de visualizacion", hidden: true })).toBeTruthy()
    expect(await screen.findByText(TEXTO_TOUR, { exact: false })).toBeTruthy()
  })
})
