/**
 * Los TPs publicados que no estan en ninguna unidad siguen al alcance del
 * alumno (review del PR #158, 2026-11-25).
 *
 * Con HU-035 la pagina de la materia redirige al campus y el campus lista los
 * TPs solo dentro de cada unidad. El selector viejo tenia un grupo "sin
 * unidad"; sin un equivalente, un TP con `unidad_id` vacio (o de una unidad
 * borrada: la FK es `ON DELETE SET NULL`) quedaba sin ningun camino.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  Outlet,
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router"
import { cleanup, render, screen, within } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { CursoView, tpsSinUnidad } from "../src/views/CursoView"
import { setupFetchMock } from "./_mocks"

const COM = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const MAT = "99999999-9999-9999-9999-999999999999"
const U1 = "11111111-1111-1111-1111-111111111111"
const U_BORRADA = "44444444-4444-4444-4444-444444444444"
const HOY = "2027-03-10"

const tp = (id: string, titulo: string, unidad_id: string | null, estado = "published") => ({
  id,
  comision_id: COM,
  codigo: id.slice(0, 4),
  titulo,
  enunciado: "x",
  fecha_inicio: null,
  fecha_fin: null,
  estado,
  unidad_id,
})

const TPS = [
  tp("t1aaaaaa", "TP 1 · En la unidad", U1),
  tp("t2aaaaaa", "TP suelto · Sin unidad", null),
  tp("t3aaaaaa", "TP huerfano · Unidad borrada", U_BORRADA),
  tp("t4aaaaaa", "TP borrador sin unidad", null, "draft"),
]

function datos(unidades: unknown[]) {
  setupFetchMock({
    [`/api/v1/comisiones/${COM}/bienvenida`]: () => ({ html: null }),
    "/api/v1/materias/mias": () => ({
      data: [
        {
          materia_id: MAT,
          codigo: "PROG1",
          nombre: "Programación 1",
          comision_id: COM,
          comision_codigo: "C1",
          comision_nombre: "Comision 1",
          horario_resumen: null,
          periodo_id: "p1",
          periodo_codigo: "2027-1",
          inscripcion_id: "i1",
          fecha_inscripcion: "2027-03-01",
        },
      ],
    }),
    "/api/v1/unidades": () => ({ data: unidades, meta: { cursor_next: null } }),
    "/api/v1/tareas-practicas": () => ({ data: TPS, meta: { cursor_next: null } }),
    "/api/v1/entregas": () => ({ data: [], meta: { cursor_next: null } }),
  })
}

function montar(node: ReactNode) {
  const root = createRootRoute({ component: () => <Outlet /> })
  const index = createRoute({ getParentRoute: () => root, path: "/", component: () => <>{node}</> })
  const router = createRouter({
    routeTree: root.addChildren([index]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router as never} />
    </QueryClientProvider>,
  )
}

const UNIDAD_1 = {
  id: U1,
  comision_id: COM,
  nombre: "Unidad 1 · Bienvenida",
  descripcion: null,
  orden: 0,
  introduccion_html: null,
  fecha_apertura: null,
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("TPs sin unidad en el campus del alumno", () => {
  it("tpsSinUnidad: sin unidad_id o con una unidad que no esta en la lista", () => {
    const sueltos = tpsSinUnidad(TPS as never, [{ id: U1 }]).map((t) => t.id)
    expect(sueltos).toEqual(["t2aaaaaa", "t3aaaaaa", "t4aaaaaa"])
  })

  it("la pagina del curso los muestra en 'Otros trabajos practicos' y linkean al TP", async () => {
    datos([UNIDAD_1])
    montar(<CursoView comisionId={COM} getToken={async () => "t"} hoy={HOY} />)
    const seccion = (await screen.findByRole("heading", { name: "Otros trabajos prácticos" }))
      .parentElement as HTMLElement
    const sinUnidad = within(seccion).getByRole("link", { name: /TP suelto · Sin unidad/ })
    expect(sinUnidad.getAttribute("href")).toContain(`/materia/${MAT}`)
    expect(sinUnidad.getAttribute("href")).toContain("tareaId=t2aaaaaa")
    expect(within(seccion).getByRole("link", { name: /TP huerfano · Unidad borrada/ })).toBeTruthy()
    // El de la unidad sigue adentro de su unidad, y un borrador no aparece.
    expect(within(seccion).queryByText(/TP 1 · En la unidad/)).toBeNull()
    expect(within(seccion).queryByText(/TP borrador sin unidad/)).toBeNull()
  })

  it("con todos los TPs adentro de unidades, la seccion no aparece", async () => {
    setupFetchMock({
      "/api/v1/materias/mias": () => ({
        data: [
          {
            materia_id: MAT,
            codigo: "PROG1",
            nombre: "Programación 1",
            comision_id: COM,
            comision_codigo: "C1",
            comision_nombre: "Comision 1",
            horario_resumen: null,
            periodo_id: "p1",
            periodo_codigo: "2027-1",
            inscripcion_id: "i1",
            fecha_inscripcion: "2027-03-01",
          },
        ],
      }),
      "/api/v1/unidades": () => ({
        data: [UNIDAD_1, { ...UNIDAD_1, id: U_BORRADA, nombre: "Unidad 2", orden: 1 }],
        meta: { cursor_next: null },
      }),
      "/api/v1/tareas-practicas": () => ({
        data: [TPS[0], TPS[2]],
        meta: { cursor_next: null },
      }),
      "/api/v1/entregas": () => ({ data: [], meta: { cursor_next: null } }),
    })
    montar(<CursoView comisionId={COM} getToken={async () => "t"} hoy={HOY} />)
    expect(await screen.findByRole("link", { name: "Unidad 1 · Bienvenida" })).toBeTruthy()
    expect(screen.queryByRole("heading", { name: "Otros trabajos prácticos" })).toBeNull()
  })
})
