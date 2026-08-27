// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
//
// Tests de `useAnchorRect`. El contrato de degradacion esta escrito en types.ts:
// "si el ancla no aparece (ruta equivocada, permiso faltante, lista vacia), el paso
// degrada a card centrada sin recorte en vez de romper el tour". Traducido al hook:
// devuelve `null`, y el overlay lo interpreta como card centrada.
//
// Se pierde el spotlight, no el contenido. Eso es lo que se testea aca.
// Timers falsos a proposito: nadie espera 2,5 segundos reales por un test.
import { act, cleanup, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useAnchorRect } from "./useAnchorRect"

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function crearAncla(anchor: string, rect = { top: 10, left: 20, width: 300, height: 40 }) {
  const el = document.createElement("div")
  el.setAttribute("data-tour", anchor)
  el.getBoundingClientRect = () =>
    ({
      ...rect,
      right: rect.left + rect.width,
      bottom: rect.top + rect.height,
      x: rect.left,
      y: rect.top,
      toJSON: () => rect,
    }) as DOMRect
  document.body.appendChild(el)
  return el
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", ResizeObserverStub)
  Element.prototype.scrollIntoView = vi.fn()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ""
})

describe("useAnchorRect", () => {
  it("resuelve [data-tour=x] y devuelve su rect", () => {
    crearAncla("hero")
    const { result } = renderHook(() => useAnchorRect("hero", "p1"))
    expect(result.current).toEqual({ top: 10, left: 20, width: 300, height: 40 })
  })

  it("devuelve null cuando el paso no declara ancla", () => {
    crearAncla("hero")
    const { result } = renderHook(() => useAnchorRect(undefined, "p1"))
    expect(result.current).toBeNull()
  })

  it("encuentra el ancla que aparece tarde, dentro del timeout", () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useAnchorRect("tardio", "p1"))
    expect(result.current).toBeNull()

    act(() => {
      crearAncla("tardio", { top: 5, left: 6, width: 7, height: 8 })
      vi.advanceTimersByTime(300)
    })
    expect(result.current).toEqual({ top: 5, left: 6, width: 7, height: 8 })
  })

  it("si el ancla NUNCA aparece, despues del timeout devuelve null (card centrada)", () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useAnchorRect("fantasma", "p1"))

    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(result.current).toBeNull()
  })

  it("el ancla que no aparece no rompe nada al desmontar despues del timeout", () => {
    vi.useFakeTimers()
    const { result, unmount } = renderHook(() => useAnchorRect("fantasma", "p1"))
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(result.current).toBeNull()
    expect(() => unmount()).not.toThrow()
  })

  it("cambiar de ancla vuelve a resolver contra el elemento nuevo", () => {
    crearAncla("uno", { top: 1, left: 1, width: 10, height: 10 })
    crearAncla("dos", { top: 100, left: 200, width: 50, height: 60 })
    const { result, rerender } = renderHook(
      ({ anchor, stepId }: { anchor: string; stepId: string }) => useAnchorRect(anchor, stepId),
      { initialProps: { anchor: "uno", stepId: "p1" } },
    )
    expect(result.current).toEqual({ top: 1, left: 1, width: 10, height: 10 })

    rerender({ anchor: "dos", stepId: "p2" })
    expect(result.current).toEqual({ top: 100, left: 200, width: 50, height: 60 })
  })
})
