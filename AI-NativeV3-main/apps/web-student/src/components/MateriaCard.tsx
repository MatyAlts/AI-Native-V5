/**
 * Card de una materia inscripta (shape alumno, post-craft Fase 2).
 *
 * Una sola card prominente cuando el alumno tiene N=1 (caso piloto típico).
 * Cuando tiene N>5, la HomePage cambia el render a list items densos y
 * NO usa este componente — evitamos el "identical card grid" baneado.
 *
 * Layout editorial:
 *   - Kicker mono (CODIGO_MATERIA · COMISION) — auditable hex rule
 *   - Headline 18px (nombre de la materia)
 *   - Meta línea (periodo + horario opcional)
 *   - CTA "Entrar →" con var(--color-accent-brand)
 *
 * Cero side-stripe coloreado, cero icono decorativo. El color vive en el
 * acento del CTA, NO en el border de la card. Borde slate neutro.
 */
import { ArrowRight } from "lucide-react"
import type { MateriaInscripta } from "../lib/api"

export interface MateriaCardProps {
  materia: MateriaInscripta
  /** Disparado por el CTA (click o Enter). El parent navega a /materia/:id. */
  onEnter: (materia: MateriaInscripta) => void
}

export function MateriaCard({ materia, onEnter }: MateriaCardProps) {
  const horario = materia.horario_resumen
  const comisionLabel = materia.comision_nombre ?? `Comision ${materia.comision_codigo}`

  return (
    <article
      data-testid="materia-card"
      data-materia-codigo={materia.codigo}
      className="hover-lift group relative overflow-hidden rounded-xl border border-border bg-surface p-6 shadow-[0_1px_2px_0_rgba(0,0,0,0.04)]"
    >
      <div
        aria-hidden="true"
        className="absolute left-0 top-0 bottom-0 w-1 bg-accent-brand/0 group-hover:bg-accent-brand/60 transition-colors"
      />
      <p
        className="text-xs font-mono uppercase tracking-wider text-muted mb-2"
        data-testid="materia-card-kicker"
      >
        {materia.codigo} <span className="text-muted-soft">·</span> {comisionLabel}
      </p>

      <h3 className="text-lg font-semibold text-ink mb-3 leading-tight tracking-tight">
        {materia.nombre}
      </h3>

      <p className="text-xs text-muted mb-5">
        <span data-testid="materia-card-periodo">{materia.periodo_codigo}</span>
        {horario && (
          <>
            <span className="text-muted-soft mx-1.5">·</span>
            <span data-testid="materia-card-horario">{horario}</span>
          </>
        )}
      </p>

      <div className="flex justify-end">
        <button
          type="button"
          data-testid="materia-card-enter"
          onClick={() => onEnter(materia)}
          className="press-shrink inline-flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium text-white bg-accent-brand hover:bg-accent-brand-deep focus:outline-none focus:ring-2 focus:ring-accent-brand focus:ring-offset-2 transition-colors shadow-[0_1px_2px_0_rgba(24,95,165,0.25)]"
        >
          Entrar
          <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
        </button>
      </div>
    </article>
  )
}
