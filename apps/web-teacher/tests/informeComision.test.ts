/**
 * informe-avance-comisiones — Lote 1 (helpers puros, sin UI).
 *
 * `buildResumenComision` arma el view-model de la PORTADA del informe desde
 * los responses ya existentes de progresión/cuartiles/alertas. Requisito
 * duro: cuando un input viene `insufficient_data: true` (k-anonymity N<5),
 * el resultado debe reflejar "no disponible por privacidad", nunca ceros que
 * se lean como dato real (ADR-022, RN-131, MIN_STUDENTS_FOR_QUARTILES=5).
 */
import { describe, expect, test } from "vitest"
import type {
  CohortAlertsSummary,
  CohortCIIQuartiles,
  CohortProgression,
  StudentTrajectory,
} from "../src/lib/api"
import { buildDetallePorAlumno, buildResumenComision } from "../src/utils/informeComision"

function trajectory(overrides: Partial<StudentTrajectory> = {}): StudentTrajectory {
  return {
    student_pseudonym: "c1c1c1c1-0001-0001-0001-000000000001",
    n_episodes: 4,
    first_classification: "delegacion_pasiva",
    last_classification: "apropiacion_reflexiva",
    max_appropriation_reached: "apropiacion_reflexiva",
    progression_label: "mejorando",
    tercile_means: [0.1, 0.4, 0.8],
    points: [],
    ...overrides,
  }
}

function progression(overrides: Partial<CohortProgression> = {}): CohortProgression {
  return {
    comision_id: "com-1",
    n_students: 8,
    n_students_with_enough_data: 8,
    mejorando: 3,
    estable: 4,
    empeorando: 1,
    insuficiente: 0,
    net_progression_ratio: 0.25,
    trajectories: [],
    ...overrides,
  }
}

function quartiles(overrides: Partial<CohortCIIQuartiles> = {}): CohortCIIQuartiles {
  return {
    comision_id: "com-1",
    labeler_version: "1.2.0",
    min_students_for_quartiles: 5,
    n_students_evaluated: 8,
    insufficient_data: false,
    q1: 0.2,
    median: 0.4,
    q3: 0.6,
    min: 0.1,
    max: 0.8,
    mean: 0.41,
    stdev: 0.15,
    ...overrides,
  }
}

function alertsSummary(overrides: Partial<CohortAlertsSummary> = {}): CohortAlertsSummary {
  return {
    comision_id: "com-1",
    n_students_evaluated: 8,
    min_students_threshold: 5,
    insufficient_data: false,
    alerts_summary: {
      regresion_vs_cohorte: 2,
      bottom_quartile: 1,
      slope_negativo_significativo: 1,
      students_with_any_alert: 3,
    },
    labeler_version: "1.2.0",
    ...overrides,
  }
}

describe("buildResumenComision", () => {
  test("caso normal: refleja los agregados reales de progresion/cuartiles/alertas", () => {
    const resumen = buildResumenComision(progression(), quartiles(), alertsSummary())

    expect(resumen.progresion.nEstudiantes).toBe(8)
    expect(resumen.progresion.mejorando).toBe(3)
    expect(resumen.progresion.netProgressionRatio).toBe(0.25)

    expect(resumen.cuartilesCII.disponible).toBe(true)
    expect(resumen.cuartilesCII.q1).toBe(0.2)
    expect(resumen.cuartilesCII.median).toBe(0.4)
    expect(resumen.cuartilesCII.q3).toBe(0.6)

    expect(resumen.alertas.disponible).toBe(true)
    expect(resumen.alertas.estudiantesConAlerta).toBe(3)
    expect(resumen.alertas.counts?.bottom_quartile).toBe(1)
  })

  test("N<5 (k-anonymity): insufficient_data=true NUNCA se lee como ceros reales", () => {
    const resumen = buildResumenComision(
      progression({ n_students: 3, mejorando: 1, estable: 2, empeorando: 0 }),
      quartiles({
        insufficient_data: true,
        q1: null,
        median: null,
        q3: null,
        n_students_evaluated: 3,
      }),
      alertsSummary({ insufficient_data: true, alerts_summary: null, n_students_evaluated: 3 }),
    )

    // La progresion en si no esta gateada por k-anonymity: son los agregados
    // reales de la comision (n_students=3 es un dato real, no redactado).
    expect(resumen.progresion.nEstudiantes).toBe(3)

    // Cuartiles y alertas SI estan gateados: nunca 0, siempre null + flag.
    expect(resumen.cuartilesCII.disponible).toBe(false)
    expect(resumen.cuartilesCII.q1).toBeNull()
    expect(resumen.cuartilesCII.median).toBeNull()
    expect(resumen.cuartilesCII.q3).toBeNull()

    expect(resumen.alertas.disponible).toBe(false)
    expect(resumen.alertas.estudiantesConAlerta).toBeNull()
    expect(resumen.alertas.counts).toBeNull()
  })

  test("comision sin estudiantes: cero es un dato real (no hay privacidad que gatear)", () => {
    const resumen = buildResumenComision(
      progression({
        n_students: 0,
        n_students_with_enough_data: 0,
        mejorando: 0,
        estable: 0,
        empeorando: 0,
        insuficiente: 0,
        net_progression_ratio: 0,
        trajectories: [],
      }),
      quartiles({
        insufficient_data: true,
        q1: null,
        median: null,
        q3: null,
        n_students_evaluated: 0,
      }),
      alertsSummary({ insufficient_data: true, alerts_summary: null, n_students_evaluated: 0 }),
    )

    expect(resumen.progresion.nEstudiantes).toBe(0)
    expect(resumen.progresion.netProgressionRatio).toBe(0)
    expect(resumen.cuartilesCII.disponible).toBe(false)
    expect(resumen.alertas.disponible).toBe(false)
  })
})

describe("buildDetallePorAlumno", () => {
  test("alumno con nombre real: usa el full_name del map de perfiles", () => {
    const profilesMap = new Map([["c1c1c1c1-0001-0001-0001-000000000001", "Maria Gomez"]])
    const filas = buildDetallePorAlumno([trajectory()], profilesMap)

    expect(filas[0]?.label).toBe("Maria Gomez")
    expect(filas[0]?.pseudonym).toBe("c1c1c1c1-0001-0001-0001-000000000001")
    expect(filas[0]?.progressionLabel).toBe("mejorando")
  })

  test("alumno sin profile: cae al fallback 'Est. xxxxxx' (ultimos 6 chars del pseudonym)", () => {
    const filas = buildDetallePorAlumno(
      [trajectory({ student_pseudonym: "c1c1c1c1-0002-0002-0002-000000000002" })],
      new Map(),
    )

    expect(filas[0]?.label).toBe("Est. 000002")
  })

  test("orden estable: el resultado no depende del orden del input", () => {
    const profilesMap = new Map([
      ["c1c1c1c1-0001-0001-0001-000000000001", "Beltran Ruiz"],
      ["c1c1c1c1-0002-0002-0002-000000000002", "Ana Diaz"],
      ["c1c1c1c1-0003-0003-0003-000000000003", "Carlos Paz"],
    ])
    const a = trajectory({ student_pseudonym: "c1c1c1c1-0001-0001-0001-000000000001" })
    const b = trajectory({ student_pseudonym: "c1c1c1c1-0002-0002-0002-000000000002" })
    const c = trajectory({ student_pseudonym: "c1c1c1c1-0003-0003-0003-000000000003" })

    const ordenA = buildDetallePorAlumno([a, b, c], profilesMap).map((f) => f.pseudonym)
    const ordenB = buildDetallePorAlumno([c, a, b], profilesMap).map((f) => f.pseudonym)

    expect(ordenA).toEqual(ordenB)
    // El orden es por label alfabetico: Ana, Beltran, Carlos.
    expect(ordenA).toEqual([
      "c1c1c1c1-0002-0002-0002-000000000002",
      "c1c1c1c1-0001-0001-0001-000000000001",
      "c1c1c1c1-0003-0003-0003-000000000003",
    ])
  })
})
