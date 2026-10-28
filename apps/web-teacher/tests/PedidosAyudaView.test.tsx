/**
 * Vista "Pedidos de ayuda" del docente (change alumno-pide-ayuda-al-docente).
 *
 * El docente ve lo que los alumnos de SU comision le pidieron, con el dato
 * adjunto (TP, ejercicio, episodio, hora). MVP: no hay respuesta escrita, solo
 * "Marcar resuelto"; el alumno ve el estado.
 */
import { fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"
import { PedidosAyudaView } from "../src/views/PedidosAyudaView"
import { renderWithRouter } from "./_mocks"

const COMISION_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
const TP_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
const EP_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
const getToken = async () => "tok"

function pedido(over: Record<string, unknown> = {}) {
  return {
    id: "p1",
    comision_id: COMISION_ID,
    student_pseudonym: "b1b1b1b1-0001-0001-0001-000000000001",
    tarea_practica_id: TP_ID,
    entrega_id: null,
    ejercicio_orden: 2,
    episode_id: EP_ID,
    categoria: "no_puedo_avanzar",
    mensaje: "no entiendo el while",
    contexto: { pantalla: "episodio" },
    estado: "pendiente",
    resuelto_por: null,
    resuelto_at: null,
    created_at: new Date().toISOString(),
    ...over,
  }
}

interface Estado {
  pendientes: ReturnType<typeof pedido>[]
  resueltos: ReturnType<typeof pedido>[]
}

let calls: { url: string; method: string }[]

function stub(e: Estado) {
  calls = []
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET"
      calls.push({ url: String(url), method })
      let body: unknown = { data: [], meta: { cursor_next: null } }
      const m = String(url).match(/\/api\/v1\/pedidos-ayuda\/([^/]+)\/resolver/)
      if (m && method === "PATCH") {
        const idx = e.pendientes.findIndex((p) => p.id === m[1])
        const [p] = e.pendientes.splice(idx, 1)
        if (p) {
          const res = { ...p, estado: "resuelto", resuelto_at: new Date().toISOString() }
          e.resueltos.unshift(res)
          body = res
        }
      } else if (String(url).includes("/api/v1/pedidos-ayuda")) {
        const resueltos = String(url).includes("estado=resuelto")
        const data = resueltos ? e.resueltos : e.pendientes
        body = { data, meta: { pendientes: e.pendientes.length, total: data.length } }
      } else if (String(url).includes("/api/v1/tareas-practicas")) {
        body = {
          data: [{ id: TP_ID, codigo: "TP2", titulo: "Agenda de turnos" }],
          meta: { cursor_next: null },
        }
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(body),
        text: () => Promise.resolve(JSON.stringify(body)),
      } as Response)
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("PedidosAyudaView", () => {
  test("lista los pendientes con alumno, TP, ejercicio, categoria y mensaje", async () => {
    stub({ pendientes: [pedido()], resueltos: [] })
    renderWithRouter(<PedidosAyudaView comisionId={COMISION_ID} getToken={getToken} />)

    expect(await screen.findByText("no entiendo el while")).toBeTruthy()
    expect(screen.getByText(/Est\. 000001/)).toBeTruthy()
    expect(await screen.findByText(/TP2/)).toBeTruthy()
    expect(screen.getByText(/Ejercicio 2/)).toBeTruthy()
    expect(screen.getAllByText("No puedo avanzar").length).toBeGreaterThan(0)
    const lista = calls.find((c) => c.url.includes("/api/v1/pedidos-ayuda"))
    expect(lista?.url).toContain(`comision_id=${COMISION_ID}`)
    expect(lista?.url).toContain("estado=pendiente")
  })

  test("Ver episodio aparece solo si hay episode_id y apunta a la timeline", async () => {
    stub({
      pendientes: [
        pedido({ id: "p1" }),
        pedido({ id: "p2", episode_id: null, mensaje: "sin episodio" }),
      ],
      resueltos: [],
    })
    renderWithRouter(<PedidosAyudaView comisionId={COMISION_ID} getToken={getToken} />)

    await screen.findByText("sin episodio")
    const links = screen.getAllByRole("link", { name: /Ver episodio/i })
    expect(links).toHaveLength(1)
    expect(links[0]?.getAttribute("href")).toContain(`episodeId=${EP_ID}`)
    expect(links[0]?.getAttribute("href")).toContain("/episode-timeline")
  })

  test("Marcar resuelto hace PATCH .../resolver y mueve la fila a Resueltos", async () => {
    stub({ pendientes: [pedido()], resueltos: [] })
    renderWithRouter(<PedidosAyudaView comisionId={COMISION_ID} getToken={getToken} />)
    await screen.findByText("no entiendo el while")

    fireEvent.click(screen.getByRole("button", { name: /Marcar resuelto/i }))

    await waitFor(() =>
      expect(
        calls.some(
          (c) => c.method === "PATCH" && c.url.endsWith("/api/v1/pedidos-ayuda/p1/resolver"),
        ),
      ).toBe(true),
    )
    await waitFor(() => expect(screen.queryByText("no entiendo el while")).toBeNull())

    fireEvent.click(screen.getByRole("tab", { name: /Resueltos/i }))
    expect(await screen.findByText("no entiendo el while")).toBeTruthy()
    expect(screen.queryByRole("button", { name: /Marcar resuelto/i })).toBeNull()
  })

  test("sin pedidos pendientes muestra un vacio honesto", async () => {
    stub({ pendientes: [], resueltos: [] })
    renderWithRouter(<PedidosAyudaView comisionId={COMISION_ID} getToken={getToken} />)
    expect(await screen.findByText(/No hay pedidos pendientes/i)).toBeTruthy()
  })

  test("si el servidor rechaza (404), lo dice en vez de quedar en blanco", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 404,
          json: () => Promise.resolve({ detail: "Pedido no existe" }),
          text: () => Promise.resolve(JSON.stringify({ detail: "Pedido no existe" })),
        } as Response),
      ),
    )
    renderWithRouter(<PedidosAyudaView comisionId={COMISION_ID} getToken={getToken} />)
    expect(await screen.findByRole("alert")).toBeTruthy()
  })
})
