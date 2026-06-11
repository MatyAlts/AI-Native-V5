/**
 * Vista docente/admin de clasificaciones N4 agregadas por comisión.
 *
 * Consume GET /api/v1/classifications/aggregated del classifier-service.
 * Muestra distribución, evolución temporal y promedios de las 3 coherencias.
 *
 * F2 — nueva medición (modo sombra):
 * Consume GET /api/v1/classifications/subgrupos del classifier-service.
 * Muestra los 8 subgrupos con roll-up a los 3 ejes y las 4 dimensiones.
 */
import { PageContainer } from "@platform/ui"
import { type ReactNode, useEffect, useState } from "react"
import { ComisionPicker } from "../components/ComisionPicker"
import { helpContent } from "../utils/helpContent"

// ── Tipos — medición oficial ──────────────────────────────────────────────

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

// ── Tipos — nueva medición (modo sombra) ──────────────────────────────────

type Eje = "reflexiva" | "superficial" | "delegacion_pasiva" | "sin_clasificar"

interface SubgrupoCount {
  key: string
  label: string
  accion_docente: string
  eje: Eje
  count: number
}

interface SubgruposStats {
  comision_id: string
  total_episodes: number
  subgrupos: SubgrupoCount[]
  avg_dimensiones: {
    autonomia: number | null
    experimentacion: number | null
    persistencia: number | null
    foco: number | null
  }
}

// Headers X-* los inyecta el proxy de Vite + el monkey-patch de `main.tsx`.

export function ClasificacionesPage(): ReactNode {
  const [comisionId, setComisionId] = useState<string | null>(null)
  const [periodDays, setPeriodDays] = useState(30)

  // Medición oficial
  const [stats, setStats] = useState<AggregatedStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Nueva medición (modo sombra)
  const [subgruposStats, setSubgruposStats] = useState<SubgruposStats | null>(null)
  const [subgruposPending, setSubgruposPending] = useState(false)

  useEffect(() => {
    if (!comisionId) {
      setStats(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)

    fetch(`/api/v1/classifications/aggregated?comision_id=${comisionId}&period_days=${periodDays}`)
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

  useEffect(() => {
    if (!comisionId) {
      setSubgruposStats(null)
      setSubgruposPending(false)
      return
    }
    let cancelled = false
    setSubgruposStats(null)
    setSubgruposPending(false)

    fetch(`/api/v1/classifications/subgrupos?comision_id=${comisionId}&period_days=${periodDays}`)
      .then(async (r) => {
        if (r.status === 404 || r.status === 501) {
          if (!cancelled) setSubgruposPending(true)
          return null
        }
        if (!r.ok) return null
        return r.json()
      })
      .then((data: SubgruposStats | null) => {
        if (!cancelled && data) setSubgruposStats(data)
      })
      .catch(() => {
        if (!cancelled) setSubgruposPending(true)
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
          ? `Últimos ${stats.period_days} días · ${stats.total_episodes} episodios cerrados`
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

            {/* Nueva medición — 8 subgrupos (modo sombra) */}
            <NuevaMedicionSection
              stats={subgruposStats}
              pending={subgruposPending}
              totalEpisodes={stats.total_episodes}
            />
          </>
        )}
      </div>
    </PageContainer>
  )
}

// ── Componentes — medición oficial ────────────────────────────────────────

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

// ── Componentes — nueva medición (modo sombra) ────────────────────────────

const EJE_CONFIG: Record<Eje, { label: string; bg: string; border: string; text: string; dot: string }> = {
  reflexiva: {
    label: "Reflexiva",
    bg: "bg-success-soft",
    border: "border-success/30",
    text: "text-success",
    dot: "bg-success",
  },
  superficial: {
    label: "Superficial",
    bg: "bg-warning-soft",
    border: "border-warning/30",
    text: "text-warning",
    dot: "bg-warning",
  },
  delegacion_pasiva: {
    label: "Delegación",
    bg: "bg-danger-soft",
    border: "border-danger/30",
    text: "text-danger",
    dot: "bg-danger",
  },
  sin_clasificar: {
    label: "Sin clasificar",
    bg: "bg-surface-alt",
    border: "border-border-soft",
    text: "text-muted",
    dot: "bg-border",
  },
}

function NuevaMedicionSection({
  stats,
  pending,
  totalEpisodes,
}: {
  stats: SubgruposStats | null
  pending: boolean
  totalEpisodes: number
}): ReactNode {
  return (
    <section className="rounded-lg border border-border-soft bg-surface p-4 space-y-4">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold uppercase text-muted">
          Nueva medición — 4 dimensiones / 8 subgrupos
        </h2>
        <span className="rounded-full bg-surface-alt border border-border-soft px-2 py-0.5 text-xs text-muted">
          modo sombra
        </span>
      </div>

      {pending && (
        <div className="rounded-lg bg-surface-alt border border-border-soft p-6 text-center">
          <p className="text-sm text-muted">
            Disponible próximamente — el endpoint de subgrupos está en implementación.
          </p>
        </div>
      )}

      {!pending && !stats && (
        <div className="rounded-lg bg-surface-alt border border-border-soft p-6 text-center">
          <p className="text-sm text-muted">Cargando subgrupos...</p>
        </div>
      )}

      {stats && (
        <>
          {/* Distribución por eje (roll-up) */}
          <EjeRollup subgrupos={stats.subgrupos} total={totalEpisodes} />

          {/* Subgrupos individuales */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {stats.subgrupos.map((sg) => (
              <SubgrupoCard key={sg.key} subgrupo={sg} total={totalEpisodes} />
            ))}
          </div>

          {/* 4 dimensiones */}
          <div className="rounded-lg bg-surface-alt border border-border-soft p-4 space-y-3">
            <p className="text-xs font-semibold uppercase text-muted">
              Promedios de las 4 dimensiones
            </p>
            <DimensionBar label="Autonomía" value={stats.avg_dimensiones.autonomia} />
            <DimensionBar label="Experimentación" value={stats.avg_dimensiones.experimentacion} />
            <DimensionBar label="Persistencia" value={stats.avg_dimensiones.persistencia} />
            <DimensionBar label="Foco" value={stats.avg_dimensiones.foco} />
          </div>
        </>
      )}
    </section>
  )
}

function EjeRollup({
  subgrupos,
  total,
}: {
  subgrupos: SubgrupoCount[]
  total: number
}): ReactNode {
  const ejeOrder: Eje[] = ["reflexiva", "superficial", "delegacion_pasiva", "sin_clasificar"]
  const ejeCount: Partial<Record<Eje, number>> = {}
  for (const sg of subgrupos) {
    ejeCount[sg.eje] = (ejeCount[sg.eje] ?? 0) + sg.count
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {ejeOrder.map((eje) => {
        const count = ejeCount[eje] ?? 0
        const pct = total > 0 ? Math.round((count / total) * 100) : 0
        const cfg = EJE_CONFIG[eje]
        return (
          <div key={eje} className={`rounded-lg border p-3 ${cfg.bg} ${cfg.border} ${cfg.text}`}>
            <div className="text-xs font-medium opacity-70">{cfg.label}</div>
            <div className="mt-1 flex items-baseline gap-1.5">
              <span className="text-2xl font-bold">{count}</span>
              <span className="text-xs opacity-60">{pct}%</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function SubgrupoCard({
  subgrupo,
  total,
}: {
  subgrupo: SubgrupoCount
  total: number
}): ReactNode {
  const pct = total > 0 ? Math.round((subgrupo.count / total) * 100) : 0
  const cfg = EJE_CONFIG[subgrupo.eje]

  return (
    <div className={`rounded-lg border p-3 ${cfg.bg} ${cfg.border}`}>
      <div className={`text-sm font-medium ${cfg.text}`}>{subgrupo.label}</div>
      <div className="mt-1.5 flex items-baseline gap-1.5">
        <span className={`text-xl font-bold ${cfg.text}`}>{subgrupo.count}</span>
        <span className="text-xs text-muted-soft">{pct}%</span>
      </div>
      <div className="mt-2 h-1 bg-white/40 rounded overflow-hidden">
        <div className={`h-full ${cfg.dot}`} style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-2 text-xs text-muted leading-tight">{subgrupo.accion_docente}</p>
    </div>
  )
}

function DimensionBar({ label, value }: { label: string; value: number | null }): ReactNode {
  if (value == null) {
    return (
      <div className="flex items-center gap-3">
        <span className="w-32 text-xs text-muted shrink-0">{label}</span>
        <span className="text-xs text-muted-soft">sin datos</span>
      </div>
    )
  }
  const pct = Math.round(value * 100)
  const color = pct > 60 ? "bg-success" : pct > 40 ? "bg-warning" : "bg-danger"
  return (
    <div className="flex items-center gap-3">
      <span className="w-32 text-xs text-muted shrink-0">{label}</span>
      <div className="flex-1 h-2 bg-surface rounded overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-10 text-right font-mono text-xs text-muted-soft">{pct}%</span>
    </div>
  )
}
