/**
 * Aceptacion HU-035, vuelta de diseño (orquestador, antes de construir; el
 * constructor no la modifica). Pedido de Juani en la demo del 25/11: "que
 * mejore el marco, que se use toda la pantalla, que sea mas similar al diseño
 * que hicimos". Prototipo (fila del alumno):
 * https://claude.ai/artifact/BzTaGZcb55VdcZUbdswv6B (`Aula.dc.html`,
 * `Unidad.dc.html`, `UnidadTps.dc.html`).
 *
 * Contrato que fija esta prueba (lo visual fino se verifica en navegador real
 * contra el prototipo):
 *  - Curso y unidad usan todo el ancho: ningun contenedor `max-w-7xl` (el
 *    default de PageContainer) dentro de la vista.
 *  - Tarjeta de unidad: arriba el numero ("Unidad 1", "Unidad 2"... por orden)
 *    y como titulo el nombre SIN el prefijo "Unidad N · " si lo trae. El link
 *    conserva el nombre completo como nombre accesible (`aria-label`).
 *    Progreso: el texto "X de Y entregados" (X = entregas `submitted` o
 *    `graded` de los TPs publicados de la unidad) y un `role="progressbar"`
 *    con `aria-valuenow`=X y `aria-valuemax`=Y. Una unidad sin TPs no muestra
 *    progreso.
 *  - Pagina de unidad: el eyebrow "Unidad N" y el h1 con el nombre sin
 *    prefijo.
 *  - Fila de TP: si el TP tiene ejercicios (`GET
 *    /api/v1/tareas-practicas/<id>/ejercicios`, lista) muestra "Ejercicios X
 *    de Y" (X = `ejercicio_estados` completados de su entrega) y un
 *    `role="progressbar"`. Un TP sin ejercicios no muestra esa barra.
 *
 * C09  Curso y unidad ocupan todo el ancho.
 * C10  Tarjetas con numero de unidad, titulo y progreso de entregas.
 * C11  La unidad muestra su numero y su titulo.
 * C12  Cada TP muestra su avance de ejercicios.
 * N12  Unidades y TPs sin trabajo no muestran barras vacias ni "0 de 0".
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
import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { CursoView } from "../src/views/CursoView"
import { UnidadView } from "../src/views/UnidadView"
import { setupFetchMock } from "./_mocks"

const COM = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const MAT = "99999999-9999-9999-9999-999999999999"
const U1 = "11111111-1111-1111-1111-111111111111"
const U2 = "22222222-2222-2222-2222-222222222222"
const U3 = "33333333-3333-3333-3333-333333333333"
const HOY = "2027-03-10"

const unidad = (id: string, nombre: string, orden: number) => ({
  id,
  comision_id: COM,
  nombre,
  descripcion: `Resumen de ${nombre}`,
  orden,
  introduccion_html: "<p>intro</p>",
  fecha_apertura: null,
})

const tp = (id: string, titulo: string, unidad_id: string) => ({
  id,
  comision_id: COM,
  codigo: id.slice(0, 4),
  titulo,
  enunciado: "x",
  fecha_inicio: null,
  fecha_fin: null,
  estado: "published",
  unidad_id,
})

const UNIDADES = [
  unidad(U1, "Unidad 1 · Recursión y listas", 0),
  unidad(U2, "Secuenciales 2027", 1),
  unidad(U3, "Unidad 3 · Pilas y colas", 2),
]

const TPS = [
  tp("t1aaaaaa", "TP 1 · Recursión", U1),
  tp("t2aaaaaa", "TP 2 · Listas", U1),
  tp("t3aaaaaa", "TP 3 · Secuenciales", U2),
]

const ENTREGAS = [
  {
    id: "e1",
    tarea_practica_id: "t1aaaaaa",
    comision_id: COM,
    estado: "submitted",
    ejercicio_estados: [{ completado: true }, { completado: true }, { completado: true }],
    nota_final: null,
  },
  {
    id: "e3",
    tarea_practica_id: "t3aaaaaa",
    comision_id: COM,
    estado: "draft",
    ejercicio_estados: [{ completado: true }, { completado: false }],
    nota_final: null,
  },
]

function datos() {
  setupFetchMock({
    [`/api/v1/comisiones/${COM}/bienvenida`]: () => ({ html: "<h1>Hola</h1>" }),
    "/api/v1/materias/mias": () => ({
      data: [
        {
          materia_id: MAT,
          codigo: "P2",
          nombre: "Programación 2",
          comision_id: COM,
          comision_codigo: "A",
          comision_nombre: "A",
          horario_resumen: null,
          periodo_id: "p",
          periodo_codigo: "2027-1",
          inscripcion_id: "i",
          fecha_inscripcion: "2027-03-01",
        },
      ],
    }),
    "/api/v1/unidades": () => ({ data: UNIDADES, meta: { cursor_next: null } }),
    // Los ejercicios van antes que el listado: la URL del listado es prefijo.
    "/api/v1/tareas-practicas/t1aaaaaa/ejercicios": () => [
      { id: "x1" },
      { id: "x2" },
      { id: "x3" },
    ],
    "/api/v1/tareas-practicas/t2aaaaaa/ejercicios": () => [],
    "/api/v1/tareas-practicas/t3aaaaaa/ejercicios": () => [{ id: "y1" }, { id: "y2" }],
    "/api/v1/tareas-practicas": () => ({ data: TPS, meta: { cursor_next: null } }),
    "/api/v1/entregas": () => ({ data: ENTREGAS, meta: { cursor_next: null } }),
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

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function tarjeta(nombreCompleto: string): HTMLElement {
  const link = screen.getByRole("link", { name: nombreCompleto })
  return (link.closest("article, li, [data-tarjeta-unidad]") as HTMLElement | null) ?? link
}

describe("HU-035 · diseño del curso", () => {
  it("C09: el curso usa todo el ancho", async () => {
    datos()
    const { container } = conRouter(<CursoView comisionId={COM} getToken={getToken} hoy={HOY} />)
    await screen.findByRole("link", { name: "Unidad 1 · Recursión y listas" })
    expect(container.querySelector(".max-w-7xl")).toBeNull()
  })

  it("C10: tarjetas con numero, titulo sin prefijo y progreso de entregas", async () => {
    datos()
    conRouter(<CursoView comisionId={COM} getToken={getToken} hoy={HOY} />)
    await screen.findByRole("link", { name: "Unidad 1 · Recursión y listas" })

    const t1 = tarjeta("Unidad 1 · Recursión y listas")
    expect(within(t1).getByText("Unidad 1")).toBeTruthy()
    expect(within(t1).getByText("Recursión y listas")).toBeTruthy()
    await waitFor(() => expect(within(t1).getByText("1 de 2 entregados")).toBeTruthy())
    const barra = within(t1).getByRole("progressbar")
    expect(barra.getAttribute("aria-valuenow")).toBe("1")
    expect(barra.getAttribute("aria-valuemax")).toBe("2")

    const t2 = tarjeta("Secuenciales 2027")
    expect(within(t2).getByText("Unidad 2")).toBeTruthy()
    expect(within(t2).getByText("Secuenciales 2027")).toBeTruthy()
    await waitFor(() => expect(within(t2).getByText("0 de 1 entregados")).toBeTruthy())
  })

  it("N12: una unidad sin TPs no muestra progreso", async () => {
    datos()
    conRouter(<CursoView comisionId={COM} getToken={getToken} hoy={HOY} />)
    const link = await screen.findByRole("link", { name: "Unidad 3 · Pilas y colas" })
    const t3 = (link.closest("article, li, [data-tarjeta-unidad]") as HTMLElement | null) ?? link
    await screen.findByText("1 de 2 entregados")
    expect(within(t3).queryByRole("progressbar")).toBeNull()
    expect(within(t3).queryByText(/0 de 0/)).toBeNull()
  })
})

describe("HU-035 · diseño de la unidad", () => {
  it("C09/C11: todo el ancho, numero y titulo sin prefijo", async () => {
    datos()
    const { container } = conRouter(
      <UnidadView comisionId={COM} unidadId={U1} pestana="tps" getToken={getToken} hoy={HOY} />,
    )
    expect(
      await screen.findByRole("heading", { level: 1, name: "Recursión y listas" }),
    ).toBeTruthy()
    expect(screen.getByText("Unidad 1")).toBeTruthy()
    expect(container.querySelector(".max-w-7xl")).toBeNull()
  })

  it("C12/N12: cada TP con ejercicios muestra su avance; sin ejercicios, no", async () => {
    datos()
    conRouter(
      <UnidadView comisionId={COM} unidadId={U1} pestana="tps" getToken={getToken} hoy={HOY} />,
    )
    const fila1 = await screen.findByRole("link", { name: /TP 1 · Recursión/ })
    await waitFor(() => expect(within(fila1).getByText("Ejercicios 3 de 3")).toBeTruthy())
    const barra = within(fila1).getByRole("progressbar")
    expect(barra.getAttribute("aria-valuenow")).toBe("3")
    expect(barra.getAttribute("aria-valuemax")).toBe("3")

    const fila2 = screen.getByRole("link", { name: /TP 2 · Listas/ })
    expect(within(fila2).queryByRole("progressbar")).toBeNull()
    expect(within(fila2).queryByText(/Ejercicios 0 de 0/)).toBeNull()
  })

  it("C12: cuenta los completados de la entrega en curso", async () => {
    datos()
    conRouter(
      <UnidadView comisionId={COM} unidadId={U2} pestana="tps" getToken={getToken} hoy={HOY} />,
    )
    const fila = await screen.findByRole("link", { name: /TP 3 · Secuenciales/ })
    await waitFor(() => expect(within(fila).getByText("Ejercicios 1 de 2")).toBeTruthy())
  })
})
