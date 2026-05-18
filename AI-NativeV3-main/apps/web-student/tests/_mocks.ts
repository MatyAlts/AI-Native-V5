/**
 * Helper compartido para mockear fetch por path-prefix en los tests del
 * web-student. Patron espejo del de web-teacher (apps/web-teacher/tests/_mocks.ts).
 *
 * Las paginas montan otros componentes (ComisionSelector, AuditFooter)
 * que disparan sus propios fetches al mount. Si solo mockeamos los
 * "interesantes" del test, los otros caen en undefined y rompen el render.
 *
 * Uso:
 *   setupFetchMock({
 *     "/api/v1/comisiones/mis": () => ({ data: [...], meta: {...} }),
 *     "/api/v1/audit/episodes/": () => ({ events_count: 470, is_intact: true }),
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
      // Default benigno: lista vacia con shape de pageable.
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
 * Mockea `matchMedia` para tests que dependen de
 * `prefers-reduced-motion`. Por default jsdom lo deja en `false`; este
 * helper lo fuerza a true cuando el query incluye "reduce".
 */
export function mockPrefersReducedMotion(prefer: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: prefer && query.includes("reduce"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}
