/**
 * Aceptacion HU-016, criterios vacios (orquestador, antes de construir; el
 * constructor no la modifica). Juani (22/11): "merega y segui con los proximos".
 *
 * Hallazgo F13 de HU-014: al publicar nota 8 dejando criterios sin completar,
 * se guardaban como 0 y el alumno veia "8/10" con casi todos los criterios en 0.
 *
 * C01  Un criterio que el docente deja vacio no viaja en `detalle_criterios`.
 * C02  Un 0 escrito por el docente si viaja, como 0.
 * N02  La nota final se publica igual aunque no haya ningun criterio completado.
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

describe("HU-016 · criterios vacios", () => {
  it("C01 y N02: sin criterios completados se publica la nota sin criterios en 0", async () => {
    const posts = montar()
    await abrirEntrega()
    const body = await publicar(posts)
    expect(body.nota_final).toBe(8)
    const detalle = (body.detalle_criterios ?? []) as unknown[]
    expect(detalle).toEqual([])
  })

  it("C01 y C02: solo viajan los criterios escritos, incluido un 0 escrito", async () => {
    const posts = montar()
    await abrirEntrega()
    fireEvent.change(screen.getByTestId("criterio-puntaje-ej-1#0"), { target: { value: "3" } })
    fireEvent.change(screen.getByTestId("criterio-puntaje-ej-1#1"), { target: { value: "0" } })
    const body = await publicar(posts)
    const detalle = (body.detalle_criterios ?? []) as { criterio: string; puntaje: number }[]
    expect(detalle.map((d) => d.puntaje)).toEqual([3, 0])
    expect(detalle).toHaveLength(2)
    expect(detalle.some((d) => /Muestra/.test(d.criterio))).toBe(false)
  })
})
