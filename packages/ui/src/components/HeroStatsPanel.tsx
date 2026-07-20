import type { ReactNode } from "react"
import { cn } from "../utils/cn"

/**
 * HeroStatsPanel — panel de stats agregados con fondo claro.
 *
 * Patrón doctoral 2026 (versión light): superficie clara con borde definido,
 * acento Stack Blue sutil (banda izquierda + glow opcional). Stats grandes
 * en mono.
 *
 * NO es "hero-metric" SaaS (PRODUCT.md anti-reference #3) — es un panel
 * resumen denso que el comité lee al primer vistazo.
 */

export type StatTone = "default" | "success" | "warning" | "danger"

export interface HeroStat {
  label: string
  value: ReactNode
  unit?: string
  tone?: StatTone
  pulse?: boolean
}

export interface HeroStatsPanelProps {
  eyebrow?: ReactNode
  icon?: ReactNode
  stats: HeroStat[]
  footnote?: ReactNode
  className?: string
}

const dotByTone: Record<StatTone, string> = {
  default: "bg-muted-soft",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
}

const valueColorByTone: Record<StatTone, string> = {
  default: "text-ink",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
}

const trackBgByTone: Record<StatTone, string> = {
  default: "bg-border-soft",
  success: "bg-success-soft",
  warning: "bg-warning-soft",
  danger: "bg-danger-soft",
}

export function HeroStatsPanel({
  eyebrow,
  icon,
  stats,
  footnote,
  className,
}: HeroStatsPanelProps) {
  const cols =
    stats.length <= 2
      ? "grid-cols-2"
      : stats.length === 3
        ? "grid-cols-3"
        : "grid-cols-2 md:grid-cols-4"
  return (
    <section
      className={cn(
        "relative overflow-hidden rounded-2xl bg-surface border border-border p-6 sm:p-8",
        "animate-fade-in-up animate-delay-100",
        "shadow-[0_2px_8px_-2px_rgba(0,0,0,0.04)]",
        className,
      )}
      aria-label={typeof eyebrow === "string" ? eyebrow : undefined}
    >
      {/* Banda vertical Stack Blue izquierda — firma identitaria */}
      <div
        aria-hidden="true"
        className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-accent-brand via-accent-brand to-accent-brand/40"
      />

      {/* Glow Stack Blue muy sutil en esquina (no satura) */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-32 -right-32 w-72 h-72 rounded-full bg-accent-brand/5 blur-3xl"
      />

      <div className="relative">
        {(eyebrow || icon) && (
          <div className="flex items-center gap-2 mb-5">
            {icon && <span className="text-accent-brand">{icon}</span>}
            {eyebrow && (
              <span className="text-[10px] uppercase tracking-[0.12em] font-semibold text-muted">
                {eyebrow}
              </span>
            )}
          </div>
        )}

        <ul className={cn("grid gap-x-6 gap-y-5", cols)}>
          {stats.map((s, i) => (
            <li key={`${s.label}-${i}`} className="flex flex-col gap-2 min-w-0">
              <div className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className={cn(
                    "inline-block w-2 h-2 rounded-full shrink-0",
                    dotByTone[s.tone ?? "default"],
                    s.pulse && "animate-pulse-soft",
                  )}
                />
                <span className="text-[10px] uppercase tracking-[0.12em] font-semibold text-muted truncate">
                  {s.label}
                </span>
              </div>
              <div className="flex items-baseline gap-2 flex-wrap">
                <span
                  className={cn(
                    "font-mono text-4xl font-semibold tracking-tight leading-none",
                    valueColorByTone[s.tone ?? "default"],
                  )}
                >
                  {s.value}
                </span>
                {s.unit && <span className="text-xs text-muted">{s.unit}</span>}
              </div>
              {/* Mini track decorativo según tone (visible solo si tone != default) */}
              {s.tone && s.tone !== "default" && (
                <div className={cn("h-0.5 rounded-full", trackBgByTone[s.tone])} />
              )}
            </li>
          ))}
        </ul>

        {footnote && (
          <p className="text-xs text-muted leading-relaxed mt-6 pt-4 border-t border-border-soft">
            {footnote}
          </p>
        )}
      </div>
    </section>
  )
}
