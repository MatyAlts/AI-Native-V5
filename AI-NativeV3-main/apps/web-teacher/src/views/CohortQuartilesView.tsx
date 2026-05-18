import { PageContainer, StateMessage } from "@platform/ui"
import { Link } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useViewMode } from "../hooks/useViewMode"
import { type CohortCIIQuartiles, getCohortCIIQuartiles } from "../lib/api"
import { helpContent } from "../utils/helpContent"

interface Props {
  getToken: () => Promise<string | null>
  initialComisionId?: string
}

function formatSlope(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—"
  return value.toFixed(3)
}

function slopeTone(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "text-muted-soft"
  if (value > 0.1) return "text-[var(--color-success)]"
  if (value < -0.1) return "text-[var(--color-danger)]"
  return "text-ink"
}

function slopeBadge(value: number | null, isDocente: boolean): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "sin dato"
  if (value > 0.1) return isDocente ? "mejorando" : "slope positivo"
  if (value < -0.1) return isDocente ? "empeorando" : "slope negativo"
  return isDocente ? "estable" : "slope ~0"
}

function QuartileCard({
  label,
  description,
  value,
  isDocente,
}: {
  label: string
  description: string
  value: number | null
  isDocente: boolean
}) {
  return (
    <div className="rounded-xl border border-border bg-white p-5 flex flex-col gap-2">
      <div className="text-xs font-medium uppercase tracking-wider text-muted">{label}</div>
      <div className={`text-3xl font-semibold ${slopeTone(value)}`}>{formatSlope(value)}</div>
      <div className="text-xs text-muted-soft">{description}</div>
      <div className="text-[11px] text-muted mt-1 italic">{slopeBadge(value, isDocente)}</div>
    </div>
  )
}

export function CohortQuartilesView({ getToken, initialComisionId }: Props) {
  const comisionId = initialComisionId ?? null
  const [data, setData] = useState<CohortCIIQuartiles | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [viewMode] = useViewMode()
  const isDocente = viewMode === "docente"

  useEffect(() => {
    if (!comisionId) {
      setData(null)
      return
    }
    setLoading(true)
    setError(null)
    let cancelled = false
    getCohortCIIQuartiles(comisionId, getToken)
      .then((d) => {
        if (!cancelled) setData(d)
      })
      .catch((e) => {
        if (!cancelled) setError(String(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [comisionId, getToken])

  return (
    <PageContainer
      title={
        isDocente ? "Distribucion de progreso en la cohorte" : "Cuartiles CII de cohorte"
      }
      description={
        isDocente
          ? "Muestra como se distribuye el progreso de tus alumnos. Los cuartiles dividen al grupo en cuatro segmentos iguales segun su evolucion en los episodios."
          : "Cuartiles agregados del mean_slope longitudinal por estudiante (ADR-022, RN-131). Privacidad k-anonymity: requiere N >= 5 estudiantes con slope computable. La mediana es Q2."
      }
      helpContent={helpContent.cohortQuartiles}
    >
      <div className="space-y-6">
        {comisionId && (
          <div className="text-xs">
            <Link
              to="/progression"
              search={{ comisionId }}
              className="text-muted hover:text-ink transition-colors"
            >
              ← {isDocente ? "Volver a mis alumnos" : "Volver a la cohorte"}
            </Link>
          </div>
        )}

        {!comisionId && !loading && (
          <div className="rounded-xl border border-dashed border-border bg-white p-6 text-sm text-muted">
            {isDocente
              ? "Elegi una comision desde la barra superior para ver la distribucion."
              : "Elegi una comision para computar los cuartiles CII de su cohorte."}
          </div>
        )}

        {loading && <StateMessage variant="loading" title="Calculando cuartiles de la cohorte..." />}

        {error && (
          <StateMessage variant="error" title="Error consultando la cohorte" description={error} />
        )}

        {data && !loading && (
          <>
            {/* Header con conteo de estudiantes y privacy gate */}
            <div className="rounded-xl border border-border bg-white px-6 py-4">
              <div className="flex flex-wrap items-baseline gap-x-8 gap-y-2">
                <div>
                  <div className="text-3xl font-semibold text-ink">
                    {data.n_students_evaluated}
                  </div>
                  <div className="text-xs text-muted mt-0.5">
                    {isDocente
                      ? `alumno${data.n_students_evaluated !== 1 ? "s" : ""} con datos suficientes`
                      : "estudiantes con mean_slope computable"}
                  </div>
                </div>
                <div className="text-xs text-muted">
                  <div>
                    {isDocente ? "Umbral de privacidad:" : "k-anonymity threshold:"}{" "}
                    <span className="font-semibold text-ink">
                      N &gt;= {data.min_students_for_quartiles}
                    </span>
                  </div>
                  <div className="mt-0.5">
                    {isDocente ? "Version del etiquetador:" : "labeler_version:"}{" "}
                    <span className="font-mono text-ink">{data.labeler_version}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Insufficient data branch (k-anonymity gate) */}
            {data.insufficient_data && (
              <div className="rounded-xl border border-warning/30 bg-warning-soft px-6 py-4 text-sm text-warning">
                <div className="font-semibold mb-1">
                  {isDocente ? "Datos insuficientes" : "Insufficient data"}
                </div>
                <div>
                  {isDocente
                    ? `Necesitamos al menos ${data.min_students_for_quartiles} alumnos con episodios suficientes para mostrar la distribucion sin exponer trayectorias individuales. La cohorte tiene ${data.n_students_evaluated} con datos.`
                    : `La cohorte tiene ${data.n_students_evaluated} estudiantes con mean_slope computable; se requieren ${data.min_students_for_quartiles} (k-anonymity, ADR-022 / packages/platform-ops cii_alerts). Con N < ${data.min_students_for_quartiles} los cuartiles son trivialmente reconstruibles. Esperar mas episodios cerrados o ampliar el periodo de la cohorte.`}
                </div>
              </div>
            )}

            {/* Quartile cards (solo si hay datos suficientes) */}
            {!data.insufficient_data && (
              <>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <QuartileCard
                    label="Q1 (25%)"
                    description={
                      isDocente
                        ? "25% de los alumnos esta por debajo de este valor."
                        : "Primer cuartil del mean_slope cohorte."
                    }
                    value={data.q1}
                    isDocente={isDocente}
                  />
                  <QuartileCard
                    label={isDocente ? "Mediana (Q2)" : "Mediana (Q2 · 50%)"}
                    description={
                      isDocente
                        ? "Valor del alumno tipico de la cohorte."
                        : "Mediana del mean_slope cohorte."
                    }
                    value={data.median}
                    isDocente={isDocente}
                  />
                  <QuartileCard
                    label="Q3 (75%)"
                    description={
                      isDocente
                        ? "75% de los alumnos esta por debajo de este valor."
                        : "Tercer cuartil del mean_slope cohorte."
                    }
                    value={data.q3}
                    isDocente={isDocente}
                  />
                </div>

                {/* Stats secundarios: min, max, mean, stdev */}
                <div className="rounded-xl border border-border bg-white overflow-hidden">
                  <div className="border-b border-border bg-canvas px-6 py-3">
                    <span className="text-xs font-semibold text-ink uppercase tracking-wider">
                      {isDocente ? "Detalle estadistico" : "Stats agregados de mean_slope"}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-border">
                    <div className="px-6 py-4">
                      <div className="text-xs text-muted uppercase tracking-wider">Min</div>
                      <div className={`text-xl font-semibold mt-1 ${slopeTone(data.min)}`}>
                        {formatSlope(data.min)}
                      </div>
                    </div>
                    <div className="px-6 py-4">
                      <div className="text-xs text-muted uppercase tracking-wider">Max</div>
                      <div className={`text-xl font-semibold mt-1 ${slopeTone(data.max)}`}>
                        {formatSlope(data.max)}
                      </div>
                    </div>
                    <div className="px-6 py-4">
                      <div className="text-xs text-muted uppercase tracking-wider">
                        {isDocente ? "Promedio" : "Mean"}
                      </div>
                      <div className={`text-xl font-semibold mt-1 ${slopeTone(data.mean)}`}>
                        {formatSlope(data.mean)}
                      </div>
                    </div>
                    <div className="px-6 py-4">
                      <div className="text-xs text-muted uppercase tracking-wider">
                        {isDocente ? "Dispersion" : "Stdev"}
                      </div>
                      <div className="text-xl font-semibold text-ink mt-1">
                        {formatSlope(data.stdev)}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Lectura interpretativa */}
                <div className="rounded-xl border border-border bg-canvas px-6 py-4 text-sm text-muted">
                  <div className="font-semibold text-ink mb-2">
                    {isDocente ? "Como leer estos numeros" : "Interpretacion"}
                  </div>
                  <ul className="list-disc list-inside space-y-1.5">
                    <li>
                      {isDocente
                        ? "Cada alumno tiene un valor de progreso (slope) calculado sobre sus episodios analogos."
                        : "Cada estudiante aporta un mean_slope (ADR-018, slope ordinal sobre APPROPRIATION_ORDINAL por template)."}
                    </li>
                    <li>
                      {isDocente
                        ? "Valores positivos = el alumno mejora. Negativos = empeora. Cerca de cero = estable."
                        : "Slope > 0.1 = mejora; slope < -0.1 = regresion; ~0 = estable. Cuartiles cardinales sobre datos ordinales (operacionalizacion conservadora declarada en ADR-018)."}
                    </li>
                    <li>
                      {isDocente
                        ? "Si la mediana es positiva, la mitad de la clase progresa. Si Q1 es muy negativo, hay un grupo en riesgo."
                        : "Si Q1 < 0 significativamente, el cuartil inferior esta regresionando: candidato para intervencion focalizada."}
                    </li>
                  </ul>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </PageContainer>
  )
}
