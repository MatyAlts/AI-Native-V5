/**
 * HU-022 (vuelta 2), aceptación del lado del docente. Sale de la prueba en
 * producción del 23/11 (F27, F29, F31 en `hu014-hallazgos.md`).
 *
 * C02 (F27): con 1 de 2 ejercicios corregidos no se ofrece "Aplicar" la nota
 *   sugerida: un clic le ponía nota a una entrega con ejercicios sin revisar.
 *   Con los dos corregidos, sí (guarda).
 * C03 (F29): al re-calificar una re-entrega, los criterios de la calificación
 *   anterior aparecen precargados; antes arrancaban vacíos y se perdían.
 * C06 (F31): la sugerencia de Active-IA no muestra el id interno de la
 *   rúbrica ("nativa:<hash>"); el form de TP no habla de ADRs.
 *
 * Lo que se prueba en navegador real en la demo: el preview de "Corregir con
 * IA" (CorreccionIAPanel) tampoco muestra el hash.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ResumenCorreccionIA } from "../src/components/ResumenCorreccionIA"
import type { CorreccionIA } from "../src/lib/api"
import { CorreccionesView } from "../src/views/CorreccionesView"
import { TareasPracticasView } from "../src/views/TareasPracticasView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const TAREA_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
const ENTREGA_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
const getToken = () => Promise.resolve("dev-token")

const entrega = {
  id: ENTREGA_ID,
  tenant_id: "t1",
  tarea_practica_id: TAREA_ID,
  comision_id: COMISION_ID,
  student_pseudonym: "b1b1b1b1-0001-0001-0001-000000000001",
  estado: "submitted",
  ejercicio_estados: [
    { orden: 1, completado: true, episode_id: "ep-1", completado_at: "2026-11-23T11:00:00Z" },
    { orden: 2, completado: true, episode_id: "ep-2", completado_at: "2026-11-23T11:10:00Z" },
  ],
  submitted_at: "2026-11-23T12:00:00Z",
  created_at: "2026-11-23T10:00:00Z",
  updated_at: "2026-11-23T12:00:00Z",
}

const tarea = {
  id: TAREA_ID,
  tenant_id: "t1",
  comision_id: COMISION_ID,
  codigo: "E2E",
  titulo: "TP de prueba",
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
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-01T00:00:00Z",
}

function tpEj(n: number) {
  return {
    id: `tpej-${n}`,
    tarea_practica_id: TAREA_ID,
    ejercicio_id: `ej-${n}`,
    orden: n,
    peso_en_tp: "1.0",
    ejercicio: {
      id: `ej-${n}`,
      titulo: `Ejercicio ${n}`,
      rubrica: {
        criterios: [
          { nombre: "Lee el dato", descripcion: "", puntaje_max: "5" },
          { nombre: "Muestra", descripcion: "", puntaje_max: "5" },
        ],
      },
    },
  }
}

const previa = {
  id: "cal-1",
  entrega_id: ENTREGA_ID,
  nota_final: 8,
  feedback_general: "Revisá el formato del 2.",
  detalle_criterios: [
    { criterio: "Ejercicio 1: Lee el dato", puntaje: "4", max_puntaje: "5", comentario: null },
    { criterio: "Ejercicio 1: Muestra", puntaje: "3", max_puntaje: "5", comentario: null },
  ],
  graded_at: "2026-11-23T13:00:00Z",
  graded_by: "docente-1",
}

function montar(opts: { conPrevia: boolean; reabierto2?: boolean }) {
  const json = (status: number, body: unknown) =>
    Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
      text: () => Promise.resolve(JSON.stringify(body)),
    } as Response)
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string | URL | Request) => {
      const u = typeof url === "string" ? url : url.toString()
      if (u.includes("/correccion-ia")) return json(200, { correcciones: [] })
      if (u.includes("/ejercicios")) return json(200, [tpEj(1), tpEj(2)])
      if (u.includes("/api/v1/tareas-practicas/")) return json(200, tarea)
      if (u.endsWith("/calificacion")) {
        return opts.conPrevia ? json(200, previa) : json(404, { detail: "no hay" })
      }
      const e = opts.reabierto2
        ? {
            ...entrega,
            ejercicio_estados: entrega.ejercicio_estados.map((x) =>
              x.orden === 2 ? { ...x, reabierto_por_docente: true } : x,
            ),
          }
        : entrega
      if (u.includes(`/api/v1/entregas/${ENTREGA_ID}`)) return json(200, e)
      return json(200, { data: [e], meta: { cursor_next: null } })
    }),
  )
  renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
}

async function abrirEntrega() {
  await waitFor(() => expect(screen.getByTestId("entrega-drill-btn")).toBeDefined())
  fireEvent.click(screen.getByTestId("entrega-drill-btn"))
  await waitFor(() => expect(screen.getByTestId("criterio-puntaje-ej-1#0")).toBeDefined())
}

function puntuar(testid: string, valor: string) {
  fireEvent.change(screen.getByTestId(testid), { target: { value: valor } })
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("C02 · Aplicar la nota sugerida solo con todo corregido", () => {
  it("con 1 de 2 ejercicios corregidos no ofrece Aplicar", async () => {
    montar({ conPrevia: false })
    await abrirEntrega()
    puntuar("criterio-puntaje-ej-1#0", "5")
    puntuar("criterio-puntaje-ej-1#1", "5")
    // Se da tiempo a que la UI reaccione antes de afirmar la ausencia.
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByTestId("aplicar-nota-sugerida-btn")).toBeNull()
  })

  it("con los 2 ejercicios corregidos sí ofrece Aplicar", async () => {
    montar({ conPrevia: false })
    await abrirEntrega()
    for (const id of ["ej-1#0", "ej-1#1"]) puntuar(`criterio-puntaje-${id}`, "5")
    const cabecera = screen.getByTestId("ej-estado-2").querySelector("button[aria-expanded]")
    if (cabecera?.getAttribute("aria-expanded") === "false") fireEvent.click(cabecera)
    await waitFor(() => expect(screen.getByTestId("criterio-puntaje-ej-2#0")).toBeDefined())
    for (const id of ["ej-2#0", "ej-2#1"]) puntuar(`criterio-puntaje-${id}`, "5")
    await waitFor(() => expect(screen.getByTestId("aplicar-nota-sugerida-btn")).toBeDefined())
  })
})

describe("C03 · re-calificar precarga los criterios anteriores", () => {
  it("los puntajes de la calificación previa aparecen en sus casilleros", async () => {
    montar({ conPrevia: true })
    await abrirEntrega()
    await waitFor(() => expect(screen.getAllByText(/nota anterior/i).length).toBeGreaterThan(0))
    await waitFor(() => {
      const leer = screen.getByTestId("criterio-puntaje-ej-1#0") as HTMLInputElement
      expect(leer.value).toBe("4")
    })
    const muestra = screen.getByTestId("criterio-puntaje-ej-1#1") as HTMLInputElement
    expect(muestra.value).toBe("3")
  })
})

describe("C02+C03 · re-entrega: lo que se pidió rehacer arranca vacío", () => {
  const previaCompleta = {
    ...previa,
    detalle_criterios: [
      { criterio: "Ejercicio 1: Lee el dato", puntaje: "4", max_puntaje: "5", comentario: null },
      { criterio: "Ejercicio 1: Muestra", puntaje: "3", max_puntaje: "5", comentario: null },
      { criterio: "Ejercicio 2: Lee el dato", puntaje: "1", max_puntaje: "5", comentario: null },
      { criterio: "Ejercicio 2: Muestra", puntaje: "0", max_puntaje: "5", comentario: null },
    ],
  }

  function montarRehacer() {
    const json = (status: number, body: unknown) =>
      Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve(body),
        text: () => Promise.resolve(JSON.stringify(body)),
      } as Response)
    const e = {
      ...entrega,
      ejercicio_estados: entrega.ejercicio_estados.map((x) =>
        x.orden === 2 ? { ...x, reabierto_por_docente: true } : x,
      ),
    }
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string | URL | Request) => {
        const u = typeof url === "string" ? url : url.toString()
        if (u.includes("/correccion-ia")) return json(200, { correcciones: [] })
        if (u.includes("/ejercicios")) return json(200, [tpEj(1), tpEj(2)])
        if (u.includes("/api/v1/tareas-practicas/")) return json(200, tarea)
        if (u.endsWith("/calificacion")) return json(200, previaCompleta)
        if (u.includes(`/api/v1/entregas/${ENTREGA_ID}`)) return json(200, e)
        return json(200, { data: [e], meta: { cursor_next: null } })
      }),
    )
    renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
  }

  it("el ejercicio no pedido se precarga; el pedido arranca vacío; no hay Aplicar", async () => {
    montarRehacer()
    await abrirEntrega()
    await waitFor(() =>
      expect((screen.getByTestId("criterio-puntaje-ej-1#0") as HTMLInputElement).value).toBe("4"),
    )
    const cabecera = screen.getByTestId("ej-estado-2").querySelector("button[aria-expanded]")
    if (cabecera?.getAttribute("aria-expanded") === "false") fireEvent.click(cabecera)
    await waitFor(() => expect(screen.getByTestId("criterio-puntaje-ej-2#0")).toBeDefined())
    expect((screen.getByTestId("criterio-puntaje-ej-2#0") as HTMLInputElement).value).toBe("")
    expect((screen.getByTestId("criterio-puntaje-ej-2#1") as HTMLInputElement).value).toBe("")
    expect(screen.queryByTestId("aplicar-nota-sugerida-btn")).toBeNull()
  })
})

describe("C06 · sin el id interno de la rúbrica", () => {
  it("la sugerencia de Active-IA no muestra 'nativa:<hash>'", () => {
    const c = {
      id: "c1",
      entrega_id: "e1",
      tp_ejercicio_id: "ej-1",
      orden: 1,
      estado: "done",
      rubrica_id: "nativa:e87fbd6493c894140f9df693670ad81d",
      nota_100: 100,
      desglose: [{ nombre: "Lee el dato", puntaje: 5, puntaje_max: 5, justificacion: "ok" }],
      tests_snapshot: {},
      artefacto_sha256: "s",
      error_code: null,
      error_detail: null,
      es_infraestructura: false,
      external_correccion_id: null,
      tiene_pdf: false,
      created_at: "2026-11-23T10:00:00Z",
      finished_at: "2026-11-23T10:02:00Z",
    } as unknown as CorreccionIA
    const { container } = render(
      <ResumenCorreccionIA
        ejercicios={[{ ejercicioId: "ej-1", orden: 1, titulo: "Ejercicio 1", peso: 1 }]}
        correcciones={[c]}
        onUsarComoBase={() => {}}
      />,
    )
    const texto = container.textContent ?? ""
    expect(texto).not.toMatch(/e87fbd64/i)
    expect(texto).not.toMatch(/nativa:/i)
  })
})

describe("C06 · el form de Nuevo TP no habla de ADRs", () => {
  it("no muestra 'ADR-' ni 'runtime'", async () => {
    setupFetchMock({})
    renderWithRouter(<TareasPracticasView comisionId={COMISION_ID} getToken={async () => "tok"} />)
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: /Nuevo TP/i }).length).toBeGreaterThan(0),
    )
    fireEvent.click(screen.getAllByRole("button", { name: /Nuevo TP/i })[0])
    await screen.findByTestId("tp-form-codigo")
    const texto = document.body.textContent ?? ""
    expect(texto).not.toMatch(/ADR-\d+/)
    expect(texto).not.toMatch(/runtime/i)
  })
})
