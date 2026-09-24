/**
 * BUG-14 (QA 2026-09-23): "Balance general" afirmaba una "mayoria" a partir de
 * un ratio NETO ((mejorando - empeorando) / estudiantes con datos), que no es
 * una mayoria. Con 0% mejorando / 50% estable / 50% en riesgo, el texto decia
 * "La mayoria de tus alumnos esta empeorando" — falso: ni el 50% es mayoria,
 * ni "estable" es "empeorando". Ademas no tenia piso de N, a diferencia de
 * Cuartiles CII (`MIN_STUDENTS_FOR_QUARTILES = 5` en
 * `packages/platform-ops/src/platform_ops/cii_alerts.py`, k-anonymity).
 *
 * `cohortBalanceLabel` es pura: no toca React, solo decide el texto por rama.
 */
import { describe, expect, test } from "vitest"
import {
  MIN_STUDENTS_FOR_COHORT_BALANCE,
  cohortBalanceLabel,
} from "../src/utils/cohortBalanceLabel"

describe("cohortBalanceLabel", () => {
  test("ratio positivo con N suficiente: balance positivo, sin afirmar mayoria", () => {
    const label = cohortBalanceLabel(0.5, 10)

    expect(label).not.toMatch(/mayor[ií]a/i)
    expect(label.toLowerCase()).toContain("positivo")
  })

  test("ratio negativo con N suficiente: balance negativo, sin afirmar mayoria", () => {
    const label = cohortBalanceLabel(-0.5, 10)

    expect(label).not.toMatch(/mayor[ií]a/i)
    expect(label.toLowerCase()).toContain("negativo")
  })

  test("ratio dentro del umbral (+-0.1): cohorte estable", () => {
    expect(cohortBalanceLabel(0, 10)).toMatch(/estable/i)
  })

  test("piso de N: el caso real del bug (0% mejorando / 50% estable / 50% en riesgo, N=4) no debe emitir veredicto de cohorte", () => {
    // mejorando=0, empeorando=2, n_con_datos=4 -> ratio = -0.5 (fuertemente
    // negativo), pero N=4 < MIN_STUDENTS_FOR_COHORT_BALANCE=5: el piso de
    // k-anonymity tiene que ganarle a la direccion del ratio.
    const label = cohortBalanceLabel(-0.5, 4)

    expect(label).not.toMatch(/mayor[ií]a/i)
    expect(label).not.toMatch(/negativo/i)
    expect(label.toLowerCase()).toContain("pocos alumnos")
  })

  test("el piso usado es MIN_STUDENTS_FOR_QUARTILES=5 (mismo criterio que Cuartiles)", () => {
    expect(MIN_STUDENTS_FOR_COHORT_BALANCE).toBe(5)
  })
})
