/**
 * B2b (6.4/6.5): `sin_clasificar` (el árbol corrió y no pudo decidir un eje)
 * es un quinto valor real de `Classification.appropriation` desde 6.2.
 *
 * Antes de este fix, `order` en `DistribucionSection` era una lista
 * hardcodeada de 5 claves (`APR_ORDER` + "autonomo" + "indeterminado") que NO
 * incluía "sin_clasificar": el backend manda la cuenta real en
 * `block.por_apropiacion["sin_clasificar"]`, pero el gráfico de barras nunca
 * la dibuja — las barras no suman el total que el propio componente muestra,
 * y el hueco es invisible (no hay error, no hay warning).
 */
import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { DistribucionSection } from "../src/pages/PedagogiaPage"

afterEach(() => {
  cleanup()
})

function buildBlock(overrides: Partial<Record<string, number>> = {}) {
  const por_apropiacion: Record<string, number> = {
    apropiacion_reflexiva: 2,
    apropiacion_superficial: 1,
    sin_clasificar: 3,
    ...overrides,
  }
  const total = Object.values(por_apropiacion).reduce((a, b) => a + b, 0)
  return {
    n_episodios_clasificados: total,
    n_indeterminados: 0,
    n_sin_clasificar: por_apropiacion.sin_clasificar ?? 0,
    por_apropiacion,
    por_subgrupo: [],
  }
}

describe("DistribucionSection — sin_clasificar", () => {
  it("dibuja una barra/leyenda para sin_clasificar, no solo para las 4 claves viejas", () => {
    render(<DistribucionSection block={buildBlock()} />)

    // Antes del fix, "sin_clasificar" no está en `order` y no se renderiza
    // ningún texto ni conteo asociado a esa clave.
    expect(screen.getByText(/sin clasificar/i)).toBeInTheDocument()
  })

  it("el label de sin_clasificar es propio, no el de indeterminado", () => {
    render(<DistribucionSection block={buildBlock()} />)

    // No debe reusar "Indeterminado" como label — son conceptos distintos
    // (uno es ausencia de señal, el otro es que el árbol corrió y no decidió).
    expect(screen.queryByText("Indeterminado")).not.toBeInTheDocument()
    expect(screen.getByText(/sin clasificar/i)).toBeInTheDocument()
  })
})
