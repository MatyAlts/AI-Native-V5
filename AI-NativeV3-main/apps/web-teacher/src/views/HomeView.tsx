/**
 * Vista home del docente — rediseño v2 (layout dashboard 2026).
 *
 * Patrón:
 * - HERO con stats agregados (cifras grandes en mono + labels uppercase).
 * - GRID de cohortes con cards hover-lift, sparkline-mini y CTAs claros.
 * - SECCIÓN tools transversales como cards secundarias, no link list.
 *
 * Honestidad técnica:
 * - el endpoint /comisiones/mis devuelve solo IDs y código; los KPIs de
 *   progression/alertas/adversos se enriquecen en paralelo (best-effort).
 * - KPI "alertas" usa GET /api/v1/analytics/cohort/{id}/alerts-summary
 *   (ADR-022). Cohortes con N<5 estudiantes con slope computable → null
 *   (insufficient_data por k-anonymity, RN-131); UI muestra "—".
 */
import { HelpButton } from "@platform/ui"
import { Link } from "@tanstack/react-router"
import { Download, FileText, Scale, Users } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { ComisionDelDocenteCard, type ComisionKpis } from "../components/ComisionDelDocenteCard"
import { comisionLabel } from "../components/ComisionSelector"
import {
  type CohortAdversarialEvents,
  type CohortAlertsSummary,
  type CohortProgression,
  type Comision,
  comisionesApi,
  getCohortAdversarialEvents,
  getCohortAlertsSummary,
  getCohortProgression,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

interface Props {
  getToken: () => Promise<string | null>
}

const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000

function countLastWeek(events: { ts: string }[]): number {
  const cutoff = Date.now() - SEVEN_DAYS_MS
  return events.filter((e) => {
    const t = Date.parse(e.ts)
    return Number.isFinite(t) && t >= cutoff
  }).length
}

interface ComisionWithKpis {
  comision: Comision
  displayName: string
  kpis: ComisionKpis
}

export function HomeView({ getToken }: Props) {
  const [items, setItems] = useState<ComisionWithKpis[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { items: comisiones } = await comisionesApi.listMine(getToken)
      const enriched = await Promise.all(
        comisiones.map(async (c) => {
          const [prog, adv, alertsSummary] = await Promise.allSettled([
            getCohortProgression(c.id, getToken) as Promise<CohortProgression>,
            getCohortAdversarialEvents(c.id, getToken) as Promise<CohortAdversarialEvents>,
            getCohortAlertsSummary(c.id, undefined, getToken) as Promise<CohortAlertsSummary>,
          ])
          const alumnos = prog.status === "fulfilled" ? prog.value.n_students : null
          const episodiosSemana =
            prog.status === "fulfilled"
              ? prog.value.trajectories.reduce((a, t) => a + t.n_episodes, 0)
              : null
          const adversosSemana =
            adv.status === "fulfilled" ? countLastWeek(adv.value.recent_events) : null
          // ADR-022: KPI alertas = n estudiantes con al menos una alerta.
          // Si insufficient_data (N<5 k-anonymity) → null → UI muestra "—".
          const alertas: number | null =
            alertsSummary.status === "fulfilled" &&
            !alertsSummary.value.insufficient_data &&
            alertsSummary.value.alerts_summary
              ? alertsSummary.value.alerts_summary.students_with_any_alert
              : null
          const alertsBreakdown: CohortAlertsSummary | null =
            alertsSummary.status === "fulfilled" ? alertsSummary.value : null
          return {
            comision: c,
            displayName: comisionLabel(c),
            kpis: {
              alumnos,
              episodiosSemana,
              alertas,
              adversosSemana,
              ...(alertsBreakdown ? { alertsBreakdown } : {}),
            },
          }
        }),
      )
      setItems(enriched)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [getToken])

  useEffect(() => {
    void load()
  }, [load])

  const totalAlumnos = items?.reduce((s, e) => s + (e.kpis.alumnos ?? 0), 0) ?? null
  const totalEpisodios = items?.reduce((s, e) => s + (e.kpis.episodiosSemana ?? 0), 0) ?? null
  const totalAdversos = items?.reduce((s, e) => s + (e.kpis.adversosSemana ?? 0), 0) ?? null

  return (
    <div className="page-enter space-y-10 max-w-7xl mx-auto">
      {/* ═══ HERO ═════════════════════════════════════════════════════ */}
      <header className="flex items-start justify-between gap-6 animate-fade-in-down">
        <div className="flex flex-col gap-1.5 min-w-0">
          <span className="text-[11px] uppercase tracking-[0.12em] font-semibold text-muted">
            Panel docente · Periodo en curso
          </span>
          <h1 className="text-3xl font-semibold tracking-tight text-ink leading-none">
            Tus comisiones
          </h1>
          <p className="text-sm text-muted leading-relaxed mt-1.5 max-w-xl">
            Cohortes asignadas a vos. Cada tarjeta condensa el pulso de la semana — episodios,
            alumnos, intentos adversos detectados.
          </p>
        </div>
        <HelpButton title="Tus comisiones" content={helpContent.home} />
      </header>

      {/* ═══ STATS HERO PANEL ═════════════════════════════════════════ */}
      {items && items.length > 0 && !loading && (
        <section
          className="relative overflow-hidden rounded-2xl bg-surface border border-border p-6 sm:p-8 animate-fade-in-up animate-delay-100 shadow-[0_2px_8px_-2px_rgba(0,0,0,0.04)]"
          aria-label="Resumen agregado de tus comisiones"
        >
          {/* Banda vertical Stack Blue — firma identitaria */}
          <div
            aria-hidden="true"
            className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-accent-brand via-accent-brand to-accent-brand/40"
          />
          {/* Glow muy sutil */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -top-32 -right-32 w-72 h-72 rounded-full bg-accent-brand/5 blur-3xl"
          />

          <div className="relative grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-6">
            <HeroStat label="Comisiones" value={items.length} unit="activas" />
            <HeroStat label="Alumnos" value={totalAlumnos} unit="con actividad" />
            <HeroStat label="Episodios" value={totalEpisodios} unit="esta semana" />
            <HeroStat
              label="Adversos"
              value={totalAdversos}
              unit="esta semana"
              tone={totalAdversos !== null && totalAdversos > 0 ? "warning" : "neutral"}
            />
          </div>
        </section>
      )}

      {/* ═══ LOADING SKELETON ═════════════════════════════════════════ */}
      {loading && (
        <div className="space-y-6 animate-fade-in">
          <div className="skeleton h-32 rounded-2xl" />
          <div className="space-y-4">
            <div className="skeleton h-28 rounded-xl" />
            <div className="skeleton h-28 rounded-xl" />
            <div className="skeleton h-28 rounded-xl" />
          </div>
        </div>
      )}

      {/* ═══ ERROR STATE ══════════════════════════════════════════════ */}
      {error && (
        <div className="rounded-xl border border-danger/30 bg-danger-soft p-5 animate-fade-in-up">
          <div className="text-sm font-semibold text-danger">No pudimos cargar tus comisiones</div>
          <div className="mt-2 font-mono text-xs text-danger/80 break-all">{error}</div>
        </div>
      )}

      {/* ═══ EMPTY STATE ══════════════════════════════════════════════ */}
      {items && items.length === 0 && !loading && (
        <div className="rounded-2xl border border-dashed border-border bg-surface p-10 max-w-2xl mx-auto text-center animate-fade-in-up">
          <div className="inline-flex items-center justify-center rounded-full bg-surface-alt p-4 mb-4">
            <Users className="h-7 w-7 text-muted" />
          </div>
          <h2 className="text-lg font-semibold text-ink mb-2">
            Todavía no tenés comisiones asignadas
          </h2>
          <p className="text-sm text-muted leading-relaxed max-w-sm mx-auto">
            El admin de tu facultad debe agregarte vía bulk-import (ADR-029) o crear una comisión
            desde web-admin asignándote el rol docente.
          </p>
        </div>
      )}

      {/* ═══ GRID DE COHORTES ════════════════════════════════════════ */}
      {items && items.length > 0 && (
        <section aria-label="Lista de comisiones">
          <div className="flex items-baseline justify-between mb-4">
            <h2 className="text-[11px] uppercase tracking-[0.12em] font-semibold text-muted">
              Cohortes ({items.length})
            </h2>
          </div>
          <ul className="grid grid-cols-1 lg:grid-cols-2 gap-4" data-testid="comisiones-list">
            {items.map((entry, idx) => (
              <li
                key={entry.comision.id}
                className="animate-fade-in-up"
                style={{ animationDelay: `${150 + idx * 50}ms` }}
              >
                <ComisionDelDocenteCard
                  comision={entry.comision}
                  displayName={entry.displayName}
                  kpis={entry.kpis}
                />
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ═══ TOOLS TRANSVERSALES ═════════════════════════════════════ */}
      {items && items.length > 0 && (
        <section
          className="pt-2 animate-fade-in-up animate-delay-300"
          aria-label="Herramientas transversales"
        >
          <h2 className="text-[11px] uppercase tracking-[0.12em] font-semibold text-muted mb-4">
            Herramientas transversales
          </h2>
          <ul className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <ToolCard
              to="/templates"
              icon={<FileText className="h-4 w-4" />}
              title="Plantillas"
              description="Catálogo de TPs canónicos por materia"
            />
            <ToolCard
              to="/kappa"
              icon={<Scale className="h-4 w-4" />}
              title="Inter-rater κ"
              description="Acuerdo entre coders sobre clasificación N4"
            />
            <ToolCard
              to="/export"
              icon={<Download className="h-4 w-4" />}
              title="Exportar dataset"
              description="Datos académicos anonimizados (SHA-256+salt)"
            />
          </ul>
        </section>
      )}
    </div>
  )
}

/* ═══ Componentes locales ═══════════════════════════════════════════ */

function HeroStat({
  label,
  value,
  unit,
  tone = "neutral",
}: {
  label: string
  value: number | null
  unit: string
  tone?: "neutral" | "warning"
}) {
  const isWarn = tone === "warning" && value !== null && value > 0
  const valueColor = isWarn ? "text-warning" : "text-ink"
  const dotColor = isWarn ? "bg-warning" : "bg-muted-soft"
  return (
    <div className="flex flex-col gap-2 min-w-0">
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className={`inline-block w-2 h-2 rounded-full shrink-0 ${dotColor} ${isWarn ? "animate-pulse-soft" : ""}`}
        />
        <span className="text-[10px] uppercase tracking-[0.12em] font-semibold text-muted truncate">
          {label}
        </span>
      </div>
      <div className="flex items-baseline gap-2 flex-wrap">
        <span
          className={`font-mono text-4xl font-semibold tracking-tight leading-none ${valueColor}`}
        >
          {value !== null ? value : <span className="text-muted-soft text-2xl">—</span>}
        </span>
        <span className="text-xs text-muted">{unit}</span>
      </div>
    </div>
  )
}

function ToolCard({
  to,
  icon,
  title,
  description,
}: {
  to: string
  icon: React.ReactNode
  title: string
  description: string
}) {
  return (
    <li>
      <Link
        to={to}
        className="hover-lift press-shrink group flex items-start gap-3 rounded-xl border border-border bg-surface p-4 transition-colors hover:border-accent-brand/40"
      >
        <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-accent-brand-soft text-accent-brand-deep transition-colors group-hover:bg-accent-brand group-hover:text-white">
          {icon}
        </span>
        <div className="flex flex-col gap-0.5 min-w-0">
          <span className="text-sm font-medium text-ink leading-tight">{title}</span>
          <span className="text-xs text-muted leading-relaxed">{description}</span>
        </div>
      </Link>
    </li>
  )
}
