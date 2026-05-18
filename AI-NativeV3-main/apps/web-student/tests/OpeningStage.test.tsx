/**
 * Tests del OpeningStage (shape alumno, brief 3.4 + D6).
 *
 * Cubre:
 *  - Las 4 lineas se renderizan con su label + detalle.
 *  - Estados: pending → inflight → done a medida que tick + episodeReady avanzan.
 *  - errorMessage muestra glifo ✗ y boton "ver detalles" en la linea correcta.
 *  - prefers-reduced-motion: el spinner inflight queda estatico (sin animate-spin).
 */
import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"
import { OpeningStage } from "../src/components/OpeningStage"
import { mockPrefersReducedMotion } from "./_mocks"

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe("OpeningStage", () => {
  test("renderiza las 4 lineas de chequeos con labels y detalles", () => {
    render(<OpeningStage tareaCodigo="TP-04" tareaTitulo="Recursividad" episodeReady={false} />)

    expect(screen.getByText(/TP validada/)).toBeInTheDocument()
    expect(screen.getByText(/Episodio registrado en CTR/)).toBeInTheDocument()
    expect(screen.getByText(/Cadena criptografica firmando/)).toBeInTheDocument()
    expect(screen.getByText(/Tutor inicializando/)).toBeInTheDocument()

    // Detalles fijos (no dependen de tick)
    expect(screen.getByText(/estado=published/)).toBeInTheDocument()
    expect(screen.getByText(/seq=0/)).toBeInTheDocument()
  })

  test("estado inicial: TP inflight, las demas pending", () => {
    render(<OpeningStage tareaCodigo="TP-04" tareaTitulo="Recursividad" episodeReady={false} />)

    const tp = screen.getByTestId("opening-step-tp")
    const ctr = screen.getByTestId("opening-step-ctr")
    const chain = screen.getByTestId("opening-step-chain")
    const tutor = screen.getByTestId("opening-step-tutor")

    expect(tp.getAttribute("data-status")).toBe("inflight")
    expect(ctr.getAttribute("data-status")).toBe("pending")
    expect(chain.getAttribute("data-status")).toBe("pending")
    expect(tutor.getAttribute("data-status")).toBe("pending")
  })

  test("transiciona a done con episodeReady + suficientes ticks", async () => {
    render(<OpeningStage tareaCodigo="TP-04" tareaTitulo="Recursividad" episodeReady={true} />)

    // Avanzar 4 ticks (1 segundo: cada tick es 250ms)
    await act(async () => {
      vi.advanceTimersByTime(1500)
    })

    const tp = screen.getByTestId("opening-step-tp")
    const ctr = screen.getByTestId("opening-step-ctr")
    const chain = screen.getByTestId("opening-step-chain")
    const tutor = screen.getByTestId("opening-step-tutor")

    expect(tp.getAttribute("data-status")).toBe("done")
    expect(ctr.getAttribute("data-status")).toBe("done")
    expect(chain.getAttribute("data-status")).toBe("done")
    expect(tutor.getAttribute("data-status")).toBe("done")
  })

  test("errorMessage marca paso CTR como error y muestra ver detalles", () => {
    const onShowError = vi.fn()
    render(
      <OpeningStage
        tareaCodigo="TP-04"
        tareaTitulo="Recursividad"
        episodeReady={false}
        errorMessage="Network down"
        onShowError={onShowError}
      />,
    )

    const ctr = screen.getByTestId("opening-step-ctr")
    expect(ctr.getAttribute("data-status")).toBe("error")
    expect(screen.getByText(/ver detalles/i)).toBeInTheDocument()
    expect(screen.getByTestId("step-glyph-error")).toBeInTheDocument()
  })

  test("muestra retry line si POST tarda >3s sin respuesta", async () => {
    render(<OpeningStage tareaCodigo="TP-04" tareaTitulo="Recursividad" episodeReady={false} />)

    expect(screen.queryByTestId("opening-retry-line")).not.toBeInTheDocument()

    await act(async () => {
      vi.advanceTimersByTime(3500)
    })

    expect(screen.getByTestId("opening-retry-line")).toBeInTheDocument()
  })

  test("muestra el episode_id truncado cuando esta disponible", () => {
    render(
      <OpeningStage
        tareaCodigo="TP-04"
        tareaTitulo="Recursividad"
        episodeReady={true}
        episodeId="a4f81c2eb7d11234"
      />,
    )
    expect(screen.getByText(/a4f81c.*1234/)).toBeInTheDocument()
  })

  test("respeta prefers-reduced-motion: el spinner queda estatico", () => {
    mockPrefersReducedMotion(true)
    render(<OpeningStage tareaCodigo="TP-04" tareaTitulo="Recursividad" episodeReady={false} />)

    // El glifo inflight existe y usa motion-safe:animate-pulse, que en
    // matchMedia=reduce queda inerte (jsdom no aplica el media query, pero
    // verificamos que la clase motion-safe esta presente — eso garantiza
    // que el browser real la suprime con prefers-reduced-motion).
    const dot = screen.getByTestId("inflight-dot")
    expect(dot.className).toContain("motion-safe:animate-pulse")
    // Sin clases puras de animacion (animate-spin / animate-bounce sin guard).
    expect(dot.className).not.toMatch(/(?<!motion-safe:)animate-spin\b/)
  })
})
