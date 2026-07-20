import type { HTMLAttributes } from "react"
import { cn } from "../utils/cn"

/**
 * TrendBadge — indicador direccional ↗↘→ con tokens semánticos.
 *
 * Uso típico: slope longitudinal (StudentLongitudinalView), evolución entre
 * unidades, delta inter-cohorte. La decisión de tono NO es automática del
 * número (un slope negativo en accuracy puede ser bueno, un slope positivo
 * en latency puede ser malo) — el caller decide el tone semánticamente.
 *
 * Color blindness safe: forma (↗↘→) + label opcional, no solo color.
 */
type Direction = "up" | "down" | "flat"
type Tone = "success" | "warning" | "danger" | "neutral"

interface TrendBadgeProps extends HTMLAttributes<HTMLSpanElement> {
  direction: Direction
  tone?: Tone
  /** Texto al lado del arrow — típicamente el delta numérico ("+0.42", "−0.18"). */
  label?: string
  size?: "sm" | "md"
}

const arrows: Record<Direction, string> = {
  up: "↗",
  down: "↘",
  flat: "→",
}

const toneClasses: Record<Tone, string> = {
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
  neutral: "text-muted",
}

const sizeClasses = {
  sm: "text-xs gap-1",
  md: "text-sm gap-1.5",
}

export function TrendBadge({
  direction,
  tone = "neutral",
  label,
  size = "sm",
  className,
  ...props
}: TrendBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center font-medium leading-none",
        toneClasses[tone],
        sizeClasses[size],
        className,
      )}
      aria-label={`Tendencia ${direction}${label ? ` ${label}` : ""}`}
      {...props}
    >
      <span aria-hidden="true">{arrows[direction]}</span>
      {label && <span>{label}</span>}
    </span>
  )
}
