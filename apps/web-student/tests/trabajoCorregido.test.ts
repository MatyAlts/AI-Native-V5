import { describe, expect, it } from "vitest"
import type { ArtefactoEntregado, Entrega } from "../src/lib/api"
import {
  archivoDeDescarga,
  ejerciciosDelTrabajo,
  esTrabajoCorregido,
} from "../src/utils/trabajoCorregido"

function art(orden: number, extra: Partial<ArtefactoEntregado> = {}): ArtefactoEntregado {
  return {
    orden,
    ejercicio_id: `e${orden}`,
    episode_id: `ep${orden}`,
    codigo: `codigo ${orden}`,
    language: "python",
    sha256: "x",
    created_at: "2026-10-01T00:00:00Z",
    ...extra,
  }
}

describe("esTrabajoCorregido", () => {
  it.each([
    ["graded", true],
    ["returned", true],
    ["submitted", false],
    ["draft", false],
  ])("%s -> %s", (estado, esperado) => {
    expect(esTrabajoCorregido({ estado: estado as Entrega["estado"] })).toBe(esperado)
  })
})

describe("ejerciciosDelTrabajo", () => {
  it("ordena por orden y rotula 'Ejercicio N'", () => {
    const r = ejerciciosDelTrabajo([art(3), art(1), art(2)])
    expect(r.map((e) => e.titulo)).toEqual(["Ejercicio 1", "Ejercicio 2", "Ejercicio 3"])
    expect(r.map((e) => e.artefacto.codigo)).toEqual(["codigo 1", "codigo 2", "codigo 3"])
  })

  it("lista vacia (legacy) -> []", () => {
    expect(ejerciciosDelTrabajo([])).toEqual([])
  })

  it("no muta el arreglo recibido", () => {
    const entrada = [art(2), art(1)]
    ejerciciosDelTrabajo(entrada)
    expect(entrada.map((a) => a.orden)).toEqual([2, 1])
  })
})

describe("archivoDeDescarga", () => {
  const meta = { ejercicioTitulo: "TP1 - Ejercicio 1", fecha: "20/10/2026" }

  it("python: el codigo entregado va intacto y la charla comentada con #", () => {
    const { filename, content } = archivoDeDescarga(
      art(1, { codigo: "x = 1\nprint(x)" }),
      [{ role: "user", content: "hola", ts: "t" }],
      meta,
    )
    expect(filename.endsWith(".py")).toBe(true)
    expect(content).toContain("x = 1\nprint(x)")
    expect(content).toContain("# [Alumno] hola")
  })

  it("java sin charla: .java y sin seccion de charla", () => {
    const { filename, content } = archivoDeDescarga(
      art(2, { language: "java", codigo: "class A {}" }),
      null,
      meta,
    )
    expect(filename.endsWith(".java")).toBe(true)
    expect(content).toContain("class A {}")
    expect(content).not.toContain("Charla con el tutor")
  })
})
