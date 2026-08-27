/**
 * Tests para useMediaQuery (fix QA 2026-06-15 #14).
 *
 * El hook gobierna el switch desktop (PanelGroup) ↔ mobile (tabs) en
 * EpisodePage. Verificamos el match inicial, la reacción a cambios del
 * media query y el fallback SSR/jsdom-sin-matchMedia.
 */
import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { useMediaQuery } from "../src/hooks/useMediaQuery"

type Listener = () => void

function installMatchMedia(initialMatches: boolean) {
  let matches = initialMatches
  const listeners = new Set<Listener>()
  const mql = {
    get matches() {
      return matches
    },
    media: "",
    onchange: null,
    addEventListener: (_: string, cb: Listener) => listeners.add(cb),
    removeEventListener: (_: string, cb: Listener) => listeners.delete(cb),
    addListener: (cb: Listener) => listeners.add(cb),
    removeListener: (cb: Listener) => listeners.delete(cb),
    dispatchEvent: () => true,
  }
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((q: string) => {
      ;(mql as { media: string }).media = q
      return mql
    }),
  })
  return {
    set(value: boolean) {
      matches = value
      for (const cb of listeners) cb()
    },
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe("useMediaQuery", () => {
  it("devuelve true cuando el query matchea al montar", () => {
    installMatchMedia(true)
    const { result } = renderHook(() => useMediaQuery("(max-width: 1023px)"))
    expect(result.current).toBe(true)
  })

  it("devuelve false cuando no matchea", () => {
    installMatchMedia(false)
    const { result } = renderHook(() => useMediaQuery("(max-width: 1023px)"))
    expect(result.current).toBe(false)
  })

  it("reacciona a cambios del media query (resize desktop → mobile)", () => {
    const ctl = installMatchMedia(false)
    const { result } = renderHook(() => useMediaQuery("(max-width: 1023px)"))
    expect(result.current).toBe(false)
    act(() => ctl.set(true))
    expect(result.current).toBe(true)
  })

  it("fallback a false si matchMedia no existe (SSR/jsdom)", () => {
    // Hay que forzar la AUSENCIA de matchMedia (SSR / jsdom viejo), no un
    // `undefined` asignado. `Reflect.deleteProperty` hace eso sin el operador
    // `delete`, que biome desaconseja.
    Reflect.deleteProperty(window, "matchMedia")
    const { result } = renderHook(() => useMediaQuery("(max-width: 1023px)"))
    expect(result.current).toBe(false)
  })
})
