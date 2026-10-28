/**
 * Modal "Pedir ayuda a tu docente" (change alumno-pide-ayuda-al-docente).
 *
 * El pedido va a una PERSONA (los docentes de la comision), no al tutor: no
 * emite nada al CTR. Estos tests fijan el contrato del modal; que el boton no
 * toque el episodio se prueba en `PedirAyudaEnEpisodio.test.tsx`.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { PedirAyudaModal } from "../src/components/PedirAyudaModal"

const TP = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
const EP = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
const ENTREGA = "cccccccc-cccc-cccc-cccc-cccccccccccc"

interface Llamada {
  url: string
  method: string
  body: Record<string, unknown> | null
}

let llamadas: Llamada[]

function mockFetch(opts: {
  post?: { status: number; body: unknown }
  mios?: unknown[]
}) {
  llamadas = []
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET"
      llamadas.push({
        url,
        method,
        body: init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null,
      })
      if (method === "POST") {
        const r = opts.post ?? { status: 201, body: { id: "p1", estado: "pendiente" } }
        return Promise.resolve({
          ok: r.status < 300,
          status: r.status,
          json: () => Promise.resolve(r.body),
          text: () => Promise.resolve(JSON.stringify(r.body)),
        } as Response)
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(opts.mios ?? []),
        text: () => Promise.resolve("[]"),
      } as Response)
    }),
  )
}

function montar(extra: Partial<React.ComponentProps<typeof PedirAyudaModal>> = {}) {
  const onClose = vi.fn()
  render(
    <PedirAyudaModal
      isOpen
      onClose={onClose}
      tareaPracticaId={TP}
      pantalla="episodio"
      ejercicioOrden={2}
      episodeId={EP}
      entregaId={ENTREGA}
      {...extra}
    />,
  )
  return { onClose }
}

beforeEach(() => {
  mockFetch({})
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("PedirAyudaModal", () => {
  it("aclara que el pedido va al docente y no al tutor", () => {
    montar()
    expect(screen.getByText(/no al tutor/i)).toBeTruthy()
  })

  it("Enviar esta deshabilitado sin categoria y se habilita al elegirla", () => {
    montar()
    const enviar = screen.getByRole("button", { name: /^Enviar/i }) as HTMLButtonElement
    expect(enviar.disabled).toBe(true)

    fireEvent.click(screen.getByLabelText(/No puedo avanzar/i))

    expect(enviar.disabled).toBe(false)
  })

  it("manda categoria, mensaje y contexto a POST /api/v1/pedidos-ayuda", async () => {
    montar()
    fireEvent.click(screen.getByLabelText(/No puedo avanzar/i))
    fireEvent.change(screen.getByLabelText(/Mensaje/i), {
      target: { value: "no entiendo el while" },
    })

    fireEvent.click(screen.getByRole("button", { name: /^Enviar/i }))

    await waitFor(() => expect(screen.getByText(/Tu pedido le llegó a tu docente/i)).toBeTruthy())
    const post = llamadas.find((l) => l.method === "POST")
    expect(post?.url).toBe("/api/v1/pedidos-ayuda")
    expect(post?.body).toMatchObject({
      tarea_practica_id: TP,
      ejercicio_orden: 2,
      episode_id: EP,
      entrega_id: ENTREGA,
      categoria: "no_puedo_avanzar",
      mensaje: "no entiendo el while",
      contexto: { pantalla: "episodio" },
    })
  })

  it("sin episodio ni ejercicio manda solo lo que hay (error de plataforma desde la lista)", async () => {
    montar({
      pantalla: "lista_ejercicios",
      episodeId: undefined,
      ejercicioOrden: undefined,
      entregaId: undefined,
    })
    fireEvent.click(screen.getByLabelText(/Error de la plataforma/i))

    fireEvent.click(screen.getByRole("button", { name: /^Enviar/i }))

    await waitFor(() => expect(llamadas.some((l) => l.method === "POST")).toBe(true))
    const body = llamadas.find((l) => l.method === "POST")?.body ?? {}
    expect(body.categoria).toBe("error_plataforma")
    expect(body).not.toHaveProperty("episode_id")
    expect(body).not.toHaveProperty("ejercicio_orden")
    expect(body).not.toHaveProperty("mensaje")
  })

  it("incluye el texto de error visible cuando lo hay", async () => {
    montar({ pantalla: "episodio_error", errorVisible: "El ejercicio no terminó de abrirse." })
    fireEvent.click(screen.getByLabelText(/Error de la plataforma/i))

    fireEvent.click(screen.getByRole("button", { name: /^Enviar/i }))

    await waitFor(() => expect(llamadas.some((l) => l.method === "POST")).toBe(true))
    expect(llamadas.find((l) => l.method === "POST")?.body?.contexto).toMatchObject({
      pantalla: "episodio_error",
      error_visible: "El ejercicio no terminó de abrirse.",
    })
  })

  it("429: muestra el motivo y NO da el pedido por enviado", async () => {
    mockFetch({
      post: { status: 429, body: { detail: "Esperá 50 segundos antes de mandar otro pedido." } },
    })
    montar()
    fireEvent.click(screen.getByLabelText(/No puedo avanzar/i))

    fireEvent.click(screen.getByRole("button", { name: /^Enviar/i }))

    await waitFor(() => expect(screen.getByText(/Esperá 50 segundos/i)).toBeTruthy())
    expect(screen.queryByText(/Tu pedido le llegó/i)).toBeNull()
  })

  it("409: muestra el motivo y no da el pedido por enviado", async () => {
    mockFetch({
      post: { status: 409, body: { detail: "Ya tenés 3 pedidos sin responder en este trabajo." } },
    })
    montar()
    fireEvent.click(screen.getByLabelText(/Otro/i))

    fireEvent.click(screen.getByRole("button", { name: /^Enviar/i }))

    await waitFor(() => expect(screen.getByText(/Ya tenés 3 pedidos sin responder/i)).toBeTruthy())
    expect(screen.queryByText(/Tu pedido le llegó/i)).toBeNull()
  })

  it("403 sin detalle legible: frase generica, no un error crudo", async () => {
    mockFetch({ post: { status: 403, body: {} } })
    montar()
    fireEvent.click(screen.getByLabelText(/No puedo avanzar/i))

    fireEvent.click(screen.getByRole("button", { name: /^Enviar/i }))

    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/inscripto|docente/i))
    expect(screen.queryByText(/Tu pedido le llegó/i)).toBeNull()
  })

  it("despues del exito no se puede enviar de nuevo (evita el doble clic)", async () => {
    montar()
    fireEvent.click(screen.getByLabelText(/No puedo avanzar/i))
    fireEvent.click(screen.getByRole("button", { name: /^Enviar/i }))
    await waitFor(() => expect(screen.getByText(/Tu pedido le llegó/i)).toBeTruthy())

    expect(screen.queryByRole("button", { name: /^Enviar/i })).toBeNull()
    expect(llamadas.filter((l) => l.method === "POST")).toHaveLength(1)
  })

  it("el mensaje tiene tope de 1000 y muestra el contador", () => {
    montar()
    const area = screen.getByLabelText(/Mensaje/i) as HTMLTextAreaElement
    expect(area.maxLength).toBe(1000)
    fireEvent.change(area, { target: { value: "hola" } })
    expect(screen.getByText("4/1000")).toBeTruthy()
  })

  it("lista 'Tus pedidos en este trabajo' con su estado", async () => {
    mockFetch({
      mios: [
        {
          id: "p1",
          categoria: "no_puedo_avanzar",
          mensaje: "uno",
          estado: "pendiente",
          ejercicio_orden: 1,
          created_at: "2026-10-28T10:00:00Z",
        },
        {
          id: "p2",
          categoria: "otro",
          mensaje: "dos",
          estado: "resuelto",
          ejercicio_orden: null,
          created_at: "2026-10-27T10:00:00Z",
        },
      ],
    })
    montar()

    expect(await screen.findByText(/Tus pedidos en este trabajo/i)).toBeTruthy()
    expect(await screen.findByText("Pendiente")).toBeTruthy()
    expect(await screen.findByText("Resuelto")).toBeTruthy()
    expect(llamadas[0]?.url).toContain(`/api/v1/pedidos-ayuda/mios?tarea_practica_id=${TP}`)
  })

  it("desde la lista de ejercicios ofrece elegir el ejercicio (opcional)", async () => {
    montar({
      pantalla: "lista_ejercicios",
      ejercicioOrden: undefined,
      episodeId: undefined,
      ejercicios: [
        { orden: 1, titulo: "Suma" },
        { orden: 2, titulo: "Resta" },
      ],
    })
    fireEvent.click(screen.getByLabelText(/No puedo avanzar/i))
    fireEvent.change(screen.getByLabelText(/En qué ejercicio/i), { target: { value: "2" } })

    fireEvent.click(screen.getByRole("button", { name: /^Enviar/i }))

    await waitFor(() => expect(llamadas.some((l) => l.method === "POST")).toBe(true))
    expect(llamadas.find((l) => l.method === "POST")?.body?.ejercicio_orden).toBe(2)
  })

  it("no ofrece selector de ejercicio cuando el contexto ya lo trae", () => {
    montar()
    expect(screen.queryByLabelText(/En qué ejercicio/i)).toBeNull()
  })
})
