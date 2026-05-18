/**
 * Vista docente/admin de clasificaciones N4 agregadas por comisión.
 *
 * Consume GET /api/v1/classifications/aggregated del classifier-service.
 * Muestra distribución, evolución temporal y promedios de las 3 coherencias.
 */
import { PageContainer } from "@platform/ui"
import { type ReactNode, useEffect, useState } from "react"
import { ComisionPicker } from "../components/ComisionPicker"
import { helpContent } from "../utils/helpContent"

type Appropriation = "delegacion_pasiva" | "apropiacion_superficial" | "apropiacion_reflexiva"

interface AggregatedStats {
  comision_id: string
  period_days: number
  total_episodes: number
  distribution: Record<Appropriation, number>
  avg_ct_summary: number | null
  avg_ccd_mean: number | null
  avg_ccd_orphan_ratio: number | null
  avg_cii_stability: number | null
  avg_cii_evolution: number | null
  timeseries: { date: string; counts: Record<Appropriation, number> }[]
}

// Headers X-* los inyecta el proxy de Vite + el monkey-patch de `main.tsx`.
// No mas mock-headers hardcoded acá.

export function ClasificacionesPage(): ReactNode {
  const [comisionId, setComisionId] = useState<string | null>(null)
  const [stats, setStats] = useState<AggregatedStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [periodDays, setPeriodDays] = useState(30)

  useEffect(() => {
    if (!comisionId) {
      setStats(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)

    fetch(
      `/api/v1/classifications/aggregated?comision_id=${comisionId}&period_days=${periodDays}`,
    )
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((data: AggregatedStats) => {
        if (!cancelled) {
          setStats(data)
          setLoading(false)
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(`Error cargando: ${e.message}`)
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [comisionId, periodDays])

  return (
    <PageContainer
      title="Clasificaciones N4"
      eyebrow="Inicio · Clasificaciones N4"
      description={
        stats
          ? `Ultimos ${stats.period_days} dias · ${stats.total_episodes} episodios cerrados`
          : "Seleccioná una comisión para ver clasificaciones agregadas"
      }
      helpContent={helpContent.clasificaciones}
    >
      <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <ComisionPicker value={comisionId} onChange={setComisionId} autoSelectFirst />
          <select
            value={periodDays}
            onChange={(e) => setPeriodDays(Number(e.target.value))}
            className="rounded border border-border px-3 py-1 text-sm"
            disabled={!comisionId}
          >
            <option value={7}>últimos 7 días</option>
            <option value={30}>últimos 30 días</option>
            <option value={90}>últimos 90 días</option>
          </select>
        </div>

        {error && (
          <div className="rounded-lg bg-danger-soft border border-danger/30 text-danger p-4">
            <p className="font-medium">No se pudo cargar</p>
            <p className="text-sm mt-1">{error}</p>
            <p className="text-xs mt-2 text-danger">
              Asegurate de que classifier-service esté corriendo en el puerto 8008 y que haya
              clasificaciones persistidas para la comisión seleccionada.
            </p>
          </div>
        )}

        {loading && <p className="text-sm text-muted">Cargando clasificaciones...</p>}

        {!loading && !comisionId && !error && (
          <div className="rounded-lg bg-surface-alt border border-border-soft p-8 text-center">
            <p className="text-muted">
              Elegí una comisión arriba para ver la distribución y promedios.
            </p>
          </div>
        )}

        {comisionId && stats && stats.total_episodes === 0 && (
          <div className="rounded-lg bg-surface-alt border border-border-soft p-8 text-center">
            <p className="text-muted">Aún no hay clasificaciones en el período seleccionado.</p>
          </div>
        )}

        {comisionId && stats && stats.total_episodes > 0 && (
          <>
            {/* Distribución por tipo */}
            <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <DistributionCard
                label="Delegación pasiva"
                count={stats.distribution.delegacion_pasiva}
                total={stats.total_episodes}
                color="red"
                emoji="⚠️"
              />
              <DistributionCard
                label="Apropiación superficial"
                count={stats.distribution.apropiacion_superficial}
                total={stats.total_episodes}
                color="yellow"
                emoji="🤔"
              />
              <DistributionCard
                label="Apropiación reflexiva"
                count={stats.distribution.apropiacion_reflexiva}
                total={stats.total_episodes}
                color="green"
                emoji="🌟"
              />
            </section>

            {/* Promedios de las 3 coherencias */}
            <section className="rounded-lg border border-border-soft bg-surface p-4">
              <h2 className="text-sm font-semibold uppercase text-muted mb-3">
                Promedios de las tres coherencias
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <AverageMetric title="Coherencia Temporal" value={stats.avg_ct_summary} />
                <AverageMetric title="Código ↔ Discurso" value={stats.avg_ccd_mean} />
                <AverageMetric title="Inter-Iteración (estab.)" value={stats.avg_cii_stability} />
              </div>
            </section>

            {/* Timeseries */}
            {stats.timeseries.length > 0 && (
              <section className="rounded-lg border border-border-soft bg-surface p-4">
                <h2 className="text-sm font-semibold uppercase text-muted mb-4">
                  Evolución temporal
                </h2>
                <Timeseries data={stats.timeseries} />
              </section>
            )}
          </>
        )}
      </div>
    </PageContainer>
  )
}

function DistributionCard({
  label,
  count,
  total,
  color,
  emoji,
}: {
  label: string
  count: number
  total: number
  color: "red" | "yellow" | "green"
  emoji: string
}): ReactNode {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0
  const bg = {
    red: "bg-danger-soft border-danger/30",
    yellow: "bg-warning-soft border-warning/30",
    green: "bg-success-soft border-success/30",
  }[color]
  const textColor = {
    red: "text-danger",
    yellow: "text-warning",
    green: "text-success",
  }[color]

  return (
    <div className={`rounded-lg border p-4 ${bg} ${textColor}`}>
      <div className="text-2xl mb-1">{emoji}</div>
      <div className="font-medium text-sm">{label}</div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-3xl font-bold">{count}</span>
        <span className="text-sm opacity-70">
          de {total} ({pct}%)
        </span>
      </div>
    </div>
  )
}

function AverageMetric({ title, value }: { title: string; value: number | null }): ReactNode {
  if (value == null) {
    return (
      <div>
        <p className="text-xs text-muted">{title}</p>
        <p className="text-sm text-muted-soft mt-1">sin datos</p>
      </div>
    )
  }
  const pct = Math.round(value * 100)
  const color = pct > 60 ? "bg-success" : pct > 40 ? "bg-warning" : "bg-danger"
  return (
    <div>
      <p className="text-xs text-muted">{title}</p>
      <div className="flex items-baseline gap-2 mt-1">
        <span className="font-mono text-xl">{value.toFixed(2)}</span>
        <span className="text-xs text-muted-soft">{pct}%</span>
      </div>
      <div className="mt-2 h-2 bg-surface-alt rounded overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function Timeseries({
  data,
}: {
  data: { date: string; counts: Record<Appropriation, number> }[]
}): ReactNode {
  const max = Math.max(
    ...data.map(
      (d) =>
        d.counts.delegacion_pasiva +
        d.counts.apropiacion_superficial +
        d.counts.apropiacion_reflexiva,
    ),
    1,
  )

  return (
    <div>
      <div className="flex items-end gap-1 h-48">
        {data.map((d) => {
          const total =
            d.counts.delegacion_pasiva +
            d.counts.apropiacion_superficial +
            d.counts.apropiacion_reflexiva
          const totalPct = (total / max) * 100
          const rPct = total > 0 ? (d.counts.delegacion_pasiva / total) * 100 : 0
          const yPct = total > 0 ? (d.counts.apropiacion_superficial / total) * 100 : 0
          const gPct = total > 0 ? (d.counts.apropiacion_reflexiva / total) * 100 : 0

          return (
            <div key={d.date} className="flex-1 flex flex-col items-center gap-1">
              <div
                className="w-full flex flex-col-reverse rounded overflow-hidden"
                style={{ height: `${totalPct}%`, minHeight: "4px" }}
                title={`${d.date}: ${total} episodios`}
              >
                <div className="bg-danger" style={{ height: `${rPct}%` }} />
                <div className="bg-warning" style={{ height: `${yPct}%` }} />
                <div className="bg-success" style={{ height: `${gPct}%` }} />
              </div>
              <span className="text-xs text-muted-soft rotate-45 origin-top-left whitespace-nowrap mt-2">
                {d.date.slice(5)}
              </span>
            </div>
          )
        })}
      </div>
      <div className="flex gap-4 mt-6 text-xs text-muted">
        <LegendDot color="bg-success" label="Reflexiva" />
        <LegendDot color="bg-warning" label="Superficial" />
        <LegendDot color="bg-danger" label="Delegación" />
      </div>
    </div>
  )
}

function LegendDot({ color, label }: { color: string; label: string }): ReactNode {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`w-3 h-3 rounded ${color}`} />
      <span>{label}</span>
    </div>
  )
}
