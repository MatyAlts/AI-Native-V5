/**
 * Aceptacion HU-013 (orquestador, antes de construir; el constructor no la
 * modifica). Criterios aprobados por Juani el 22/11/2026 ("sisi apruebo hu 13").
 *
 * Pedido de Ariel Enferrel (docente, 21/11): "la IA corrige pero no carga la
 * calificacion en los puntos evaluados". Hallazgo del orquestador sobre datos
 * reales: el autocompletado ya existe dentro de "Usar como base", pero ese
 * boton desaparece si falta la correccion de algun ejercicio (6 de 15
 * entregas reales con correccion IA), y entonces no hay forma de cargar los
 * puntos de los ejercicios que si estan corregidos.
 *
 * Contrato que fija esta prueba:
 *   - boton data-testid="completar-criterios-ia", visible si hay al menos una
 *     correccion terminada con desglose, aunque falten otras;
 *   - resultado en data-testid="completar-criterios-resultado";
 *   - sugerirPuntajesDesdeCorrecciones(rows, correcciones, actuales?) con
 *     `puntajeMax` opcional en cada fila.
 *
 * C01  El boton aparece aunque falten correcciones y completa los criterios de
 *      los ejercicios corregidos, sin tocar la nota final.
 * C02  Avisa cuantos criterios completo y de que ejercicio falta correccion.
 * C03  Lo completado se puede editar y nada se guarda sin Calificar.
 * N01  Nombre distinto no se completa (mayusculas y espacios no cuentan).
 * N02  Maximo distinto no se completa; sin maximo declarado, solo si el
 *      puntaje no supera el maximo de la rubrica.
 * N03  Criterio en 0 porque el codigo no compilo (sin_ejecucion) no se completa.
 * N04  No pisa un puntaje que el docente ya escribio.
 * N05  Ejercicio sin correccion terminada: sus criterios quedan como estan.
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { CorreccionIA } from "../src/lib/api"
import { sugerirPuntajesDesdeCorrecciones } from "../src/utils/correccionIA"
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
    { orden: 2, completado: true, episode_id: "ep-2", completado_at: "2026-05-06T11:30:00Z" },
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

const tpEj = (n: number) => ({
  id: `tpej-${n}`,
  tarea_practica_id: TAREA_ID,
  ejercicio_id: `ej-${n}`,
  orden: n,
  peso_en_tp: "0.50",
  ejercicio: {
    id: `ej-${n}`,
    titulo: `Ejercicio ${n}`,
    rubrica: {
      criterios: [
        { nombre: "Usa la interfaz", descripcion: "", puntaje_max: "5" },
        { nombre: "Produce la salida esperada", descripcion: "", puntaje_max: "5" },
      ],
    },
  },
})

const correccion = (over: Partial<CorreccionIA> & { desglose: CorreccionIA["desglose"] }) =>
  ({
    id: "corr-1",
    entrega_id: ENTREGA_ID,
    tp_ejercicio_id: "ej-1",
    orden: 1,
    estado: "done",
    rubrica_id: "nativa:v1",
    nota_100: 70,
    tests_snapshot: {},
    artefacto_sha256: "a".repeat(64),
    error_code: null,
    error_detail: null,
    created_at: "2026-09-23T12:00:00Z",
    ...over,
  }) as unknown as CorreccionIA

const SOLO_EJ1 = [
  correccion({
    desglose: [
      { nombre: "Usa la interfaz", puntaje: 3, max_puntaje: 5 },
      { nombre: "Produce la salida esperada", puntaje: 4, max_puntaje: 5 },
    ],
  }),
]

const getToken = () => Promise.resolve("dev-token")

function montar(correcciones: CorreccionIA[]) {
  const urls: { url: string; method: string }[] = []
  setupFetchMock({
    "/correccion-ia": () => ({ correcciones }),
    "/ejercicios": () => [tpEj(1), tpEj(2)],
    "/api/v1/entregas": () => ({ data: [entrega], meta: { cursor_next: null } }),
    "/api/v1/tareas-practicas/": () => tarea,
  })
  const base = globalThis.fetch
  vi.stubGlobal("fetch", (url: string | URL | Request, init?: RequestInit) => {
    urls.push({ url: String(url), method: (init?.method ?? "GET").toUpperCase() })
    return (base as typeof fetch)(url as never, init)
  })
  renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
  return urls
}

async function abrirEntrega() {
  await waitFor(() => expect(screen.getByTestId("entrega-drill-btn")).toBeDefined())
  fireEvent.click(screen.getByTestId("entrega-drill-btn"))
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

// ── C01 / C02 / C03 en la pantalla ─────────────────────────────────────

describe("HU-013 · completar criterios aunque falten correcciones", () => {
  it("C01: con un ejercicio sin corregir no hay 'Usar como base' pero si 'Completar criterios'", async () => {
    montar(SOLO_EJ1)
    await abrirEntrega()
    const boton = await screen.findByTestId("completar-criterios-ia")
    expect(screen.queryByTestId("resumen-usar-como-base")).toBeNull()
    fireEvent.click(boton)
    await waitFor(() => expect(screen.getByTestId("criterio-puntaje-ej-1#0")).toHaveValue(3))
    expect(screen.getByTestId("criterio-puntaje-ej-1#1")).toHaveValue(4)
    expect((screen.getByTestId("nota-final-input") as HTMLInputElement).value).toBe("")
  })

  it("C02: avisa cuantos completo y de que ejercicio falta la correccion", async () => {
    montar(SOLO_EJ1)
    await abrirEntrega()
    fireEvent.click(await screen.findByTestId("completar-criterios-ia"))
    const resultado = await screen.findByTestId("completar-criterios-resultado")
    expect(resultado.textContent).toMatch(/2 de 4/)
    expect(resultado.textContent).toMatch(/Ejercicio 2/)
  })

  it("C03: lo completado se puede editar y no se guarda nada sin Calificar", async () => {
    const urls = montar(SOLO_EJ1)
    await abrirEntrega()
    fireEvent.click(await screen.findByTestId("completar-criterios-ia"))
    const input = await screen.findByTestId("criterio-puntaje-ej-1#0")
    await waitFor(() => expect(input).toHaveValue(3))
    fireEvent.change(input, { target: { value: "5" } })
    expect(input).toHaveValue(5)
    expect(urls.some((u) => u.method !== "GET")).toBe(false)
  })

  it("sin ninguna correccion terminada no aparece el boton", async () => {
    montar([])
    await abrirEntrega()
    await waitFor(() => expect(screen.getByTestId("calificar-btn")).toBeDefined())
    expect(screen.queryByTestId("completar-criterios-ia")).toBeNull()
  })
})

// ── N01 a N05 en la regla ──────────────────────────────────────────────

const ROWS = [
  { key: "ej-1#0", ejercicioId: "ej-1", orden: 1, nombre: "Usa la interfaz", puntajeMax: 5 },
  {
    key: "ej-1#1",
    ejercicioId: "ej-1",
    orden: 1,
    nombre: "Produce la salida esperada",
    puntajeMax: 5,
  },
  { key: "ej-2#0", ejercicioId: "ej-2", orden: 2, nombre: "Usa la interfaz", puntajeMax: 5 },
]

describe("HU-013 · la regla para completar", () => {
  it("N01: mayusculas y espacios no cuentan, un nombre distinto si", () => {
    const c = [
      correccion({
        desglose: [
          { nombre: "  usa la INTERFAZ ", puntaje: 3, max_puntaje: 5 },
          { nombre: "Produce la salida", puntaje: 4, max_puntaje: 5 },
        ],
      }),
    ]
    expect(sugerirPuntajesDesdeCorrecciones(ROWS, c)).toEqual({ "ej-1#0": "3" })
  })

  it("N02: maximo distinto no se completa", () => {
    const c = [
      correccion({
        desglose: [
          { nombre: "Usa la interfaz", puntaje: 3, max_puntaje: 4 },
          { nombre: "Produce la salida esperada", puntaje: 4, max_puntaje: 5 },
        ],
      }),
    ]
    expect(sugerirPuntajesDesdeCorrecciones(ROWS, c)).toEqual({ "ej-1#1": "4" })
  })

  it("N02: sin maximo declarado, solo si el puntaje no supera el de la rubrica", () => {
    const c = [
      correccion({
        desglose: [
          { nombre: "Usa la interfaz", puntaje: 3 },
          { nombre: "Produce la salida esperada", puntaje: 7 },
        ],
      }),
    ]
    expect(sugerirPuntajesDesdeCorrecciones(ROWS, c)).toEqual({ "ej-1#0": "3" })
  })

  it("N03: el cero de un codigo que no compilo no se completa", () => {
    const c = [
      correccion({
        desglose: [
          { nombre: "Usa la interfaz", puntaje: 0, max_puntaje: 5, sin_ejecucion: true },
          { nombre: "Produce la salida esperada", puntaje: 4, max_puntaje: 5 },
        ],
      }),
    ]
    expect(sugerirPuntajesDesdeCorrecciones(ROWS, c)).toEqual({ "ej-1#1": "4" })
  })

  it("N04: no pisa lo que el docente ya escribio (un casillero vacio si se completa)", () => {
    const actuales = { "ej-1#0": "2", "ej-1#1": "" }
    expect(sugerirPuntajesDesdeCorrecciones(ROWS, SOLO_EJ1, actuales)).toEqual({ "ej-1#1": "4" })
  })

  it("N05: un ejercicio sin correccion terminada queda como esta", () => {
    const c = [
      ...SOLO_EJ1,
      correccion({
        id: "corr-2",
        tp_ejercicio_id: "ej-2",
        orden: 2,
        estado: "error",
        nota_100: null,
        desglose: [{ nombre: "Usa la interfaz", puntaje: 5, max_puntaje: 5 }],
      }),
    ]
    const r = sugerirPuntajesDesdeCorrecciones(ROWS, c)
    expect(r).not.toHaveProperty("ej-2#0")
    expect(r).toEqual({ "ej-1#0": "3", "ej-1#1": "4" })
  })
})
