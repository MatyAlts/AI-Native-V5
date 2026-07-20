import type { HTMLAttributes } from "react"
import { cn } from "../utils/cn"

/**
 * Badge — paleta v2 con vocabulario semántico extendido.
 *
 * Variants semánticas (severidad/estado): default, success, warning, danger, info.
 * Variants pedagógicas (modelo N4): n1, n2, n3, n4 — para etiquetar episodios,
 *   eventos del CTR, slopes longitudinales con el vocabulario de la tesis.
 *
 * Variant `n2` cohesiona visualmente con `info` y con el acento brand (Stack
 * Blue): "lectura activa" comparte el hue 245 con la columna del sistema.
 */
type Variant =
  | "default"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "n1"
  | "n2"
  | "n3"
  | "n4"

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: Variant
}

const variants: Record<Variant, string> = {
  default: "bg-surface-alt text-body border border-border",
  success: "bg-success-soft text-success border border-success/30",
  warning: "bg-warning-soft text-warning border border-warning/30",
  danger: "bg-danger-soft text-danger border border-danger/30",
  info: "bg-accent-brand-soft text-accent-brand-deep border border-accent-brand/30",
  n1: "bg-level-n1/10 text-level-n1 border border-level-n1/30",
  n2: "bg-level-n2/10 text-level-n2 border border-level-n2/30",
  n3: "bg-level-n3/10 text-level-n3 border border-level-n3/30",
  n4: "bg-level-n4/10 text-level-n4 border border-level-n4/30",
}

export function Badge({ variant = "default", className, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium tracking-wide leading-none",
        variants[variant],
        className,
      )}
      {...props}
    />
  )
}
