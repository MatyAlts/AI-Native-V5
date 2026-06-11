/**
 * Vista de cohorte para los 3 instrumentos del diseño cuasi-experimental.
 *
 * Lectura de agregados con k-anonymity gate (MIN_STUDENTS_FOR_COHORT_SUMMARY=5).
 * Si la cohorte tiene <5 respondientes, el endpoint devuelve `insufficient_data:true`
 * y esta vista renderiza un empty state con CTA al docente.
 *
 * Cierra P2-1/2/3 del PlanMejora.md (esqueleto frontend para docente).
 * ADR de respaldo: ADR-053.
 */

import { useEffect, useMemo, useState } from "react"
import { useViewMode } from "../hooks/useViewMode"
import {
  type InstrumentoSummary,
  type TransferenciaSummary,
  instrumentosSummaryApi,
} from "../lib/api"
import { APPROPRIATION_REIFICATION_DISCLAIMER } from "../utils/docenteLabels"

interface Props {
  comisionId: string
  getToken?: () => Promise<string | null>
}

export function InstrumentosCohorteView({ comisionId, getToken }: Props) {
  const [cuestionarioIA, setCuestionarioIA] = useState<InstrumentoSummary | null>(null)
  const [pretest, setPretest] = useState<InstrumentoSummary | null>(null)
  const [transferencia, setTransferencia] = useState<TransferenciaSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [linkCopied, setLinkCopied] = useState(false)
  const [viewMode] = useViewMode()
  const isDocente = viewMode === "docente"

  const STUDENT_BASE =
    (import.meta.env.VITE_STUDENT_APP_URL as string | undefined) ??
    window.location.origin.replace(/:51\d\d$/, ":5175")

  const studentLink = useMemo(
    () => `${STUDENT_BASE}/instrumentos?comisionId=${comisionId}`,
    [comisionId],
  )

  useEffect(() => {
    setLoading(true)
    Promise.allSettled([
      instrumentosSummaryApi.cuestionarioIA(comisionId, undefined, getToken),
      instrumentosSummaryApi.pretest(comisionId, undefined, getToken),
      instrumentosSummaryApi.transferencia(comisionId, undefined, getToken),
    ]).then(([c, p, t]) => {
      if (c.status === "fulfilled") setCuestionarioIA(c.value)
      if (p.status === "fulfilled") setPretest(p.value)
      if (t.status === "fulfilled") setTransferencia(t.value)
      setLoading(false)
    })
  }, [comisionId, getToken])

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(studentLink)
      setLinkCopied(true)
      setTimeout(() => setLinkCopied(false), 2500)
    } catch {
      // best-effort
    }
  }

  const nCuestionario = cuestionarioIA?.n_responses ?? 0
  const nPretest = pretest?.n_responses ?? 0
  const nTransferencia = transferencia
    ? Object.values(transferencia.by_group).reduce(
        (acc, g) => acc + (g.n_students ?? 0),
        0,
      )
    : 0
  const totalRespondientes = Math.max(nCuestionario, nPretest, nTransferencia)
  const noResponsesYet = !loading && totalRespondientes === 0

  return (
    <section className="space-y-6">
      {/* ── Header con summary ───────────────────────────────────────── */}
      <header className="space-y-2">
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="text-lg font-semibold text-ink">
            Instrumentos de investigación · Cohorte
          </h2>
          {totalRespondientes > 0 && (
            <div className="text-sm text-muted">
              <span className="font-semibold text-ink">{totalRespondientes}</span> alumno
              {totalRespondientes !== 1 ? "s" : ""} respondió al menos un instrumento
            </div>
          )}
        </div>
        <p className="text-sm text-muted leading-relaxed">
          {isDocente
            ? "Resultados agregados de los 3 instrumentos opcionales que tus alumnos pueden responder. Sin atribución individual — solo distribuciones cuando hay ≥5 respondientes."
            : "Agregados con k-anonymity gate (k≥5). Si N<5 por grupo, el item devuelve insufficient_data."}
        </p>
      </header>

      {/* ── Empty state global con CTA ───────────────────────────────── */}
      {noResponsesYet && (
        <div className="rounded-xl border-2 border-dashed border-accent-brand/30 bg-accent-brand/5 p-6">
          <div className="flex items-start gap-4">
            <div
              aria-hidden="true"
              className="shrink-0 w-10 h-10 rounded-full bg-accent-brand/10 flex items-center justify-center text-accent-brand text-lg"
            >
              ✉
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-base font-semibold text-ink mb-1">
                Todavía no respondió ningún alumno
              </h3>
              <p className="text-sm text-muted mb-3">
                Compartí este link con tu cohorte para que respondan los 3 instrumentos
                (5–10 min cada uno). Los datos se agregan acá cuando llegan a 5 respondientes.
              </p>
              <div className="flex items-center gap-2 bg-white border border-border rounded-lg px-3 py-2">
                <code className="flex-1 min-w-0 text-xs font-mono text-ink truncate">
                  {studentLink}
                </code>
                <button
                  type="button"
                  onClick={copyLink}
                  className="shrink-0 text-xs font-medium px-3 py-1 rounded bg-accent-brand text-white hover:bg-accent-brand-deep transition"
                >
                  {linkCopied ? "✓ Copiado" : "Copiar"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── 3 cards instrumentos ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <InstrumentoStatCard
          icon="🧠"
          title="Experiencia previa con IA"
          subtitle="Cuestionario sobre uso previo de asistentes"
          summary={cuestionarioIA}
          loading={loading}
          testId="summary-cuestionario-ia"
          isDocente={isDocente}
        >
          {cuestionarioIA && !cuestionarioIA.insufficient_data && (
            <p className="text-xs text-muted mt-2">
              {cuestionarioIA.n_responses} alumno
              {cuestionarioIA.n_responses !== 1 ? "s" : ""} respondió. Distribuciones
              por item disponibles en modo investigador.
            </p>
          )}
        </InstrumentoStatCard>

        <InstrumentoStatCard
          icon="📊"
          title="Autoeficacia inicial"
          subtitle="Pretest basado en Lishinski 2016"
          summary={pretest}
          loading={loading}
          testId="summary-pretest"
          isDocente={isDocente}
        >
          {pretest && !pretest.insufficient_data && (
            <p className="text-xs text-muted mt-2">
              {pretest.n_responses} alumno{pretest.n_responses !== 1 ? "s" : ""} ·
              score promedio:{" "}
              <strong className="text-ink">
                {pretest.avg_total_score !== undefined && pretest.avg_total_score !== null
                  ? pretest.avg_total_score.toFixed(1)
                  : "—"}
              </strong>{" "}
              / 7.0
            </p>
          )}
        </InstrumentoStatCard>

        <TransferenciaStatCard summary={transferencia} loading={loading} isDocente={isDocente} />
      </div>

      {/* ── Disclaimer al final, prominente pero no invasivo ─────────── */}
      <aside
        className="rounded-lg border border-border bg-canvas p-3 text-xs text-muted leading-relaxed flex gap-2 items-start"
        data-testid="instrumentos-cohorte-disclaimer"
      >
        <span aria-hidden="true" className="shrink-0">
          ⓘ
        </span>
        <span>{APPROPRIATION_REIFICATION_DISCLAIMER}</span>
      </aside>
    </section>
  )
}

function InstrumentoStatCard({
  icon,
  title,
  subtitle,
  summary,
  loading,
  testId,
  isDocente,
  children,
}: {
  icon: string
  title: string
  subtitle: string
  summary: InstrumentoSummary | null
  loading: boolean
  testId: string
  isDocente: boolean
  children?: React.ReactNode
}) {
  const n = summary?.n_responses ?? 0
  const isInsufficient = summary?.insufficient_data ?? true
  const threshold = summary?.k_anonymity_threshold ?? 5

  return (
    <div
      className="rounded-xl border border-border bg-surface p-4 flex flex-col"
      data-testid={testId}
    >
      <div className="flex items-start gap-3 mb-3">
        <div
          aria-hidden="true"
          className="w-10 h-10 rounded-lg bg-canvas flex items-center justify-center text-xl shrink-0"
        >
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-ink leading-tight">{title}</h3>
          <p className="text-xs text-muted mt-0.5">{subtitle}</p>
        </div>
      </div>

      {loading ? (
        <div className="text-xs text-muted-soft animate-pulse">Cargando...</div>
      ) : isInsufficient ? (
        <div
          className="flex items-baseline gap-2"
          data-testid={`${testId}-insufficient`}
        >
          <span className="text-2xl font-bold text-muted-soft">{n}</span>
          <span className="text-xs text-muted">
            {isDocente
              ? `de ${threshold} mínimo para ver agregados`
              : `< ${threshold} (k-anonymity, RN-131)`}
          </span>
        </div>
      ) : (
        <>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-ink">{n}</span>
            <span className="text-xs text-muted">respondientes</span>
          </div>
          {children}
        </>
      )}
    </div>
  )
}

function TransferenciaStatCard({
  summary,
  loading,
  isDocente,
}: {
  summary: TransferenciaSummary | null
  loading: boolean
  isDocente: boolean
}) {
  const groups = summary ? Object.entries(summary.by_group) : []
  const hasData = groups.some(([_, s]) => !s.insufficient_data)
  const totalStudents = groups.reduce((acc, [_, s]) => acc + (s.n_students ?? 0), 0)

  return (
    <div
      className="rounded-xl border border-border bg-surface p-4 flex flex-col"
      data-testid="summary-transferencia"
    >
      <div className="flex items-start gap-3 mb-3">
        <div
          aria-hidden="true"
          className="w-10 h-10 rounded-lg bg-canvas flex items-center justify-center text-xl shrink-0"
        >
          🎯
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-ink leading-tight">
            Test de transferencia
          </h3>
          <p className="text-xs text-muted mt-0.5">
            Problemas sin IA para medir transferencia
          </p>
        </div>
      </div>

      {loading ? (
        <div className="text-xs text-muted-soft animate-pulse">Cargando...</div>
      ) : groups.length === 0 ? (
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold text-muted-soft">0</span>
          <span className="text-xs text-muted">
            {isDocente ? "ningún alumno completó el test" : "sin respuestas"}
          </span>
        </div>
      ) : !hasData ? (
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold text-muted-soft">{totalStudents}</span>
          <span className="text-xs text-muted">de 5 mínimo por grupo</span>
        </div>
      ) : (
        <table className="w-full text-xs mt-1">
          <thead>
            <tr className="border-b border-border-soft text-muted">
              <th className="text-left py-1 font-medium">Grupo</th>
              <th className="text-right py-1 font-medium">N</th>
              <th className="text-right py-1 font-medium">Accuracy</th>
            </tr>
          </thead>
          <tbody>
            {groups.map(([group, stats]) => (
              <tr key={group} className="border-b border-border-soft last:border-0">
                <td className="py-1.5 font-mono text-[11px]">{group}</td>
                {stats.insufficient_data ? (
                  <td colSpan={2} className="text-warning text-right text-[11px]">
                    N={stats.n_students} (&lt; {stats.k_anonymity_threshold})
                  </td>
                ) : (
                  <>
                    <td className="text-right">{stats.n_students}</td>
                    <td className="text-right font-mono">
                      {stats.accuracy !== undefined
                        ? `${(stats.accuracy * 100).toFixed(1)}%`
                        : "—"}
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
