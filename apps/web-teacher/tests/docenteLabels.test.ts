/**
 * B2b (6.5): `sin_clasificar` es un 5to valor real de `appropriation` desde
 * 6.2. `APPROPRIATION_DOCENTE`/`APPROPRIATION_INVESTIGADOR` no tenían
 * entrada para él — el fallback seguro (`dict[category] ?? category`) de
 * `appropriationWithScope` no rompe, pero muestra la clave cruda
 * ("sin_clasificar (este episodio)") en vez de una frase legible. "Sin
 * clasificar" no es un estado de error: es información sobre el episodio.
 */
import { describe, expect, test } from "vitest"
import { appropriationWithScope } from "../src/utils/docenteLabels"

describe("appropriationWithScope — sin_clasificar", () => {
  test("audiencia docente: frase legible, no la clave cruda", () => {
    const label = appropriationWithScope("sin_clasificar", "docente")
    expect(label).not.toContain("sin_clasificar")
    expect(label.toLowerCase()).toContain("sin clasificar")
  })

  test("audiencia investigador: frase legible propia, distinta de la docente", () => {
    const label = appropriationWithScope("sin_clasificar", "investigador")
    expect(label).not.toContain("sin_clasificar")
    expect(label.toLowerCase()).toContain("sin clasificar")
  })

  test("triangulación: un valor conocido (apropiacion_reflexiva) sigue con su label de siempre", () => {
    expect(appropriationWithScope("apropiacion_reflexiva", "docente")).toBe(
      "En este episodio: trabajo de forma autonoma (este episodio)",
    )
  })
})
