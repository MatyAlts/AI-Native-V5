/**
 * BUG-20 (QA 2026-09-23): en "Evolucion por estudiante", la cabecera decia
 * "3 trabajos completados · 1 tipo de trabajo" mientras el detalle de abajo
 * listaba ~10 TPs con ~20 sesiones y "Evolucion por unidad" sumaba 6+3=9
 * intentos. No es el mismo numero desactualizado: son DOS calculos distintos.
 *
 * `n_episodes_total`/`n_groups_evaluated` (backend, `cii_longitudinal.py`)
 * cuentan solo los grupos por Unidad que entran al calculo de tendencia
 * longitudinal (excluyen "sin_unidad" y agregan por grupo) — no son "todos
 * los trabajos del alumno". El detalle de abajo (`episodesData.episodes`,
 * endpoint `/student/{id}/episodes`) lista TODOS los episodios cerrados sin
 * ese filtro. Las dos poblaciones son legitimamente distintas; el bug es que
 * la cabecera no lo decia.
 *
 * `computeDocenteWorkSummary` es pura: decide si agregar una aclaracion
 * cuando el detalle tiene mas trabajos/episodios que el resumen de tendencia.
 */
import { describe, expect, test } from "vitest"
import { computeDocenteWorkSummary } from "../src/utils/docenteWorkSummary"

describe("computeDocenteWorkSummary", () => {
  test("sin discrepancia: el resumen coincide con el detalle, sin aclaracion", () => {
    const episodes = [{ problema_id: "tp-a" }, { problema_id: "tp-a" }, { problema_id: "tp-a" }]
    const summary = computeDocenteWorkSummary(3, 1, episodes)

    expect(summary.caption).toBeNull()
  })

  test("caso real del bug: cabecera 3/1 pero el detalle tiene mas trabajos y sesiones", () => {
    const episodes = [
      { problema_id: "tp-1" },
      { problema_id: "tp-1" },
      { problema_id: "tp-2" },
      { problema_id: "tp-2" },
      { problema_id: "tp-2" },
      { problema_id: "tp-3" },
      { problema_id: "tp-3" },
      { problema_id: "tp-3" },
      { problema_id: "tp-4" },
    ]
    const summary = computeDocenteWorkSummary(3, 1, episodes)

    expect(summary.caption).not.toBeNull()
    // biome-ignore lint/style/noNonNullAssertion: chequeado arriba
    expect(summary.caption!).toContain("4")
    // biome-ignore lint/style/noNonNullAssertion: chequeado arriba
    expect(summary.caption!).toContain("9")
  })

  test("episodios todavia no cargaron (null): sin aclaracion, no revienta", () => {
    const summary = computeDocenteWorkSummary(3, 1, null)

    expect(summary.caption).toBeNull()
  })
})
