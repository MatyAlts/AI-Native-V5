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
