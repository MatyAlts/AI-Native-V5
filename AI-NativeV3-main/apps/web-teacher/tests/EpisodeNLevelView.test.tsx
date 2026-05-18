/**
 * Tests E2E de EpisodeNLevelView (ADR-020 + ADR-022).
 *
 * Cubre:
 * - Render inicial sin episodio: input + botón disabled
 * - Click "Analizar" con UUID válido → fetch + render de barra apilada
 * - initialEpisodeId (drill-down): autocarga al montar
 * - Error de API: render del bloque de error
 */
import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"
import { EpisodeNLevelView } from "../src/views/EpisodeNLevelView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const fakeGetToken = async () => "test-token"

const mockResponse = {
  episode_id: "11111111-2222-3333-4444-555555555555",
  labeler_version: "1.0.0",
  distribution_seconds: { N1: 30, N2: 60, N3: 15, N4: 45, meta: 5 },
  distribution_ratio: { N1: 0.19, N2: 0.39, N3: 0.1, N4: 0.29, meta: 0.03 },
  total_events_per_level: { N1: 2, N2: 3, N3: 1, N4: 4, meta: 2 },
}

beforeEach(() => {
  localStorage.setItem("analytics-view-mode", "investigador")
  setupFetchMock({ "/n-level-distribution": () => mockResponse })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("EpisodeNLevelView", () => {
  test("render inicial muestra input + boton 'Analizar' disabled", async () => {
    renderWithRouter(<EpisodeNLevelView getToken={fakeGetToken} />)
    expect(await screen.findByLabelText(/UUID del episodio/i)).toBeInTheDocument()
    const button = screen.getByRole("button", { name: /Analizar/i })
    expect(button).toBeDisabled()
  })

  test("click 'Analizar' con UUID dispara fetch y muestra distribución", async () => {
    const user = userEvent.setup()
    renderWithRouter(<EpisodeNLevelView getToken={fakeGetToken} />)

    const input = await screen.findByLabelText(/UUID del episodio/i)
    await user.type(input, "11111111-2222-3333-4444-555555555555")

    const button = screen.getByRole("button", { name: /Analizar/i })
    await user.click(button)

    await waitFor(() => {
      expect(screen.getByText(/labeler v1\.0\.0/i)).toBeInTheDocument()
    })
    // Tarjetas de los 5 niveles renderizadas
    expect(screen.getByText(/N1.*Comprensi/i)).toBeInTheDocument()
    expect(screen.getByText(/N4.*Interacci/i)).toBeInTheDocument()
  })

  test("initialEpisodeId autocarga al montar (drill-down)", async () => {
    renderWithRouter(
      <EpisodeNLevelView
        getToken={fakeGetToken}
        initialEpisodeId="11111111-2222-3333-4444-555555555555"
      />,
    )
    await waitFor(() => {
      expect(screen.getByText(/labeler v1\.0\.0/i)).toBeInTheDocument()
    })
    // El input está pre-poblado
    const input = screen.getByLabelText(/UUID del episodio/i) as HTMLInputElement
    expect(input.value).toBe("11111111-2222-3333-4444-555555555555")
  })

  test("error de API se renderiza con mensaje", async () => {
    setupFetchMock({
      "/n-level-distribution": {
        ok: false,
        status: 404,
        body: () => ({ detail: "Episode not found" }),
      },
    })
    const user = userEvent.setup()
    renderWithRouter(<EpisodeNLevelView getToken={fakeGetToken} />)
    const input = await screen.findByLabelText(/UUID del episodio/i)
    await user.type(input, "11111111-2222-3333-4444-555555555555")
    await user.click(screen.getByRole("button", { name: /Analizar/i }))

    await waitFor(() => {
      expect(screen.getByText(/Error consultando el episodio/i)).toBeInTheDocument()
    })
  })
})
