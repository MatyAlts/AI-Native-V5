/**
 * Un episodio que no se pudo cargar (404 tras los reintentos) NO saca al alumno
 * en silencio.
 *
 * POR QUE EXISTE ESTE ARCHIVO
 * ---------------------------
 * 2026-10-16 y 2026-10-23: con los workers del CTR caidos, `POST /events`
 * devolvia 202 pero el episodio nunca llegaba a Postgres. `getEpisodeState`
 * agotaba sus reintentos con 404 y la hidratacion de `EpisodePage` llamaba a
 * `salir()`: el alumno apretaba "Empezar" y volvia a la lista sin ningun
 * mensaje, sin saber si habia fallado algo ni si reintentar.
 *
 * Contrato (spec student-exercise-flow): 404 => mensaje de que el ejercicio no
 * termino de abrirse + "Reintentar" + "Volver", sin navegar solo, y el marcador
 * de episodio activo se limpia (asi "Volver" no reabre el mismo episodio).
 * 403 conserva el comportamiento previo (`salir()`).
 *
 * `getEpisodeState` se mockea entero: su backoff real tarda ~3 s y lo que se
 * prueba aca es lo que hace la pantalla cuando ya se agoto.
 */
import { fireEvent, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { setupFetchMock } from "./_mocks"
import { resetMonacoMock } from "./_monacoMock"

vi.mock("../src/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/lib/api")>()
  return { ...actual, getEpisodeState: vi.fn() }
})

import { EpisodeStateError, getEpisodeState } from "../src/lib/api"
import { EpisodeView } from "../src/pages/EpisodePage"

const TAREA_ID = "tp-e2-agenda"
const EPISODIO_ID = "ep-ejercicio-1"
const ACTIVE_EPISODE_KEY = "active-episode-id"

const ESTADO_EPISODIO = {
  episode_id: EPISODIO_ID,
  tarea_practica_id: TAREA_ID,
  comision_id: "com-1",
  estado: "open",
  opened_at: "2026-08-27T10:00:00Z",
  closed_at: null,
  last_code_snapshot: null,
  messages: [],
  notes: [],
  ejercicio_id: "ej-1",
  ejercicio_orden: 1,
}

const TAREA = {
  id: TAREA_ID,
  codigo: "TP2",
  titulo: "Agenda de turnos",
  enunciado: "Enunciado",
  fecha_inicio: null,
  fecha_fin: null,
  peso: "1.00",
  estado: "published",
  version: 1,
  inicial_codigo: null,
  language: "python",
  permite_pausa: true,
}

const EJERCICIOS_TP = [
  {
    id: "tpe-1",
    tarea_practica_id: TAREA_ID,
    ejercicio_id: "ej-1",
    orden: 1,
    peso_en_tp: "1.00",
    ejercicio: {
      id: "ej-1",
      titulo: "E1",
      enunciado: "Escribi la funcion saludar",
      language: "python",
      inicial_codigo: null,
      test_cases: [],
    },
  },
]

const getEstado = vi.mocked(getEpisodeState)

function montar() {
  setupFetchMock({
    "/resume": () => ({ ok: true }),
    [`/api/v1/tareas-practicas/${TAREA_ID}/ejercicios`]: () => EJERCICIOS_TP,
    [`/api/v1/tareas-practicas/${TAREA_ID}`]: () => TAREA,
  })
  const salidas: number[] = []
  const vista = render(
    <EpisodeView episodeId={EPISODIO_ID} onExit={() => salidas.push(Date.now())} />,
  )
  return { salidas, vista }
}

beforeEach(() => {
  resetMonacoMock()
  window.sessionStorage.clear()
  window.localStorage.clear()
  window.sessionStorage.setItem(ACTIVE_EPISODE_KEY, EPISODIO_ID)
  getEstado.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("404 al hidratar el episodio", () => {
  it("muestra el mensaje de apertura con Reintentar y Volver, sin salir solo", async () => {
    getEstado.mockRejectedValue(new EpisodeStateError(404, "get episode state failed: 404"))

    const { salidas, vista } = montar()

    expect(await vista.findByText(/no termin[oó] de abrirse/i)).toBeTruthy()
    expect(vista.getByRole("button", { name: /Reintentar/i })).toBeTruthy()
    expect(vista.getByRole("button", { name: /Volver/i })).toBeTruthy()
    expect(salidas).toHaveLength(0)
  })

  it("limpia el marcador de episodio activo para que Volver no reabra el mismo", async () => {
    getEstado.mockRejectedValue(new EpisodeStateError(404, "x"))

    const { vista } = montar()
    await vista.findByText(/no termin[oó] de abrirse/i)

    expect(window.sessionStorage.getItem(ACTIVE_EPISODE_KEY)).toBeNull()
  })

  it("Reintentar con el episodio ya persistido carga normal y quita el error", async () => {
    getEstado.mockRejectedValueOnce(new EpisodeStateError(404, "x"))
    getEstado.mockResolvedValue(ESTADO_EPISODIO as never)

    const { salidas, vista } = montar()
    const reintentar = await vista.findByRole("button", { name: /Reintentar/i })
    fireEvent.click(reintentar)

    await waitFor(() => expect(vista.queryByText(/no termin[oó] de abrirse/i)).toBeNull())
    await waitFor(() => expect(getEstado).toHaveBeenCalledTimes(2))
    expect(await vista.findByText(/Agenda de turnos|TP2/)).toBeTruthy()
    expect(salidas).toHaveLength(0)
  })

  it("Reintentar que vuelve a dar 404 sigue mostrando el error (no queda en blanco)", async () => {
    getEstado.mockRejectedValue(new EpisodeStateError(404, "x"))

    const { vista } = montar()
    fireEvent.click(await vista.findByRole("button", { name: /Reintentar/i }))

    await waitFor(() => expect(getEstado).toHaveBeenCalledTimes(2))
    expect(await vista.findByText(/no termin[oó] de abrirse/i)).toBeTruthy()
  })

  it("Volver sale una sola vez por el camino de siempre", async () => {
    getEstado.mockRejectedValue(new EpisodeStateError(404, "x"))

    const { salidas, vista } = montar()
    fireEvent.click(await vista.findByRole("button", { name: /Volver/i }))

    await waitFor(() => expect(salidas).toHaveLength(1))
    expect(window.sessionStorage.getItem(ACTIVE_EPISODE_KEY)).toBeNull()
  })
})

describe("otros errores de hidratacion", () => {
  it("403 conserva el comportamiento previo: sale solo", async () => {
    getEstado.mockRejectedValue(new EpisodeStateError(403, "forbidden"))

    const { salidas, vista } = montar()

    await waitFor(() => expect(salidas).toHaveLength(1))
    expect(vista.queryByText(/no termin[oó] de abrirse/i)).toBeNull()
    expect(window.sessionStorage.getItem(ACTIVE_EPISODE_KEY)).toBeNull()
  })

  it("un 500 sigue con su mensaje generico, no con el de apertura", async () => {
    getEstado.mockRejectedValue(new EpisodeStateError(500, "boom"))

    const { vista } = montar()

    expect(await vista.findByText(/No se pudo cargar el episodio/i)).toBeTruthy()
    expect(vista.queryByText(/no termin[oó] de abrirse/i)).toBeNull()
  })
})
