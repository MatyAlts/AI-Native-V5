/**
 * BUG-19 (QA 2026-09-23) — "Ver calificacion" del alumno mostraba
 * "CRITERIOS DE EVALUACION -> 0 / NaN".
 *
 * El denominador salia de `criterio.peso`, un campo que no existe en el
 * contrato real de `CriterioCalificacion` (evaluation-service): el shape
 * persistido es `{criterio, puntaje, max_puntaje, comentario}`. `peso` daba
 * `undefined` y `Math.round(undefined * 10)` da `NaN` — y ese `NaN` se
 * mostraba tal cual, con la autoridad de un numero real.
 *
 * Esta funcion vive aparte del componente por la misma razon que
 * `chequearAritmetica` vive aparte en el web-teacher: es la pieza que puede
 * estar mal EN SILENCIO. Un "0 / NaN" se lee como "sacaste 0 sobre no-se-sabe-
 * cuanto", y eso no se ve como un bug de renderizado — se lee como una nota.
 */
import { describe, expect, test } from "vitest"
import { formatoCriterioPuntaje } from "../src/utils/calificacionCriterios"

describe("formatoCriterioPuntaje", () => {
  test("con puntaje y max_puntaje numericos, los muestra tal cual", () => {
    expect(formatoCriterioPuntaje(3, 5)).toBe("3 / 5")
  })

  test("un max_puntaje ausente NUNCA se muestra como NaN", () => {
    // El caso real del bug: el campo que el frontend leia no existia.
    expect(formatoCriterioPuntaje(3, undefined)).toBe("3 / —")
  })

  test("puntaje y max_puntaje llegan como STRING (Decimal de Postgres) y igual se muestran", () => {
    // `Numeric` serializa como string aunque el tipo de TS diga `number`,
    // igual que `nota_100` y `peso_en_tp` en el resto del epic.
    expect(formatoCriterioPuntaje("3.00", "5.00")).toBe("3 / 5")
  })

  test("un valor no numerico tampoco produce NaN", () => {
    expect(formatoCriterioPuntaje("no-es-un-numero", 5)).toBe("— / 5")
  })
})
