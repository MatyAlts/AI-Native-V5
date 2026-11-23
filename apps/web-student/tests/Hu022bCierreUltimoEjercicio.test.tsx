/**
 * HU-022 (vuelta 2), C05 b (F30): al cerrar el ÚLTIMO ejercicio de la TP el
 * panel de cierre no ofrece "Siguiente ejercicio →", que no existe: ofrece
 * volver al TP. En un ejercicio que no es el último sigue el "Siguiente".
 * Prueba propia del constructor (sin aceptación congelada para este punto).
 */
import { act, fireEvent, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { EpisodeView } from "../src/pages/EpisodePage"
import { setupFetchMock } from "./_mocks"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

const TAREA_ID = "tp-ultimo"
const EPISODIO_ID = "ep-ultimo"
const ENTREGA_ID = "entrega-ultimo"
const ACTIVE_EPISODE_KEY = "active-episode-id"

function tpEj(orden: number) {
  return {
    id: `tpe-${orden}`,
    tarea_practica_id: TAREA_ID,
    ejercicio_id: `ej-${orden}`,
    orden,
    peso_en_tp: "1.00",
    ejercicio: {
      id: `ej-${orden}`,
      titulo: `E${orden}`,
      enunciado: `Enunciado ${orden}`,
      language: "python",
      inicial_codigo: null,
      test_cases: [],
    },
  }
}

function montar(orden: number, onExit: () => void = () => {}) {
  setupFetchMock({
    [`/api/v1/episodes/${EPISODIO_ID}/close`]: () => ({ ok: true }),
    [`/api/v1/classify_episode/${EPISODIO_ID}`]: () => ({
      appropriation: "apropiacion_reflexiva",
      features: {},
    }),
    [`/api/v1/entregas/${ENTREGA_ID}/ejercicio/${orden}`]: () => ({ id: ENTREGA_ID }),
    "/resume": () => ({ ok: true }),
    [`/api/v1/tareas-practicas/${TAREA_ID}/ejercicios`]: () => [tpEj(1), tpEj(2), tpEj(3)],
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
      opened_at: "2026-11-23T10:00:00Z",
      closed_at: null,
      last_code_snapshot: null,
      messages: [],
      notes: [],
      ejercicio_id: `ej-${orden}`,
      ejercicio_orden: orden,
    }),
  })
  return render(
    <EpisodeView
      episodeId={EPISODIO_ID}
      onExit={onExit}
      ejercicioContext={{ entregaId: ENTREGA_ID, ejercicioId: `ej-${orden}`, ejercicioOrden: orden }}
    />,
  )
}

async function cerrarYSaltear(vista: ReturnType<typeof render>) {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
  await act(async () => {
    editoresCreados[0]?.__tipear("print('hola')")
  })
  const btn = await vista.findByTestId("close-episode-button")
  await act(async () => {
    fireEvent.click(btn)
  })
  const saltar = await vista.findByRole("button", { name: /no quiero reflexionar/i })
  await act(async () => {
    fireEvent.click(saltar)
  })
}

beforeEach(() => {
  resetMonacoMock()
  window.sessionStorage.clear()
  window.localStorage.clear()
  window.sessionStorage.setItem(ACTIVE_EPISODE_KEY, EPISODIO_ID)
})
afterEach(() => vi.unstubAllGlobals())

describe("C05 b · el cierre del último ejercicio vuelve al TP", () => {
  it("en el último ejercicio no ofrece 'Siguiente ejercicio' y vuelve al TP", async () => {
    const onExit = vi.fn()
    const vista = montar(3, onExit)
    await cerrarYSaltear(vista)
    const volver = await vista.findByRole("button", { name: /volver al tp/i })
    expect(vista.queryByRole("button", { name: /siguiente ejercicio/i })).toBeNull()
    await act(async () => {
      fireEvent.click(volver)
    })
    await waitFor(() => expect(onExit).toHaveBeenCalledTimes(1))
  })

  it("en un ejercicio que no es el último sigue ofreciendo 'Siguiente ejercicio'", async () => {
    const vista = montar(2)
    await cerrarYSaltear(vista)
    await vista.findByRole("button", { name: /siguiente ejercicio/i })
    expect(vista.queryByRole("button", { name: /volver al tp/i })).toBeNull()
  })
})
