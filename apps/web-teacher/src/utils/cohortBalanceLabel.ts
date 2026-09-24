// BUG-14 (QA 2026-09-23): "Balance general" leia un ratio NETO
// ((mejorando - empeorando) / estudiantes con datos) y lo traducia a "La
// mayoria de tus alumnos esta [mejorando|empeorando]". Un ratio neto no es una
// proporcion de mayoria: con 0% mejorando / 50% estable / 50% en riesgo el
// ratio da -0.5 (fuertemente negativo) y el texto viejo decia "la mayoria esta
// empeorando" — falso en los dos sentidos (50% no es mayoria, "estable" no es
// "empeorando"). Ademas no tenia piso de N, a diferencia de Cuartiles CII
// (`MIN_STUDENTS_FOR_QUARTILES = 5` en
// `packages/platform-ops/src/platform_ops/cii_alerts.py`, k-anonymity):
// una cohorte de 4 estudiantes con datos podia recibir un veredicto tan
// categorico como una de 40.

/** Mismo piso k-anonymity que Cuartiles CII (`MIN_STUDENTS_FOR_QUARTILES`). */
export const MIN_STUDENTS_FOR_COHORT_BALANCE = 5

/**
 * Traduce el ratio neto de progresion de la cohorte a un texto honesto: dice
 * lo que el numero mide (un balance agregado, no una mayoria), y con menos
 * estudiantes con datos que `MIN_STUDENTS_FOR_COHORT_BALANCE` no emite
 * veredicto de cohorte.
 */
export function cohortBalanceLabel(ratio: number, nStudentsWithData: number): string {
  if (nStudentsWithData < MIN_STUDENTS_FOR_COHORT_BALANCE) {
    return "Pocos alumnos con datos para un balance de cohorte"
  }
  if (ratio > 0.1) return "El balance de la cohorte es positivo"
  if (ratio < -0.1) return "El balance de la cohorte es negativo"
  return "La cohorte se mantiene estable"
}
