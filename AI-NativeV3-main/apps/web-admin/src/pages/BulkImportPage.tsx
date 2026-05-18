import { PageContainer } from "@platform/ui"
import { type ReactNode, useState } from "react"
import { type BulkImportCommitResult, type BulkImportReport, HttpError, bulkApi } from "../lib/api"
import { helpContent } from "../utils/helpContent"

type Entity =
  | "facultades"
  | "carreras"
  | "planes"
  | "materias"
  | "periodos"
  | "comisiones"
  | "inscripciones"

const ENTITY_OPTIONS: { value: Entity; label: string }[] = [
  { value: "facultades", label: "Facultades" },
  { value: "carreras", label: "Carreras" },
  { value: "planes", label: "Planes" },
  { value: "materias", label: "Materias" },
  { value: "periodos", label: "Periodos" },
  { value: "comisiones", label: "Comisiones" },
  { value: "inscripciones", label: "Inscripciones (estudiantes)" },
]

/**
 * Columnas esperadas por entidad (cotejadas contra Pydantic schemas en
 * `apps/academic-service/src/academic_service/schemas/*.py`).
 * Si el backend cambia los schemas, actualizar acá.
 */
const ENTITY_COLUMNS: Record<Entity, { required: string[]; optional: string[] }> = {
  facultades: {
    required: ["nombre", "codigo", "universidad_id"],
    optional: ["decano_user_id"],
  },
  carreras: {
    required: ["nombre", "codigo", "facultad_id"],
    optional: ["duracion_semestres", "modalidad", "director_user_id"],
  },
  planes: {
    required: ["carrera_id", "version", "año_inicio"],
    optional: ["ordenanza", "vigente"],
  },
  materias: {
    required: ["plan_id", "codigo", "nombre", "horas_totales", "cuatrimestre_sugerido"],
    optional: ["objetivos", "correlativas_cursar", "correlativas_rendir"],
  },
  periodos: {
    required: ["codigo", "nombre", "fecha_inicio", "fecha_fin"],
    optional: ["estado"],
  },
  comisiones: {
    required: ["materia_id", "periodo_id", "codigo"],
    optional: ["cupo_maximo", "horario", "ai_budget_monthly_usd"],
  },
  // ADR-029 (B.1): inscripciones — destraba el alta masiva de estudiantes.
  // student_pseudonym es un UUID derivado por federación LDAP / enrollment;
  // el CSV asume que ya viene resuelto. Rol y estado tienen defaults pero se
  // listan como optional para que el docente vea las opciones disponibles.
  inscripciones: {
    required: ["comision_id", "student_pseudonym", "fecha_inscripcion"],
    optional: ["rol", "estado", "nota_final", "fecha_cierre"],
  },
}

type DryRunState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; report: BulkImportReport }
  | { status: "error"; message: string }

type CommitState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; result: BulkImportCommitResult }
  | { status: "error"; message: string; report?: BulkImportReport }

export function BulkImportPage(): ReactNode {
  const [entity, setEntity] = useState<Entity>("facultades")
  const [file, setFile] = useState<File | null>(null)
  const [dryRun, setDryRun] = useState<DryRunState>({ status: "idle" })
  const [commit, setCommit] = useState<CommitState>({ status: "idle" })

  const reset = () => {
    setEntity("facultades")
    setFile(null)
    setDryRun({ status: "idle" })
    setCommit({ status: "idle" })
  }

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null
    setFile(f)
    // Si cambia el archivo, invalidar dry-run y commit anteriores.
    setDryRun({ status: "idle" })
    setCommit({ status: "idle" })
  }

  const onEntityChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setEntity(e.target.value as Entity)
    setDryRun({ status: "idle" })
    setCommit({ status: "idle" })
  }

  const handleDryRun = async () => {
    if (!file) return
    setDryRun({ status: "loading" })
    setCommit({ status: "idle" })
    try {
      const report = await bulkApi.dryRun(entity, file)
      setDryRun({ status: "ok", report })
    } catch (e) {
      setDryRun({
        status: "error",
        message: e instanceof HttpError ? `${e.status}: ${e.detail || e.title}` : String(e),
      })
    }
  }

  const handleCommit = async () => {
    if (!file) return
    setCommit({ status: "loading" })
    try {
      const result = await bulkApi.commit(entity, file)
      setCommit({ status: "ok", result })
    } catch (e) {
      // Si vino un 422 con report estructurado, intentar parsear.
      let parsedReport: BulkImportReport | undefined
      const message = e instanceof HttpError ? `${e.status}: ${e.detail || e.title}` : String(e)
      if (e instanceof HttpError && e.detail) {
        try {
          const parsed = JSON.parse(e.detail)
          if (parsed && typeof parsed === "object" && "errors" in parsed) {
            parsedReport = parsed as BulkImportReport
          }
        } catch {
          /* detail no era JSON */
        }
      }
      setCommit({
        status: "error",
        message,
        ...(parsedReport ? { report: parsedReport } : {}),
      })
    }
  }

  const cols = ENTITY_COLUMNS[entity]
  const canValidate = file !== null && dryRun.status !== "loading"
  const canCommit =
    dryRun.status === "ok" &&
    dryRun.report.invalid_rows === 0 &&
    dryRun.report.total_rows > 0 &&
    commit.status !== "loading" &&
    commit.status !== "ok"

  return (
    <PageContainer
      title="Importacion masiva"
      eyebrow="Inicio · Importacion masiva"
      description="Carga un CSV, valida con dry-run y luego confirma la importacion."
      helpContent={helpContent.bulkImport}
    >
      <div className="space-y-6">
        <div className="flex justify-end">
          <button
            type="button"
            onClick={reset}
            className="rounded-md border border-border bg-surface px-4 py-2 text-sm font-medium text-body hover:bg-surface-alt"
          >
            Reiniciar
          </button>
        </div>

        <section className="rounded-lg border border-border-soft bg-surface p-6 space-y-4">
          <h3 className="font-medium">1. Entidad</h3>
          <label className="flex flex-col gap-1 max-w-md">
            <span className="text-xs font-medium text-body">Tipo de entidad a importar</span>
            <select
              value={entity}
              onChange={onEntityChange}
              className={inputClass}
              disabled={commit.status === "ok"}
            >
              {ENTITY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>

          <div className="rounded-md border border-border-soft bg-surface-alt p-4 text-sm">
            <p className="font-medium text-body mb-2">Formato esperado</p>
            <p className="text-xs text-muted mb-2">
              Columnas para <span className="font-mono">{entity}</span>:
            </p>
            <ul className="text-xs space-y-1">
              {cols.required.map((c) => (
                <li key={c} className="font-mono">
                  <span className="text-ink">{c}</span>{" "}
                  <span className="text-danger">(requerida)</span>
                </li>
              ))}
              {cols.optional.map((c) => (
                <li key={c} className="font-mono">
                  <span className="text-body">{c}</span>{" "}
                  <span className="text-muted">(opcional)</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="rounded-lg border border-border-soft bg-surface p-6 space-y-4">
          <h3 className="font-medium">2. Archivo CSV</h3>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={onFileChange}
            disabled={commit.status === "ok"}
            className="block w-full text-sm text-body file:mr-4 file:rounded-md file:border-0 file:bg-accent-brand-soft file:px-4 file:py-2 file:text-sm file:font-medium file:text-accent-brand-deep hover:file:bg-accent-brand-soft"
          />
          {file && (
            <p className="text-xs text-muted">
              Seleccionado: <span className="font-mono text-ink">{file.name}</span>{" "}
              <span className="text-muted">({(file.size / 1024).toFixed(1)} KB)</span>
            </p>
          )}
        </section>

        <section className="rounded-lg border border-border-soft bg-surface p-6 space-y-4">
          <h3 className="font-medium">3. Validar (dry-run)</h3>
          <p className="text-sm text-muted">
            Sube el archivo y muestra errores sin escribir nada en la base.
          </p>
          <button
            type="button"
            onClick={handleDryRun}
            disabled={!canValidate}
            className="rounded-md bg-accent-brand text-white px-4 py-2 text-sm font-medium hover:bg-accent-brand-deep disabled:opacity-50"
          >
            {dryRun.status === "loading" ? "Validando…" : "Validar"}
          </button>

          {dryRun.status === "error" && (
            <div className="rounded-md border border-danger/40 bg-danger-soft p-4 text-sm text-danger">
              {dryRun.message}
            </div>
          )}

          {dryRun.status === "ok" && <ReportView report={dryRun.report} />}
        </section>

        <section className="rounded-lg border border-border-soft bg-surface p-6 space-y-4">
          <h3 className="font-medium">4. Confirmar importación</h3>
          <p className="text-sm text-muted">Sólo habilitado si el dry-run no mostró errores.</p>
          <button
            type="button"
            onClick={handleCommit}
            disabled={!canCommit}
            className="rounded-md bg-success text-white px-4 py-2 text-sm font-medium hover:bg-success disabled:opacity-50"
          >
            {commit.status === "loading" ? "Importando…" : "Confirmar"}
          </button>

          {commit.status === "error" && (
            <div className="space-y-2">
              <div className="rounded-md border border-danger/40 bg-danger-soft p-4 text-sm text-danger">
                {commit.message}
              </div>
              {commit.report && <ReportView report={commit.report} />}
            </div>
          )}

          {commit.status === "ok" && (
            <div className="rounded-md border border-success/40 bg-success-soft p-4 text-sm text-success space-y-2">
              <p className="font-medium">Importadas {commit.result.created_count} filas</p>
              {commit.result.created_ids.length > 0 && (
                <details className="text-xs">
                  <summary className="cursor-pointer text-success hover:text-success">
                    Ver IDs creados
                    {commit.result.created_ids.length > 10
                      ? ` (mostrando primeros 10 de ${commit.result.created_ids.length})`
                      : ""}
                  </summary>
                  <ul className="mt-2 font-mono space-y-0.5">
                    {commit.result.created_ids.slice(0, 10).map((id) => (
                      <li key={id}>{id}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}
        </section>
      </div>
    </PageContainer>
  )
}

function ReportView({ report }: { report: BulkImportReport }): ReactNode {
  const allValid = report.invalid_rows === 0 && report.total_rows > 0

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Totales" value={report.total_rows} tone="slate" />
        <Stat label="Válidas" value={report.valid_rows} tone="emerald" />
        <Stat label="Inválidas" value={report.invalid_rows} tone="red" />
      </div>

      {allValid && (
        <div className="rounded-md border border-success/40 bg-success-soft p-4 text-sm text-success">
          Todas las filas son válidas — listas para importar.
        </div>
      )}

      {report.total_rows === 0 && (
        <div className="rounded-md border border-warning/40 bg-warning-soft p-4 text-sm text-warning">
          El archivo no contiene filas.
        </div>
      )}

      {report.invalid_rows > 0 && (
        <div className="rounded-md border border-danger/30 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-danger-soft border-b border-danger/30 text-left">
              <tr>
                <th className="px-4 py-2 font-medium text-danger">Fila</th>
                <th className="px-4 py-2 font-medium text-danger">Columna</th>
                <th className="px-4 py-2 font-medium text-danger">Mensaje</th>
              </tr>
            </thead>
            <tbody>
              {report.errors.map((err, i) => (
                <tr
                  key={`${err.row_number}-${err.column ?? "_"}-${i}`}
                  className="border-b border-danger/20 last:border-b-0"
                >
                  <td className="px-4 py-2 font-mono text-xs">{err.row_number}</td>
                  <td className="px-4 py-2 font-mono text-xs">{err.column ?? "—"}</td>
                  <td className="px-4 py-2 text-danger">{err.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone: "slate" | "emerald" | "red"
}): ReactNode {
  const toneClasses = {
    slate: "border-border-soft bg-surface-alt text-ink",
    emerald: "border-success/30 bg-success-soft text-success",
    red: "border-danger/30 bg-danger-soft text-danger",
  }[tone]
  return (
    <div className={`rounded-md border p-4 ${toneClasses}`}>
      <div className="text-xs uppercase tracking-wide opacity-75">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
    </div>
  )
}

const inputClass =
  "w-full rounded-md border border-border px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-brand"
