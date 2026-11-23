// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
/**
 * HU-022, prueba de cableado del panel docente (constructor). La aceptacion
 * (Hu022VerComoAlumno) prueba el boton suelto y que `__root.tsx` lo nombre; esta
 * mira lo que corre de verdad:
 *  - el layout completo (router real, `routeTree.gen`, memory history) muestra
 *    "Ver como alumno" en el header, y tocarlo guarda la eleccion y va a `/`;
 *  - `main.tsx` real, sin sesion (lo que queda despues de cerrar sesion con el
 *    UserButton de Clerk), borra `localStorage["modo-vista"]`; con sesion no.
 */
import { ConfirmProvider } from "@platform/ui"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router"
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { routeTree } from "../src/routeTree.gen"
import { setupFetchMock } from "./_mocks"

const clerk = vi.hoisted(() => ({ signedIn: false }))

vi.mock("@clerk/clerk-react", () => ({
  ClerkProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
  SignedOut: ({ children }: { children: ReactNode }) => (clerk.signedIn ? null : <>{children}</>),
  SignedIn: ({ children }: { children: ReactNode }) => (clerk.signedIn ? <>{children}</> : null),
  SignIn: () => <div>Pantalla de ingreso</div>,
  UserButton: () => null,
  useAuth: () => ({ isLoaded: true, isSignedIn: clerk.signedIn, getToken: async () => null }),
  // Sin user: InnerApp no resuelve el acceso y se queda en "Verificando tu acceso".
  useUser: () => ({ isLoaded: true, user: null }),
}))

let assign: ReturnType<typeof vi.fn>

beforeEach(() => {
  window.localStorage.clear()
  assign = vi.fn()
  vi.stubGlobal("location", { ...window.location, assign })
  setupFetchMock({
    "/api/v1/comisiones/mis": () => ({ items: [], next_cursor: null }),
  })
})

afterEach(() => {
  cleanup()
  // `main.tsx` monta su propia raiz en #root: se saca aunque el test haya fallado.
  document.getElementById("root")?.remove()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  window.localStorage.clear()
})

describe("HU-022 · el panel docente muestra Ver como alumno", () => {
  it("el header del layout completo tiene el boton y lleva a la vista de alumno", async () => {
    const router = createRouter({
      routeTree,
      history: createMemoryHistory({ initialEntries: ["/interrater-admin"] }),
      context: { getToken: async () => null, modoAcceso: "completo" },
    })
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <ConfirmProvider>
          <RouterProvider router={router} />
        </ConfirmProvider>
      </QueryClientProvider>,
    )
    const header = await screen.findByTestId("teacher-global-header")
    const boton = Array.from(header.querySelectorAll("button")).find(
      (b) => b.textContent?.trim() === "Ver como alumno",
    )
    expect(boton, "el header no tiene 'Ver como alumno'").toBeTruthy()
    if (!boton) return
    fireEvent.click(boton)
    expect(window.localStorage.getItem("modo-vista")).toBe("alumno")
    expect(assign).toHaveBeenCalledWith("/")
  })
})

describe("HU-022 · cerrar sesion olvida la eleccion", () => {
  async function montarMain() {
    vi.resetModules()
    vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "pk_test_hu022")
    const raiz = document.createElement("div")
    raiz.id = "root"
    document.body.appendChild(raiz)
    await act(async () => {
      await import("../src/main")
    })
    return raiz
  }

  it("sin sesion se borra localStorage['modo-vista']", async () => {
    clerk.signedIn = false
    window.localStorage.setItem("modo-vista", "alumno")
    const raiz = await montarMain()
    await waitFor(() => expect(raiz.textContent).toContain("Pantalla de ingreso"))
    await waitFor(() => expect(window.localStorage.getItem("modo-vista")).toBeNull())
  })

  it("control: con sesion la eleccion se conserva", async () => {
    clerk.signedIn = true
    window.localStorage.setItem("modo-vista", "alumno")
    const raiz = await montarMain()
    await waitFor(() => expect(raiz.textContent).toContain("Verificando tu acceso"))
    expect(window.localStorage.getItem("modo-vista")).toBe("alumno")
  })
})
