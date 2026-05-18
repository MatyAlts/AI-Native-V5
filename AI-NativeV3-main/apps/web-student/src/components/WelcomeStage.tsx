/**
 * Welcome stage del web-student (shape alumno, brief 3.2 + D2).
 *
 * Sustituye al EmptyHero generico cuando no hay comision seleccionada.
 * Anuncia el contrato de la tesis ANTES de que el alumno arranque:
 *  - Modelo N4 visible desde el primer pixel (strip horizontal de 4 dots).
 *  - Honestidad tecnica del gap B.2 (mensaje literal del CLAUDE.md).
 *  - Acento de marca committed en el CTA (var(--color-accent-brand)).
 *
 * NO usa EmptyHero (icono generico + frase). Es welcome editorial denso:
 * kicker + display + sub honesto + strip + CTA. Cumple ban "identical
 * card grids" porque el strip tiene 4 columnas con texto desigual y un
 * heading unico.
 */

interface WelcomeStageProps {
  /** Disparado por el CTA primario para abrir el popover de comisiones. */
  onPickComision?: () => void
  /** True si el endpoint /comisiones/mis vino vacio (gap B.2). */
  comisionesVacias?: boolean
}

interface LevelBlurb {
  level: "N1" | "N2" | "N3" | "N4"
  label: string
  description: string
  colorVar: string
}

const LEVELS: LevelBlurb[] = [
  {
    level: "N1",
    label: "Lectura",
    description: "Lees el enunciado y planeas tu abordaje.",
    colorVar: "var(--color-level-n1)",
  },
  {
    level: "N2",
    label: "Anotacion",
    description: "Anotas tu plan, dudas, ideas.",
    colorVar: "var(--color-level-n2)",
  },
  {
    level: "N3",
    label: "Validacion",
    description: "Corres tests y debugeas.",
    colorVar: "var(--color-level-n3)",
  },
  {
    level: "N4",
    label: "Tutor",
    description: "Preguntas cuando te trabas.",
    colorVar: "var(--color-level-n4)",
  },
]

export function WelcomeStage({ onPickComision, comisionesVacias = false }: WelcomeStageProps) {
  return (
    <div className="flex-1 overflow-y-auto px-6 py-12">
      <div className="max-w-3xl mx-auto">
        <p className="text-xs font-mono uppercase tracking-wider text-muted mb-4">
          Programacion 2 (2026, 1er cuatrimestre)
        </p>

        <h1 className="text-2xl font-semibold leading-tight text-ink mb-4">
          Tutor socratico con trazabilidad cognitiva.
        </h1>

        <p className="text-sm text-body leading-relaxed mb-10 max-w-2xl">
          No te da la respuesta. Te acompana a construirla. Cada interaccion queda registrada en
          una cadena verificable.
        </p>

        <section
          aria-label="Como trabajas con el tutor"
          className="border-t border-border-soft pt-6 mb-10"
        >
          <p className="text-xs font-mono uppercase tracking-wider text-muted mb-5">
            Como trabajas
          </p>
          <ol className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-6">
            {LEVELS.map((lvl) => (
              <li key={lvl.level} className="flex flex-col">
                <div className="flex items-center gap-2 mb-2">
                  <span
                    aria-hidden="true"
                    data-testid={`level-dot-${lvl.level.toLowerCase()}`}
                    className="inline-block w-2 h-2 rounded-full"
                    style={{ backgroundColor: lvl.colorVar }}
                  />
                  <span className="text-sm font-semibold text-ink">
                    {lvl.level} {lvl.label}
                  </span>
                </div>
                <p className="text-xs text-muted leading-relaxed">
                  {lvl.description}
                </p>
              </li>
            ))}
          </ol>
        </section>

        <div className="flex flex-col gap-4">
          <button
            type="button"
            onClick={onPickComision}
            data-testid="welcome-cta-pick-comision"
            className="self-start px-5 py-2.5 rounded text-sm font-medium text-white shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2"
            style={{
              backgroundColor: "var(--color-accent-brand)",
              boxShadow: "0 1px 2px 0 rgb(0 0 0 / 0.05)",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = "var(--color-accent-brand-deep)"
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = "var(--color-accent-brand)"
            }}
          >
            Elegir comision para empezar
          </button>

          {comisionesVacias && (
            <div
              role="status"
              data-testid="welcome-gap-b2"
              className="text-xs text-muted leading-relaxed max-w-xl border-l border-border pl-3"
            >
              <p className="font-medium text-body mb-1">
                No estas viendo tus comisiones?
              </p>
              <p>
                Tu Direccion de Informatica todavia no activo el acceso. Ver gap-B.2 / ADR-029
                para el detalle.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
