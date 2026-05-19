import { PageContainer, StateMessage } from "@platform/ui"
import { Link } from "@tanstack/react-router"
import { ArrowDown, ArrowRight, ArrowUp, ChevronDown, Info, Users } from "lucide-react"
import { useEffect, useState } from "react"
import { useViewMode } from "../hooks/useViewMode"
import { type CohortCIIQuartiles, getCohortCIIQuartiles } from "../lib/api"
import { helpContent } from "../utils/helpContent"

interface Props {
  getToken: () => Promise<string | null>
  initialComisionId?: string
}

function formatSlope(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—"
  return value.toFixed(3)
}

function slopeTone(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "text-muted-soft"
  if (value > 0.1) return "text-[var(--color-success)]"
  if (value < -0.1) return "text-[var(--color-danger)]"
  return "text-ink"
}

function slopeBadge(value: number | null, isDocente: boolean): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "sin dato"
  if (value > 0.1) return isDocente ? "mejorando" : "slope positivo"
  if (value < -0.1) return isDocente ? "empeorando" : "slope negativo"
  return isDocente ? "estable" : "slope ~0"
}

// ── Narrativa pedagogica ─────────────────────────────────────────────────

function classOverviewMessage(data: CohortCIIQuartiles): {
  headline: string
  detail: string
  tone: "good" | "mixed" | "warning"
} | null {
  if (data.insufficient_data || data.median === null) return null
  const med = data.median
  const q1 = data.q1 ?? 0
  const q3 = data.q3 ?? 0

  // La mayoria progresa Y el cuartil inferior tambien esta por encima de 0
  if (med > 0.1 && q1 > -0.1) {
    return {
      headline: "Tu clase avanza saludablemente",
      detail:
        "La mayoría de los alumnos está mejorando episodio a episodio. Incluso los que avanzan más despacio mantienen tendencia positiva. Buen momento para reforzar lo que está funcionando.",
      tone: "good",
    }
  }
  // La mayoria progresa pero el cuartil inferior empeora
  if (med > 0.1 && q1 < -0.1) {
    return {
      headline: "La mayoría avanza, pero un grupo se está atrasando",
      detail:
        "La clase en general progresa, pero el 25% que va más despacio está empeorando episodio a episodio. Vale la pena identificar a esos alumnos y conversar pronto antes de que la brecha se agrande.",
      tone: "warning",
    }
  }
  // Mediana negativa: la clase no esta progresando
  if (med < -0.1) {
    return {
      headline: "La clase no está progresando",
      detail:
        "Más de la mitad de los alumnos está empeorando o estancado. Esto puede señalar un problema con el ritmo de la materia, la dificultad de los ejercicios actuales o algo más estructural. Conviene revisar con el equipo docente.",
      tone: "warning",
    }
  }
  // Mediana cerca de cero pero Q3 alto: hay diversidad
  if (Math.abs(med) <= 0.1 && q3 > 0.2) {
    return {
      headline: "Resultados mixtos en la cohorte",
      detail:
        "Hay un grupo que está avanzando bien y otro que se quedó. La mediana cercana a cero sugiere que la clase está partida — un seguimiento por subgrupos puede ayudar.",
      tone: "mixed",
    }
  }
  // Mediana ~0 y Q3 bajo: clase estancada
  return {
    headline: "La clase está mayormente estable",
    detail:
      "Los alumnos no están retrocediendo, pero tampoco hay un avance fuerte. Puede ser etapa normal de consolidación o señal de que hace falta variar el tipo de ejercicios.",
    tone: "mixed",
  }
}

// ── Boxplot visual horizontal ────────────────────────────────────────────

function MiniBoxplot({ data }: { data: CohortCIIQuartiles }) {
  if (data.insufficient_data || data.min === null || data.max === null) return null
  const min = data.min
  const max = data.max
  const q1 = data.q1 ?? min
  const q3 = data.q3 ?? max
  const median = data.median ?? (q1 + q3) / 2

  // Mapeo logico: rango fijo [-1, +1] del slope ordinal sobre APPROPRIATION_ORDINAL.
  // Eso asegura que el "cero" siempre esta en el medio visual y los cuartiles
  // comparan entre cohortes distintas en la misma escala.
  const VISUAL_MIN = -1
  const VISUAL_MAX = 1
  const range = VISUAL_MAX - VISUAL_MIN
  const pct = (v: number) => ((Math.max(VISUAL_MIN, Math.min(VISUAL_MAX, v)) - VISUAL_MIN) / range) * 100

  return (
    <div className="w-full">
      {/* Etiquetas extremos */}
      <div className="flex justify-between text-[10px] text-muted mb-1 uppercase tracking-wider">
        <span className="flex items-center gap-1">
          <ArrowDown className="h-3 w-3" />
          Empeoran
        </span>
        <span>Estables</span>
        <span className="flex items-center gap-1">
          Mejoran
          <ArrowUp className="h-3 w-3" />
        </span>
      </div>

      {/* Track con gradiente */}
      <div className="relative h-12 rounded-lg overflow-visible">
        {/* Background con zonas */}
        <div
          className="absolute inset-0 rounded-lg"
          style={{
            background:
              "linear-gradient(to right, var(--color-danger-soft, #fee2e2) 0%, var(--color-canvas, #f7f7f5) 50%, var(--color-success-soft, #dcfce7) 100%)",
          }}
        />

        {/* Barra Q1-Q3 (caja del boxplot) */}
        <div
          className="absolute top-2 bottom-2 border-2 border-ink rounded"
          style={{
            left: `${pct(q1)}%`,
            width: `${Math.max(pct(q3) - pct(q1), 1)}%`,
            backgroundColor: "var(--color-surface, #ffffff)",
          }}
          aria-label="Rango de los alumnos que están entre el 25% y el 75%"
        />

        {/* Mediana (línea más gruesa) */}
        <div
          className="absolute top-1 bottom-1 w-0.5 bg-ink"
          style={{ left: `${pct(median)}%` }}
          aria-label="Mediana — alumno típico"
        />

        {/* Whiskers min/max */}
        <div
          className="absolute top-4 bottom-4 w-0.5 bg-muted"
          style={{ left: `${pct(min)}%` }}
        />
        <div
          className="absolute top-4 bottom-4 w-0.5 bg-muted"
          style={{ left: `${pct(max)}%` }}
        />

        {/* Línea base que conecta los whiskers */}
        <div
          className="absolute top-1/2 h-px bg-muted -translate-y-1/2"
          style={{ left: `${pct(min)}%`, width: `${pct(max) - pct(min)}%` }}
        />

        {/* Marcador del cero */}
        <div
          className="absolute top-0 bottom-0 w-px bg-ink/30 border-dashed"
          style={{ left: `${pct(0)}%` }}
        />
      </div>

      {/* Leyenda valores */}
      <div className="flex justify-between text-[10px] text-muted mt-1.5 font-mono">
        <span>{formatSlope(min)}</span>
        <span className="text-ink font-semibold">mediana {formatSlope(median)}</span>
        <span>{formatSlope(max)}</span>
      </div>
    </div>
  )
}

// ── Tarjetas de cuartiles repensadas ─────────────────────────────────────

function QuartileBucketCard({
  badge,
  badgeColor,
  studentsApprox,
  totalStudents,
  description,
  value,
  isDocente,
}: {
  badge: string
  badgeColor: string
  studentsApprox: number
  totalStudents: number
  description: string
  value: number | null
  isDocente: boolean
}) {
  return (
    <div className="rounded-xl border border-border bg-white p-5 flex flex-col gap-2.5">
      <div
        className={`inline-flex items-center gap-1.5 self-start text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full ${badgeColor}`}
      >
        {badge}
      </div>
      <div className="flex items-baseline gap-2">
        <Users className="h-4 w-4 text-muted" aria-hidden="true" />
        <span className="text-2xl font-semibold text-ink">≈ {studentsApprox}</span>
        <span className="text-xs text-muted">de {totalStudents} alumnos</span>
      </div>
      <p className="text-sm text-ink leading-snug">{description}</p>
      {isDocente && (
        <div className="text-[11px] text-muted-soft mt-1 pt-2 border-t border-border">
          Valor de progreso:{" "}
          <span className={`font-mono font-semibold ${slopeTone(value)}`}>{formatSlope(value)}</span>{" "}
          <span className="italic">({slopeBadge(value, isDocente)})</span>
        </div>
      )}
    </div>
  )
}

// ── Vista principal ──────────────────────────────────────────────────────

export function CohortQuartilesView({ getToken, initialComisionId }: Props) {
  const comisionId = initialComisionId ?? null
  const [data, setData] = useState<CohortCIIQuartiles | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [viewMode] = useViewMode()
  const isDocente = viewMode === "docente"
  const [showStats, setShowStats] = useState(!isDocente)

  useEffect(() => {
    if (!comisionId) {
      setData(null)
      return
    }
    setLoading(true)
    setError(null)
    let cancelled = false
    getCohortCIIQuartiles(comisionId, getToken)
      .then((d) => {
        if (!cancelled) setData(d)
      })
      .catch((e) => {
        if (!cancelled) setError(String(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [comisionId, getToken])

  const overview = data ? classOverviewMessage(data) : null

  return (
    <PageContainer
      title={isDocente ? "Distribucion de progreso en la cohorte" : "Cuartiles CII de cohorte"}
      description={
        isDocente
          ? "Muestra cómo se reparte el progreso de tus alumnos. Sirve para ver si la clase avanza pareja o si hay subgrupos con ritmos muy distintos."
          : "Cuartiles agregados del mean_slope longitudinal por estudiante (ADR-022, RN-131). Privacidad k-anonymity: requiere N >= 5 estudiantes con slope computable. La mediana es Q2."
      }
      helpContent={helpContent.cohortQuartiles}
    >
      <div className="space-y-6">
        {comisionId && (
          <div className="text-xs">
            <Link
              to="/progression"
              search={{ comisionId }}
              className="text-muted hover:text-ink transition-colors"
            >
              ← {isDocente ? "Volver a mis alumnos" : "Volver a la cohorte"}
            </Link>
          </div>
        )}

        {!comisionId && !loading && (
          <div className="rounded-xl border border-dashed border-border bg-white p-6 text-sm text-muted">
            {isDocente
              ? "Elegi una comision desde la barra superior para ver la distribucion."
              : "Elegi una comision para computar los cuartiles CII de su cohorte."}
          </div>
        )}

        {loading && <StateMessage variant="loading" title="Calculando cuartiles de la cohorte..." />}

        {error && (
          <StateMessage variant="error" title="Error consultando la cohorte" description={error} />
        )}

        {data && !loading && (
          <>
            {/* Privacy gate — todavia no hay datos suficientes */}
            {data.insufficient_data && (
              <div className="rounded-xl border border-warning/30 bg-warning-soft px-6 py-4 text-sm text-warning">
                <div className="font-semibold mb-1">
                  {isDocente ? "Datos insuficientes para mostrar la distribución" : "Insufficient data"}
                </div>
                <div>
                  {isDocente
                    ? `Necesitamos al menos ${data.min_students_for_quartiles} alumnos con episodios suficientes. La cohorte tiene ${data.n_students_evaluated} con datos por ahora — esperá a que cierren más episodios.`
                    : `La cohorte tiene ${data.n_students_evaluated} estudiantes con mean_slope computable; se requieren ${data.min_students_for_quartiles} (k-anonymity, ADR-022). Esperar mas episodios cerrados o ampliar el periodo de la cohorte.`}
                </div>
              </div>
            )}

            {/* ── Modo DOCENTE: didáctico ── */}
            {isDocente && !data.insufficient_data && (
              <>
                {/* 1. Resumen narrativo "lo que está pasando" */}
                {overview && (
                  <div
                    className={`rounded-xl border px-6 py-5 ${
                      overview.tone === "good"
                        ? "border-success/30 bg-success-soft"
                        : overview.tone === "warning"
                          ? "border-warning/40 bg-warning-soft"
                          : "border-border bg-canvas"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex-1">
                        <h3 className="text-base font-semibold text-ink">{overview.headline}</h3>
                        <p className="text-sm text-ink/80 mt-1.5 leading-relaxed">
                          {overview.detail}
                        </p>
                      </div>
                      <div className="text-right shrink-0">
                        <div className="text-3xl font-semibold text-ink">
                          {data.n_students_evaluated}
                        </div>
                        <div className="text-[11px] text-muted uppercase tracking-wider mt-0.5">
                          alumnos
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* 2. Boxplot visual */}
                <div className="rounded-xl border border-border bg-white px-6 py-5">
                  <h3 className="text-sm font-semibold text-ink mb-1">
                    Cómo se distribuye el progreso de la clase
                  </h3>
                  <p className="text-xs text-muted mb-4">
                    La caja muestra al 50% central de los alumnos. La línea del medio es el alumno
                    típico. Los extremos son el que más avanza y el que menos.
                  </p>
                  <MiniBoxplot data={data} />
                </div>

                {/* 3. Tarjetas de cuartiles repensadas */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <QuartileBucketCard
                    badge="Avanzan más despacio"
                    badgeColor="bg-warning-soft text-warning"
                    studentsApprox={Math.max(1, Math.floor(data.n_students_evaluated * 0.25))}
                    totalStudents={data.n_students_evaluated}
                    description={
                      data.q1 !== null && data.q1 < -0.1
                        ? "Este grupo está empeorando episodio a episodio. Vale la pena tomar contacto pedagógico pronto."
                        : data.q1 !== null && data.q1 < 0.1
                          ? "Este grupo avanza, pero más lento que la mayoría. Puede ser ritmo personal — observalos."
                          : "Incluso este grupo está progresando. La clase entera tiene buen ritmo."
                    }
                    value={data.q1}
                    isDocente
                  />
                  <QuartileBucketCard
                    badge="Alumno típico (mediana)"
                    badgeColor="bg-canvas text-ink border border-border"
                    studentsApprox={Math.max(1, Math.floor(data.n_students_evaluated * 0.5))}
                    totalStudents={data.n_students_evaluated}
                    description={
                      data.median !== null && data.median > 0.1
                        ? "Así avanza el alumno promedio de tu clase: con buen progreso entre episodios."
                        : data.median !== null && data.median < -0.1
                          ? "El alumno promedio de tu clase está empeorando. Esto es una señal seria — revisar con el equipo."
                          : "El alumno promedio se mantiene estable, sin progreso fuerte ni regresión."
                    }
                    value={data.median}
                    isDocente
                  />
                  <QuartileBucketCard
                    badge="Avanzan más rápido"
                    badgeColor="bg-success-soft text-success"
                    studentsApprox={Math.max(1, Math.floor(data.n_students_evaluated * 0.25))}
                    totalStudents={data.n_students_evaluated}
                    description={
                      data.q3 !== null && data.q3 > 0.2
                        ? "Este grupo está progresando rápido. Considerá darles ejercicios de mayor dificultad para mantenerlos desafiados."
                        : "Este grupo va al frente de la clase, pero la diferencia no es muy grande con el resto."
                    }
                    value={data.q3}
                    isDocente
                  />
                </div>

                {/* 4. Detalle estadístico colapsable (para docentes que quieran ver los números) */}
                <div className="rounded-xl border border-border bg-white overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setShowStats((v) => !v)}
                    className="w-full border-b border-border bg-canvas px-6 py-3 flex items-center justify-between hover:bg-surface transition-colors"
                    aria-expanded={showStats}
                  >
                    <span className="text-xs font-semibold text-ink uppercase tracking-wider">
                      Detalle estadístico (opcional)
                    </span>
                    <ChevronDown
                      className={`h-4 w-4 text-muted transition-transform ${showStats ? "rotate-180" : ""}`}
                    />
                  </button>
                  {showStats && (
                    <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-border">
                      <StatCell label="Mínimo" value={data.min} tone={slopeTone(data.min)} />
                      <StatCell label="Promedio" value={data.mean} tone={slopeTone(data.mean)} />
                      <StatCell
                        label="Dispersión"
                        value={data.stdev}
                        tone="text-ink"
                        hint="Qué tan distintos son los alumnos entre sí"
                      />
                      <StatCell label="Máximo" value={data.max} tone={slopeTone(data.max)} />
                    </div>
                  )}
                </div>

                {/* 5. Glosario chico — solo expandible */}
                <details className="rounded-xl border border-border bg-canvas">
                  <summary className="px-6 py-3 cursor-pointer text-sm font-medium text-ink flex items-center gap-2">
                    <Info className="h-4 w-4 text-muted" />
                    ¿Cómo se calcula este "valor de progreso"?
                  </summary>
                  <div className="px-6 pb-4 text-sm text-muted space-y-2 leading-relaxed">
                    <p>
                      Cada alumno tiene un <strong>valor de progreso</strong> que se calcula mirando
                      cómo cambió su clasificación N4 (delegación pasiva → superficial → reflexiva)
                      a lo largo de los episodios que resolvió.
                    </p>
                    <p>
                      <strong>Positivo</strong> (verde) = mejora. <strong>Negativo</strong> (rojo) =
                      empeora. <strong>Cerca de cero</strong> = se mantiene estable.
                    </p>
                    <p>
                      La <strong>mediana</strong> es el valor del alumno que está justo en el medio
                      de la clase: la mitad tiene un valor más alto y la mitad más bajo. Es más
                      representativa que el promedio cuando hay alumnos muy extremos.
                    </p>
                    <p className="text-xs text-muted-soft italic">
                      Detalle técnico: slope ordinal sobre APPROPRIATION_ORDINAL por template
                      académico (ADR-018). Cuartiles cardinales sobre datos ordinales —
                      operacionalización conservadora declarada en el ADR.
                    </p>
                  </div>
                </details>
              </>
            )}

            {/* ── Modo INVESTIGADOR/ADMIN: técnico (sin tocar) ── */}
            {!isDocente && !data.insufficient_data && (
              <>
                {/* Header con conteo de estudiantes y privacy gate */}
                <div className="rounded-xl border border-border bg-white px-6 py-4">
                  <div className="flex flex-wrap items-baseline gap-x-8 gap-y-2">
                    <div>
                      <div className="text-3xl font-semibold text-ink">
                        {data.n_students_evaluated}
                      </div>
                      <div className="text-xs text-muted mt-0.5">
                        estudiantes con mean_slope computable
                      </div>
                    </div>
                    <div className="text-xs text-muted">
                      <div>
                        k-anonymity threshold:{" "}
                        <span className="font-semibold text-ink">
                          N &gt;= {data.min_students_for_quartiles}
                        </span>
                      </div>
                      <div className="mt-0.5">
                        labeler_version:{" "}
                        <span className="font-mono text-ink">{data.labeler_version}</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Cuartiles "raw" técnicos */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="rounded-xl border border-border bg-white p-5 flex flex-col gap-2">
                    <div className="text-xs font-medium uppercase tracking-wider text-muted">
                      Q1 (25%)
                    </div>
                    <div className={`text-3xl font-semibold ${slopeTone(data.q1)}`}>
                      {formatSlope(data.q1)}
                    </div>
                    <div className="text-xs text-muted-soft">
                      Primer cuartil del mean_slope cohorte.
                    </div>
                    <div className="text-[11px] text-muted mt-1 italic">
                      {slopeBadge(data.q1, false)}
                    </div>
                  </div>
                  <div className="rounded-xl border border-border bg-white p-5 flex flex-col gap-2">
                    <div className="text-xs font-medium uppercase tracking-wider text-muted">
                      Mediana (Q2 · 50%)
                    </div>
                    <div className={`text-3xl font-semibold ${slopeTone(data.median)}`}>
                      {formatSlope(data.median)}
                    </div>
                    <div className="text-xs text-muted-soft">Mediana del mean_slope cohorte.</div>
                    <div className="text-[11px] text-muted mt-1 italic">
                      {slopeBadge(data.median, false)}
                    </div>
                  </div>
                  <div className="rounded-xl border border-border bg-white p-5 flex flex-col gap-2">
                    <div className="text-xs font-medium uppercase tracking-wider text-muted">
                      Q3 (75%)
                    </div>
                    <div className={`text-3xl font-semibold ${slopeTone(data.q3)}`}>
                      {formatSlope(data.q3)}
                    </div>
                    <div className="text-xs text-muted-soft">
                      Tercer cuartil del mean_slope cohorte.
                    </div>
                    <div className="text-[11px] text-muted mt-1 italic">
                      {slopeBadge(data.q3, false)}
                    </div>
                  </div>
                </div>

                {/* Stats secundarios: min, max, mean, stdev */}
                <div className="rounded-xl border border-border bg-white overflow-hidden">
                  <div className="border-b border-border bg-canvas px-6 py-3">
                    <span className="text-xs font-semibold text-ink uppercase tracking-wider">
                      Stats agregados de mean_slope
                    </span>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-border">
                    <StatCell label="Min" value={data.min} tone={slopeTone(data.min)} />
                    <StatCell label="Max" value={data.max} tone={slopeTone(data.max)} />
                    <StatCell label="Mean" value={data.mean} tone={slopeTone(data.mean)} />
                    <StatCell label="Stdev" value={data.stdev} tone="text-ink" />
                  </div>
                </div>

                {/* Lectura interpretativa (modo investigador) */}
                <div className="rounded-xl border border-border bg-canvas px-6 py-4 text-sm text-muted">
                  <div className="font-semibold text-ink mb-2">Interpretacion</div>
                  <ul className="list-disc list-inside space-y-1.5">
                    <li>
                      Cada estudiante aporta un mean_slope (ADR-018, slope ordinal sobre
                      APPROPRIATION_ORDINAL por template).
                    </li>
                    <li>
                      Slope &gt; 0.1 = mejora; slope &lt; -0.1 = regresion; ~0 = estable. Cuartiles
                      cardinales sobre datos ordinales (operacionalizacion conservadora declarada en
                      ADR-018).
                    </li>
                    <li>
                      Si Q1 &lt; 0 significativamente, el cuartil inferior esta regresionando:
                      candidato para intervencion focalizada.
                    </li>
                  </ul>
                </div>
              </>
            )}

            {/* CTA — volver a la lista de alumnos para tomar accion */}
            {isDocente && !data.insufficient_data && (
              <div className="rounded-xl border border-border bg-white px-6 py-4 flex items-center justify-between gap-4 flex-wrap">
                <div className="text-sm text-muted">
                  ¿Querés ver quiénes son los alumnos detrás de estos números?
                </div>
                <Link
                  to="/progression"
                  search={{ comisionId: comisionId ?? "" }}
                  className="inline-flex items-center gap-1.5 text-sm text-[var(--color-accent-brand)] hover:underline font-medium"
                >
                  Ver alumno por alumno
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            )}
          </>
        )}
      </div>
    </PageContainer>
  )
}

function StatCell({
  label,
  value,
  tone,
  hint,
}: {
  label: string
  value: number | null
  tone: string
  hint?: string
}) {
  return (
    <div className="px-6 py-4">
      <div className="text-xs text-muted uppercase tracking-wider">{label}</div>
      <div className={`text-xl font-semibold mt-1 ${tone}`}>{formatSlope(value)}</div>
      {hint && <div className="text-[10px] text-muted-soft mt-0.5 italic">{hint}</div>}
    </div>
  )
}
