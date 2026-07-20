import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { MateriaCard } from "../src/components/MateriaCard"
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

describe("MateriaCard", () => {
  it("muestra kicker con codigo materia + nombre comision", () => {
    const materia = makeMateria()
    render(<MateriaCard materia={materia} onEnter={() => {}} />)
    const kicker = screen.getByTestId("materia-card-kicker")
    expect(kicker.textContent).toContain("PROG2")
    expect(kicker.textContent).toContain("A-Manana")
  })

  it("muestra el nombre completo de la materia como headline", () => {
    const materia = makeMateria()
    render(<MateriaCard materia={materia} onEnter={() => {}} />)
    expect(screen.getByText("Programacion 2")).toBeInTheDocument()
  })

  it("muestra el periodo en la metaline", () => {
    const materia = makeMateria()
    render(<MateriaCard materia={materia} onEnter={() => {}} />)
    expect(screen.getByTestId("materia-card-periodo").textContent).toBe("2026-S1")
  })

  it("muestra horario resumen si esta disponible", () => {
    const materia = makeMateria({ horario_resumen: "Lun/Mie 8-10" })
    render(<MateriaCard materia={materia} onEnter={() => {}} />)
    expect(screen.getByTestId("materia-card-horario").textContent).toBe("Lun/Mie 8-10")
  })

  it("oculta horario cuando es null (no string vacio en DOM)", () => {
    const materia = makeMateria({ horario_resumen: null })
    render(<MateriaCard materia={materia} onEnter={() => {}} />)
    expect(screen.queryByTestId("materia-card-horario")).toBeNull()
  })

  it("cae a 'Comision X' cuando comision_nombre es null", () => {
    const materia = makeMateria({ comision_nombre: null, comision_codigo: "B" })
    render(<MateriaCard materia={materia} onEnter={() => {}} />)
    const kicker = screen.getByTestId("materia-card-kicker")
    expect(kicker.textContent).toContain("Comision B")
  })

  it("dispara onEnter con la materia cuando se clickea el CTA", () => {
    const materia = makeMateria()
    const onEnter = vi.fn()
    render(<MateriaCard materia={materia} onEnter={onEnter} />)
    fireEvent.click(screen.getByTestId("materia-card-enter"))
    expect(onEnter).toHaveBeenCalledTimes(1)
    expect(onEnter).toHaveBeenCalledWith(materia)
  })

  it("expone data-materia-codigo para selectores E2E", () => {
    const materia = makeMateria({ codigo: "REDES1" })
    render(<MateriaCard materia={materia} onEnter={() => {}} />)
    const card = screen.getByTestId("materia-card")
    expect(card.getAttribute("data-materia-codigo")).toBe("REDES1")
  })
})
