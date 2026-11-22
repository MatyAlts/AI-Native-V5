/**
 * Aceptacion HU-012 (orquestador, antes de construir; el constructor no la
 * modifica). Criterios aprobados por Juani el 22/11/2026 ("sisi").
 *
 * Pedido de Ariel Enferrel (docente, 21/11): en las entregas a corregir no
 * hay filtro por trabajo practico. El backend ya acepta `tarea_practica_id`
 * en `GET /api/v1/entregas`; falta la pantalla.
 *
 * Contrato que fija esta prueba: un <select> con aria-label "Filtro por TP",
 * con la opcion vacia "Todos los TP" y una opcion por TP de la comision
 * (`GET /api/v1/tareas-practicas?comision_id=...`) que muestra su codigo.
 *
 * C01  El selector existe, arranca en "Todos los TP" y lista los TP.
 * C02  Elegir un TP pide al servidor `tarea_practica_id` y muestra solo esas.
 * C03  Se combina con "Solo re-entregas" (los dos parametros en el pedido).
 * C04  "Cargar mas" mantiene el TP elegido.
 * C05  Un TP sin entregas lo dice: "No hay entregas de este TP".
 * N01  Con "Todos los TP" el pedido no lleva `tarea_practica_id` (como hoy).
 * N02  Al cambiar de comision el filtro vuelve a "Todos los TP".
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

describe("HU-012 · filtro por TP en Correcciones", () => {
  it("C01: el selector arranca en Todos los TP y lista los TP de la comision", async () => {
    stubFetch()
    renderWithRouter(<CorreccionesView comisionId={COM_A} getToken={getToken} />)
    const sel = await selectorTp()
    await esperarOpciones(sel)
    expect(sel.value).toBe("")
    const textos = [...sel.options].map((o) => o.textContent ?? "")
    expect(textos[0]).toMatch(/todos los tp/i)
    expect(textos.join(" ")).toMatch(/SEC2027/)
    expect(textos.join(" ")).toMatch(/COND01/)
  })

  it("N01: con Todos los TP el pedido no lleva tarea_practica_id", async () => {
    const urls = stubFetch()
    renderWithRouter(<CorreccionesView comisionId={COM_A} getToken={getToken} />)
    await waitFor(() => expect(filas().length).toBe(4))
    const pedidos = pedidosDeEntregas(urls)
    expect(pedidos.length).toBeGreaterThan(0)
    expect(pedidos.every((q) => !q.has("tarea_practica_id"))).toBe(true)
  })

  it("C02: elegir un TP filtra en el servidor y muestra solo esas entregas", async () => {
    const urls = stubFetch()
    renderWithRouter(<CorreccionesView comisionId={COM_A} getToken={getToken} />)
    await waitFor(() => expect(filas().length).toBe(4))
    await elegir(await selectorTp(), TP2)
    await waitFor(() => expect(filas().length).toBe(2))
    const ultimo = pedidosDeEntregas(urls).at(-1)
    expect(ultimo?.get("tarea_practica_id")).toBe(TP2)
  })

  it("C03: se combina con Solo re-entregas", async () => {
    const urls = stubFetch()
    renderWithRouter(<CorreccionesView comisionId={COM_A} getToken={getToken} />)
    await waitFor(() => expect(filas().length).toBe(4))
    await elegir(await selectorTp(), TP1)
    await waitFor(() => expect(filas().length).toBe(2))
    fireEvent.click(screen.getByTestId("solo-reentregas-toggle"))
    await waitFor(() => expect(filas().length).toBe(1))
    const ultimo = pedidosDeEntregas(urls).at(-1)
    expect(ultimo?.get("tarea_practica_id")).toBe(TP1)
    expect(ultimo?.get("reentrega")).toBe("true")
  })

  it("C04: Cargar mas mantiene el TP elegido", async () => {
    const urls = stubFetch({ paginar: true })
    renderWithRouter(<CorreccionesView comisionId={COM_A} getToken={getToken} />)
    await waitFor(() => expect(filas().length).toBe(1))
    await elegir(await selectorTp(), TP2)
    await waitFor(() => {
      const ultimo = pedidosDeEntregas(urls).at(-1)
      expect(ultimo?.get("tarea_practica_id")).toBe(TP2)
    })
    fireEvent.click(await screen.findByRole("button", { name: /cargar m[aá]s/i }))
    await waitFor(() => expect(filas().length).toBe(2))
    const conCursor = pedidosDeEntregas(urls).filter((q) => q.has("cursor"))
    expect(conCursor.length).toBeGreaterThan(0)
    expect(conCursor.at(-1)?.get("tarea_practica_id")).toBe(TP2)
  })

  it("C05: un TP sin entregas lo dice", async () => {
    stubFetch()
    renderWithRouter(<CorreccionesView comisionId={COM_A} getToken={getToken} />)
    await waitFor(() => expect(filas().length).toBe(4))
    await elegir(await selectorTp(), TP_VACIO)
    expect(await screen.findByText(/no hay entregas de este tp/i)).toBeTruthy()
  })

  it("N02: al cambiar de comision el filtro vuelve a Todos los TP", async () => {
    const urls = stubFetch()
    function DosComisiones() {
      const [com, setCom] = useState(COM_A)
      return (
        <>
          <button type="button" onClick={() => setCom(COM_B)}>
            cambiar-comision
          </button>
          <CorreccionesView comisionId={com} getToken={getToken} />
        </>
      )
    }
    renderWithRouter(<DosComisiones />)
    await waitFor(() => expect(filas().length).toBe(4))
    await elegir(await selectorTp(), TP2)
    await waitFor(() => expect(filas().length).toBe(2))
    fireEvent.click(screen.getByText("cambiar-comision"))
    await waitFor(() => {
      const ultimo = pedidosDeEntregas(urls).at(-1)
      expect(ultimo?.get("comision_id")).toBe(COM_B)
      expect(ultimo?.has("tarea_practica_id")).toBe(false)
    })
    expect((await selectorTp()).value).toBe("")
  })
})
