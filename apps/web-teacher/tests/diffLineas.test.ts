// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
/**
 * Diff de lineas entre dos estados de codigo de la traza ciega
 * (`src/utils/diffLineas.ts`). Reusa el LCS de `lineDiff.ts`; lo propio de
 * este modulo es la forma que consume la traza (una lista de lineas marcadas)
 * y que un CRLF no se lea como "todas las lineas cambiaron": el alumno puede
 * pegar desde Windows y la traza no tiene que inventar ediciones.
 */
import { describe, expect, it } from "vitest"
import { diffLineas } from "../src/utils/diffLineas"

describe("diffLineas", () => {
  it("textos iguales: todo igual, sin agregadas ni quitadas", () => {
    const r = diffLineas("a\nb", "a\nb")
    expect(r.lineas).toEqual([
      { tipo: "igual", texto: "a" },
      { tipo: "igual", texto: "b" },
    ])
    expect(r.agregadas).toBe(0)
    expect(r.quitadas).toBe(0)
  })

  it("una linea cambiada: se marca la vieja como quitada y la nueva como agregada", () => {
    const r = diffLineas("x = 1\nprint(x)", "x = 2\nprint(x)")
    expect(r.lineas).toEqual([
      { tipo: "quitada", texto: "x = 1" },
      { tipo: "agregada", texto: "x = 2" },
      { tipo: "igual", texto: "print(x)" },
    ])
    expect(r.agregadas).toBe(1)
    expect(r.quitadas).toBe(1)
  })

  it("linea agregada al final", () => {
    const r = diffLineas("a", "a\nb")
    expect(r.lineas).toEqual([
      { tipo: "igual", texto: "a" },
      { tipo: "agregada", texto: "b" },
    ])
  })

  it("linea borrada al inicio", () => {
    const r = diffLineas("a\nb", "b")
    expect(r.lineas).toEqual([
      { tipo: "quitada", texto: "a" },
      { tipo: "igual", texto: "b" },
    ])
  })

  it("desde texto vacio: todo agregado", () => {
    const r = diffLineas("", "a\nb")
    expect(r.lineas).toEqual([
      { tipo: "agregada", texto: "a" },
      { tipo: "agregada", texto: "b" },
    ])
    expect(r.agregadas).toBe(2)
  })

  it("hacia texto vacio: todo quitado", () => {
    const r = diffLineas("a", "")
    expect(r.lineas).toEqual([{ tipo: "quitada", texto: "a" }])
    expect(r.quitadas).toBe(1)
  })

  it("CRLF contra LF con el mismo contenido: sin cambios", () => {
    const r = diffLineas("a\r\nb\r\n", "a\nb\n")
    expect(r.agregadas).toBe(0)
    expect(r.quitadas).toBe(0)
    expect(r.lineas.every((l) => l.tipo === "igual")).toBe(true)
  })

  it("CRLF no deja retornos de carro en el texto de las lineas", () => {
    const r = diffLineas("", "a\r\nb")
    expect(r.lineas.map((l) => l.texto)).toEqual(["a", "b"])
  })

  it("snapshot desmesurado: avisa que el diff no esta disponible en vez de colgar", () => {
    const grande = Array.from({ length: 6000 }, (_, i) => `l${i}`).join("\n")
    const r = diffLineas(grande, `${grande}\nmas`)
    expect(r.disponible).toBe(false)
    expect(r.lineas).toEqual([])
  })
})
