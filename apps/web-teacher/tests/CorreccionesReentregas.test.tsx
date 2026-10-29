/**
 * Re-entregas marcadas en la lista de pendientes (change
 * reentregas-marcadas-en-pendientes): badge con la nota anterior, toggle
 * "Solo re-entregas" que filtra en el servidor, y "Correccion pedida: ej. X".
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { CorreccionesView } from "../src/views/CorreccionesView"
import { renderWithRouter } from "./_mocks"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const TAREA_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

const estados = (marcas: Record<number, boolean> | null) =>
  [1, 2, 3, 4].map((orden) => ({
    orden,
    completado: true,
    episode_id: null,
    ejercicio_id: null,
    completed_at: null,
    ...(marcas && orden in marcas ? { reabierto_por_docente: marcas[orden] } : {}),
  }))

const entrega = (
  id: string,
  estado: string,
  extra: {
    es_reentrega?: boolean
    nota_final?: number | null
    marcas?: Record<number, boolean>
  } = {},
) => ({
  id,
  tenant_id: "t1",
  tarea_practica_id: TAREA_ID,
  comision_id: COMISION_ID,
  student_pseudonym: `b1b1b1b1-0001-0001-0001-00000000000${id.slice(-1)}`,
  estado,
  ejercicio_estados: estados(extra.marcas ?? null),
  submitted_at: "2026-05-06T12:00:00Z",
  created_at: "2026-05-06T10:00:00Z",
  updated_at: "2026-05-06T12:00:00Z",
  es_reentrega: extra.es_reentrega ?? false,
  nota_final: extra.nota_final ?? null,
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

const getToken = () => Promise.resolve("dev-token")

function stubFetch(todas: ReturnType<typeof entrega>[]) {
  const urls: string[] = []
  const json = (body: unknown) =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
      text: () => Promise.resolve(JSON.stringify(body)),
    } as Response)
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string | URL | Request) => {
      const u = typeof url === "string" ? url : url.toString()
      urls.push(u)
      if (u.includes("/api/v1/tareas-practicas/")) return json(tarea)
      if (u.includes("/api/v1/entregas?")) {
        const solo = new URL(u, "http://x").searchParams.get("reentrega") === "true"
        const data = solo ? todas.filter((e) => e.es_reentrega) : todas
        return json({ data, meta: { cursor_next: null } })
      }
      return json({ data: [], meta: { cursor_next: null } })
    }),
  )
  return urls
}

const abrir = async () => {
  renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
  await waitFor(() => expect(screen.getAllByTestId("entrega-row").length).toBeGreaterThan(0))
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("badge Re-entrega", () => {
  it("la re-entrega muestra 'Re-entrega · antes 6' y la nueva no", async () => {
    stubFetch([
      entrega("e1", "submitted", { es_reentrega: true, nota_final: 6 }),
      entrega("e2", "submitted"),
    ])
    await abrir()
    const filas = screen.getAllByTestId("entrega-row")
    expect(filas).toHaveLength(2)
    expect(filas[0]?.textContent).toContain("Re-entrega · antes 6")
    expect(filas[1]?.textContent).not.toContain("Re-entrega")
  })

  it("una entrega graded con nota no lleva el badge", async () => {
    stubFetch([entrega("e3", "graded", { es_reentrega: false, nota_final: 8 })])
    await abrir()
    expect(screen.getByTestId("entrega-row").textContent).not.toContain("Re-entrega")
  })
})

describe("Correccion pedida en la tarjeta", () => {
  it("re-entrega con marca en 2 y 4", async () => {
    stubFetch([
      entrega("e1", "submitted", {
        es_reentrega: true,
        nota_final: 6,
        marcas: { 1: false, 2: true, 3: false, 4: true },
      }),
    ])
    await abrir()
    expect(screen.getByTestId("entrega-row").textContent).toContain("Corrección pedida: ej. 2 y 4")
  })

  it("re-entrega sin marca: solo el badge, sin detalle inventado", async () => {
    stubFetch([entrega("e1", "submitted", { es_reentrega: true, nota_final: 6 })])
    await abrir()
    const t = screen.getByTestId("entrega-row").textContent ?? ""
    expect(t).toContain("Re-entrega · antes 6")
    expect(t).not.toContain("Corrección pedida")
  })

  it("una entrega nueva con marca vieja no muestra el detalle", async () => {
    stubFetch([entrega("e1", "submitted", { marcas: { 2: true } })])
    await abrir()
    expect(screen.getByTestId("entrega-row").textContent).not.toContain("Corrección pedida")
  })
})

describe("toggle Solo re-entregas", () => {
  it("sin el toggle no manda reentrega; con el toggle lo manda y la cola se acota", async () => {
    const urls = stubFetch([
      entrega("e1", "submitted", { es_reentrega: true, nota_final: 6 }),
      entrega("e2", "submitted"),
      entrega("e3", "submitted"),
    ])
    await abrir()
    expect(
      urls.filter((u) => u.includes("/api/v1/entregas?")).every((u) => !u.includes("reentrega")),
    ).toBe(true)
    expect(screen.getByTestId("corregir-en-lote-btn").textContent).toContain("3")

    const toggle = screen.getByRole("button", { name: /Solo re-entregas|Sólo re-entregas/ })
    expect(toggle.getAttribute("aria-pressed")).toBe("false")
    fireEvent.click(toggle)

    await waitFor(() => expect(screen.getAllByTestId("entrega-row")).toHaveLength(1))
    expect(urls.some((u) => u.includes("reentrega=true"))).toBe(true)
    expect(
      screen
        .getByRole("button", { name: /Solo re-entregas|Sólo re-entregas/ })
        .getAttribute("aria-pressed"),
    ).toBe("true")
    expect(screen.getByTestId("corregir-en-lote-btn").textContent).toContain("1")
  })
})
