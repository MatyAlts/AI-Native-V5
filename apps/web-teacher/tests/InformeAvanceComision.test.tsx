/**
 * informe-avance-comisiones — Lote 2, IAC-03.
 *
 * `InformeAvanceComision` es presentacion pura: recibe el view-model ya
 * armado por los helpers del Lote 1 (`buildResumenComision`,
 * `buildDetallePorAlumno`) y renderiza portada + detalle por alumno. NO
 * fetchea nada (eso es IAC-04, en `ExportView`).
 *
 * Cubre:
 *  - Portada normal: progresion + cuartiles + alertas disponibles.
 *  - Portada con `disponible:false` (k-anonymity N<5): "datos insuficientes
 *    por privacidad", NUNCA ceros.
 *  - Detalle por alumno: nombres reales del map (via `buildDetallePorAlumno`),
 *    y el rotulo de privacidad explicito.
 */
import { render, screen } from "@testing-library/react"
import { describe, expect, test } from "vitest"
import { InformeAvanceComision } from "../src/components/InformeAvanceComision"
import { buildDetallePorAlumno, buildResumenComision } from "../src/utils/informeComision"
import type {
  CohortAlertsSummary,
  CohortCIIQuartiles,
  CohortProgression,
  StudentTrajectory,
} from "../src/lib/api"

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

describe("InformeAvanceComision", () => {
  test("portada: muestra nombre de comision y los agregados reales", () => {
    const resumen = buildResumenComision(progression(), quartiles(), alertsSummary())
    const detalle = buildDetallePorAlumno([], new Map())

    render(
      <InformeAvanceComision comisionLabel="Prog 1 · A-Manana" resumen={resumen} detalle={detalle} />,
    )

    expect(screen.getByText("Prog 1 · A-Manana")).toBeInTheDocument()
    expect(screen.getByTestId("informe-avance-portada")).toHaveTextContent("8")
    expect(screen.getByTestId("informe-avance-portada")).toHaveTextContent(/0[.,]6/)
  })

  test("portada con insufficient_data: muestra 'datos insuficientes por privacidad', nunca ceros", () => {
    const resumen = buildResumenComision(
      progression({ n_students: 3, mejorando: 1, estable: 2, empeorando: 0 }),
      quartiles({ insufficient_data: true, q1: null, median: null, q3: null }),
      alertsSummary({ insufficient_data: true, alerts_summary: null }),
    )
    const detalle = buildDetallePorAlumno([], new Map())

    render(
      <InformeAvanceComision comisionLabel="Prog 1 · A-Manana" resumen={resumen} detalle={detalle} />,
    )

    const portada = screen.getByTestId("informe-avance-portada")
    expect(portada).toHaveTextContent(/datos insuficientes por privacidad/i)
    // Ninguno de los "0" de cuartiles/alertas gateados debe aparecer como dato.
    expect(portada).not.toHaveTextContent(/^0$/)
  })

  test("detalle por alumno: renderiza el nombre real del map y el rotulo de privacidad", () => {
    const resumen = buildResumenComision(progression(), quartiles(), alertsSummary())
    const profilesMap = new Map([["c1c1c1c1-0001-0001-0001-000000000001", "Maria Gomez"]])
    const detalle = buildDetallePorAlumno([trajectory()], profilesMap)

    render(
      <InformeAvanceComision comisionLabel="Prog 1 · A-Manana" resumen={resumen} detalle={detalle} />,
    )

    expect(screen.getByText("Maria Gomez")).toBeInTheDocument()
    expect(
      screen.getByText(
        /uso interno de la c[aá]tedra.*contiene datos personales.*no publicar/i,
      ),
    ).toBeInTheDocument()
  })

  test("detalle por alumno sin profile: cae al fallback 'Est. xxxxxx'", () => {
    const resumen = buildResumenComision(progression(), quartiles(), alertsSummary())
    const detalle = buildDetallePorAlumno(
      [trajectory({ student_pseudonym: "c1c1c1c1-0002-0002-0002-000000000002" })],
      new Map(),
    )

    render(
      <InformeAvanceComision comisionLabel="Prog 1 · A-Manana" resumen={resumen} detalle={detalle} />,
    )

    expect(screen.getByText("Est. 000002")).toBeInTheDocument()
  })
})
