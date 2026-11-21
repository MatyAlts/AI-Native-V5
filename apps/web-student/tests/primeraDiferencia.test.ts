import { describe, expect, it } from "vitest"
import { describirDiferencia, primeraDiferencia } from "../src/lib/primeraDiferencia"

function describir(esperado: string, obtenido: string): string {
  const d = primeraDiferencia(esperado, obtenido)
  if (d === null) throw new Error("no hubo diferencia")
  return describirDiferencia(d)
}

describe("primeraDiferencia (HU-009 C11)", () => {
  it("grado contra ordinal: posicion y los dos codigos", () => {
    const d = primeraDiferencia("68.0 °F", "68.0 ºF")
    expect(d).toEqual({ linea: null, posicion: 6, esperado: "°", obtenido: "º" })
    expect(describir("68.0 °F", "68.0 ºF")).toBe(
      "posición 6: se esperaba ° (U+00B0) y salió º (U+00BA)",
    )
  })

  it("salida mas corta lo dice", () => {
    expect(describir("Su IMC es: 22.86 kg/m²", "Su IMC es: 22.86 kg/m")).toBe(
      "posición 22: tu salida termina antes; se esperaba ² (U+00B2)",
    )
  })

  it("salida mas larga lo dice", () => {
    expect(describir("hola", "holas")).toMatch(/sigue después del final, con s \(U\+0073\)/)
  })

  it("con varias lineas da la linea y la posicion dentro de ella", () => {
    const d = primeraDiferencia("Área: 78.54\nPerímetro: 31.42", "Área: 78.54\nPerimetro: 31.42")
    expect(d).toMatchObject({ linea: 2, posicion: 4, esperado: "í", obtenido: "i" })
  })

  it("nombra los caracteres invisibles", () => {
    expect(describir("a b", "a\tb")).toBe(
      "posición 2: se esperaba un espacio (U+0020) y salió una tabulación (U+0009)",
    )
  })

  it("lo que la comparacion perdona no cuenta como diferencia", () => {
    expect(primeraDiferencia("hola\n", "hola   \n\n")).toBeNull()
  })
})
