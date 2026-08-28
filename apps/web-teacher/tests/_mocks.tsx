import {
  Outlet,
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router"
/**
 * Helper compartido para mockear fetch por path-prefix.
 *
 * Las vistas montan otros componentes (ComisionSelector, AcademicContextSelector)
 * que disparan sus propios fetches al mount. Si solo mockeamos los fetches
 * "interesantes" del test, los otros caen en undefined y rompen el render.
 *
 * Uso:
 *   setupFetchMock({
 *     "/api/v1/analytics/episode/": () => mockNLevelResponse,
 *     "/api/v1/comisiones": () => ({ data: [], meta: { cursor_next: null } }),
 *   })
 *
 * Adicionalmente expone `renderWithRouter`: muchas views ahora usan
 * `<Link>` de TanStack Router para drill-down navegacional (volver a la
 * cohorte, navegar a episode-n-level desde un alumno). El componente
 * Link requiere RouterProvider en el arbol — sin él tira "Cannot read
 * properties of null (reading 'isServer')".
 */
import { render } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { vi } from "vitest"

type Handler = () => unknown

export function setupFetchMock(
  handlers: Record<string, Handler | { ok: boolean; status: number; body: () => unknown }>,
) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string | URL | Request) => {
      const urlStr = typeof url === "string" ? url : url.toString()
      for (const [pathPrefix, handler] of Object.entries(handlers)) {
        if (urlStr.includes(pathPrefix)) {
          if (typeof handler === "function") {
            return Promise.resolve({
              ok: true,
              status: 200,
              json: () => Promise.resolve(handler()),
              text: () => Promise.resolve(JSON.stringify(handler())),
            } as Response)
          }
          return Promise.resolve({
            ok: handler.ok,
            status: handler.status,
            json: () => Promise.resolve(handler.body()),
            text: () => Promise.resolve(JSON.stringify(handler.body())),
          } as Response)
        }
      }
      // Default benigno: lista vacía con shape de pageable
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ data: [], meta: { cursor_next: null } }),
        text: () => Promise.resolve('{"data":[],"meta":{"cursor_next":null}}'),
      } as Response)
    }),
  )
}

/**
 * Render envuelto en un RouterProvider de TanStack con memory history.
 * Necesario para views que usan `<Link>` (drill-down). El wrapper monta
 * la view dentro de la ruta `/` del router test, asi que los Link a
 * cualquier `to` resuelven sin tirar (TanStack permite navegar a rutas
 * que no estan registradas, solo no se mueve la URL — suficiente para
 * los tests E2E unitarios).
 */
export function renderWithRouter(node: ReactNode) {
  const rootRoute = createRootRoute({
    component: () => <Outlet />,
  })
  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/",
    component: () => node as JSX.Element,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  // QueryClientProvider ADEMAS del router. `HomeView` y `CorreccionesView` ya
  // usaban react-query en `main` y este helper solo montaba el router, asi que
  // los dos archivos morian con "No QueryClient set" — 14 rojos que vivian en
  // `main` sin que nadie los viera, porque hasta el 2026-08-27 el CI no corria
  // vitest. Se arreglan aca y no test por test: el que agregue la proxima vista
  // con react-query no tiene por que enterarse de esto.
  //
  // `retry: false` para que un fetch que el mock no cubre falle de una en vez
  // de reintentar tres veces y agotar el timeout del test.
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}
