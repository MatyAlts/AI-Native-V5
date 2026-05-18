import type { ReactNode } from "react"
import { HelpButton } from "./HelpButton"

interface PageContainerProps {
  /** Heading principal de la página (display, 3xl). */
  title: string
  /** Línea descriptiva debajo del title. */
  description?: string
  /** Mini-label opcional sobre el title (uppercase letter-spacing) — útil para
   *  breadcrumbs o categorización ("Panel docente · Periodo en curso"). */
  eyebrow?: ReactNode
  /** Contenido del modal de ayuda — pasado al HelpButton del header. */
  helpContent: ReactNode
  /** Si false, el container ocupa el ancho completo (default: max-w-7xl centered). */
  fullWidth?: boolean
  children: ReactNode
}

/**
 * PageContainer v2 — wrapper estándar para todas las views.
 *
 * Layout 2026:
 * - `page-enter` fade-in al montar.
 * - Header con eyebrow opcional + título display 3xl + descripción + HelpButton.
 * - Animación `fade-in-down` para que el header entre suave (no jump).
 * - `max-w-7xl mx-auto` por default (~80rem) — centrado en pantallas grandes,
 *   full en pantallas chicas. Override con `fullWidth=true` para panels que
 *   necesitan todo el ancho (ej. tablas densas, kanbans).
 * - Padding base p-6 — densidad académica, no whitespace SaaS gratuito.
 */
export function PageContainer({
  title,
  description,
  eyebrow,
  helpContent,
  fullWidth = false,
  children,
}: PageContainerProps) {
  const widthClass = fullWidth ? "" : "max-w-7xl mx-auto"
  return (
    <div className={`page-enter space-y-8 p-6 ${widthClass}`}>
      <header className="flex items-start justify-between gap-4 animate-fade-in-down">
        <div className="flex flex-col gap-1.5 min-w-0">
          {eyebrow && (
            <div className="text-[11px] uppercase tracking-[0.12em] font-semibold text-muted">
              {eyebrow}
            </div>
          )}
          <h1 className="text-3xl font-semibold tracking-tight text-ink leading-none">{title}</h1>
          {description && (
            <p
              data-testid="page-description"
              className="text-sm text-muted leading-relaxed mt-1.5 max-w-2xl"
            >
              {description}
            </p>
          )}
        </div>
        <HelpButton title={title} content={helpContent} />
      </header>
      {children}
    </div>
  )
}
