/**
 * Aceptacion HU-035, regresion (orquestador, antes de arreglar; el constructor
 * no la modifica). Bug que encontro Juani en la demo del 25/11.
 *
 * Al salir de un episodio cerrado el alumno entraba en un bucle
 * home -> episodio -> home (159 pedidos en 8 s, 429 del gateway y un
 * `POST /entregas` por vuelta). En `main` no pasa: lo trajo la barra
 * "Mis cursos". `CampusShell` devolvia `<Outlet/>` suelto en `/episodio/...` y
 * `<div><BarraCursos/><div><Outlet/></div></div>` en el resto: al cambiar el
 * path el Outlet cambiaba de lugar en el arbol, React volvia a montar la pagina
 * del episodio que se estaba yendo y su efecto de montaje reescribia
 * `active-episode-id`, que la home usa para redirigir al episodio.
 *
 * Contrato que fija esta prueba:
 *  - `CampusShell` vive en `src/components/CampusShell.tsx` (export nombrado)
 *    y `__root.tsx` lo usa.
 *  - La pagina que esta en pantalla se monta UNA vez por navegacion: pasar de
 *    `/episodio/...` a otra ruta (o al reves) no vuelve a montar la que se va.
 *  - La barra sigue sin aparecer en el episodio y aparece en el resto.
 *
 * N08  Salir del episodio no lo vuelve a montar (no reescribe el marcador
 *      que usa la home para redirigir).
 * N09  Entrar al episodio desde el campus no vuelve a montar la pagina del
 *      campus que se va.
 * C01  La barra esta fuera del episodio y dentro del resto (como antes).
 */
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router"
import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import { useEffect } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CampusShell } from "../src/components/CampusShell"
import { setupFetchMock } from "./_mocks"

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..")
const MARCADOR = "active-episode-id"

const montajes: Record<string, number> = {}

function Sonda({ nombre, marca }: { nombre: string; marca?: string }) {
  useEffect(() => {
    montajes[nombre] = (montajes[nombre] ?? 0) + 1
    // Igual que EpisodePage: al montarse con el episodio "abierto" escribe el
    // marcador que la home usa para volver al episodio.
    if (marca) window.sessionStorage.setItem(MARCADOR, marca)
  }, [nombre, marca])
  return <p>{`pagina ${nombre}`}</p>
}

function armar(inicial: string) {
  const root = createRootRoute({ component: CampusShell })
  const home = createRoute({
    getParentRoute: () => root,
    path: "/",
    component: () => <Sonda nombre="home" />,
  })
  const curso = createRoute({
    getParentRoute: () => root,
    path: "/curso/$comisionId",
    component: () => <Sonda nombre="curso" />,
  })
  const episodio = createRoute({
    getParentRoute: () => root,
    path: "/episodio/$id",
    component: () => <Sonda nombre="episodio" marca="ep-1" />,
  })
  const router = createRouter({
    routeTree: root.addChildren([home, curso, episodio]),
    history: createMemoryHistory({ initialEntries: [inicial] }),
  })
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router as never} />
    </QueryClientProvider>,
  )
  return router
}

beforeEach(() => {
  for (const k of Object.keys(montajes)) delete montajes[k]
  window.sessionStorage.clear()
  setupFetchMock({ "/api/v1/materias/mias": () => ({ data: [] }) })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("HU-035 · salir del episodio no lo reabre", () => {
  it("N08: al salir a la home el episodio no se vuelve a montar ni reescribe el marcador", async () => {
    const router = armar("/episodio/ep-1")
    expect(await screen.findByText("pagina episodio")).toBeTruthy()
    expect(montajes.episodio).toBe(1)

    // Lo que hace EpisodePage al ver el episodio cerrado: borra el marcador y sale.
    window.sessionStorage.removeItem(MARCADOR)
    await act(async () => {
      await router.navigate({ to: "/" })
    })
    expect(await screen.findByText("pagina home")).toBeTruthy()
    await waitFor(() => expect(montajes.home).toBe(1))

    expect(montajes.episodio).toBe(1)
    expect(window.sessionStorage.getItem(MARCADOR)).toBeNull()
  })

  it("N09: entrar al episodio desde el curso no vuelve a montar el curso", async () => {
    const router = armar("/curso/c-1")
    expect(await screen.findByText("pagina curso")).toBeTruthy()
    await act(async () => {
      await router.navigate({ to: "/episodio/$id", params: { id: "ep-1" } })
    })
    expect(await screen.findByText("pagina episodio")).toBeTruthy()
    expect(montajes.curso).toBe(1)
    expect(montajes.episodio).toBe(1)
  })

  it("C01: la barra no esta en el episodio y si en el curso", async () => {
    const router = armar("/episodio/ep-1")
    expect(await screen.findByText("pagina episodio")).toBeTruthy()
    expect(screen.queryByRole("navigation", { name: "Mis cursos" })).toBeNull()
    await act(async () => {
      await router.navigate({ to: "/curso/$comisionId", params: { comisionId: "c-1" } })
    })
    expect(await screen.findByRole("navigation", { name: "Mis cursos" })).toBeTruthy()
  })

  it("el layout raiz usa CampusShell del componente compartido", () => {
    const raiz = readFileSync(join(RAIZ, "src/routes/__root.tsx"), "utf-8")
    expect(raiz).toMatch(
      /import\s*\{[^}]*CampusShell[^}]*\}\s*from\s*"\.\.\/components\/CampusShell"/,
    )
    expect(raiz).toContain("<CampusShell")
  })
})
