/**
 * Tests para fetch-interceptor.ts, acotados a la politica de timeout por ruta.
 *
 * Contexto del fix: el default de 25s (P-12) cortaba
 * `POST /api/v1/ejercicios/generate`, que genera un borrador completo con UNA
 * llamada al LLM (sin streaming, asi que la exencion de SSE no aplica) y puede
 * tardar minutos. El sintoma era "Request timeout tras 25000ms" con el backend
 * todavia sirviendo la request.
 *
 * Se usan fake timers: los tests no esperan segundos reales, adelantan el reloj.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { installApiFetchInterceptor } from "./fetch-interceptor"

const LONG_PATH = "/api/v1/ejercicios/generate"
const SHORT_PATH = "/api/v1/ejercicios"

let restore: (() => void) | undefined

/** fetch que nunca resuelve solo: termina unicamente si lo abortan. */
function hangingFetch() {
  return vi.fn(
    (_input: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new Error("aborted")), {
          once: true,
        })
      }),
  )
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  restore?.()
  restore = undefined
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe("requestTimeoutMs como funcion (politica por ruta)", () => {
  it("respeta el timeout largo de la ruta configurada y NO corta al default", async () => {
    globalThis.fetch = hangingFetch()
    restore = installApiFetchInterceptor({
      devNoClerk: true,
      requestTimeoutMs: (url) => (url.includes(LONG_PATH) ? 300_000 : 25_000),
    })

    const pending = fetch(LONG_PATH, { method: "POST" })
    // Assert antes de que expire: el bug original abortaba justo acá.
    const settled = vi.fn()
    pending.then(settled, settled)

    await vi.advanceTimersByTimeAsync(120_000)
    expect(settled).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(180_001)
    await expect(pending).rejects.toThrow("Request timeout tras 300000ms")
  })

  it("mantiene el default corto en las rutas que no son largas", async () => {
    globalThis.fetch = hangingFetch()
    restore = installApiFetchInterceptor({
      devNoClerk: true,
      requestTimeoutMs: (url) => (url.includes(LONG_PATH) ? 300_000 : 25_000),
    })

    // La assertion se adjunta ANTES de correr el reloj: si se adjunta despues,
    // el rechazo ya ocurrio sin handler y vitest lo reporta como unhandled.
    const assertion = expect(fetch(SHORT_PATH)).rejects.toThrow("Request timeout tras 25000ms")
    await vi.advanceTimersByTimeAsync(25_001)
    await assertion
  })

  it("evalua la url YA reescrita al apiBase", async () => {
    globalThis.fetch = hangingFetch()
    const seen: string[] = []
    restore = installApiFetchInterceptor({
      apiBase: "https://tutor.active-ia.com",
      devNoClerk: true,
      requestTimeoutMs: (url) => {
        seen.push(url)
        return 1_000
      },
    })

    const assertion = expect(fetch(LONG_PATH, { method: "POST" })).rejects.toThrow()
    await vi.advanceTimersByTimeAsync(1_001)
    await assertion

    expect(seen).toEqual([`https://tutor.active-ia.com${LONG_PATH}`])
  })

  it("cae al default si el callback tira, en vez de romper la request", async () => {
    globalThis.fetch = hangingFetch()
    restore = installApiFetchInterceptor({
      devNoClerk: true,
      requestTimeoutMs: () => {
        throw new Error("politica mal configurada")
      },
    })

    // Lo que importa: el error es el timeout normal, NO el del callback. Este
    // patch envuelve window.fetch — si propagara, romperia TODA la app.
    const assertion = expect(fetch(SHORT_PATH)).rejects.toThrow("Request timeout tras 25000ms")
    await vi.advanceTimersByTimeAsync(25_001)
    await assertion
  })

  it("sigue exceptuando SSE aunque la ruta tenga timeout configurado", async () => {
    const fetchMock = hangingFetch()
    globalThis.fetch = fetchMock
    restore = installApiFetchInterceptor({ devNoClerk: true, requestTimeoutMs: () => 1_000 })

    const settled = vi.fn()
    fetch("/api/v1/episodes/abc/message", {
      method: "POST",
      headers: { Accept: "text/event-stream" },
    }).then(settled, settled)

    await vi.advanceTimersByTimeAsync(600_000)

    expect(settled).not.toHaveBeenCalled()
    expect(fetchMock.mock.calls[0]?.[1]?.signal).toBeUndefined()
  })
})
