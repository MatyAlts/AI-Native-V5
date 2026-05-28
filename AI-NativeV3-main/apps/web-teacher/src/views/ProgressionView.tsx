import { HelpButton, StateMessage } from "@platform/ui"
import { Link } from "@tanstack/react-router"
import { ChevronDown, ChevronRight, TrendingUp, TriangleAlert } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { useComisionLabel } from "../components/ComisionSelector"
import { useViewMode } from "../hooks/useViewMode"
import {
  type CIIEvolutionUnidad,
  type CohortProgression,
  type EntregaDocente,
  type StudentTrajectory,
  type Unidad,
  getCohortProgression,
  getStudentCIIEvolution,
  listEntregas,
  listUnidades,
} from "../lib/api"
import {
  APPROPRIATION_DOCENTE,
  APPROPRIATION_REIFICATION_DISCLAIMER,
  PROGRESSION_DOCENTE,
  studentShortLabel,
} from "../utils/docenteLabels"
import { helpContent } from "../utils/helpContent"
import { useStudentProfiles } from "../hooks/useStudentProfiles"

const LABEL_COLOR_VAR: Record<string, string> = {
  delegacion_pasiva: "var(--color-appropriation-delegacion)",
  apropiacion_superficial: "var(--color-appropriation-superficial)",
  apropiacion_reflexiva: "var(--color-appropriation-reflexiva)",
}

interface Props {
  comisionId: string
  getToken: () => Promise<string | null>
}

/** Estadisticas de entregas por student_pseudonym. */
type EntregaStatsMap = Record<
  string,
  { pendientes: number; corregidas: number; nota_promedio: number | null }
>

export function ProgressionView({ comisionId, getToken }: Props) {
  const comisionLabelText = useComisionLabel(comisionId)
  const [data, setData] = useState<CohortProgression | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [entregaStats, setEntregaStats] = useState<EntregaStatsMap>({})
  const [unidades, setUnidades] = useState<Unidad[]>([])
  const [viewMode] = useViewMode()
  const isDocente = viewMode === "docente"
  const profilesMap = useStudentProfiles(comisionId, getToken)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getCohortProgression(comisionId, getToken)
      .then(setData)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [comisionId, getToken])

  // Fetch unidades best-effort para mostrar desglose por unidad
  useEffect(() => {
    if (!comisionId) return
    let cancelled = false
    listUnidades(comisionId, getToken)
      .then((u) => {
        if (!cancelled) setUnidades(u)
      })
      .catch(() => {
        /* best-effort */
      })
    return () => {
      cancelled = true
    }
  }, [comisionId, getToken])

  // Fetch entrega stats best-effort para enriquecer la tabla
  useEffect(() => {
    if (!comisionId) return
    let cancelled = false
    listEntregas({ comision_id: comisionId, limit: 200 }, getToken)
      .then((resp) => {
        if (cancelled) return
        const map: EntregaStatsMap = {}
        const entregas: EntregaDocente[] = resp.data
        for (const e of entregas) {
          const s = map[e.student_pseudonym] ?? {
            pendientes: 0,
            corregidas: 0,
            nota_promedio: null,
          }
          if (e.estado === "submitted") s.pendientes++
          if (e.estado === "graded" || e.estado === "returned") s.corregidas++
          map[e.student_pseudonym] = s
        }
        setEntregaStats(map)
      })
      .catch(() => {
        // Best-effort — si falla, no mostramos stats de entregas
      })
    return () => {
      cancelled = true
    }
  }, [comisionId, getToken])

  if (loading) {
    return (
      <div className="page-enter space-y-8 max-w-7xl mx-auto">
        <div className="space-y-3">
          <div className="skeleton h-3 w-32 rounded" />
          <div className="skeleton h-9 w-64 rounded" />
          <div className="skeleton h-4 w-96 rounded" />
        </div>
        <div className="skeleton h-32 rounded-2xl" />
        <div className="skeleton h-20 rounded-xl" />
        <div className="skeleton h-96 rounded-xl" />
      </div>
    )
  }
  if (error) {
    return (
      <div className="page-enter max-w-7xl mx-auto p-8">
        <StateMessage variant="error" title="No se pudo cargar la progresion" description={error} />
      </div>
    )
  }
  if (!data) return null

  const subtitle = isDocente
    ? `${data.n_students} alumnos · ordenados por quienes necesitan más atención primero`
    : `${data.n_students} estudiantes · ${data.n_students_with_enough_data} con datos suficientes (≥3 episodios)`

  return (
    <div className="page-enter space-y-8 max-w-7xl mx-auto">
      {/* ═══ HEADER ═════════════════════════════════════════════════════ */}
      <header className="flex items-start justify-between gap-6 animate-fade-in-down">
        <div className="flex flex-col gap-1.5 min-w-0">
          <nav className="text-[11px] uppercase tracking-[0.12em] font-semibold text-muted flex items-center gap-2 flex-wrap">
            <Link to="/" className="hover:text-ink transition-colors">
              Inicio
            </Link>
            <span aria-hidden="true" className="text-border-strong">
              /
            </span>
            <span className="text-ink">{comisionLabelText}</span>
          </nav>
          <h1 className="text-3xl font-semibold tracking-tight text-ink leading-none">
            {isDocente ? "Cómo van mis alumnos" : "Progresión longitudinal"}
          </h1>
          <p className="text-sm text-muted leading-relaxed mt-1.5 max-w-2xl">{subtitle}</p>
          {!isDocente && (
            <p
              className="text-[11px] text-muted leading-relaxed mt-2 max-w-2xl italic"
              data-testid="appropriation-reification-disclaimer"
            >
              {APPROPRIATION_REIFICATION_DISCLAIMER}
            </p>
          )}
        </div>
        <HelpButton title="Progresión" content={helpContent.progression} />
      </header>

      {/* ═══ HERO PANEL — 4 stats agregadas ═════════════════════════════ */}
      <SummaryStrip data={data} isDocente={isDocente} />

      {/* ═══ Net progression bar ═══ */}
      <NetProgressionBar ratio={data.net_progression_ratio} isDocente={isDocente} />

      {/* ═══ Action insight (alumnos en riesgo) ═══ */}
      {isDocente && data.empeorando > 0 && <ActionInsight count={data.empeorando} />}

      {/* ═══ Tabla de trayectorias por alumno ═══ */}
      <TrajectoriesSection
        trajectories={data.trajectories}
        comisionId={comisionId}
        isDocente={isDocente}
        entregaStats={entregaStats}
        unidades={unidades}
        getToken={getToken}
        profilesMap={profilesMap}
      />
    </div>
  )
}

function ActionInsight({ count }: { count: number }) {
  return (
    <div
      role="alert"
      className="animate-fade-in-up rounded-xl border border-warning/30 bg-gradient-to-r from-warning-soft to-warning-soft/40 px-5 py-4 flex items-start gap-3"
    >
      <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-warning/15 text-warning">
        <TriangleAlert className="h-5 w-5" aria-hidden="true" />
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-warning">
          {count} alumno{count !== 1 ? "s" : ""} en riesgo
        </div>
        <p className="text-sm text-warning/85 leading-relaxed mt-0.5">
          Considerá revisar sus últimos trabajos y acercarte a conversar con ellos.
        </p>
      </div>
    </div>
  )
}

function SummaryStrip({ data, isDocente }: { data: CohortProgression; isDocente: boolean }) {
  type Item = {
    label: string
    value: number
    dot: string
    isHighlight?: boolean
  }
  const items: Item[] = [
    {
      label: "Mejorando",
      value: data.mejorando,
      dot: "var(--color-success)",
    },
    {
      label: "Estable",
      value: data.estable,
      dot: "var(--color-neutral)",
    },
    {
      label: "En riesgo",
      value: data.empeorando,
      dot: "var(--color-danger)",
      isHighlight: data.empeorando > 0,
    },
    {
      label: "Sin datos",
      value: data.insuficiente,
      dot: "var(--color-border-strong)",
    },
  ]
  const total = data.n_students || 1
  return (
    <section
      data-testid="progression-summary-strip"
      className="relative overflow-hidden rounded-2xl bg-surface border border-border p-6 sm:p-8 animate-fade-in-up animate-delay-100 shadow-[0_2px_8px_-2px_rgba(0,0,0,0.04)]"
      aria-label="Resumen de progresión de la cohorte"
    >
      {/* Banda vertical Stack Blue */}
      <div
        aria-hidden="true"
        className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-accent-brand via-accent-brand to-accent-brand/40"
      />
      {/* Glow muy sutil */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-32 -right-32 w-72 h-72 rounded-full bg-accent-brand/5 blur-3xl"
      />

      <div className="relative">
        <div className="flex items-center gap-2 mb-5">
          <TrendingUp className="h-4 w-4 text-accent-brand" />
          <span className="text-[10px] uppercase tracking-[0.12em] font-semibold text-muted">
            {isDocente ? "Distribución de la cohorte" : "Distribución de trayectorias"}
          </span>
        </div>
        <ul className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-5">
          {items.map((it) => {
            const pct = total > 0 ? (it.value / total) * 100 : 0
            return (
              <li key={it.label} className="flex flex-col gap-2 min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className={`inline-block w-2 h-2 rounded-full shrink-0 ${it.isHighlight ? "animate-pulse-soft" : ""}`}
                    style={{ backgroundColor: it.dot }}
                  />
                  <span className="text-[10px] uppercase tracking-[0.12em] font-semibold text-muted">
                    {it.label}
                  </span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-4xl font-semibold tracking-tight leading-none text-ink">
                    {it.value}
                  </span>
                  <span className="text-xs font-mono text-muted">{pct.toFixed(0)}%</span>
                </div>
                {/* Mini bar */}
                <div className="h-1 rounded-full bg-border-soft overflow-hidden">
                  <div
                    className="h-full rounded-full transition-[width] duration-700 ease-out"
                    style={{
                      width: `${pct}%`,
                      backgroundColor: it.dot,
                    }}
                  />
                </div>
              </li>
            )
          })}
        </ul>
      </div>
    </section>
  )
}

function NetProgressionBar({ ratio, isDocente }: { ratio: number; isDocente: boolean }) {
  const pct = Math.abs(ratio) * 100
  const isPositive = ratio > 0.1
  const isNegative = ratio < -0.1
  const tone = isPositive ? "success" : isNegative ? "danger" : "neutral"
  const barColor =
    tone === "success"
      ? "var(--color-success)"
      : tone === "danger"
        ? "var(--color-danger)"
        : "var(--color-border-strong)"
  const labelColor =
    tone === "success" ? "text-success" : tone === "danger" ? "text-danger" : "text-muted"

  const plainLabel = isPositive
    ? "La mayoría de tus alumnos está mejorando"
    : isNegative
      ? "La mayoría de tus alumnos está empeorando"
      : "La cohorte se mantiene estable"

  return (
    <section
      className="rounded-xl border border-border bg-surface px-6 py-5 animate-fade-in-up animate-delay-150"
      aria-label={isDocente ? "Balance general de la cohorte" : "Net progression"}
    >
      <div className="flex items-center justify-between mb-4 gap-4 flex-wrap">
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] uppercase tracking-[0.12em] font-semibold text-muted">
            {isDocente ? "Balance general" : "Net progression"}
          </span>
          <span className={`text-sm font-medium ${labelColor}`}>{plainLabel}</span>
        </div>
        {!isDocente && (
          <span
            className={`font-mono text-3xl font-semibold tracking-tight leading-none ${labelColor}`}
          >
            {ratio > 0 ? "+" : ""}
            {ratio.toFixed(3)}
          </span>
        )}
      </div>

      {/* Barra centrada con divider en 0 */}
      <div className="relative h-2 bg-surface-alt rounded-full overflow-hidden">
        <div
          aria-hidden="true"
          className="absolute left-1/2 top-0 h-full w-px bg-border-strong z-10"
        />
        <div
          className="absolute top-0 h-full rounded-full transition-[left,width] duration-700 ease-out"
          style={{
            left: ratio >= 0 ? "50%" : `${50 - pct / 2}%`,
            width: `${pct / 2}%`,
            backgroundColor: barColor,
          }}
        />
      </div>

      {!isDocente && (
        <p className="text-xs text-muted mt-3 leading-relaxed">
          <span className="font-mono">(mejorando − empeorando) / estudiantes con datos</span> ·
          Rango [−1, +1]
        </p>
      )}
    </section>
  )
}

function TrajectoriesSection({
  trajectories,
  comisionId,
  isDocente,
  entregaStats,
  unidades,
  getToken,
  profilesMap,
}: {
  trajectories: StudentTrajectory[]
  comisionId: string
  isDocente: boolean
  entregaStats: EntregaStatsMap
  unidades: Unidad[]
  getToken: () => Promise<string | null>
  profilesMap: Map<string, string>
}) {
  if (trajectories.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-white p-8 text-center text-muted">
        {isDocente
          ? "Todavia no hay datos de tus alumnos. Aparecerán cuando completen trabajos practicos."
          : "No hay trayectorias registradas en esta cohorte aun."}
      </div>
    )
  }

  const sorted = [...trajectories].sort((a, b) => {
    const riskOrder: Record<string, number> = {
      empeorando: 0,
      estable: 1,
      insuficiente: 2,
      mejorando: 3,
    }
    return (riskOrder[a.progression_label] ?? 2) - (riskOrder[b.progression_label] ?? 2)
  })

  return (
    <div className="rounded-xl border border-border bg-white overflow-hidden">
      <div className="border-b border-border px-6 py-3">
        <h2 className="text-sm font-semibold text-ink">
          {isDocente ? "Detalle por alumno" : "Trayectorias individuales"}
        </h2>
        <p className="text-xs text-muted">
          {isDocente
            ? "ordenados por quienes necesitan mas atencion primero"
            : "ordenadas por riesgo (en riesgo primero)"}
        </p>
      </div>
      {isDocente && (
        <div className="px-6 py-2 border-b border-border bg-canvas flex items-center gap-4 text-xs text-muted">
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block w-2 h-2 rounded-full"
              style={{ backgroundColor: "var(--color-appropriation-reflexiva)" }}
            />
            Autonomo
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block w-2 h-2 rounded-full"
              style={{ backgroundColor: "var(--color-appropriation-superficial)" }}
            />
            Superficial
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block w-2 h-2 rounded-full"
              style={{ backgroundColor: "var(--color-appropriation-delegacion)" }}
            />
            Depende de la IA
          </span>
        </div>
      )}
      {isDocente && Object.keys(entregaStats).length > 0 && (
        <div className="px-6 py-2 border-b border-border bg-canvas text-xs text-muted flex items-center gap-4">
          <span className="font-mono">Pendientes = entregas esperando correccion</span>
        </div>
      )}
      <ul className="divide-y divide-[#EAEAEA]">
        {sorted.map((t) => {
          const stat = entregaStats[t.student_pseudonym]
          return (
            <TrajectoryRow
              key={t.student_pseudonym}
              trajectory={t}
              comisionId={comisionId}
              isDocente={isDocente}
              unidades={unidades}
              getToken={getToken}
              profilesMap={profilesMap}
              {...(stat !== undefined ? { entregaStat: stat } : {})}
            />
          )
        })}
      </ul>
    </div>
  )
}

function TrajectoryRow({
  trajectory,
  comisionId,
  isDocente,
  entregaStat,
  unidades,
  getToken,
  profilesMap,
}: {
  trajectory: StudentTrajectory
  comisionId: string
  isDocente: boolean
  entregaStat?: { pendientes: number; corregidas: number; nota_promedio: number | null }
  unidades: Unidad[]
  getToken: () => Promise<string | null>
  profilesMap: Map<string, string>
}) {
  const [unidadExpanded, setUnidadExpanded] = useState(false)
  const [unidadData, setUnidadData] = useState<CIIEvolutionUnidad[] | null>(null)
  const [unidadLoading, setUnidadLoading] = useState(false)

  const fetchUnidadEvolucion = useCallback(() => {
    if (unidadData !== null || unidadLoading) return
    setUnidadLoading(true)
    getStudentCIIEvolution(trajectory.student_pseudonym, comisionId, getToken)
      .then((evo) => {
        setUnidadData(evo.evolution_per_unidad)
      })
      .catch(() => setUnidadData([]))
      .finally(() => setUnidadLoading(false))
  }, [trajectory.student_pseudonym, comisionId, getToken, unidadData, unidadLoading])

  function handleToggleUnidad(e: React.MouseEvent) {
    e.preventDefault()
    e.stopPropagation()
    if (!unidadExpanded) fetchUnidadEvolucion()
    setUnidadExpanded((v) => !v)
  }

  const progressionBg: Record<string, string> = {
    mejorando: "bg-green-50 text-green-800",
    estable: "bg-canvas text-muted",
    empeorando: "bg-danger-soft text-danger",
    insuficiente: "bg-canvas text-muted",
  }
  const badgeClass = progressionBg[trajectory.progression_label] ?? "bg-canvas text-muted"
  const label = isDocente
    ? (PROGRESSION_DOCENTE[trajectory.progression_label] ?? trajectory.progression_label)
    : trajectory.progression_label

  // Solo mostrar el expand de unidades si hay unidades en esta comision
  const hasUnidades = unidades.length > 0

  return (
    <li>
      <Link
        data-testid="student-row"
        to="/student-longitudinal"
        search={{ comisionId, studentId: trajectory.student_pseudonym }}
        className="flex items-center gap-4 px-6 py-3 hover:bg-canvas transition-colors"
      >
        <div className="w-40 shrink-0">
          <div className="font-mono text-xs font-medium text-ink">
            {isDocente
              ? studentShortLabel(trajectory.student_pseudonym, profilesMap)
              : trajectory.student_pseudonym.slice(0, 12)}
          </div>
          {!isDocente && <div className="text-xs text-muted">{trajectory.n_episodes} ep.</div>}
          {isDocente && (
            <div className="text-xs text-muted">
              {trajectory.n_episodes} trabajo{trajectory.n_episodes !== 1 ? "s" : ""}
            </div>
          )}
        </div>
        <div className="flex-1 flex items-center gap-1">
          <TrajectoryDots points={trajectory.points} isDocente={isDocente} />
        </div>
        {/* Entrega stats — solo si hay datos y el usuario es docente */}
        {isDocente && entregaStat && (
          <div className="shrink-0 flex items-center gap-2 text-xs font-mono">
            {entregaStat.pendientes > 0 && (
              <span
                data-testid="entrega-pendiente-badge"
                className="px-1.5 py-0.5 rounded bg-accent-brand-soft text-accent-brand-deep"
                title="Entregas pendientes de correccion"
              >
                {entregaStat.pendientes}p
              </span>
            )}
            {entregaStat.corregidas > 0 && (
              <span
                data-testid="entrega-corregida-badge"
                className="px-1.5 py-0.5 rounded bg-green-50 text-green-700"
                title="Entregas corregidas"
              >
                {entregaStat.corregidas}c
              </span>
            )}
          </div>
        )}
        <span className={`shrink-0 px-2.5 py-1 rounded-full text-xs font-medium ${badgeClass}`}>
          {label}
        </span>
        {hasUnidades && (
          <button
            type="button"
            onClick={handleToggleUnidad}
            className="shrink-0 p-1 rounded text-muted hover:text-ink hover:bg-border transition-colors"
            title={unidadExpanded ? "Ocultar desglose por unidad" : "Ver desglose por unidad"}
            aria-label={unidadExpanded ? "Ocultar desglose por unidad" : "Ver desglose por unidad"}
          >
            {unidadExpanded ? (
              <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
            )}
          </button>
        )}
        {!hasUnidades && (
          <span aria-hidden="true" className="text-border shrink-0">
            ›
          </span>
        )}
      </Link>

      {/* Desglose por unidad — expandible */}
      {hasUnidades && unidadExpanded && (
        <div className="border-t border-border px-6 py-3 bg-canvas">
          {unidadLoading && (
            <span className="text-xs text-muted">Cargando evolucion por unidad...</span>
          )}
          {!unidadLoading && unidadData !== null && unidadData.length === 0 && (
            <span className="text-xs text-muted">
              {isDocente
                ? "El alumno no tiene episodios en unidades todavia."
                : "Sin episodios clasificados en unidades para este estudiante."}
            </span>
          )}
          {!unidadLoading && unidadData !== null && unidadData.length > 0 && (
            <UnidadBreakdown entries={unidadData} isDocente={isDocente} />
          )}
        </div>
      )}
    </li>
  )
}

// ── UnidadBreakdown ────────────────────────────────────────────────────
// Desglose por unidad expandido en el row de un estudiante.

const SLOPE_ARROW: Record<string, string> = {
  mejorando: "↑",
  estable: "→",
  empeorando: "↓",
  insuficiente: "?",
}
const SLOPE_COLOR: Record<string, string> = {
  mejorando: "text-[var(--color-success)]",
  estable: "text-muted",
  empeorando: "text-[var(--color-danger)]",
  insuficiente: "text-border",
}

function slopeToTrend(
  slope: number | null,
): "mejorando" | "estable" | "empeorando" | "insuficiente" {
  if (slope === null) return "insuficiente"
  if (slope > 0.1) return "mejorando"
  if (slope < -0.1) return "empeorando"
  return "estable"
}

function UnidadBreakdown({
  entries,
  isDocente,
}: {
  entries: CIIEvolutionUnidad[]
  isDocente: boolean
}) {
  return (
    <div className="space-y-1">
      <div className="text-xs font-semibold text-muted uppercase tracking-wide mb-2">
        {isDocente ? "Por tema" : "Evolucion por unidad"}
      </div>
      <div className="flex flex-wrap gap-2">
        {entries.map((entry) => {
          const trend = slopeToTrend(entry.insufficient_data ? null : entry.slope)
          const arrow = SLOPE_ARROW[trend] ?? "?"
          const color = SLOPE_COLOR[trend] ?? "text-muted"
          const isSinUnidad = entry.unidad_id === "sin_unidad"
          return (
            <div
              key={entry.unidad_id}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-white px-2.5 py-1.5 text-xs"
              title={entry.insufficient_data ? "Datos insuficientes (min. 3 episodios)" : undefined}
            >
              <span className={`font-semibold shrink-0 ${color}`}>{arrow}</span>
              <span className={isSinUnidad ? "text-muted italic" : "text-ink"}>
                {entry.unidad_nombre}
              </span>
              <span className="text-muted">{entry.n_episodes}ep</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function TrajectoryDots({
  points,
  isDocente,
}: {
  points: Array<{ appropriation: string; classified_at: string; episode_id: string }>
  isDocente: boolean
}) {
  if (points.length === 0) {
    return <span className="text-xs text-muted">Sin clasificaciones</span>
  }

  return (
    <div className="flex items-center gap-1 flex-wrap">
      {points.map((p) => (
        <span
          key={p.episode_id}
          className="inline-block w-3 h-3 rounded-full shrink-0"
          style={{
            backgroundColor: LABEL_COLOR_VAR[p.appropriation] ?? "var(--color-level-meta)",
          }}
          title={
            isDocente
              ? `${new Date(p.classified_at).toLocaleDateString("es-AR")} · ${APPROPRIATION_DOCENTE[p.appropriation] ?? p.appropriation}`
              : `${new Date(p.classified_at).toLocaleDateString()} · ${p.appropriation}`
          }
          aria-label={
            isDocente
              ? (APPROPRIATION_DOCENTE[p.appropriation] ?? p.appropriation)
              : p.appropriation
          }
        />
      ))}
    </div>
  )
}
