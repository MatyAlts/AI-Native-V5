/**
 * QA 08/10 #9 y #13: etiquetas de los paneles del episodio.
 *  - #9: el badge del panel del tutor decia "Mistral" hardcodeado aunque el
 *    episodio use otro modelo. El cliente NO recibe el modelo (ni el open ni el
 *    estado ni el stream lo traen), asi que se muestra "Tutor", sin inventar.
 *  - #13: escribir codigo es N2, no N3 (N3 es ejecucion).
 */
import { cleanup, render, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { EpisodeView } from "../src/pages/EpisodePage"
import { setupFetchMock } from "./_mocks"
import { resetMonacoMock } from "./_monacoMock"

const TAREA_ID = "tp-paneles"
const EPISODIO_ID = "ep-paneles"

function montar() {
  setupFetchMock({
    "/resume": () => ({ ok: true }),
    [`/api/v1/tareas-practicas/${TAREA_ID}`]: () => ({
      id: TAREA_ID,
      codigo: "TP",
      titulo: "TP",
      enunciado: "x",
      fecha_inicio: null,
      fecha_fin: null,
      peso: "1.00",
      estado: "published",
      version: 1,
      inicial_codigo: null,
      language: "python",
      permite_pausa: true,
    }),
    [`/api/v1/episodes/${EPISODIO_ID}`]: () => ({
      episode_id: EPISODIO_ID,
      tarea_practica_id: TAREA_ID,
      comision_id: "com-1",
      estado: "open",
      opened_at: "2026-08-27T10:00:00Z",
      closed_at: null,
      last_code_snapshot: null,
      messages: [],
      notes: [],
    }),
  })
  return render(<EpisodeView episodeId={EPISODIO_ID} onExit={() => {}} />)
}

beforeEach(() => {
  resetMonacoMock()
  window.sessionStorage.clear()
  window.localStorage.clear()
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("etiquetas de paneles del episodio", () => {
  it("#13: el panel del editor es N2 con el color N2", async () => {
    const vista = montar()
    const editor = await vista.findByLabelText("Editor de código")
    const kicker = within(editor).getByTestId("section-kicker-n2")
    expect(kicker.textContent).toContain("N2")
    expect(kicker.innerHTML).toContain("--color-level-n2")
    expect(kicker.innerHTML).not.toContain("--color-level-n3")
    expect(vista.queryByTestId("section-kicker-n3")).toBeNull()
  })

  it("#9: el badge del tutor no inventa 'Mistral' y dice 'Tutor'", async () => {
    const vista = montar()
    const tutor = await vista.findByLabelText("Tutor socrático")
    await waitFor(() => expect(within(tutor).getByTestId("section-kicker-n4")).toBeDefined())
    const kicker = within(tutor).getByTestId("section-kicker-n4")
    expect(kicker.textContent).not.toContain("Mistral")
    expect(kicker.textContent).toMatch(/Tutor socrático\s*Tutor$/)
  })
})
