/**
 * HU-020 (F22 completo), prueba de apoyo del constructor (no es la aceptacion).
 *
 * El paso "TP validada" se ponia en verde con "ventana fechas OK" a los 250 ms,
 * antes de que respondiera el servidor: si despues el servidor decia que el
 * plazo habia vencido, la pantalla ya habia afirmado lo contrario. Tiene que
 * quedar en curso hasta que haya respuesta, y los detalles hablan en palabras
 * simples.
 */
import { act, cleanup, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { OpeningStage } from "../src/components/OpeningStage"

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe("HU-020 · OpeningStage espera al servidor", () => {
  it("sin respuesta, el paso 1 sigue en curso y no dice 'ventana fechas OK'", async () => {
    render(<OpeningStage tareaCodigo="VERIF" tareaTitulo="TP" episodeReady={false} />)
    await act(async () => {
      vi.advanceTimersByTime(2000)
    })
    const tp = screen.getByTestId("opening-step-tp")
    expect(tp.getAttribute("data-status")).toBe("inflight")
    expect(screen.queryByText(/ventana fechas OK/i)).toBeNull()
  })

  it("con el episodio listo, el paso 1 queda validado", async () => {
    render(<OpeningStage tareaCodigo="VERIF" tareaTitulo="TP" episodeReady={true} />)
    await act(async () => {
      vi.advanceTimersByTime(1500)
    })
    expect(screen.getByTestId("opening-step-tp").getAttribute("data-status")).toBe("done")
  })

  it("los detalles no usan jerga tecnica", () => {
    const { container } = render(
      <OpeningStage tareaCodigo="VERIF" tareaTitulo="TP" episodeReady={false} />,
    )
    expect(container.textContent ?? "").not.toMatch(
      /estado=published|seq=0|EpisodioAbierto|chain_hash|tutor\/v\d/,
    )
  })
})
