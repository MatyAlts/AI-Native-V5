/**
 * "Publicar nota" y "Pedir corrección" (change publicar-nota-y-pedir-correccion).
 *
 * El rótulo de la primera calificación dice lo que el sistema hace (el alumno ve
 * la nota al guardarla), y devolver pasa a ser un pedido OPCIONAL de corrección
 * de los ejercicios que el docente elige.
 */
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { CorreccionesView } from "../src/views/CorreccionesView"
import { renderWithRouter } from "./_mocks"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const TAREA_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
const ENTREGA_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"

function estadosEjercicios(marcas: Record<number, boolean> = {}) {
  return [1, 2, 3, 4].map((orden) => ({
    orden,
    completado: !(orden in marcas && marcas[orden]),
    episode_id: `ep-000000${orden}-abcd`,
    ejercicio_id: null,
    completed_at: null,
    ...(orden in marcas ? { reabierto_por_docente: marcas[orden] } : {}),
  }))
}

const entrega = (estado: string, marcas: Record<number, boolean> = {}) => ({
  id: ENTREGA_ID,
  tenant_id: "t1",
  tarea_practica_id: TAREA_ID,
  comision_id: COMISION_ID,
  student_pseudonym: "b1b1b1b1-0001-0001-0001-000000000001",
  estado,
  ejercicio_estados: estadosEjercicios(marcas),
  submitted_at: "2026-05-06T12:00:00Z",
  created_at: "2026-05-06T10:00:00Z",
  updated_at: "2026-05-06T12:00:00Z",
})

const tarea = {
  id: TAREA_ID,
  tenant_id: "t1",
  comision_id: COMISION_ID,
  codigo: "TP01",
  titulo: "Funciones",
  enunciado: "x",
  fecha_inicio: null,
  fecha_fin: null,
  peso: "1.0",
  rubrica: null,
  estado: "published",
  version: 1,
  parent_tarea_id: null,
  template_id: null,
  has_drift: false,
  created_by: "u1",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
}

const calificacion = {
  id: "d1",
  entrega_id: ENTREGA_ID,
  nota_final: 8,
  feedback_general: "Bien",
  detalle_criterios: [],
  graded_at: "2026-05-06T13:00:00Z",
  graded_by: "docente-1",
}

const getToken = () => Promise.resolve("dev-token")

function stubFetch(estado: string, marcas: Record<number, boolean> = {}) {
  const calls: { method: string; url: string; body: string | null }[] = []
  const json = (status: number, body: unknown) =>
    Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
      text: () => Promise.resolve(JSON.stringify(body)),
    } as Response)
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string | URL | Request, init?: RequestInit) => {
      const u = typeof url === "string" ? url : url.toString()
      const method = init?.method ?? "GET"
      calls.push({ method, url: u, body: typeof init?.body === "string" ? init.body : null })
      if (u.includes("/correccion-ia")) return json(200, { correcciones: [] })
      if (u.includes("/ejercicios")) return json(200, [])
      if (u.includes("/api/v1/tareas-practicas/")) return json(200, tarea)
      if (u.endsWith("/return")) return json(200, entrega("returned", { 2: true, 4: true }))
      if (u.endsWith("/calificacion")) {
        return estado === "submitted" ? json(404, { detail: "no hay" }) : json(200, calificacion)
      }
      if (u.includes(`/api/v1/entregas/${ENTREGA_ID}`)) return json(200, entrega(estado, marcas))
      return json(200, { data: [entrega(estado, marcas)], meta: { cursor_next: null } })
    }),
  )
  return calls
}

async function abrir() {
  renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
  await waitFor(() => expect(screen.getByTestId("entrega-drill-btn")).toBeDefined())
  fireEvent.click(screen.getByTestId("entrega-drill-btn"))
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("Publicar nota", () => {
  it("el boton de la primera calificacion dice 'Publicar nota'", async () => {
    stubFetch("submitted")
    await abrir()
    await waitFor(() => expect(screen.getByTestId("calificar-btn")).toBeDefined())
    expect(screen.getByTestId("calificar-btn").textContent).toBe("Publicar nota")
  })
})

describe("Pedir correccion", () => {
  it("en graded aparece 'Pedir correccion' y ya no 'Devolver al estudiante'", async () => {
    stubFetch("graded")
    await abrir()
    await waitFor(() => expect(screen.getByTestId("devolver-btn")).toBeDefined())
    expect(screen.getByTestId("devolver-btn").textContent).toBe("Pedir corrección")
    expect(screen.queryByText("Devolver al estudiante")).toBeNull()
  })

  it("el modal lista los ejercicios, confirmar esta deshabilitado con cero y manda {ordenes:[2,4]}", async () => {
    const calls = stubFetch("graded")
    await abrir()
    await waitFor(() => expect(screen.getByTestId("devolver-btn")).toBeDefined())
    fireEvent.click(screen.getByTestId("devolver-btn"))

    const modal = await screen.findByTestId("pedir-correccion-modal")
    for (const o of [1, 2, 3, 4]) {
      expect(within(modal).getByTestId(`pedir-correccion-ej-${o}`)).toBeDefined()
    }
    const confirmar = within(modal).getByTestId(
      "pedir-correccion-confirmar-btn",
    ) as HTMLButtonElement
    expect(confirmar.disabled).toBe(true)
    expect(calls.some((c) => c.url.endsWith("/return"))).toBe(false)

    fireEvent.click(within(modal).getByTestId("pedir-correccion-ej-2"))
    fireEvent.click(within(modal).getByTestId("pedir-correccion-ej-4"))
    expect(confirmar.disabled).toBe(false)
    fireEvent.click(confirmar)

    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/return"))).toBe(true))
    const post = calls.find((c) => c.url.endsWith("/return"))
    expect(post?.method).toBe("POST")
    expect(JSON.parse(post?.body ?? "null")).toEqual({ ordenes: [2, 4] })
  })

  it("destildar vuelve a deshabilitar confirmar", async () => {
    stubFetch("graded")
    await abrir()
    await waitFor(() => expect(screen.getByTestId("devolver-btn")).toBeDefined())
    fireEvent.click(screen.getByTestId("devolver-btn"))
    const modal = await screen.findByTestId("pedir-correccion-modal")
    const confirmar = within(modal).getByTestId(
      "pedir-correccion-confirmar-btn",
    ) as HTMLButtonElement
    fireEvent.click(within(modal).getByTestId("pedir-correccion-ej-3"))
    expect(confirmar.disabled).toBe(false)
    fireEvent.click(within(modal).getByTestId("pedir-correccion-ej-3"))
    expect(confirmar.disabled).toBe(true)
  })

  it("en returned muestra que ejercicios se pidieron corregir", async () => {
    stubFetch("returned", { 1: false, 2: true, 3: false, 4: true })
    await abrir()
    const pedidos = await screen.findByTestId("pedidos-correccion")
    expect(pedidos.textContent).toContain("2, 4")
  })

  it("en returned legacy (sin marcas) dice 'todos'", async () => {
    stubFetch("returned")
    await abrir()
    const pedidos = await screen.findByTestId("pedidos-correccion")
    expect(pedidos.textContent?.toLowerCase()).toContain("todos")
  })
})
