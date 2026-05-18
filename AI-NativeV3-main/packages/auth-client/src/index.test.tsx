/**
 * Tests para index.tsx:
 *  - useAuth tira si se usa fuera de AuthProvider.
 *  - AuthProvider con keycloak mockeado expone state correcto post-init (auth ok).
 *  - hasRole responde correctamente.
 *  - getAccessToken: happy path y error path.
 *  - login/logout delegan al cliente Keycloak.
 *
 * Mockeamos `keycloak-js` para no abrir conexiones reales.
 */
import { act, cleanup, render, renderHook, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// Estado controlable del cliente Keycloak fake.
type KcFake = {
  init: ReturnType<typeof vi.fn>
  login: ReturnType<typeof vi.fn>
  logout: ReturnType<typeof vi.fn>
  updateToken: ReturnType<typeof vi.fn>
  onTokenExpired: (() => void) | undefined
  token: string | undefined
  tokenParsed: Record<string, unknown> | undefined
}

let kcInstance: KcFake

vi.mock("keycloak-js", () => {
  return {
    default: vi.fn().mockImplementation(() => kcInstance),
  }
})

import { AuthProvider, useAuth } from "./index"

function makeKc(overrides: Partial<KcFake> = {}): KcFake {
  return {
    init: vi.fn().mockResolvedValue(true),
    login: vi.fn(),
    logout: vi.fn(),
    updateToken: vi.fn().mockResolvedValue(true),
    onTokenExpired: undefined,
    token: "tok-initial",
    tokenParsed: {
      sub: "user-123",
      email: "alice@example.com",
      name: "Alice",
      tenant_id: "t-unsl",
      realm: "platform",
      realm_access: { roles: ["docente", "estudiante"] },
      comisiones_activas: ["c-1", "c-2"],
    },
    ...overrides,
  }
}

const config = { url: "http://kc.local", realm: "r", clientId: "c" }

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider config={config}>{children}</AuthProvider>
}

beforeEach(() => {
  kcInstance = makeKc()
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe("useAuth (sin provider)", () => {
  it("tira un Error si se invoca fuera de AuthProvider", () => {
    // Silenciamos el console.error que React emite cuando un hook tira al render.
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {})
    expect(() => renderHook(() => useAuth())).toThrow(/AuthProvider/)
    errSpy.mockRestore()
  })
})

describe("AuthProvider + useAuth (auth ok)", () => {
  it("post-init expone isAuthenticated=true, user mapeado y token", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    // Inicialmente isLoading true
    expect(result.current.isLoading).toBe(true)
    expect(result.current.isAuthenticated).toBe(false)

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.token).toBe("tok-initial")
    expect(result.current.user).toEqual({
      sub: "user-123",
      email: "alice@example.com",
      name: "Alice",
      tenantId: "t-unsl",
      realm: "platform",
      roles: ["docente", "estudiante"],
      comisionesActivas: ["c-1", "c-2"],
    })
  })

  it("hasRole devuelve true para roles presentes y false para los ausentes", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.hasRole("docente")).toBe(true)
    expect(result.current.hasRole("estudiante")).toBe(true)
    expect(result.current.hasRole("admin")).toBe(false)
  })

  it("login() y logout() delegan al cliente Keycloak", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    act(() => {
      result.current.login()
    })
    expect(kcInstance.login).toHaveBeenCalledOnce()

    act(() => {
      result.current.logout()
    })
    expect(kcInstance.logout).toHaveBeenCalledOnce()
  })

  it("getAccessToken() refresca y devuelve el token actual", async () => {
    kcInstance.updateToken.mockImplementation(async () => {
      kcInstance.token = "tok-refreshed"
      return true
    })

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    const tok = await result.current.getAccessToken()
    expect(kcInstance.updateToken).toHaveBeenCalledWith(30)
    expect(tok).toBe("tok-refreshed")
  })

  it("getAccessToken() devuelve null cuando updateToken falla", async () => {
    kcInstance.updateToken.mockRejectedValueOnce(new Error("network"))

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    const tok = await result.current.getAccessToken()
    expect(tok).toBeNull()
  })

  it("registra onTokenExpired y al dispararlo intenta updateToken; si falla cae a login()", async () => {
    renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(kcInstance.onTokenExpired).toBeTypeOf("function"))

    // Caso ok
    kcInstance.updateToken.mockResolvedValueOnce(true)
    kcInstance.onTokenExpired?.()
    expect(kcInstance.updateToken).toHaveBeenCalledWith(60)

    // Caso fallo -> login()
    kcInstance.updateToken.mockRejectedValueOnce(new Error("expired"))
    kcInstance.onTokenExpired?.()
    await waitFor(() => expect(kcInstance.login).toHaveBeenCalled())
  })
})

describe("AuthProvider (auth false)", () => {
  beforeEach(() => {
    kcInstance = makeKc({
      init: vi.fn().mockResolvedValue(false),
      tokenParsed: undefined,
      token: undefined,
    })
  })

  it("isAuthenticated=false y user=null cuando init devuelve false", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.user).toBeNull()
    expect(result.current.token).toBeNull()
    expect(result.current.hasRole("docente")).toBe(false)
  })
})

describe("AuthProvider (rendering children)", () => {
  it("renderiza los children pasados", async () => {
    render(
      <AuthProvider config={config}>
        <span>contenido protegido</span>
      </AuthProvider>,
    )
    expect(screen.getByText("contenido protegido")).toBeInTheDocument()
    // Esperamos a que init() resuelva para evitar warning de act() por el setState async post-mount.
    await waitFor(() => expect(kcInstance.init).toHaveBeenCalled())
    await act(async () => {
      await Promise.resolve()
    })
  })
})
