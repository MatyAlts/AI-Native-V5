import { describe, expect, it } from "vitest"
import { textoPedidosReentrega } from "../src/utils/pedidosCorreccion"

const est = (orden: number, marca?: boolean) => ({
  orden,
  completado: true,
  ...(marca === undefined ? {} : { reabierto_por_docente: marca }),
})

describe("textoPedidosReentrega", () => {
  it("dos ejercicios: ej. 2 y 4", () => {
    expect(textoPedidosReentrega([est(1, false), est(2, true), est(3, false), est(4, true)])).toBe(
      "ej. 2 y 4",
    )
  })
  it("uno solo: ej. 2", () => {
    expect(textoPedidosReentrega([est(1, false), est(2, true), est(3, false)])).toBe("ej. 2")
  })
  it("tres: ej. 1, 3 y 5 (ordenados)", () => {
    expect(
      textoPedidosReentrega([
        est(5, true),
        est(4, false),
        est(3, true),
        est(2, false),
        est(1, true),
      ]),
    ).toBe("ej. 1, 3 y 5")
  })
  it("marca en todos: todos", () => {
    expect(textoPedidosReentrega([est(1, true), est(2, true)])).toBe("todos")
  })
  it("sin marca (devolucion anterior al change): null, no inventa", () => {
    expect(textoPedidosReentrega([est(1), est(2)])).toBeNull()
  })
  it("marcas todas en false: null", () => {
    expect(textoPedidosReentrega([est(1, false), est(2, false)])).toBeNull()
  })
  it("lista vacia: null", () => {
    expect(textoPedidosReentrega([])).toBeNull()
  })
})
