/**
 * El boton "Pedir ayuda a tu docente" en la pantalla del episodio
 * (change alumno-pide-ayuda-al-docente).
 *
 * Dos lugares: el header del episodio abierto y la pantalla de error "El
 * ejercicio no terminó de abrirse" (el caso por el que existe el change: el
 * alumno quedaba mudo cuando los workers del CTR se caian).
 *
 * Y una promesa de tesis: abrir el modal NO pausa, NO cierra ni abandona el
 * episodio, y no emite nada al CTR. Se prueba mirando TODOS los fetch que
 * ocurren al abrirlo y al enviar.
 */
import { fireEvent, render, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { resetMonacoMock } from "./_monacoMock"

vi.mock("../src/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/lib/api")>()
  return { ...actual, getEpisodeState: vi.fn() }
})

import { EpisodeStateError, getEpisodeState } from "../src/lib/api"
import { EpisodeView } from "../src/pages/EpisodePage"

const TAREA_ID = "tp-e2-agenda"
const EPISODIO_ID = "ep-ejercicio-1"
const ENTREGA_ID = "entrega-1"

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
let urls: { url: string; method: string }[]

function stubFetch() {
  urls = []
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      urls.push({ url, method: init?.method ?? "GET" })
      let body: unknown = { data: [], meta: { cursor_next: null } }
      if (url.includes("/pedidos-ayuda/mios")) body = []
      else if (url.includes("/pedidos-ayuda")) body = { id: "p1", estado: "pendiente" }
      else if (url.includes(`/tareas-practicas/${TAREA_ID}/ejercicios`)) body = EJERCICIOS_TP
      else if (url.includes(`/tareas-practicas/${TAREA_ID}`)) body = TAREA
      else if (url.includes("/resume")) body = { ok: true }
      return Promise.resolve({
        ok: true,
        status: url.endsWith("/api/v1/pedidos-ayuda") ? 201 : 200,
        json: () => Promise.resolve(body),
        text: () => Promise.resolve(JSON.stringify(body)),
      } as Response)
    }),
  )
}

function montar(conContexto: boolean) {
  stubFetch()
  return render(
    <EpisodeView
      episodeId={EPISODIO_ID}
      onExit={() => undefined}
      {...(conContexto
        ? {
            ejercicioContext: {
              entregaId: ENTREGA_ID,
              ejercicioId: "ej-1",
              ejercicioOrden: 1,
              tareaId: TAREA_ID,
            },
          }
        : {})}
    />,
  )
}

beforeEach(() => {
  resetMonacoMock()
  window.sessionStorage.clear()
  window.localStorage.clear()
  getEstado.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("header del episodio abierto", () => {
  it("muestra el boton y el pedido sale con el episodio y el ejercicio", async () => {
    getEstado.mockResolvedValue(ESTADO_EPISODIO as never)
    const vista = montar(true)

    const boton = await vista.findByTestId("pedir-ayuda-button")
    fireEvent.click(boton)
    fireEvent.click(await vista.findByLabelText(/No puedo avanzar/i))
    fireEvent.click(within(vista.getByRole("dialog")).getByRole("button", { name: /^Enviar/i }))

    await waitFor(() => expect(vista.getByText(/Tu pedido le llegó a tu docente/i)).toBeTruthy())
    const post = vi
      .mocked(fetch)
      .mock.calls.find(
        ([u, init]) =>
          String(u) === "/api/v1/pedidos-ayuda" && (init as RequestInit)?.method === "POST",
      )
    const body = JSON.parse(String((post?.[1] as RequestInit).body))
    expect(body).toMatchObject({
      tarea_practica_id: TAREA_ID,
      episode_id: EPISODIO_ID,
      ejercicio_orden: 1,
      entrega_id: ENTREGA_ID,
      categoria: "no_puedo_avanzar",
      contexto: { pantalla: "episodio" },
    })
  })

  it("abrir el modal y enviar NO toca el episodio: ni pausa, ni cierre, ni abandono, ni eventos", async () => {
    getEstado.mockResolvedValue(ESTADO_EPISODIO as never)
    const vista = montar(true)
    const boton = await vista.findByTestId("pedir-ayuda-button")
    // Dejar que termine lo que el episodio hace solo al montar.
    await waitFor(() => expect(urls.some((u) => u.url.includes("/ejercicios"))).toBe(true))
    const antes = urls.length

    fireEvent.click(boton)
    fireEvent.click(await vista.findByLabelText(/No puedo avanzar/i))
    fireEvent.click(within(vista.getByRole("dialog")).getByRole("button", { name: /^Enviar/i }))
    await waitFor(() => expect(vista.getByText(/Tu pedido le llegó/i)).toBeTruthy())

    const nuevas = urls.slice(antes).map((u) => u.url)
    expect(nuevas.length).toBeGreaterThan(0)
    for (const u of nuevas) {
      expect(u).toContain("/api/v1/pedidos-ayuda")
      expect(u).not.toMatch(/\/abandoned|\/close|\/pause|\/resume|\/events|\/episodes/)
    }
  })
})

describe("pantalla 'El ejercicio no terminó de abrirse'", () => {
  it("con el contexto del ejercicio, ofrece pedir ayuda con el episodio de la URL", async () => {
    getEstado.mockRejectedValue(new EpisodeStateError(404, "x"))
    const vista = montar(true)

    await vista.findByText(/no termin[oó] de abrirse/i)
    fireEvent.click(vista.getByTestId("pedir-ayuda-button"))
    fireEvent.click(await vista.findByLabelText(/Error de la plataforma/i))
    fireEvent.click(within(vista.getByRole("dialog")).getByRole("button", { name: /^Enviar/i }))

    await waitFor(() => expect(vista.getByText(/Tu pedido le llegó a tu docente/i)).toBeTruthy())
    const post = vi
      .mocked(fetch)
      .mock.calls.find(
        ([u, init]) =>
          String(u) === "/api/v1/pedidos-ayuda" && (init as RequestInit)?.method === "POST",
      )
    const body = JSON.parse(String((post?.[1] as RequestInit).body))
    expect(body).toMatchObject({
      tarea_practica_id: TAREA_ID,
      episode_id: EPISODIO_ID,
      ejercicio_orden: 1,
      entrega_id: ENTREGA_ID,
      categoria: "error_plataforma",
      contexto: { pantalla: "episodio_error" },
    })
    expect(body.contexto.error_visible).toMatch(/no terminó de abrirse/i)
  })

  it("sin contexto de TP (TP monolitica tras un F5) no hay boton: queda Volver", async () => {
    getEstado.mockRejectedValue(new EpisodeStateError(404, "x"))
    const vista = montar(false)

    await vista.findByText(/no termin[oó] de abrirse/i)

    expect(vista.queryByTestId("pedir-ayuda-button")).toBeNull()
    expect(vista.getByRole("button", { name: /Volver/i })).toBeTruthy()
  })

  it("un error que no es 'no se abrio' (500) no ofrece el boton", async () => {
    getEstado.mockRejectedValue(new EpisodeStateError(500, "boom"))
    const vista = montar(true)

    await vista.findByText(/No se pudo cargar el episodio/i)

    expect(vista.queryByTestId("pedir-ayuda-button")).toBeNull()
  })
})
