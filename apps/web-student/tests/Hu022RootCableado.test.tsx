/**
 * HU-022, prueba de cableado (constructor). La aceptacion (Hu022Interruptor)
 * prueba la regla y el boton sueltos, y que `__root.tsx` nombre la regla; esta
 * monta el layout REAL de Clerk (`ClerkRootLayout`, via `routeTree.gen` con
 * memory history) con `fetch` simulado y mira lo que pasa de verdad:
 *  - docente con "Ver como alumno" elegido: no rebota, ve "Volver al panel docente"
 *    y, sin inscripciones, la pantalla del codigo de invitacion (N02);
 *  - docente sin elegir nada: rebota a /teacher/;
 *  - alumno comun: ni rebote ni boton;
 *  - sin sesion: se borra la eleccion guardada.
 *
 * `DEV_NO_CLERK` se calcula al importar `auth.ts`, por eso se fija la clave de
 * Clerk con `vi.stubEnv` y se importa el arbol de rutas despues.
 *
 * Todos los casos responden `/materias/mias` vacio: asi el cuerpo es la pantalla
 * del codigo de invitacion y no la home, que con el mock generico se cae y
 * reemplaza el layout entero por el error del router (una ausencia mirada ahi no
 * mediria nada). Cada ausencia tiene al lado un control positivo.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { setupFetchMock } from "./_mocks"

const clerk = vi.hoisted(() => ({ signedIn: true }))

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ isLoaded: true, isSignedIn: clerk.signedIn }),
  useUser: () => ({
    isLoaded: true,
    user: clerk.signedIn
      ? {
          id: "user_hu022",
          fullName: "Docente Prueba",
          firstName: "Docente",
          lastName: "Prueba",
          primaryEmailAddress: { emailAddress: "docente@utn.edu" },
        }
      : null,
  }),
  SignedOut: ({ children }: { children: ReactNode }) => (clerk.signedIn ? null : <>{children}</>),
  SignInButton: ({ children }: { children: ReactNode }) => <>{children}</>,
  SignUpButton: ({ children }: { children: ReactNode }) => <>{children}</>,
  UserButton: () => null,
}))

const COMISION = { id: "c-1", nombre: "Comision de prueba" }
const HREF_INICIAL = "http://localhost/"
let loc: { href: string; assign: ReturnType<typeof vi.fn>; replace: ReturnType<typeof vi.fn> }

async function montar() {
  vi.resetModules()
  vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "pk_test_hu022")
  const { routeTree } = await import("../src/routeTree.gen")
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/"] }),
    context: { getToken: async () => null },
  })
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

function fetchs(comisiones: unknown[], materias: unknown[]) {
  setupFetchMock({
    "/api/v1/comisiones/mis": () => ({ data: comisiones }),
    "/api/v1/materias/mias": () => ({ data: materias }),
  })
}

function pidio(path: string): boolean {
  return vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes(path))
}

/** Espera a que el layout consulte si es docente y deja correr lo que sigue. */
async function despuesDeConsultarComisiones() {
  await waitFor(() => expect(pidio("/api/v1/comisiones/mis")).toBe(true))
  await new Promise((r) => setTimeout(r, 50))
}

beforeEach(() => {
  // jsdom no trae scrollIntoView y el onboarding del alumno lo usa para
  // enganchar su cartel al campo del codigo.
  Element.prototype.scrollIntoView = vi.fn()
  clerk.signedIn = true
  window.localStorage.clear()
  loc = { ...window.location, href: HREF_INICIAL, assign: vi.fn(), replace: vi.fn() }
  vi.stubGlobal("location", loc)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  window.localStorage.clear()
})

describe("HU-022 · el layout del alumno con Clerk", () => {
  it("docente que eligio ver como alumno: no rebota, ve el boton para volver y, sin inscripciones, la pantalla del codigo", async () => {
    window.localStorage.setItem("modo-vista", "alumno")
    fetchs([COMISION], [])
    await montar()
    expect(await screen.findByText("Unirte a una comision")).toBeTruthy()
    expect(screen.getByText("Volver al panel docente")).toBeTruthy()
    await despuesDeConsultarComisiones()
    expect(loc.href).toBe(HREF_INICIAL)
  })

  it("docente sin elegir nada: rebota a /teacher/", async () => {
    fetchs([COMISION], [])
    await montar()
    await waitFor(() => expect(loc.href).toBe("/teacher/"))
  })

  it("alumno comun: ni rebote ni boton", async () => {
    fetchs([], [])
    await montar()
    await despuesDeConsultarComisiones()
    // Control positivo: el layout del alumno esta montado (no un error).
    expect(await screen.findByText("Unirte a una comision")).toBeTruthy()
    expect(loc.href).toBe(HREF_INICIAL)
    expect(screen.queryByText("Volver al panel docente")).toBeNull()
  })

  it("sin sesion (despues de cerrar sesion) se borra la eleccion", async () => {
    clerk.signedIn = false
    window.localStorage.setItem("modo-vista", "alumno")
    fetchs([], [])
    await montar()
    await screen.findByText("Bienvenido a Plataforma N4")
    await waitFor(() => expect(window.localStorage.getItem("modo-vista")).toBeNull())
  })

  it("control: con sesion la eleccion no se borra", async () => {
    window.localStorage.setItem("modo-vista", "alumno")
    fetchs([COMISION], [])
    await montar()
    await screen.findByText("Volver al panel docente")
    expect(window.localStorage.getItem("modo-vista")).toBe("alumno")
  })
})
