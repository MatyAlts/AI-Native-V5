/**
 * Tests del header contextual de la página de materia (post-craft Fase 2).
 *
 * `MateriaContextLine` es el kicker mono que reemplaza al ComisionSelector
 * eliminado: muestra `CODIGO_MATERIA · COMISION · PERIODO` en una sola
 * línea. Es el "anchor" auditorial visible mientras el alumno navega
 * dentro de una materia. La RutaPage real envuelve esto con un `Link`
 * de TanStack que requiere RouterProvider — testeamos solo la línea pura.
 */
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { MateriaInscripta } from "../src/lib/api"
import { MateriaContextLine } from "../src/routes/materia.$id"

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

describe("MateriaContextLine", () => {
  it("muestra los 3 segmentos: codigo, comision, periodo", () => {
    const materia = makeMateria()
    render(<MateriaContextLine materia={materia} />)
    expect(screen.getByTestId("materia-header-codigo").textContent).toBe("PROG2")
    expect(screen.getByTestId("materia-header-comision").textContent).toBe("A-Manana")
    expect(screen.getByTestId("materia-header-periodo").textContent).toBe("2026-S1")
  })

  it("cae a 'Comision X' cuando comision_nombre es null", () => {
    const materia = makeMateria({ comision_nombre: null, comision_codigo: "B" })
    render(<MateriaContextLine materia={materia} />)
    expect(screen.getByTestId("materia-header-comision").textContent).toBe("Comision B")
  })

  it("renderiza el contenedor con data-testid='materia-context-line'", () => {
    const materia = makeMateria()
    render(<MateriaContextLine materia={materia} />)
    expect(screen.getByTestId("materia-context-line")).toBeInTheDocument()
  })
})
