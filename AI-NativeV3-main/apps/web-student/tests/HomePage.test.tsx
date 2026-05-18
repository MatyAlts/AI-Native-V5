/**
 * Tests del shell de la home (post-craft Fase 2).
 *
 * Atacamos `HomeContent`, la vista presentacional pura extraída de la
 * ruta `/`. Evita el costo de envolver en RouterProvider para verificar
 * los 3 estados (loading, error, lista) + el empty state honesto del
 * gap B.2.
 */
import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { HomeContent } from "../src/routes/index"
import type { MateriaInscripta } from "../src/lib/api"

function makeMateria(overrides: Partial<MateriaInscripta> = {}): MateriaInscripta {
  return {
    materia_id: "ffffffff-ffff-ffff-ffff-ffffffffffff",
    codigo: "PROG2",
    nombre: "Programacion 2",
    comision_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    comision_codigo: "A",
    comision_nombre: "A-Manana",
    horario_resumen: null,
    periodo_id: "12345678-1234-1234-1234-123456789abc",
    periodo_codigo: "2026-S1",
    inscripcion_id: "aa0940aa-d7d9-4fb1-b4f0-fa8ec151dffe",
    fecha_inscripcion: "2026-03-20",
    ...overrides,
  }
}

describe("HomeContent", () => {
  it("muestra loading spinner mientras isLoading=true", () => {
    render(<HomeContent isLoading={true} error={null} materias={[]} onEnter={() => {}} />)
    expect(screen.getByTestId("home-loading")).toBeInTheDocument()
  })

  it("muestra detalle del error cuando hay error", () => {
    render(
      <HomeContent
        isLoading={false}
        error="Error: 500 internal"
        materias={[]}
        onEnter={() => {}}
      />,
    )
    expect(screen.getByText(/no pudimos cargar tus materias/i)).toBeInTheDocument()
    expect(screen.getByText(/500 internal/i)).toBeInTheDocument()
  })

  it("muestra empty state honesto con mensaje gap B.2 cuando materias=[]", () => {
    render(<HomeContent isLoading={false} error={null} materias={[]} onEnter={() => {}} />)
    const empty = screen.getByTestId("home-empty-gap-b2")
    expect(empty).toBeInTheDocument()
    expect(empty.textContent).toMatch(/no estas viendo tus materias/i)
    expect(empty.textContent).toMatch(/gap-b\.2/i)
  })

  it("empty state muestra strip N1-N4 (los 4 niveles del modelo)", () => {
    render(<HomeContent isLoading={false} error={null} materias={[]} onEnter={() => {}} />)
    expect(screen.getByTestId("level-dot-n1")).toBeInTheDocument()
    expect(screen.getByTestId("level-dot-n2")).toBeInTheDocument()
    expect(screen.getByTestId("level-dot-n3")).toBeInTheDocument()
    expect(screen.getByTestId("level-dot-n4")).toBeInTheDocument()
  })

  it("renderiza 1 MateriaCard cuando hay 1 materia inscripta", () => {
    const materia = makeMateria()
    render(
      <HomeContent isLoading={false} error={null} materias={[materia]} onEnter={() => {}} />,
    )
    const cards = screen.getAllByTestId("materia-card")
    expect(cards).toHaveLength(1)
    expect(screen.getByText("Programacion 2")).toBeInTheDocument()
  })

  it("renderiza N>5 materias en lista densa, NO como cards uniformes", () => {
    const materias = Array.from({ length: 6 }, (_, i) =>
      makeMateria({
        materia_id: `materia-${i}`,
        inscripcion_id: `insc-${i}`,
        codigo: `MAT${i}`,
        nombre: `Materia ${i}`,
      }),
    )
    render(
      <HomeContent isLoading={false} error={null} materias={materias} onEnter={() => {}} />,
    )
    expect(screen.getByTestId("home-densa-list")).toBeInTheDocument()
    const items = screen.getAllByTestId("materia-list-item")
    expect(items).toHaveLength(6)
    // Y NO debe haber cards (el switch a lista densa es exclusivo).
    expect(screen.queryAllByTestId("materia-card")).toHaveLength(0)
  })

  it("muestra el periodo del primer item como kicker de la home", () => {
    const m = makeMateria({ periodo_codigo: "2026-S2" })
    render(<HomeContent isLoading={false} error={null} materias={[m]} onEnter={() => {}} />)
    expect(screen.getByTestId("home-kicker-periodo").textContent).toBe("2026-S2")
  })

  it("dispara onEnter con la materia correcta al clickear el CTA de una card", () => {
    const materia = makeMateria()
    const onEnter = vi.fn()
    render(<HomeContent isLoading={false} error={null} materias={[materia]} onEnter={onEnter} />)
    fireEvent.click(screen.getByTestId("materia-card-enter"))
    expect(onEnter).toHaveBeenCalledTimes(1)
    expect(onEnter).toHaveBeenCalledWith(materia)
  })
})
