/**
 * Hallazgo de QA (2026-09-27), consumidor que el relevamiento 6.1 clasificó
 * mal: `KappaRatingView` (modo episodios reales, `isTraining=false`) consume
 * `GET /api/v1/analytics/kappa/sample`, que trae `Classification.appropriation`
 * de TODAS las filas `is_current=true` de la comisión — sin excluir `autonomo`
 * ni `sin_clasificar` (a diferencia de `/interrater/sample`, que sí filtra por
 * subgrupo). El relevamiento asumió que ese filtro cubría también esta
 * pantalla; no la cubre.
 *
 * `appropriationDotColor` es un `if/if/else` de 3 ramas — verde, ámbar, y
 * ROJO para cualquier otra cosa. Con `autonomo` (PREEXISTENTE, ya rompía hoy)
 * o `sin_clasificar` (introducido por B2b), el punto sale rojo — el color de
 * `delegacion_pasiva`. El fix 6.5 de este bloque lo empeoró sin querer: ahora
 * hay una etiqueta de texto que dice la verdad ("sin clasificar") al lado de
 * un punto de color que miente (rojo = delegación pasiva).
 *
 * Fix: casos explícitos para `autonomo` y `sin_clasificar` (ninguno de los
 * dos es delegación pasiva), y el `else` deja de significar "delegación
 * pasiva" para pasar a significar "valor que esta función no conoce" — mismo
 * razonamiento que el grupo defensivo de `RevisionColaView` (bloque 5): un
 * cajón que se disfraza de categoría real es peor que uno que se declara.
 */
import { describe, expect, test } from "vitest"
import { appropriationDotColor } from "../src/views/KappaRatingView"

describe("appropriationDotColor", () => {
  test("apropiacion_reflexiva: verde (caso feliz, ya funcionaba)", () => {
    expect(appropriationDotColor("apropiacion_reflexiva")).toBe("#16a34a")
  })

  test("delegacion_pasiva: sigue siendo rojo — es la categoría real, no el cajón", () => {
    expect(appropriationDotColor("delegacion_pasiva")).toBe("#dc2626")
  })

  test("autonomo: bug PREEXISTENTE (ya rompía antes de esta change) — no debe ser el rojo de delegacion_pasiva", () => {
    expect(appropriationDotColor("autonomo")).not.toBe("#dc2626")
  })

  test("sin_clasificar: no debe ser el rojo de delegacion_pasiva (B2b lo volvió más visible)", () => {
    expect(appropriationDotColor("sin_clasificar")).not.toBe("#dc2626")
  })

  test("autonomo y sin_clasificar no se confunden entre sí ni con el cajón defensivo genérico", () => {
    const autonomo = appropriationDotColor("autonomo")
    const sinClasificar = appropriationDotColor("sin_clasificar")
    // biome-ignore lint: valor deliberadamente fuera del dominio conocido,
    // simula una desincronización backend/frontend real (mismo patrón que
    // el test del "quinto grupo" de RevisionColaView).
    const desconocido = appropriationDotColor("un_valor_que_esta_funcion_no_conoce" as never)

    expect(autonomo).not.toBe("#dc2626")
    expect(sinClasificar).not.toBe("#dc2626")
    expect(desconocido).not.toBe("#dc2626")
  })
})
