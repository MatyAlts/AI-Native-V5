/**
 * Vista de exportación académica anonymizada.
 *
 * Flow:
 *  1. Docente/investigador completa form: comisión + salt + período
 *  2. POST /cohort/export → devuelve job_id
 *  3. Polling cada 2s al endpoint /status hasta succeeded|failed
 *  4. Si succeeded, botón "Descargar JSON" invoca /download
 *
 * Salt mínimo 16 chars — el componente valida en cliente antes de enviar.
 */
import { HelpButton, PageContainer } from "@platform/ui"
import { useCallback, useEffect, useRef, useState } from "react"
import {
  type ExportJobStatus,
  downloadExport,
  getExportStatus,
  requestCohortExport,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

interface Props {
  getToken: () => Promise<string | null>
  comisionIdDefault?: string
}

export function ExportView({ getToken, comisionIdDefault = "" }: Props) {
  const [comisionId, setComisionId] = useState(comisionIdDefault)
  const [salt, setSalt] = useState("")
  const [periodDays, setPeriodDays] = useState(90)
  const [includePrompts, setIncludePrompts] = useState(false)
  const [cohortAlias, setCohortAlias] = useState("")

  const [job, setJob] = useState<ExportJobStatus | null>(null)
  const [requesting, setRequesting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const pollRef = useRef<number | null>(null)

  const saltValid = salt.length >= 16
  const canSubmit = Boolean(comisionId) && saltValid && !requesting && !job

  const startPolling = useCallback(
    (jobId: string) => {
      let cancelled = false
      const tick = async () => {
        if (cancelled) return
        try {
          const status = await getExportStatus(jobId, getToken)
          setJob(status)
          if (status.status === "succeeded" || status.status === "failed") {
            return // stop polling
          }
        } catch (e) {
          setError(`Error en polling: ${String(e)}`)
          return
        }
        pollRef.current = window.setTimeout(tick, 2000)
      }
      tick()
      return () => {
        cancelled = true
        if (pollRef.current !== null) clearTimeout(pollRef.current)
      }
    },
    [getToken],
  )

  useEffect(() => {
    return () => {
      if (pollRef.current !== null) clearTimeout(pollRef.current)
    }
  }, [])

  const handleSubmit = async () => {
    setError(null)
    setRequesting(true)
    try {
      const r = await requestCohortExport(
        {
          comision_id: comisionId,
          period_days: periodDays,
          include_prompts: includePrompts,
          salt,
          cohort_alias: cohortAlias || "COHORT",
        },
        getToken,
      )
      setJob({
        job_id: r.job_id,
        status: "pending",
        comision_id: comisionId,
        requested_at: new Date().toISOString(),
        period_days: periodDays,
        include_prompts: includePrompts,
        salt_hash: "", // se completa en el primer poll
        cohort_alias: cohortAlias || "COHORT",
        started_at: null,
        completed_at: null,
        error: null,
      })
      startPolling(r.job_id)
    } catch (e) {
      setError(String(e))
    } finally {
      setRequesting(false)
    }
  }

  const handleDownload = async () => {
    if (!job) return
    try {
      const payload = await downloadExport(job.job_id, getToken)
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${job.cohort_alias}_${job.job_id.slice(0, 8)}.json`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(String(e))
    }
  }

  const handleReset = () => {
    setJob(null)
    setError(null)
    if (pollRef.current !== null) clearTimeout(pollRef.current)
  }

  return (
    <PageContainer
      title="Exportar dataset academico"
      description="Genera un dataset anonimizado con los episodios, eventos y clasificaciones N4 de una cohorte."
      helpContent={helpContent.export}
    >
      <div className="max-w-2xl space-y-6">
        {!job && (
          <div className="rounded-lg border border-border-soft dark:border-sidebar-bg-edge bg-white dark:bg-sidebar-bg p-6 space-y-4">
            <div className="flex items-center gap-2 mb-2">
              <HelpButton
                size="sm"
                title="Formulario de exportacion"
                content={
                  <div className="space-y-3 text-sidebar-text-muted">
                    <p>
                      <strong>Completa los siguientes campos</strong> para generar el dataset:
                    </p>
                    <ul className="list-disc pl-5 space-y-2">
                      <li>
                        <strong>Comision (UUID):</strong> Identificador de la comision a exportar.
                        Obligatorio.
                      </li>
                      <li>
                        <strong>Salt:</strong> Minimo 16 caracteres. Mismo salt = mismos pseudonimos
                        → datasets correlacionables.
                      </li>
                      <li>
                        <strong>Periodo (dias):</strong> Ventana de tiempo hacia atras. Default 90.
                      </li>
                      <li>
                        <strong>Alias de cohorte:</strong> Nombre libre para identificar el archivo
                        (ej. UNSL_2026_P2).
                      </li>
                      <li>
                        <strong>Incluir prompts:</strong> Activa con precaucion: riesgo de
                        re-identificacion.
                      </li>
                    </ul>
                  </div>
                }
              />
              <span className="text-sm text-muted dark:text-sidebar-text-muted">
                Ayuda sobre el formulario
              </span>
            </div>
            <label className="block">
              <span className="block text-sm font-medium mb-1">Comisión (UUID)</span>
              <input
                type="text"
                value={comisionId}
                onChange={(e) => setComisionId(e.target.value)}
                placeholder="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
                className="w-full px-3 py-2 border border-border dark:border-sidebar-bg-edge rounded font-mono text-sm bg-transparent"
              />
            </label>

            <div>
              <label className="block">
                <span className="block text-sm font-medium mb-1">
                  Salt de anonimización{" "}
                  <span className="text-xs text-muted">(mínimo 16 caracteres)</span>
                </span>
                <input
                  type="text"
                  value={salt}
                  onChange={(e) => setSalt(e.target.value)}
                  placeholder="mi-investigacion-unsl-2026-xxxxx"
                  className={`w-full px-3 py-2 border rounded font-mono text-sm bg-transparent ${
                    salt.length > 0 && !saltValid
                      ? "border-danger/40"
                      : "border-border dark:border-sidebar-bg-edge"
                  }`}
                />
              </label>
              {salt.length > 0 && !saltValid && (
                <p className="text-xs text-danger mt-1">
                  Salt muy corto ({salt.length} chars, mínimo 16).
                </p>
              )}
              <p className="text-xs text-muted mt-1">
                Guardalo en un lugar seguro: sin el salt no podés correlacionar datasets posteriores
                con éste.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <label className="block">
                <span className="block text-sm font-medium mb-1">Período (días)</span>
                <input
                  type="number"
                  min={1}
                  max={365}
                  value={periodDays}
                  onChange={(e) => setPeriodDays(Number(e.target.value))}
                  className="w-full px-3 py-2 border border-border dark:border-sidebar-bg-edge rounded text-sm bg-transparent"
                />
              </label>
              <label className="block">
                <span className="block text-sm font-medium mb-1">Alias de cohorte</span>
                <input
                  type="text"
                  value={cohortAlias}
                  onChange={(e) => setCohortAlias(e.target.value)}
                  placeholder="UNSL_2026_P2"
                  className="w-full px-3 py-2 border border-border dark:border-sidebar-bg-edge rounded text-sm bg-transparent"
                />
              </label>
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={includePrompts}
                onChange={(e) => setIncludePrompts(e.target.checked)}
                className="h-4 w-4"
              />
              <span>Incluir texto de prompts</span>
              <span className="text-xs text-warning/85 bg-warning-soft px-2 py-0.5 rounded">
                riesgo re-identificación
              </span>
            </label>

            <button
              type="button"
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="w-full px-4 py-2 bg-accent-brand hover:bg-accent-brand-deep disabled:bg-border-strong text-white rounded font-medium"
            >
              {requesting ? "Encolando..." : "Generar dataset"}
            </button>
          </div>
        )}

        {job && <JobProgressPanel job={job} onDownload={handleDownload} onReset={handleReset} />}

        {error && <div className="p-3 rounded bg-danger-soft text-danger text-sm">{error}</div>}
      </div>
    </PageContainer>
  )
}

function JobProgressPanel({
  job,
  onDownload,
  onReset,
}: {
  job: ExportJobStatus
  onDownload: () => void
  onReset: () => void
}) {
  const PENDING_CFG = { color: "bg-border-strong", label: "En cola", progress: 15 }
  const statusConfig: Record<string, { color: string; label: string; progress: number }> = {
    pending: PENDING_CFG,
    running: { color: "bg-accent-brand", label: "Procesando", progress: 60 },
    succeeded: { color: "bg-green-600", label: "Completado", progress: 100 },
    failed: { color: "bg-danger", label: "Error", progress: 100 },
  }
  const cfg = statusConfig[job.status] ?? PENDING_CFG

  return (
    <div className="rounded-lg border border-border-soft dark:border-sidebar-bg-edge bg-white dark:bg-sidebar-bg p-6 space-y-4">
      <div className="flex items-baseline justify-between">
        <h3 className="font-medium">Job {job.job_id.slice(0, 12)}...</h3>
        <span className={`px-2 py-0.5 rounded text-xs text-white ${cfg.color}`}>{cfg.label}</span>
      </div>

      <div className="relative h-2 bg-surface-alt dark:bg-sidebar-bg-edge rounded overflow-hidden">
        <div
          className={`absolute left-0 top-0 h-full transition-all ${cfg.color} ${
            job.status === "running" ? "animate-pulse" : ""
          }`}
          style={{ width: `${cfg.progress}%` }}
        />
      </div>

      <dl className="grid grid-cols-2 gap-2 text-xs text-muted dark:text-muted-soft">
        <div>
          <dt className="font-medium">Cohorte</dt>
          <dd className="font-mono">{job.cohort_alias}</dd>
        </div>
        <div>
          <dt className="font-medium">Período</dt>
          <dd>{job.period_days} días</dd>
        </div>
        <div>
          <dt className="font-medium">Prompts</dt>
          <dd>{job.include_prompts ? "incluidos" : "excluidos"}</dd>
        </div>
        {job.salt_hash && (
          <div>
            <dt className="font-medium">Salt hash</dt>
            <dd className="font-mono">{job.salt_hash}</dd>
          </div>
        )}
      </dl>

      {job.status === "failed" && job.error && (
        <div className="p-3 rounded bg-danger-soft text-danger text-sm font-mono">{job.error}</div>
      )}

      <div className="flex gap-2 pt-2">
        {job.status === "succeeded" && (
          <button
            type="button"
            onClick={onDownload}
            className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded font-medium text-sm"
          >
            Descargar JSON
          </button>
        )}
        <button
          type="button"
          onClick={onReset}
          className="px-4 py-2 border border-border dark:border-sidebar-bg-edge rounded hover:bg-surface-alt dark:hover:bg-sidebar-bg-edge text-sm"
        >
          Nuevo export
        </button>
      </div>
    </div>
  )
}
