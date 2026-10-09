/**
 * Hallazgo #1: "Cerrar episodio" en un ejercicio de TP multi-ejercicio debe
 * dejar el ejercicio marcado como completado (PATCH /entregas/:id/ejercicio/:orden).
 * Antes solo lo marcaban el "Siguiente ejercicio" del panel de clasificacion y
 * el cierre del modal de reflexion: si el alumno cerraba y recargaba, el
 * ejercicio quedaba pendiente.
 */
import { act, fireEvent, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { EpisodeView } from "../src/pages/EpisodePage"
import { setupFetchMock } from "./_mocks"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

const TAREA_ID = "tp-cierra-marca"
const EPISODIO_ID = "ep-cierra-marca"
const ENTREGA_ID = "entrega-cierra-marca"
const ORDEN = 2
const ACTIVE_EPISODE_KEY = "active-episode-id"

type Llamada = { url: string; method: string; body: string }

function montar(opciones: { patchFalla?: boolean; classifyFalla?: boolean } = {}) {
  const llamadas: Llamada[] = []
  setupFetchMock({
    [`/api/v1/episodes/${EPISODIO_ID}/close`]: () => ({ ok: true }),
    [`/api/v1/classify_episode/${EPISODIO_ID}`]: () => {
      if (opciones.classifyFalla) throw new Error("classifier caido")
      return { appropriation: "apropiacion_reflexiva", features: {} }
    },
    [`/api/v1/entregas/${ENTREGA_ID}/ejercicio/${ORDEN}`]: () => {
      if (opciones.patchFalla) throw new Error("patch caido")
      return { id: ENTREGA_ID }
    },
    "/resume": () => ({ ok: true }),
    [`/api/v1/tareas-practicas/${TAREA_ID}/ejercicios`]: () => [
      {
        id: "tpe-2",
        tarea_practica_id: TAREA_ID,
        ejercicio_id: "ej-2",
        orden: ORDEN,
        peso_en_tp: "1.00",
        ejercicio: {
          id: "ej-2",
          titulo: "E2",
          enunciado: "Enunciado 2",
          language: "python",
          inicial_codigo: null,
          test_cases: [],
        },
      },
    ],
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
      ejercicio_id: "ej-2",
      ejercicio_orden: ORDEN,
    }),
  })
  const stub = globalThis.fetch
  vi.stubGlobal("fetch", (url: string | URL | Request, init?: RequestInit) => {
    llamadas.push({
      url: typeof url === "string" ? url : url.toString(),
      method: init?.method ?? "GET",
      body: String(init?.body ?? ""),
    })
    return (stub as typeof fetch)(url as never, init)
  })
  const vista = render(
    <EpisodeView
      episodeId={EPISODIO_ID}
      onExit={() => {}}
      ejercicioContext={{ entregaId: ENTREGA_ID, ejercicioId: "ej-2", ejercicioOrden: ORDEN }}
    />,
  )
  return { llamadas, vista }
}

const patches = (ll: Llamada[]) =>
  ll.filter((l) => l.method === "PATCH" && l.url.includes(`/entregas/${ENTREGA_ID}/ejercicio/`))

async function escribir(texto: string) {
  await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
  await act(async () => {
    editoresCreados[0]?.__tipear(texto)
  })
}

async function cerrar(vista: ReturnType<typeof render>) {
  const btn = await vista.findByTestId("close-episode-button")
  await act(async () => {
    fireEvent.click(btn)
  })
}

beforeEach(() => {
  resetMonacoMock()
  window.sessionStorage.clear()
  window.localStorage.clear()
  window.sessionStorage.setItem(ACTIVE_EPISODE_KEY, EPISODIO_ID)
})
afterEach(() => vi.unstubAllGlobals())

describe("handleClose marca el ejercicio completado", () => {
  it("al cerrar con codigo, manda UN PATCH completado:true al ejercicio", async () => {
    const { llamadas, vista } = montar()
    await escribir("print('hola')")
    await cerrar(vista)
    await waitFor(() => expect(patches(llamadas)).toHaveLength(1))
    expect(JSON.parse(patches(llamadas)[0]?.body ?? "{}")).toMatchObject({
      completado: true,
      episode_id: EPISODIO_ID,
      ejercicio_id: "ej-2",
    })
  })

  it("si el PATCH falla, igual clasifica y suelta la llave (cierre no se rompe)", async () => {
    const { llamadas, vista } = montar({ patchFalla: true })
    await escribir("print('hola')")
    await cerrar(vista)
    await waitFor(() =>
      expect(llamadas.some((l) => l.url.includes("/classify_episode/"))).toBe(true),
    )
    await waitFor(() => expect(window.sessionStorage.getItem(ACTIVE_EPISODE_KEY)).toBeNull())
  })

  it("si la clasificacion falla, el ejercicio igual queda marcado (panel fallback)", async () => {
    const { llamadas, vista } = montar({ classifyFalla: true })
    await escribir("print('hola')")
    await cerrar(vista)
    await waitFor(() => expect(patches(llamadas)).toHaveLength(1))
  })

  it("sin codigo no marca (safeguard hayCodigo se mantiene)", async () => {
    const { llamadas, vista } = montar()
    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    await cerrar(vista)
    await waitFor(() =>
      expect(llamadas.some((l) => l.url.includes("/classify_episode/"))).toBe(true),
    )
    expect(patches(llamadas)).toHaveLength(0)
  })

  it("'Siguiente ejercicio' despues de cerrar no duplica el PATCH", async () => {
    const { llamadas, vista } = montar()
    await escribir("print('hola')")
    await cerrar(vista)
    await waitFor(() => expect(patches(llamadas)).toHaveLength(1))
    // Saltear la reflexion lleva al panel de clasificacion; "Siguiente
    // ejercicio" vuelve a pedir el marcado, que debe ser no-op (markedCompletedRef).
    const saltar = await vista.findByRole("button", { name: /no quiero reflexionar/i })
    await act(async () => {
      fireEvent.click(saltar)
    })
    const siguiente = await vista.findByRole("button", { name: /siguiente ejercicio/i })
    await act(async () => {
      fireEvent.click(siguiente)
    })
    expect(patches(llamadas)).toHaveLength(1)
  })
})
