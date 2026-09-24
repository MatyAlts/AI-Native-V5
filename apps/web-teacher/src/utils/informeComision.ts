/**
 * Helpers puros para el "Informe de avance de comisión" (imprimible, para el
 * docente). Componen el view-model del informe a partir de responses ya
 * existentes y gateados por comisión — sin fetch propio, sin endpoint nuevo
 * (ver proposal.md de `informe-avance-comisiones`).
 */
import type {
  AppropriationLabel,
  CohortAlertsSummary,
  CohortAlertsSummaryCounts,
  CohortCIIQuartiles,
  CohortProgression,
  StudentTrajectory,
} from "../lib/api"
import { studentShortLabel } from "./docenteLabels"

export interface ResumenComisionProgresion {
  nEstudiantes: number
  nEstudiantesConDatos: number
  mejorando: number
  estable: number
  empeorando: number
  insuficiente: number
  netProgressionRatio: number
}

export interface ResumenComisionCuartiles {
  disponible: boolean
  q1: number | null
  median: number | null
  q3: number | null
}

export interface ResumenComisionAlertas {
  disponible: boolean
  estudiantesConAlerta: number | null
  counts: CohortAlertsSummaryCounts | null
}

export interface ResumenComisionPortada {
  progresion: ResumenComisionProgresion
  cuartilesCII: ResumenComisionCuartiles
  alertas: ResumenComisionAlertas
}

export function buildResumenComision(
  progression: CohortProgression,
  quartiles: CohortCIIQuartiles,
  alertsSummary: CohortAlertsSummary,
): ResumenComisionPortada {
  return {
    progresion: {
      nEstudiantes: progression.n_students,
      nEstudiantesConDatos: progression.n_students_with_enough_data,
      mejorando: progression.mejorando,
      estable: progression.estable,
      empeorando: progression.empeorando,
      insuficiente: progression.insuficiente,
      netProgressionRatio: progression.net_progression_ratio,
    },
    cuartilesCII: quartiles.insufficient_data
      ? { disponible: false, q1: null, median: null, q3: null }
      : { disponible: true, q1: quartiles.q1, median: quartiles.median, q3: quartiles.q3 },
    alertas: alertsSummary.insufficient_data
      ? { disponible: false, estudiantesConAlerta: null, counts: null }
      : {
          disponible: true,
          estudiantesConAlerta: alertsSummary.alerts_summary?.students_with_any_alert ?? null,
          counts: alertsSummary.alerts_summary,
        },
  }
}

export interface DetalleAlumnoRow {
  pseudonym: string
  label: string
  progressionLabel: StudentTrajectory["progression_label"]
  nEpisodes: number
  firstClassification: AppropriationLabel | null
  lastClassification: AppropriationLabel | null
  maxAppropriationReached: AppropriationLabel | null
  tercileMeans: [number, number, number] | null
}

/**
 * Arma las filas de la tabla "detalle por alumno" cruzando las trayectorias
 * de `getCohortProgression` con el Map de nombres reales de
 * `useStudentProfiles`. NO fetchea nada: recibe los datos ya provistos (el
 * gate de privacidad está en el endpoint de perfiles, no acá).
 */
export function buildDetallePorAlumno(
  trajectories: readonly StudentTrajectory[],
  profilesMap: Map<string, string>,
): DetalleAlumnoRow[] {
  const rows = trajectories.map((t) => ({
    pseudonym: t.student_pseudonym,
    label: studentShortLabel(t.student_pseudonym, profilesMap),
    progressionLabel: t.progression_label,
    nEpisodes: t.n_episodes,
    firstClassification: t.first_classification,
    lastClassification: t.last_classification,
    maxAppropriationReached: t.max_appropriation_reached,
    tercileMeans: t.tercile_means,
  }))

  // Orden estable independiente del orden de `trajectories`: alfabetico por
  // label visible (nombre real o fallback "Est. xxxxxx"), desempatado por
  // pseudonym para determinismo si dos labels coinciden.
  return rows.sort((a, b) => {
    const cmp = a.label.localeCompare(b.label, "es", { sensitivity: "base" })
    return cmp !== 0 ? cmp : a.pseudonym.localeCompare(b.pseudonym)
  })
}
