/**
 * Aceptacion HU-012, segunda ronda (orquestador, antes de corregir; el
 * constructor no la modifica). Sale de la verificacion independiente del
 * PR #144 (22/11/2026). Juani: "si dale" a la ronda de arreglos. Los helpers
 * son copia de Hu012FiltroTp.test.tsx (aceptacion `55dc286`).
 *
 * N02b  Al cambiar de comision, NINGUN pedido a la comision nueva lleva el TP
 *       elegido en la anterior (no solo el ultimo).
 * N02c  Ir de A a B y volver a A deja el filtro en "Todos los TP": no
 *       reaparece el TP elegido antes, como promete la ayuda.
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { useState } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { CorreccionesView } from "../src/views/CorreccionesView"
import { renderWithRouter } from "./_mocks"

const COM_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const COM_B = "cccccccc-cccc-cccc-cccc-cccccccccccc"
const TP1 = "11111111-1111-1111-1111-111111111111"
const TP2 = "22222222-2222-2222-2222-222222222222"
const TP_VACIO = "33333333-3333-3333-3333-333333333333"

const tp = (id: string, codigo: string, titulo: string, comision = COM_A) => ({
  id,
  tenant_id: "t1",
  comision_id: comision,
  codigo,
  titulo,
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
})

const TPS = [
  tp(TP1, "SEC2027", "Secuenciales"),
  tp(TP2, "COND01", "Condicionales"),
  tp(TP_VACIO, "REP01", "Repetitivas"),
]

const entrega = (id: string, tareaId: string, extra: { es_reentrega?: boolean } = {}) => ({
  id,
  tenant_id: "t1",
  tarea_practica_id: tareaId,
  comision_id: COM_A,
  student_pseudonym: `b1b1b1b1-0001-0001-0001-0000000000${id.slice(-2)}`,
  estado: "submitted",
  ejercicio_estados: [],
  submitted_at: "2026-05-06T12:00:00Z",
  created_at: "2026-05-06T10:00:00Z",
  updated_at: "2026-05-06T12:00:00Z",
  es_reentrega: extra.es_reentrega ?? false,
  nota_final: null,
})

const TODAS = [
  entrega("e01", TP1),
  entrega("e02", TP1, { es_reentrega: true }),
  entrega("e03", TP2),
  entrega("e04", TP2),
]

const getToken = () => Promise.resolve("dev-token")

/** Mock de fetch que filtra como el backend y pagina de a 1 si `paginar`. */
function stubFetch(opts: { paginar?: boolean } = {}) {
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
      const q = new URL(u, "http://x").searchParams
      if (u.includes("/api/v1/tareas-practicas?")) {
        const com = q.get("comision_id")
        return json({ data: TPS.filter((t) => t.comision_id === com), meta: { cursor_next: null } })
      }
      const m = u.match(/\/api\/v1\/tareas-practicas\/([0-9a-f-]+)/)
      if (m) return json(TPS.find((t) => t.id === m[1]) ?? TPS[0])
      if (u.includes("/api/v1/entregas?")) {
        let data = TODAS.filter((e) => e.comision_id === q.get("comision_id"))
        const tpId = q.get("tarea_practica_id")
        if (tpId) data = data.filter((e) => e.tarea_practica_id === tpId)
        if (q.get("reentrega") === "true") data = data.filter((e) => e.es_reentrega)
        if (opts.paginar) {
          const cursor = q.get("cursor")
          const i = cursor ? data.findIndex((e) => e.id === cursor) + 1 : 0
          const pagina = data.slice(i, i + 1)
          const next = i + 1 < data.length ? (pagina[0]?.id ?? null) : null
          return json({ data: pagina, meta: { cursor_next: next } })
        }
        return json({ data, meta: { cursor_next: null } })
      }
      return json({ data: [], meta: { cursor_next: null } })
    }),
  )
  return urls
}

const pedidosDeEntregas = (urls: string[]) =>
  urls
    .filter((u) => u.includes("/api/v1/entregas?"))
    .map((u) => new URL(u, "http://x").searchParams)

async function selectorTp(): Promise<HTMLSelectElement> {
  const sel = await screen.findByLabelText(/filtro por tp/i)
  expect(sel.tagName).toBe("SELECT")
  return sel as HTMLSelectElement
}

async function esperarOpciones(sel: HTMLSelectElement) {
  await waitFor(() => expect(sel.options.length).toBeGreaterThanOrEqual(1 + TPS.length))
}

async function elegir(sel: HTMLSelectElement, tpId: string) {
  await esperarOpciones(sel)
  fireEvent.change(sel, { target: { value: tpId } })
}

const filas = () => screen.queryAllByTestId("entrega-row")

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function DosComisiones() {
  const [com, setCom] = useState(COM_A)
  return (
    <>
      <button type="button" onClick={() => setCom(COM_B)}>
        ir-a-b
      </button>
      <button type="button" onClick={() => setCom(COM_A)}>
        volver-a-a
      </button>
      <CorreccionesView comisionId={com} getToken={getToken} />
    </>
  )
}

describe("HU-012 · cambio de comision (segunda ronda)", () => {
  it("N02b: ningun pedido a la comision nueva lleva el TP viejo", async () => {
    const urls = stubFetch()
    renderWithRouter(<DosComisiones />)
    await waitFor(() => expect(filas().length).toBe(4))
    await elegir(await selectorTp(), TP2)
    await waitFor(() => expect(filas().length).toBe(2))
    fireEvent.click(screen.getByText("ir-a-b"))
    await waitFor(() =>
      expect(pedidosDeEntregas(urls).some((q) => q.get("comision_id") === COM_B)).toBe(true),
    )
    const aB = pedidosDeEntregas(urls).filter((q) => q.get("comision_id") === COM_B)
    expect(aB.every((q) => !q.has("tarea_practica_id"))).toBe(true)
  })

  it("N02c: ir a otra comision y volver deja el filtro en Todos los TP", async () => {
    const urls = stubFetch()
    renderWithRouter(<DosComisiones />)
    await waitFor(() => expect(filas().length).toBe(4))
    await elegir(await selectorTp(), TP2)
    await waitFor(() => expect(filas().length).toBe(2))
    fireEvent.click(screen.getByText("ir-a-b"))
    await waitFor(() => expect(pedidosDeEntregas(urls).at(-1)?.get("comision_id")).toBe(COM_B))
    const antesDeVolver = urls.length
    fireEvent.click(screen.getByText("volver-a-a"))
    await waitFor(() => expect(filas().length).toBe(4))
    expect((await selectorTp()).value).toBe("")
    const alVolver = pedidosDeEntregas(urls.slice(antesDeVolver)).filter(
      (q) => q.get("comision_id") === COM_A,
    )
    expect(alVolver.every((q) => !q.has("tarea_practica_id"))).toBe(true)
  })
})
