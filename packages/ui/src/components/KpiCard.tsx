import type { HTMLAttributes, ReactNode } from "react"
import { cn } from "../utils/cn"

/**
 * KpiCard — métrica con gravitas, no big-number-saas.
 *
 * Patrón doctoral: el valor numérico domina pero NO grita. Label uppercase
 * arriba, valor en mono (JetBrains) para cifras críticas, hint debajo para
 * el contexto que el comité doctoral espera ("n=7", "sufficient_data=true",
 * "p<0.05"). El delta es opcional y sigue tokens semánticos.
 *
 * Tonos:
 * - `tone="default"` — neutro, métrica de inventario.
 * - `tone="brand"` — métrica primaria de la vista (acento Stack Blue sutil).
 * - `tone="success" | "warning" | "danger"` — métrica con interpretación cargada.
 */
type Tone = "default" | "brand" | "success" | "warning" | "danger"

interface KpiCardProps extends HTMLAttributes<HTMLDivElement> {
  label: string
  value: ReactNode
  /** Pequeño contexto debajo del valor (ej. "n=7", "intra-cohorte"). */
  hint?: ReactNode
  /** Delta numérico/textual (ej. "+0.42", "↗ 12%"). */
  delta?: ReactNode
  /** Color del delta, independiente del tono general. */
  deltaTone?: "success" | "warning" | "danger" | "neutral"
  tone?: Tone
  /** Si true, el valor se renderiza en mono (JetBrains). Default true para cifras. */
  monospace?: boolean
}

const toneClasses: Record<Tone, string> = {
  default: "border-border bg-surface",
  brand: "border-accent-brand/30 bg-accent-brand-soft/40",
  success: "border-success/30 bg-success-soft/40",
  warning: "border-warning/30 bg-warning-soft/40",
  danger: "border-danger/30 bg-danger-soft/40",
}

const deltaToneClasses = {
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
  neutral: "text-muted",
}

export function KpiCard({
  label,
  value,
  hint,
  delta,
  deltaTone = "neutral",
  tone = "default",
  monospace = true,
  className,
  ...props
}: KpiCardProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1 rounded-lg border p-4",
        "shadow-[0_1px_2px_0_rgba(0,0,0,0.03)]",
        toneClasses[tone],
        className,
      )}
      {...props}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[10px] uppercase tracking-[0.08em] font-semibold text-muted">
          {label}
        </span>
        {delta && (
          <span
            className={cn(
              "text-xs font-medium leading-none",
              deltaToneClasses[deltaTone],
            )}
          >
            {delta}
          </span>
        )}
      </div>
      <div
        className={cn(
          "text-2xl leading-none font-semibold text-ink mt-1",
          monospace && "font-mono tracking-tight",
        )}
      >
        {value}
      </div>
      {hint && <span className="text-xs text-muted leading-relaxed mt-0.5">{hint}</span>}
    </div>
  )
}
