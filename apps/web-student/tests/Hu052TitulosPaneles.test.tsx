/**
 * HU-052 (nivel S): en el episodio, los títulos de los paneles (Consigna,
 * Editor de código y Tutor socrático) son los títulos principales y tienen que
 * notarse: se muestran como h2 grandes (text-lg) y en negrita (font-bold).
 * N01: los textos de los títulos no cambian y siguen siendo h2.
 */
import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { EpisodeView } from "../src/pages/EpisodePage"
import { setupFetchMock } from "./_mocks"
import { resetMonacoMock } from "./_monacoMock"

const TAREA_ID = "tp-hu052"
const EPISODIO_ID = "ep-hu052"

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

describe("HU-052 · títulos de los paneles del episodio", () => {
  for (const titulo of ["Consigna", "Editor de código", "Tutor socrático"]) {
    it(`"${titulo}" es un h2 grande y en negrita`, async () => {
      montar()
      const h = await screen.findByRole("heading", { level: 2, name: titulo })
      expect(h.className).toContain("text-lg")
      expect(h.className).toContain("font-bold")
      expect(h.className).not.toContain("text-sm")
    })
  }
})
