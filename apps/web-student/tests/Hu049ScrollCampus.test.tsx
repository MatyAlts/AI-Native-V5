/**
 * HU-049 (nivel S). En la pagina del curso aparecia un segundo scroll del
 * documento y un espacio vacio enorme debajo del pie. Causa medida en Chrome:
 * el contenedor con scroll del campus (`CampusPagina`, `flex-1
 * overflow-y-auto`) no era `position: relative`, asi que los `sr-only`
 * (posicion absoluta) de la lista de unidades tomaban como bloque contenedor
 * el documento y lo estiraban (scrollHeight 1526 con la ventana en 937).
 *
 * jsdom no mide layout: esta prueba fija lo que si se puede afirmar. En el
 * curso y en la unidad, el contenedor con scroll es el bloque contenedor de
 * sus descendientes absolutos (clase `relative`), y sigue siendo el que
 * scrollea (`overflow-y-auto`, `flex-1`). La medicion real va en navegador.
 *
 * C01  El curso no estira el documento: su contenedor con scroll es `relative`
 *      y todo `sr-only`/`absolute` adentro tiene un ancestro posicionado
 *      dentro de ese contenedor.
 * C02  Lo mismo en la pagina de la unidad (comparte `CampusPagina`).
 * N01  El scroll interno sigue: el contenedor conserva `flex-1 overflow-y-auto`.
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
import { cleanup, render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { CursoView } from "../src/views/CursoView"
import { UnidadView } from "../src/views/UnidadView"
import { setupFetchMock } from "./_mocks"

const COM = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const MAT = "99999999-9999-9999-9999-999999999999"
const U1 = "11111111-1111-1111-1111-111111111111"
const HOY = "2027-03-10"

function datos() {
  setupFetchMock({
    [`/api/v1/comisiones/${COM}/bienvenida`]: () => ({ html: "<h1>Hola</h1>" }),
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
      data: [
        {
          id: U1,
          comision_id: COM,
          nombre: "Unidad 1 · Secuenciales",
          descripcion: "Resumen",
          orden: 0,
          introduccion_html: "<h2>Intro</h2>",
          fecha_apertura: null,
        },
      ],
      meta: { cursor_next: null },
    }),
    "/api/v1/tareas-practicas": () => ({
      data: [
        {
          id: "t1aaaaaa",
          comision_id: COM,
          codigo: "t1aa",
          titulo: "TP 1 · Primeros programas",
          enunciado: "x",
          fecha_inicio: null,
          fecha_fin: null,
          estado: "published",
          unidad_id: U1,
        },
      ],
      meta: { cursor_next: null },
    }),
    "/api/v1/entregas": () => ({ data: [], meta: { cursor_next: null } }),
  })
}

function conRouter(node: ReactNode) {
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

const getToken = async () => "t"

const POSICIONADO = ["relative", "absolute", "fixed", "sticky"]

function contenedorConScroll(el: Element): HTMLElement {
  const c = el.closest(".overflow-y-auto")
  if (!c) throw new Error("no hay contenedor con scroll")
  return c as HTMLElement
}

/** Ancestro posicionado mas cercano (por clase Tailwind), o null. */
function ancestroPosicionado(el: Element): Element | null {
  let actual = el.parentElement
  while (actual) {
    if (POSICIONADO.some((c) => actual?.classList.contains(c))) return actual
    actual = actual.parentElement
  }
  return null
}

function verificar(scroll: HTMLElement) {
  // N01: sigue siendo el que scrollea.
  expect(scroll.classList.contains("overflow-y-auto")).toBe(true)
  expect(scroll.classList.contains("flex-1")).toBe(true)
  // C01/C02: es el bloque contenedor de sus absolutos.
  expect(scroll.classList.contains("relative")).toBe(true)
  for (const abs of Array.from(scroll.querySelectorAll(".sr-only, .absolute"))) {
    const anc = ancestroPosicionado(abs)
    expect(anc !== null && scroll.contains(anc)).toBe(true)
  }
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("HU-049 · el campus no estira el documento", () => {
  it("C01/N01: el contenedor con scroll del curso contiene sus absolutos", async () => {
    datos()
    conRouter(<CursoView comisionId={COM} getToken={getToken} hoy={HOY} />)
    const titulo = await screen.findByRole("heading", { name: "Programación 1" })
    await screen.findByRole("link", { name: /Unidad 1 · Secuenciales/ })
    const scroll = contenedorConScroll(titulo)
    // El caso del bug: hay sr-only adentro (titulo oculto de la lista de unidades).
    expect(scroll.querySelectorAll(".sr-only").length).toBeGreaterThan(0)
    verificar(scroll)
  })

  it("C02/N01: el contenedor con scroll de la unidad contiene sus absolutos", async () => {
    datos()
    conRouter(
      <UnidadView
        comisionId={COM}
        unidadId={U1}
        pestana="introduccion"
        getToken={getToken}
        hoy={HOY}
      />,
    )
    const tab = await screen.findByRole("tab", { name: "Introducción" })
    verificar(contenedorConScroll(tab))
  })
})
