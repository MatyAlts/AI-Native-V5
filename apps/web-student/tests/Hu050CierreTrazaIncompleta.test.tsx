/**
 * Aceptacion HU-050 C04 (orquestador, antes de construir; el constructor no
 * la modifica). Desde la HU-050, `POST /classify_episode/{id}` responde 202
 * «traza incompleta» mientras la cola del CTR no guardo el cierre. El cierre
 * del alumno no puede tratar ese 202 como una clasificacion ni como un error.
 *
 * C04a  Si el classifier responde 202 siempre: la web reintenta (mas de un
 *       pedido), no muestra error ni el panel de clasificacion («sin
 *       reflexión») armado con el cuerpo del 202, y termina mostrando «Tu cierre se está procesando».
 *       Los reintentos terminan dentro de 60 s.
 * C04b  Si el primer pedido da 202 y el siguiente 201 con la clasificacion:
 *       se muestra el panel de clasificacion normal (con reflexion salteada:
 *       «Cierre del ejercicio · sin reflexión»), despues de al menos dos
 *       pedidos, y no el aviso de «procesando».
 *
 * Hoy (antes de construir): `classifyEpisode` solo mira `r.ok`, asi que un
 * 202 se toma como clasificacion y se pinta un panel con `{detail: ...}`.
 */
import { act, fireEvent, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { EpisodeView } from "../src/pages/EpisodePage"
import { setupFetchMock } from "./_mocks"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

const TAREA_ID = "tp-hu050"
const EPISODIO_ID = "ep-hu050"
const ENTREGA_ID = "entrega-hu050"
const ORDEN = 1
const ACTIVE_EPISODE_KEY = "active-episode-id"

type Respuesta = { ok: boolean; status: number; body: () => unknown }

const INCOMPLETA: Respuesta = {
  ok: true,
  status: 202,
  body: () => ({ detail: "traza incompleta: el cierre todavia no esta guardado" }),
}
const CLASIFICACION: Respuesta = {
  ok: true,
  status: 201,
  body: () => ({
    episode_id: EPISODIO_ID,
    comision_id: "com-1",
    classifier_config_hash: "h",
    appropriation: "apropiacion_reflexiva",
    appropriation_reason: "x",
    ct_summary: 0.5,
    ccd_mean: 0.5,
    ccd_orphan_ratio: 0.1,
    cii_stability: 0.5,
    cii_evolution: 0.5,
    is_current: true,
    subgrupo: null,
    regimen_llm: null,
    pasiva_por_sobreuso: false,
    cii_iteraciones: null,
    features: {},
  }),
}

function montar(respuestas: Respuesta[]) {
  let pedidos = 0
  const base = {
    [`/api/v1/episodes/${EPISODIO_ID}/close`]: () => ({ ok: true }),
    [`/api/v1/entregas/${ENTREGA_ID}/ejercicio/${ORDEN}`]: () => ({ id: ENTREGA_ID }),
    "/resume": () => ({ ok: true }),
    [`/api/v1/tareas-practicas/${TAREA_ID}/ejercicios`]: () => [
      {
        id: "tpe-1",
        tarea_practica_id: TAREA_ID,
        ejercicio_id: "ej-1",
        orden: ORDEN,
        peso_en_tp: "1.00",
        ejercicio: {
          id: "ej-1",
          titulo: "E1",
          enunciado: "Enunciado 1",
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
      opened_at: "2026-10-14T20:00:00Z",
      closed_at: null,
      last_code_snapshot: null,
      messages: [],
      notes: [],
      ejercicio_id: "ej-1",
      ejercicio_orden: ORDEN,
    }),
  }
  // El handler del classify va primero: el mock matchea por prefijo y
  // `/api/v1/episodes/...` no debe tapar a `/classify_episode/...`.
  setupFetchMock({
    [`/api/v1/classify_episode/${EPISODIO_ID}`]: {
      get ok() {
        return (respuestas[Math.min(pedidos, respuestas.length - 1)] ?? INCOMPLETA).ok
      },
      get status() {
        const r = respuestas[Math.min(pedidos, respuestas.length - 1)] ?? INCOMPLETA
        pedidos += 1
        return r.status
      },
      body: () => (respuestas[Math.min(pedidos - 1, respuestas.length - 1)] ?? INCOMPLETA).body(),
    },
    ...base,
  })
  const vista = render(
    <EpisodeView
      episodeId={EPISODIO_ID}
      onExit={() => {}}
      ejercicioContext={{ entregaId: ENTREGA_ID, ejercicioId: "ej-1", ejercicioOrden: ORDEN }}
    />,
  )
  return { vista, pedidosClassify: () => pedidos }
}

async function cerrarYSaltearReflexion(vista: ReturnType<typeof render>) {
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

async function dejarPasar(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  resetMonacoMock()
  window.sessionStorage.clear()
  window.localStorage.clear()
  window.sessionStorage.setItem(ACTIVE_EPISODE_KEY, EPISODIO_ID)
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe("HU-050 C04 · el cierre ante una traza incompleta (202)", () => {
  it("C04a: con 202 siempre reintenta y termina en «Tu cierre se está procesando»", async () => {
    const { vista, pedidosClassify } = montar([INCOMPLETA])
    await cerrarYSaltearReflexion(vista)
    await dejarPasar(60_000)
    await waitFor(() => expect(vista.getByText(/tu cierre se está procesando/i)).toBeTruthy())
    expect(pedidosClassify()).toBeGreaterThan(1)
    // Ni error ni un panel armado con el cuerpo del 202.
    expect(vista.queryByText(/error/i)).toBeNull()
    expect(vista.queryByText(/sin reflexión/i)).toBeNull()
    // Los reintentos terminaron: no hay pedidos nuevos despues de los 60 s.
    const hechos = pedidosClassify()
    await dejarPasar(60_000)
    expect(pedidosClassify()).toBe(hechos)
  })

  it("C04b: 202 y despues 201 muestra la clasificacion normal", async () => {
    const { vista, pedidosClassify } = montar([INCOMPLETA, CLASIFICACION])
    await cerrarYSaltearReflexion(vista)
    await dejarPasar(60_000)
    // Panel de clasificacion del cierre sin reflexion (el mismo que hoy sale con un 201 directo).
    await waitFor(() => expect(vista.getByText(/sin reflexión/i)).toBeTruthy())
    expect(pedidosClassify()).toBeGreaterThanOrEqual(2)
    expect(vista.queryByText(/tu cierre se está procesando/i)).toBeNull()
  })
})
