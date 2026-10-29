import { describe, expect, it } from "vitest"
import { devolucionParcialVigente, estaBloqueado, ordenesACorregir } from "../src/lib/estaBloqueado"

type E = { orden: number; completado: boolean; reabierto_por_docente?: boolean }
const est = (orden: number, completado: boolean, marca?: boolean): E =>
  marca === undefined ? { orden, completado } : { orden, completado, reabierto_por_docente: marca }

const bloqueados = (estados: E[]) => estados.map((e) => estaBloqueado(e.orden, estados))

describe("estaBloqueado: el lock secuencial es solo entre pendientes", () => {
  it("avance normal: solo el primero libre", () => {
    expect(bloqueados([est(1, false), est(2, false), est(3, false)])).toEqual([false, true, true])
  })

  it("avance normal: el siguiente se libera al completar el anterior", () => {
    expect(bloqueados([est(1, true), est(2, false), est(3, false)])).toEqual([false, false, true])
  })

  it("devolucion '2 y 4' de 5: el 2 libre, el 4 espera al 2, los completados nunca bloqueados", () => {
    const estados = [est(1, true), est(2, false), est(3, true), est(4, false), est(5, true)]
    expect(bloqueados(estados)).toEqual([false, false, false, true, false])
  })

  it("el 4 se libera cuando el 2 se completa", () => {
    const estados = [est(1, true), est(2, true), est(3, true), est(4, false), est(5, true)]
    expect(bloqueados(estados)).toEqual([false, false, false, false, false])
  })

  it("devolucion total: solo el 1, como antes", () => {
    expect(bloqueados([est(1, false), est(2, false), est(3, false)])).toEqual([false, true, true])
  })

  it("draft con 'Volver a abrir' del 1 teniendo el 2 completo: el 3 pendiente queda bloqueado", () => {
    const estados = [est(1, false), est(2, true), est(3, false)]
    expect(bloqueados(estados)).toEqual([false, false, true])
  })

  it("un orden anterior sin estado cuenta como pendiente", () => {
    expect(estaBloqueado(2, [est(2, false)])).toBe(true)
  })
})

describe("ordenesACorregir (espejo del backend)", () => {
  it("sin marcas son todos", () => {
    expect(ordenesACorregir([est(1, false), est(2, false)])).toEqual(new Set([1, 2]))
  })
  it("con marcas son solo los marcados", () => {
    const estados = [
      est(1, true, false),
      est(2, false, true),
      est(3, true, false),
      est(4, false, true),
    ]
    expect(ordenesACorregir(estados)).toEqual(new Set([2, 4]))
  })
  it("lista vacia es vacio", () => {
    expect(ordenesACorregir([])).toEqual(new Set())
  })
})

describe("devolucionParcialVigente: la marca persiste, pero solo manda en `returned`", () => {
  const marcados = [est(1, true, false), est(2, false, true)]
  it("returned con marca: parcial", () => {
    expect(devolucionParcialVigente("returned", marcados)).toBe(true)
  })
  it.each(["submitted", "graded", "draft"])("%s con marca vieja: no es parcial", (estado) => {
    expect(devolucionParcialVigente(estado, marcados)).toBe(false)
  })
  it("returned sin marcas (legacy / total): no es parcial", () => {
    expect(devolucionParcialVigente("returned", [est(1, false), est(2, false)])).toBe(false)
  })
})
