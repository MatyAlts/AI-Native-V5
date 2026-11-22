/**
 * Aceptacion HU-013, segunda ronda (orquestador, antes de corregir; el
 * constructor no la modifica). Sale de la verificacion independiente del
 * PR #145 (22/11/2026). Juani delego el circuito: si el PR no esta ok, se
 * arregla y despues va a main. Helpers copiados de Hu013CriteriosIA.test.tsx
 * (aceptacion `c44c420`).
 *
 * R01  En una entrega SIN calificar, "Completar criterios" no la pone en modo
 *      re-calificacion: siguen "Calificar" y no aparecen "Guardar
 *      re-calificacion" ni "Cancelar".
 * R02  El aviso dice cuantos casilleros ya tenian valor y por eso no se tocaron.
 * R03  El aviso de faltantes nombra solo ejercicios con rubrica, y no nombra
 *      un ejercicio cuya correccion terminada trajo desglose aunque no traiga nota.
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { CorreccionIA } from "../src/lib/api"
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

function montarCon(ejercicios: unknown[], correcciones: CorreccionIA[]) {
  setupFetchMock({
    "/correccion-ia": () => ({ correcciones }),
    "/ejercicios": () => ejercicios,
    "/api/v1/entregas": () => ({ data: [entrega], meta: { cursor_next: null } }),
    "/api/v1/tareas-practicas/": () => tarea,
  })
  renderWithRouter(<CorreccionesView comisionId={COMISION_ID} getToken={getToken} />)
}

// Margen de espera: con la suite entera en paralelo el montaje puede pasar
// el segundo por defecto (R01 fallo 1 de 7 corridas por tiempo, 22/11).
// Solo cambia cuanto se espera, no que se comprueba.
const ESPERA = { timeout: 5000 }

describe("HU-013 · segunda ronda", () => {
  it("R01: en una entrega sin calificar no entra en modo re-calificacion", async () => {
    montar(SOLO_EJ1)
    await abrirEntrega()
    fireEvent.click(await screen.findByTestId("completar-criterios-ia", {}, ESPERA))
    await waitFor(
      () => expect(screen.getByTestId("criterio-puntaje-ej-1#0")).toHaveValue(3),
      ESPERA,
    )
    expect(screen.getByTestId("calificar-btn")).toBeDefined()
    expect(screen.queryByTestId("guardar-recalificacion-btn")).toBeNull()
    expect(screen.queryByTestId("cancelar-recalificacion-btn")).toBeNull()
  })

  it("R02: avisa cuantos casilleros ya tenian valor", async () => {
    montar(SOLO_EJ1)
    await abrirEntrega()
    const input = await screen.findByTestId("criterio-puntaje-ej-1#0", {}, ESPERA)
    fireEvent.change(input, { target: { value: "2" } })
    fireEvent.click(await screen.findByTestId("completar-criterios-ia", {}, ESPERA))
    const resultado = await screen.findByTestId("completar-criterios-resultado", {}, ESPERA)
    expect(resultado.textContent).toMatch(/1 de 4/)
    expect(resultado.textContent).toMatch(/1 ya ten[ií]a valor/)
    expect(screen.getByTestId("criterio-puntaje-ej-1#0")).toHaveValue(2)
  })

  it("R03: no nombra como faltante un ejercicio sin rubrica", async () => {
    const sinRubrica = {
      ...tpEj(2),
      ejercicio: { id: "ej-2", titulo: "Ejercicio 2", rubrica: null },
    }
    montarCon([tpEj(1), sinRubrica], SOLO_EJ1)
    await abrirEntrega()
    fireEvent.click(await screen.findByTestId("completar-criterios-ia", {}, ESPERA))
    const resultado = await screen.findByTestId("completar-criterios-resultado", {}, ESPERA)
    expect(resultado.textContent).toMatch(/2 de 2/)
    expect(resultado.textContent).not.toMatch(/Ejercicio 2/)
  })

  it("R03: no nombra como faltante un ejercicio con desglose aunque no traiga nota", async () => {
    const ej1SinNota = [
      correccion({
        nota_100: null,
        desglose: [
          { nombre: "Usa la interfaz", puntaje: 3, max_puntaje: 5 },
          { nombre: "Produce la salida esperada", puntaje: 4, max_puntaje: 5 },
        ],
      }),
    ]
    montar(ej1SinNota)
    await abrirEntrega()
    fireEvent.click(await screen.findByTestId("completar-criterios-ia", {}, ESPERA))
    const resultado = await screen.findByTestId("completar-criterios-resultado", {}, ESPERA)
    expect(resultado.textContent).toMatch(/2 de 4/)
    expect(resultado.textContent).not.toMatch(/Ejercicio 1/)
    expect(resultado.textContent).toMatch(/Ejercicio 2/)
  })
})
