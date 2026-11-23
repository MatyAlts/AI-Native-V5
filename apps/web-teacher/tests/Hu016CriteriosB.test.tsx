/**
 * Aceptacion HU-016, ronda de arreglos (orquestador, antes de corregir; el
 * constructor no la modifica). Sale de la verificacion independiente del PR
 * #147 (22/11). Juani: "vos terminas todo entonces".
 *
 * R01  Un comentario escrito en un criterio sin puntaje no se pierde en
 *      silencio: no se publica y se avisa "Falta el puntaje...".
 * R02  La nota sugerida se calcula solo con los criterios completados (vacio
 *      no es 0, igual que en lo que se guarda).
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { CorreccionesView } from "../src/views/CorreccionesView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const TAREA_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
const ENTREGA_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"

const entrega = {
  id: ENTREGA_ID,
  tenant_id: "t1",
  tarea_practica_id: TAREA_ID,
  comision_id: COMISION_ID,
  student_pseudonym: "b1b1b1b1-0001-0001-0001-000000000001",
  estado: "submitted",
  ejercicio_estados: [
    { orden: 1, completado: true, episode_id: "ep-1", completado_at: "2026-05-06T11:00:00Z" },
  ],
  submitted_at: "2026-05-06T12:00:00Z",
  created_at: "2026-05-06T10:00:00Z",
  updated_at: "2026-05-06T12:00:00Z",
}

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

const tpEj = {
  id: "tpej-1",
  tarea_practica_id: TAREA_ID,
  ejercicio_id: "ej-1",
  orden: 1,
  peso_en_tp: "1.0",
  ejercicio: {
    id: "ej-1",
    titulo: "Ejercicio 1",
    rubrica: {
      criterios: [
        { nombre: "Lee el dato", descripcion: "", puntaje_max: "5" },
        { nombre: "Calcula", descripcion: "", puntaje_max: "5" },
        { nombre: "Muestra", descripcion: "", puntaje_max: "5" },
      ],
    },
  },
}

const getToken = () => Promise.resolve("dev-token")

function montar() {
  const posts: { url: string; body: Record<string, unknown> }[] = []
  setupFetchMock({
    "/correccion-ia": () => ({ correcciones: [] }),
    "/ejercicios": () => [tpEj],
    "/api/v1/entregas": () => ({ data: [entrega], meta: { cursor_next: null } }),
    "/api/v1/tareas-practicas/": () => tarea,
  })
  const base = globalThis.fetch
  vi.stubGlobal("fetch", (url: string | URL | Request, init?: RequestInit) => {
    const metodo = (init?.method ?? "GET").toUpperCase()
    if (metodo !== "GET" && /\/calific/.test(String(url))) {
      posts.push({ url: String(url), body: JSON.parse(String(init?.body ?? "{}")) })
    }
    return (base as typeof fetch)(url as never, init)
  })
  renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
  return posts
}

async function abrirEntrega() {
  await waitFor(() => expect(screen.getByTestId("entrega-drill-btn")).toBeDefined())
  fireEvent.click(screen.getByTestId("entrega-drill-btn"))
  await waitFor(() => expect(screen.getByTestId("criterio-puntaje-ej-1#0")).toBeDefined())
}

async function publicar(posts: { body: Record<string, unknown> }[]) {
  fireEvent.change(screen.getByTestId("nota-final-input"), { target: { value: "8" } })
  fireEvent.change(screen.getByTestId("feedback-input"), { target: { value: "Bien" } })
  fireEvent.click(screen.getByTestId("calificar-btn"))
  await waitFor(() => expect(posts.length).toBeGreaterThan(0), { timeout: 5000 })
  return posts[0]?.body ?? {}
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("HU-016 · ronda de arreglos", () => {
  it("R01: comentario sin puntaje no se publica y se avisa", async () => {
    const posts = montar()
    await abrirEntrega()
    fireEvent.change(screen.getByTestId("criterio-comentario-ej-1#2"), {
      target: { value: "No muestra nada" },
    })
    fireEvent.change(screen.getByTestId("nota-final-input"), { target: { value: "8" } })
    fireEvent.change(screen.getByTestId("feedback-input"), { target: { value: "Bien" } })
    fireEvent.click(screen.getByTestId("calificar-btn"))
    await waitFor(() => expect(screen.getByText(/falta[n]? (el|poner el) puntaje/i)).toBeDefined())
    expect(posts).toHaveLength(0)
  })

  it("R02: la nota sugerida no cuenta los criterios vacios como 0", async () => {
    montar()
    await abrirEntrega()
    fireEvent.change(screen.getByTestId("criterio-puntaje-ej-1#0"), { target: { value: "5" } })
    await waitFor(() => expect(screen.getByText(/Nota sugerida/)).toBeDefined())
    const fila = screen.getByText(/Nota sugerida/).closest("div")
    expect(fila?.textContent).toMatch(/10\.0/)
  })
})
