/**
 * Aceptacion HU-043 (orquestador, antes de construir; el constructor no la
 * modifica). Hallazgo de la prueba en produccion del 25/11: la home "Mis
 * materias" del alumno (ruta `/`) sigue en la columna angosta `max-w-3xl`,
 * cuando el resto del campus usa todo el ancho (HU-040 lo saco de
 * `/mis-notas` y `/progreso`; `CursoView` no tiene tope de ancho).
 *
 * C04  La home del alumno no usa el contenedor angosto `max-w-3xl`.
 *
 * Contrato (sobre `HomeContent` y `AvisoEntregaVencida`, exportados de
 * `src/routes/index.tsx`, igual que `tests/HomePage.test.tsx`):
 *  - Ningun estado de la home renderiza un elemento con clase `max-w-3xl`:
 *    con materias, cargando, sin materias, y el aviso de entrega vencida que
 *    se muestra arriba de la lista.
 *  - Con materias, ningun ANCESTRO del titulo "Mis materias" ni de la tarjeta
 *    de una materia tiene un tope de ancho (`max-w-*`, salvo `max-w-full` y
 *    `max-w-none`). Esto descarta cambiar `max-w-3xl` por `max-w-4xl` o
 *    `max-w-5xl`, que sigue siendo una columna. Los `max-w-*` de un parrafo
 *    suelto (la bajada, que hoy tiene `max-w-xl` para que la linea se lea)
 *    no cuentan: no son ancestros del titulo ni de las tarjetas.
 */
import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

// Igual que HomePage.test.tsx: la home usa <Link>; sin RouterProvider explota.
vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-router")>()
  return {
    ...actual,
    Link: (props: Record<string, unknown>) => {
      const { to, children, search: _search, params: _params, ...rest } = props
      return (
        <a href={String(to)} {...rest}>
          {children as React.ReactNode}
        </a>
      )
    },
    useNavigate: () => vi.fn(),
  }
})

import type { MateriaInscripta } from "../src/lib/api"
import { AvisoEntregaVencida, HomeContent } from "../src/routes/index"

function materia(): MateriaInscripta {
  return {
    materia_id: "ffffffff-ffff-ffff-ffff-ffffffffffff",
    codigo: "PROG1",
    nombre: "Programacion 1",
    comision_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    comision_codigo: "A",
    comision_nombre: "A-Manana",
    horario_resumen: null,
    periodo_id: "12345678-1234-1234-1234-123456789abc",
    periodo_codigo: "2027-S1",
    inscripcion_id: "aa0940aa-d7d9-4fb1-b4f0-fa8ec151dffe",
    fecha_inscripcion: "2027-03-20",
  }
}

const TOPE = /^max-w-(?!full$|none$)/

/** Clases `max-w-*` con tope en los ancestros de `el` hasta `raiz` (inclusive). */
function topesEnAncestros(el: Element, raiz: Element): string[] {
  const topes: string[] = []
  let actual: Element | null = el.parentElement
  while (actual) {
    for (const c of Array.from(actual.classList)) if (TOPE.test(c)) topes.push(c)
    if (actual === raiz) break
    actual = actual.parentElement
  }
  return topes
}

afterEach(() => {
  cleanup()
})

describe("HU-043 · la home del alumno usa todo el ancho", () => {
  it("C04: con materias no hay max-w-3xl ni tope de ancho sobre el titulo y las tarjetas", () => {
    const { container } = render(
      <HomeContent isLoading={false} error={null} materias={[materia()]} onEnter={() => {}} />,
    )
    const titulo = screen.getByRole("heading", { name: "Mis materias" })
    const tarjeta = screen.getByText("Programacion 1")
    expect(container.querySelector(".max-w-3xl")).toBeNull()
    expect(topesEnAncestros(titulo, container)).toEqual([])
    expect(topesEnAncestros(tarjeta, container)).toEqual([])
  })

  it("C04: cargando, el esqueleto tampoco usa max-w-3xl", () => {
    const { container } = render(
      <HomeContent isLoading={true} error={null} materias={[]} onEnter={() => {}} />,
    )
    expect(screen.getByTestId("home-loading")).toBeTruthy()
    expect(container.querySelector(".max-w-3xl")).toBeNull()
  })

  it("C04: sin materias, la home tampoco usa max-w-3xl", () => {
    const { container } = render(
      <HomeContent isLoading={false} error={null} materias={[]} onEnter={() => {}} />,
    )
    expect(container.textContent?.length ?? 0).toBeGreaterThan(0)
    expect(container.querySelector(".max-w-3xl")).toBeNull()
  })

  it("C04: el aviso de entrega vencida tampoco usa max-w-3xl", () => {
    const { container } = render(<AvisoEntregaVencida onClose={() => {}} />)
    expect(screen.getByTestId("aviso-entrega-vencida")).toBeTruthy()
    expect(container.querySelector(".max-w-3xl")).toBeNull()
  })
})
