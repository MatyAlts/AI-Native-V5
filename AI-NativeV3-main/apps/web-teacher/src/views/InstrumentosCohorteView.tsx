/**
 * Vista de cohorte para los 3 instrumentos del diseño cuasi-experimental.
 *
 * Lectura de agregados con k-anonymity gate (MIN_STUDENTS_FOR_COHORT_SUMMARY=5).
 * Si la cohorte tiene <5 respondientes, el endpoint devuelve `insufficient_data:true`
 * y esta vista renderiza un placeholder explicativo.
 *
 * Cierra P2-1/2/3 del PlanMejora.md (esqueleto frontend para docente).
 * ADR de respaldo: ADR-053.
 */

import { useEffect, useState } from "react"
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
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      instrumentosSummaryApi.cuestionarioIA(comisionId, undefined, getToken),
      instrumentosSummaryApi.pretest(comisionId, undefined, getToken),
      instrumentosSummaryApi.transferencia(comisionId, undefined, getToken),
    ])
      .then(([c, p, t]) => {
        setCuestionarioIA(c)
        setPretest(p)
        setTransferencia(t)
      })
      .catch((e) => setError(String(e)))
  }, [comisionId, getToken])

  if (error) {
    return (
      <div className="text-danger text-sm p-4">
        Error cargando agregados de instrumentos: {error}
      </div>
    )
  }

  return (
    <section className="space-y-4">
      <header className="border-b border-border pb-2">
        <h2 className="text-base font-semibold text-ink">
          Instrumentos de investigacion (cohorte)
        </h2>
        <p
          className="text-[11px] text-muted italic mt-1"
          data-testid="instrumentos-cohorte-disclaimer"
        >
          {APPROPRIATION_REIFICATION_DISCLAIMER}
        </p>
      </header>

      <SummaryCard
        title="Cuestionario sobre IA previa"
        summary={cuestionarioIA}
        testId="summary-cuestionario-ia"
      >
        {cuestionarioIA && !cuestionarioIA.insufficient_data && (
          <p className="text-xs text-muted">
            {cuestionarioIA.n_responses} estudiantes respondieron. Distribuciones por item:{" "}
            <code>{cuestionarioIA.by_item_distribution_status}</code>.
          </p>
        )}
      </SummaryCard>

      <SummaryCard title="Pretest de autoeficacia" summary={pretest} testId="summary-pretest">
        {pretest && !pretest.insufficient_data && (
          <p className="text-xs text-muted">
            {pretest.n_responses} estudiantes · score promedio:{" "}
            <strong>
              {pretest.avg_total_score !== undefined && pretest.avg_total_score !== null
                ? pretest.avg_total_score.toFixed(1)
                : "—"}
            </strong>
            <br />
            Subescalas: <code>{pretest.subscale_aggregation_status}</code>.
          </p>
        )}
      </SummaryCard>

      <TransferenciaSummaryCard summary={transferencia} />
    </section>
  )
}

function SummaryCard({
  title,
  summary,
  testId,
  children,
}: {
  title: string
  summary: InstrumentoSummary | null
  testId: string
  children?: React.ReactNode
}) {
  return (
    <div className="border border-border rounded-md bg-surface p-3" data-testid={testId}>
      <h3 className="text-sm font-semibold text-ink mb-1">{title}</h3>
      {!summary && <p className="text-xs text-muted">Cargando...</p>}
      {summary?.insufficient_data && (
        <p className="text-xs text-warning italic" data-testid={`${testId}-insufficient`}>
          Datos insuficientes: {summary.n_responses ?? 0} respuesta(s); se requieren al menos{" "}
          {summary.k_anonymity_threshold} (k-anonymity, RN-131).
        </p>
      )}
      {children}
    </div>
  )
}

function TransferenciaSummaryCard({
  summary,
}: {
  summary: TransferenciaSummary | null
}) {
  return (
    <div
      className="border border-border rounded-md bg-surface p-3"
      data-testid="summary-transferencia"
    >
      <h3 className="text-sm font-semibold text-ink mb-1">Test de transferencia</h3>
      {!summary && <p className="text-xs text-muted">Cargando...</p>}
      {summary && Object.entries(summary.by_group).length === 0 && (
        <p className="text-xs text-muted italic">Sin respuestas todavia.</p>
      )}
      {summary && (
        <table className="w-full text-xs mt-2">
          <thead>
            <tr className="border-b border-border text-muted">
              <th className="text-left pb-1">Grupo</th>
              <th className="text-right pb-1">N estudiantes</th>
              <th className="text-right pb-1">N intentos</th>
              <th className="text-right pb-1">Accuracy</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(summary.by_group).map(([group, stats]) => (
              <tr key={group} className="border-b border-border last:border-0">
                <td className="py-1.5 font-mono">{group}</td>
                {stats.insufficient_data ? (
                  <td colSpan={3} className="text-warning text-right">
                    Datos insuficientes (N={stats.n_students} &lt; {stats.k_anonymity_threshold})
                  </td>
                ) : (
                  <>
                    <td className="text-right">{stats.n_students}</td>
                    <td className="text-right">{stats.n_attempts}</td>
                    <td className="text-right font-mono">
                      {stats.accuracy !== undefined ? `${(stats.accuracy * 100).toFixed(1)}%` : "—"}
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
