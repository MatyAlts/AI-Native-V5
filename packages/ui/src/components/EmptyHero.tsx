import type { ReactNode } from "react"

interface EmptyHeroProps {
  /** Icono lucide ya configurado por el caller (ej. <BookOpen className="h-12 w-12" />). */
  icon: ReactNode
  /** Heading principal. */
  title: string
  /** Texto secundario, 1-2 oraciones. */
  description: string
  /** CTA opcional. */
  primaryAction?: {
    label: string
    onClick: () => void
  }
  /** Línea pequeña al pie. */
  hint?: string
}

/**
 * Empty state hero para pantallas que arrancan sin selección (ej. comisión).
 * Paleta v2: surface-alt para el icon container, acento brand para el CTA.
 * Sin dark mode adhoc — el modo oscuro vive en sidebars/modales, no aquí.
 */
export function EmptyHero({ icon, title, description, primaryAction, hint }: EmptyHeroProps) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-6 mx-auto max-w-md">
      <div className="rounded-full bg-surface-alt p-4 flex items-center justify-center text-muted">
        {icon}
      </div>
      <h2 className="mt-6 text-xl font-semibold tracking-tight text-ink">{title}</h2>
      <p className="text-muted text-base leading-relaxed mt-2">{description}</p>
      {primaryAction ? (
        <button
          type="button"
          onClick={primaryAction.onClick}
          className="inline-flex items-center gap-2 mt-6 rounded-md bg-accent-brand text-white px-5 py-2.5 text-sm font-medium hover:bg-accent-brand-deep transition-colors"
        >
          {primaryAction.label}
        </button>
      ) : null}
      {hint ? <p className="text-xs text-muted-soft mt-4">{hint}</p> : null}
    </div>
  )
}
