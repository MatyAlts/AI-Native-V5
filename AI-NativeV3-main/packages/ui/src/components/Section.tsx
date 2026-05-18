import type { HTMLAttributes, ReactNode } from "react"
import { cn } from "../utils/cn"

/**
 * Section — contenedor tipográfico para bloques de contenido en vistas analíticas.
 *
 * Patrón densidad académica: title compacto + eyebrow opcional (label suprior tipo
 * "TRAZABILIDAD LONGITUDINAL") + description corta + actions a la derecha + body.
 *
 * Anti-pattern explícito: NO replica el "hero header de SaaS dashboard" (big title
 * + subtitle de 2 líneas + botón CTA gigante). Aquí el title es informativo, no
 * decorativo, y las acciones son secundarias.
 */
interface SectionProps extends HTMLAttributes<HTMLElement> {
  title: string
  /** Pequeño label sobre el title, uppercase + letter-spacing — categoriza el bloque. */
  eyebrow?: string
  description?: ReactNode
  actions?: ReactNode
  children: ReactNode
}

export function Section({
  title,
  eyebrow,
  description,
  actions,
  children,
  className,
  ...props
}: SectionProps) {
  return (
    <section className={cn("flex flex-col gap-4", className)} {...props}>
      <header className="flex items-start justify-between gap-4 border-b border-border-soft pb-3">
        <div className="flex flex-col gap-1 min-w-0">
          {eyebrow && (
            <span className="text-[10px] uppercase tracking-[0.08em] font-semibold text-muted">
              {eyebrow}
            </span>
          )}
          <h2 className="text-lg font-semibold text-ink leading-tight tracking-tight">
            {title}
          </h2>
          {description && (
            <p className="text-sm text-muted leading-relaxed mt-0.5">{description}</p>
          )}
        </div>
        {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
      </header>
      <div className="flex flex-col gap-4">{children}</div>
    </section>
  )
}
