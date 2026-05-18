/**
 * Tests para http.ts:
 *  - useAuthenticatedFetch: inyeccion de Authorization, content-type, autoRetry en 401, fallback login.
 *  - authenticatedSSE: stream parsing happy path y error.
 *
 * Mockeamos `./index` (useAuth) para no tener que arrancar Keycloak ni renderizar el provider.
 */
import { renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// Mock de useAuth — el hook bajo test consume este modulo.
const getAccessTokenMock = vi.fn<() => Promise<string | null>>()
const loginMock = vi.fn()
let isAuthenticatedFlag = true

vi.mock("./index", () => ({
  useAuth: () => ({
    getAccessToken: getAccessTokenMock,
    login: loginMock,
    isAuthenticated: isAuthenticatedFlag,
    // El resto del contrato AuthContext no lo usa http.ts pero lo dejamos por completitud:
    isLoading: false,
    user: null,
    token: null,
    logout: vi.fn(),
    hasRole: () => false,
  }),
}))

import { authenticatedSSE, useAuthenticatedFetch } from "./http"

beforeEach(() => {
  getAccessTokenMock.mockReset()
  loginMock.mockReset()
  isAuthenticatedFlag = true
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("useAuthenticatedFetch", () => {
  it("inyecta Authorization: Bearer <token> en cada request", async () => {
    getAccessTokenMock.mockResolvedValue("token-abc")
    const fetchMock = vi.fn().mockResolvedValue(new Response("ok", { status: 200 }))
    vi.stubGlobal("fetch", fetchMock)

    const { result } = renderHook(() => useAuthenticatedFetch())
    await result.current("/api/v1/foo")

    expect(fetchMock).toHaveBeenCalledOnce()
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    const headers = init.headers as Headers
    expect(headers.get("Authorization")).toBe("Bearer token-abc")
  })

  it("setea Content-Type: application/json cuando hay body string sin content-type", async () => {
    getAccessTokenMock.mockResolvedValue("t1")
    const fetchMock = vi.fn().mockResolvedValue(new Response("ok"))
    vi.stubGlobal("fetch", fetchMock)

    const { result } = renderHook(() => useAuthenticatedFetch())
    await result.current("/api/v1/foo", { method: "POST", body: JSON.stringify({ a: 1 }) })

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    const headers = init.headers as Headers
    expect(headers.get("Content-Type")).toBe("application/json")
  })

  it("respeta Content-Type pre-existente del caller", async () => {
    getAccessTokenMock.mockResolvedValue("t1")
    const fetchMock = vi.fn().mockResolvedValue(new Response("ok"))
    vi.stubGlobal("fetch", fetchMock)

    const { result } = renderHook(() => useAuthenticatedFetch())
    await result.current("/api/v1/foo", {
      method: "POST",
      body: "raw",
      headers: { "Content-Type": "text/plain" },
    })

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    const headers = init.headers as Headers
    expect(headers.get("Content-Type")).toBe("text/plain")
  })

  it("dispara login() y throw si !isAuthenticated", async () => {
    isAuthenticatedFlag = false
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)

    const { result } = renderHook(() => useAuthenticatedFetch())
    await expect(result.current("/x")).rejects.toThrow(/No autenticado/)
    expect(loginMock).toHaveBeenCalledOnce()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("dispara login() y throw si getAccessToken devuelve null", async () => {
    getAccessTokenMock.mockResolvedValue(null)
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)

    const { result } = renderHook(() => useAuthenticatedFetch())
    await expect(result.current("/x")).rejects.toThrow(/Token no disponible/)
    expect(loginMock).toHaveBeenCalledOnce()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("en 401 con token nuevo distinto, reintenta con el token refrescado", async () => {
    getAccessTokenMock.mockResolvedValueOnce("token-old").mockResolvedValueOnce("token-new")
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("unauth", { status: 401 }))
      .mockResolvedValueOnce(new Response("ok", { status: 200 }))
    vi.stubGlobal("fetch", fetchMock)

    const { result } = renderHook(() => useAuthenticatedFetch())
    const res = await result.current("/api/v1/foo")

    expect(res.status).toBe(200)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const retryInit = fetchMock.mock.calls[1]?.[1] as RequestInit
    const retryHeaders = retryInit.headers as Headers
    expect(retryHeaders.get("Authorization")).toBe("Bearer token-new")
    expect(loginMock).not.toHaveBeenCalled()
  })

  it("en 401 con token igual tras refresh, dispara login() y devuelve el 401", async () => {
    getAccessTokenMock.mockResolvedValue("token-same")
    const fetchMock = vi.fn().mockResolvedValue(new Response("unauth", { status: 401 }))
    vi.stubGlobal("fetch", fetchMock)

    const { result } = renderHook(() => useAuthenticatedFetch())
    const res = await result.current("/api/v1/foo")

    expect(res.status).toBe(401)
    expect(loginMock).toHaveBeenCalledOnce()
    // Solo un fetch: como el token nuevo == viejo, no se reintenta y cae a login()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it("autoRetryOn401=false NO dispara retry ni login en 401", async () => {
    getAccessTokenMock.mockResolvedValue("token-x")
    const fetchMock = vi.fn().mockResolvedValue(new Response("unauth", { status: 401 }))
    vi.stubGlobal("fetch", fetchMock)

    const { result } = renderHook(() => useAuthenticatedFetch())
    const res = await result.current("/api/v1/foo", { autoRetryOn401: false })

    expect(res.status).toBe(401)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(loginMock).not.toHaveBeenCalled()
  })

  it("no debe dejar autoRetryOn401 dentro del init pasado a fetch (es opcion del wrapper)", async () => {
    getAccessTokenMock.mockResolvedValue("token-x")
    const fetchMock = vi.fn().mockResolvedValue(new Response("ok"))
    vi.stubGlobal("fetch", fetchMock)

    const { result } = renderHook(() => useAuthenticatedFetch())
    await result.current("/api/v1/foo", { autoRetryOn401: true, method: "GET" })

    const init = fetchMock.mock.calls[0]?.[1] as Record<string, unknown>
    expect(init.autoRetryOn401).toBeUndefined()
    expect(init.method).toBe("GET")
  })
})

describe("authenticatedSSE", () => {
  function makeSSEResponse(chunks: string[]): Response {
    const encoder = new TextEncoder()
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const c of chunks) controller.enqueue(encoder.encode(c))
        controller.close()
      },
    })
    return new Response(stream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    })
  }

  it("parsea eventos data: JSON y los yieldea uno por uno", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      makeSSEResponse([
        'data: {"msg":"hola"}\n',
        'data: {"msg":"chau"}\n',
        // linea malformada — debe ignorarse silenciosamente
        "data: {malformado\n",
      ]),
    )
    vi.stubGlobal("fetch", fetchMock)

    const events: unknown[] = []
    for await (const ev of authenticatedSSE("token-1", "/api/v1/stream")) events.push(ev)

    expect(events).toEqual([{ msg: "hola" }, { msg: "chau" }])

    // Headers correctos
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    const headers = init.headers as Headers
    expect(headers.get("Authorization")).toBe("Bearer token-1")
    expect(headers.get("Accept")).toBe("text/event-stream")
  })

  it("tira si la respuesta no es ok", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("nope", { status: 500 }))
    vi.stubGlobal("fetch", fetchMock)

    const gen = authenticatedSSE("token-1", "/api/v1/stream")
    await expect(gen.next()).rejects.toThrow(/SSE failed: 500/)
  })
})
