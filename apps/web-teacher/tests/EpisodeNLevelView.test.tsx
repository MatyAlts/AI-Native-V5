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

  // ── Veredicto del juez trivaluado (D3 del design.md) ─────────────────
  const mockClassificationConDimNoEvaluable = {
    episode_id: "11111111-2222-3333-4444-555555555555",
    comision_id: "c1",
    classifier_config_hash: "hash",
    appropriation: "apropiacion_reflexiva",
    appropriation_reason: "juez",
    ct_summary: null,
    ccd_mean: null,
    ccd_orphan_ratio: null,
    cii_stability: null,
    cii_evolution: null,
    is_current: true,
    subgrupo: null,
    regimen_llm: {
      estado: "ok",
      regimen: "REFLEXIVA",
      confianza: 0.9,
      raw: {
        verbalizacion: { presente: "presente", evidencia: "explica el porque" },
        // No evaluable: registro incompleto. Con el colapso viejo esto se
        // dibujaba como "ausente" — exactamente lo que D3 vino a corregir.
        verificacion: { presente: "no_evaluable", evidencia: "" },
        justificacion: { presente: "presente", evidencia: "defiende su eleccion" },
        autonomia: { presente: "presente", evidencia: "cuestiona la propuesta" },
        regimen: "REFLEXIVA",
        confianza: 0.9,
        justificacion_global: "test",
      },
      razon: "ok",
      model_used: "gpt-4o",
      prompt_version: "eje_fino_v1.2.0",
    },
  }

  test("dimension no_evaluable del juez NO se dibuja como ausente (D3)", async () => {
    setupFetchMock({
      "/n-level-distribution": () => mockResponse,
      "/api/v1/classifications/": () => mockClassificationConDimNoEvaluable,
    })
    renderWithRouter(
      <EpisodeNLevelView
        getToken={fakeGetToken}
        initialEpisodeId="11111111-2222-3333-4444-555555555555"
      />,
    )
    await waitFor(() => {
      expect(screen.getByText(/no evaluable/i)).toBeInTheDocument()
    })
    // La fila de Verificacion (la que vino no_evaluable) no debe quedar
    // etiquetada "ausente" — ese es el colapso que D3 elimina.
    const filaVerificacion = screen.getByText("Verificacion").closest("div")
    expect(filaVerificacion).not.toHaveTextContent(/^ausente$/i)
  })

  // ── Corrección post-QA (2026-09-25): el test de abajo ANTES fabricaba
  // `autonomia: { presente: true, evidencia }` — una forma que ningún registro
  // real tuvo jamás. La forma legada REAL de autonomía es `{ oraculo: bool }`,
  // SIN clave `presente`, y el fix real es que el BACKEND normalice esa forma
  // en el borde de lectura (ver `normalizar_regimen_llm_persistido` en
  // `regimen_llm.py`) — el frontend no debe aprender a entender `oraculo`
  // (sería la segunda forma del mismo dato viviendo en la UI). Por eso este
  // test usa la forma que la API YA FIJADA devuelve hoy para un registro
  // juzgado bajo `eje_fino_v1.1.0`: strings trivaluados en las 4 dimensiones,
  // nunca `oraculo`, nunca boolean para autonomía.
  test("registro juzgado con autonomia legada (oraculo) llega normalizado por el backend y se muestra correcto", async () => {
    const mockClassificationLegadaNormalizadaPorElBackend = {
      ...mockClassificationConDimNoEvaluable,
      regimen_llm: {
        ...mockClassificationConDimNoEvaluable.regimen_llm,
        raw: {
          verbalizacion: { presente: "presente", evidencia: "explica el porque" },
          verificacion: { presente: "ausente", evidencia: "" },
          justificacion: { presente: "presente", evidencia: "defiende su eleccion" },
          // Esto es lo que el backend fijado devuelve HOY para un registro
          // cuyo dato crudo en JSONB es `{"oraculo": false, "evidencia": "..."}`
          // — normalizado por `normalizar_regimen_llm_persistido` antes de
          // salir por HTTP. El frontend nunca ve la clave `oraculo`.
          autonomia: { presente: "presente", evidencia: "razona sin que se lo pidan" },
          regimen: "REFLEXIVA",
          confianza: 0.95,
          justificacion_global: "consenso docente",
        },
      },
    }
    setupFetchMock({
      "/n-level-distribution": () => mockResponse,
      "/api/v1/classifications/": () => mockClassificationLegadaNormalizadaPorElBackend,
    })
    renderWithRouter(
      <EpisodeNLevelView
        getToken={fakeGetToken}
        initialEpisodeId="11111111-2222-3333-4444-555555555555"
      />,
    )
    await waitFor(() => {
      expect(screen.getByText("Verificacion")).toBeInTheDocument()
    })
    const filaVerificacion = screen.getByText("Verificacion").closest("div")
    expect(filaVerificacion).toHaveTextContent(/ausente/i)
    const filaVerbalizacion = screen.getByText("Verbalizacion").closest("div")
    expect(filaVerbalizacion).toHaveTextContent(/presente/i)
    // La dimension que en el registro original era `oraculo: false` tiene que
    // mostrarse como "interlocutor" — NO en blanco (ese era el bug de QA).
    const filaAutonomia = screen.getByText("Autonomia").closest("div")
    expect(filaAutonomia).toHaveTextContent(/interlocutor/i)
    expect(screen.queryByText(/no evaluable/i)).not.toBeInTheDocument()
  })

  test("dato degradado (booleanos + oraculo crudo, sin normalizar) no rompe el render", async () => {
    // Borde defensivo: si por lo que sea la normalizacion del backend
    // fallara y el dict crudo llegara tal cual al frontend (booleanos en
    // V/E/J + `oraculo` en autonomia — la forma REAL pre-B2a), el componente
    // NO debe crashear. Autonomia puede quedar sin label legible en este
    // caso patologico (residual, documentado) — lo que NO es aceptable es
    // una excepcion que tire abajo toda la vista.
    const mockClassificationCruda = {
      ...mockClassificationConDimNoEvaluable,
      regimen_llm: {
        ...mockClassificationConDimNoEvaluable.regimen_llm,
        raw: {
          verbalizacion: { presente: true, evidencia: "explica el porque" },
          verificacion: { presente: false, evidencia: "" },
          justificacion: { presente: true, evidencia: "defiende su eleccion" },
          oraculo: false,
          autonomia: { oraculo: false, evidencia: "razona sin que se lo pidan" },
          regimen: "REFLEXIVA",
          confianza: 0.95,
          justificacion_global: "consenso docente",
        },
      },
    }
    setupFetchMock({
      "/n-level-distribution": () => mockResponse,
      "/api/v1/classifications/": () => mockClassificationCruda,
    })
    expect(() => {
      renderWithRouter(
        <EpisodeNLevelView
          getToken={fakeGetToken}
          initialEpisodeId="11111111-2222-3333-4444-555555555555"
        />,
      )
    }).not.toThrow()
    await waitFor(() => {
      expect(screen.getByText("Verificacion")).toBeInTheDocument()
    })
    const filaVerbalizacion = screen.getByText("Verbalizacion").closest("div")
    expect(filaVerbalizacion).toHaveTextContent(/presente/i)
  })
})
