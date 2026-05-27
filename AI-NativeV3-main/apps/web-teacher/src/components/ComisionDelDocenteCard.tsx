/**
 * Card por comisión del docente — rediseño v2 (layout 2026).
 *
 * Patrón: card con hover-lift + jerarquía visual fuerte (kicker · headline ·
 * KPIs grid 2x2 con valores en mono · CTAs en footer). Acento vertical Stack
 * Blue en el borde izquierdo para identificar comisiones rápido al escanear.
 *
 * Honestidad técnica: cuando el cohort tiene N=0 episodios o N<3 estudiantes
 * con datos, los KPIs muestran "—" en color muted (PRODUCT.md auditabilidad).
 */
import { Link } from "@tanstack/react-router"
import { ArrowRight, ShieldAlert, Users } from "lucide-react"
import type { CohortAlertsSummary, Comision } from "../lib/api"

export interface ComisionKpis {
  alumnos: number | null
  episodiosSemana: number | null
  alertas: number | null
  adversosSemana: number | null
  // Breakdown opcional para tooltip del KPI alertas (ADR-022). Cuando es
  // `insufficient_data=true` la card muestra "—" + tooltip explicando
  // k-anonymity. Cuando hay data, tooltip lista counts por tipo.
  alertsBreakdown?: CohortAlertsSummary
}

export interface ComisionDelDocenteCardProps {
  comision: Comision
  displayName: string
  kpis: ComisionKpis
}

export function ComisionDelDocenteCard({
  comision,
  displayName,
  kpis,
}: ComisionDelDocenteCardProps) {
  const horarioStr = (() => {
    const horario = comision.horario as Record<string, unknown>
    if (typeof horario?.resumen === "string") return horario.resumen
    return null
  })()

  const hasAdversos = kpis.adversosSemana !== null && kpis.adversosSemana > 0
  const hasActividad = kpis.episodiosSemana !== null && kpis.episodiosSemana > 0

  return (
    <article
      data-testid="comision-card"
      data-comision-id={comision.id}
      className="hover-lift group relative overflow-hidden rounded-xl border border-border bg-surface flex flex-col h-full"
    >
      {/* Acento vertical brand a la izquierda */}
      <div
        aria-hidden="true"
        className="absolute left-0 top-0 bottom-0 w-1 bg-accent-brand/0 group-hover:bg-accent-brand transition-colors duration-200"
      />

      <div className="p-5 flex-1">
        {/* ═══ Kicker ═══ */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <span
              className="font-mono text-[11px] uppercase tracking-wider text-muted px-2 py-0.5 rounded bg-surface-alt border border-border-soft"
              data-testid="comision-card-kicker"
            >
              {comision.codigo}
            </span>
            {horarioStr && <span className="text-[11px] text-muted truncate">{horarioStr}</span>}
          </div>
          {(comision as { invite_code?: string }).invite_code && (
            <span
              className="font-mono text-xs font-semibold text-accent-brand bg-accent-brand/10 px-2 py-1 rounded border border-accent-brand/20"
              title="Codigo de invitacion para alumnos"
            >
              {(comision as { invite_code?: string }).invite_code}
            </span>
          )}
          {/* Indicador de estado (puntito) */}
          <span
            className={`inline-flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide ${hasActividad ? "text-success" : "text-muted-soft"}`}
            title={hasActividad ? "Actividad esta semana" : "Sin actividad reciente"}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${hasActividad ? "bg-success animate-pulse-soft" : "bg-muted-soft"}`}
            />
            {hasActividad ? "activa" : "sin act."}
          </span>
        </div>

        {/* ═══ Headline ═══ */}
        <h3 className="text-[17px] font-semibold text-ink leading-tight tracking-tight mb-4">
          {displayName}
        </h3>

        {/* ═══ KPIs grid 2x2 ═══ */}
        <dl className="grid grid-cols-4 gap-3 mb-1" data-testid="comision-card-kpis">
          <KpiCell value={kpis.alumnos} label="alumnos" tone="default" />
          <KpiCell value={kpis.episodiosSemana} label="episodios" sublabel="sem." tone="default" />
          <KpiCell
            value={kpis.alertas}
            label="alertas"
            tone={kpis.alertas !== null && kpis.alertas > 0 ? "warning" : "default"}
            {...(() => {
              const t = buildAlertsTooltip(kpis.alertsBreakdown)
              return t ? { title: t } : {}
            })()}
            testId="comision-card-kpi-alertas"
          />
          <KpiCell
            value={kpis.adversosSemana}
            label="adversos"
            sublabel="sem."
            tone={hasAdversos ? "danger" : "default"}
          />
        </dl>
      </div>

      {/* ═══ Footer con CTAs ═══ */}
      <footer className="flex items-stretch border-t border-border-soft">
        <Link
          to="/progression"
          search={{ comisionId: comision.id }}
          data-testid="comision-card-cohort-link"
          className="press-shrink flex-1 inline-flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium text-ink hover:bg-accent-brand-soft hover:text-accent-brand-deep transition-colors"
        >
          <Users className="h-4 w-4" />
          Ver cohorte
          <ArrowRight className="h-3.5 w-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
        </Link>
        <Link
          to="/cohort-adversarial"
          search={{ comisionId: comision.id }}
          className={`press-shrink inline-flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium border-l border-border-soft transition-colors ${
            hasAdversos
              ? "text-warning hover:bg-warning-soft"
              : "text-muted hover:bg-surface-alt hover:text-ink"
          }`}
          title={hasAdversos ? "Hay intentos adversos esta semana" : "Adversarial events"}
        >
          <ShieldAlert className="h-4 w-4" />
          {hasAdversos && <span className="font-mono font-semibold">{kpis.adversosSemana}</span>}
        </Link>
      </footer>
    </article>
  )
}

/* ═══ KpiCell — celda compacta con jerarquía visual ═══════════════════ */
function KpiCell({
  value,
  label,
  sublabel,
  tone = "default",
  title,
  testId,
}: {
  value: number | null
  label: string
  sublabel?: string
  tone?: "default" | "warning" | "danger"
  title?: string
  testId?: string
}) {
  const valueColor =
    value === null
      ? "text-muted-soft"
      : tone === "danger" && value > 0
        ? "text-danger"
        : tone === "warning" && value > 0
          ? "text-warning"
          : "text-ink"

  return (
    <div
      className="flex flex-col gap-0.5 min-w-0"
      {...(title ? { title } : {})}
      {...(testId ? { "data-testid": testId } : {})}
    >
      <span className={`font-mono text-xl font-semibold leading-none tracking-tight ${valueColor}`}>
        {value !== null ? value : "—"}
      </span>
      <span className="text-[10px] uppercase tracking-wider text-muted truncate">
        {label}
        {sublabel && <span className="text-muted-soft"> {sublabel}</span>}
      </span>
    </div>
  )
}

/**
 * Construye el tooltip del KPI alertas (ADR-022, k-anonymity RN-131).
 *
 * - sin breakdown disponible → undefined (no se renderiza title).
 * - insufficient_data → mensaje k-anonymity.
 * - con data → breakdown por tipo de alerta para diagnostico rapido.
 */
function buildAlertsTooltip(breakdown?: CohortAlertsSummary): string | undefined {
  if (!breakdown) return undefined
  if (breakdown.insufficient_data) {
    return `Cohorte con N<${breakdown.min_students_threshold} estudiantes con datos longitudinales (k-anonymity).`
  }
  const s = breakdown.alerts_summary
  if (!s) return undefined
  return (
    `${s.students_with_any_alert} estudiantes con alguna alerta · ` +
    `regresion vs cohorte: ${s.regresion_vs_cohorte} · ` +
    `cuartil inferior: ${s.bottom_quartile} · ` +
    `slope negativo: ${s.slope_negativo_significativo}`
  )
}
