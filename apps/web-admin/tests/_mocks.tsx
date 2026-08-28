import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render } from "@testing-library/react"
import type { ReactNode } from "react"
/**
 * Helper compartido para mockear fetch por path-prefix (espejo del helper de
 * web-teacher en `apps/web-teacher/tests/_mocks.ts`).
 *
 * Las pages montan otros componentes que disparan sus propios fetches al mount
 * (ej. HelpButton no, pero PageContainer en otros casos sí). Si solo mockeamos
 * los fetches "interesantes" del test, los otros caen en undefined y rompen el
 * render. El default benigno del helper devuelve un envelope vacío.
 *
 * Uso:
 *   setupFetchMock({
 *     "/api/v1/universidades": () => ({ items: [{}, {}, {}] }),
 *     "/api/v1/comisiones": { ok: false, status: 500, body: () => ({ detail: "boom" }) },
 *   })
 */
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
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ data: [], meta: { cursor_next: null, total: null } }),
        text: () => Promise.resolve('{"data":[],"meta":{"cursor_next":null,"total":null}}'),
      } as Response)
    }),
  )
}

/**
 * Render con `QueryClientProvider`.
 *
 * `HomePage` y `GovernanceEventsPage` usan `useQuery`, y sin el provider mueren
 * con "No QueryClient set" — 10 rojos que vivian en `main` sin que nadie los
 * viera, porque el CI **no corria vitest en ningun frontend**. El mismo agujero
 * que ya se cerro en `web-teacher`.
 *
 * `retry: false` para que un fetch que el mock no cubre falle de una en vez de
 * reintentar y agotar el timeout del test.
 */
export function renderConQuery(node: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(<QueryClientProvider client={queryClient}>{node}</QueryClientProvider>)
}
