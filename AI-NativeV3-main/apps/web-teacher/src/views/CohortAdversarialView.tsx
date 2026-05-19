import { Badge, PageContainer, StateMessage } from "@platform/ui"
import { Link } from "@tanstack/react-router"
import { ChevronRight, ExternalLink, Info } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useViewMode } from "../hooks/useViewMode"
import {
  type AdversarialRecentEvent,
  type CohortAdversarialEvents,
  getCohortAdversarialEvents,
} from "../lib/api"
import { ADVERSARIAL_DOCENTE, SEVERITY_DOCENTE, studentShortLabel } from "../utils/docenteLabels"
import { helpContent } from "../utils/helpContent"

// Umbral minimo de eventos para hacer afirmaciones de "% concentrado".
// Con N<5 cualquier proporcion (50%, 100%) es estadisticamente engañosa.
const MIN_EVENTS_FOR_CONCENTRATION_INSIGHT = 5

interface Props {
  getToken: () => Promise<string | null>
  initialComisionId?: string
}

const CATEGORY_LABELS: Record<string, string> = {
  jailbreak_indirect: "Jailbreak indirecto",
  jailbreak_substitution: "Jailbreak (sustitucion)",
  jailbreak_fiction: "Jailbreak (ficcion)",
  persuasion_urgency: "Persuasion por urgencia",
  prompt_injection: "Prompt injection",
}

const CATEGORY_TOKEN_VAR: Record<string, string> = {
  jailbreak_indirect: "--color-adversarial-jailbreak-indirect",
  jailbreak_substitution: "--color-adversarial-jailbreak-substitution",
  jailbreak_fiction: "--color-adversarial-jailbreak-fiction",
  persuasion_urgency: "--color-adversarial-persuasion-urgency",
  prompt_injection: "--color-adversarial-prompt-injection",
}

const SEVERITY_TOKEN_VAR: Record<string, string> = {
  "1": "--color-severity-1",
  "2": "--color-severity-2",
  "3": "--color-severity-3",
  "4": "--color-severity-4",
  "5": "--color-severity-5",
}

const CATEGORY_FALLBACK: Record<string, string> = {
  jailbreak_indirect: "#a855f7",
  jailbreak_substitution: "#dc2626",
  jailbreak_fiction: "#06b6d4",
  persuasion_urgency: "#f59e0b",
  prompt_injection: "#7f1d1d",
}

const SEVERITY_FALLBACK: Record<string, string> = {
  "1": "#94a3b8",
  "2": "#fbbf24",
  "3": "#fb923c",
  "4": "#ef4444",
  "5": "#7f1d1d",
}

function resolveCssVar(varName: string, fallback: string): string {
  if (typeof window === "undefined") return fallback
  const v = window.getComputedStyle(document.documentElement).getPropertyValue(varName).trim()
  return v || fallback
}

/**
 * Resuelve un label legible para una categoria, con fallbacks robustos.
 *
 * Caso real: el seed `seed-utn-prog1-cohorte-30.py` siembra `category: "jailbreak"`
 * generico (sin subtipo), y los mappings completos solo tienen las variantes
 * especificas (`jailbreak_substitution`, `jailbreak_fiction`, etc.). En vez de
 * mostrar el code raw al docente, devolvemos una etiqueta razonable por prefijo.
 */
function resolveCategoryLabel(category: string, isDocente: boolean): string {
  const labels = isDocente ? ADVERSARIAL_DOCENTE : CATEGORY_LABELS
  if (labels[category]) return labels[category] as string
  if (category.startsWith("jailbreak")) {
    return isDocente ? "Intento de manipular al tutor" : "Jailbreak (sin subcategoria)"
  }
  if (category.includes("injection")) {
    return isDocente ? "Intento de inyectar instrucciones" : "Prompt injection (generica)"
  }
  if (category.includes("persuasion")) {
    return isDocente ? "Intento de persuadir al tutor" : "Persuasion (generica)"
  }
  return category
}

function CategoryBars({
  counts,
  colors,
  isDocente,
}: {
  counts: Record<string, number>
  colors: Record<string, string>
  isDocente: boolean
}) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1])
  if (entries.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border p-4 text-center text-sm text-muted">
        {isDocente
          ? "No se detectaron intentos de uso inapropiado."
          : "Sin eventos adversos detectados en la cohorte."}
      </div>
    )
  }
  const max = Math.max(...entries.map(([, v]) => v))
  return (
    <div className="space-y-2.5">
      {entries.map(([cat, count]) => {
        const ratio = max > 0 ? count / max : 0
        return (
          <div key={cat} className="flex items-center gap-3">
            <div className="w-56 shrink-0 text-sm text-ink truncate">
              {resolveCategoryLabel(cat, isDocente)}
            </div>
            <div className="flex-1 h-5 rounded-full bg-border overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${ratio * 100}%`,
                  backgroundColor: colors[cat] ?? "#64748b",
                }}
              />
            </div>
            <div className="w-10 shrink-0 text-right text-sm font-semibold text-ink">{count}</div>
          </div>
        )
      })}
    </div>
  )
}

function SeverityBars({
  counts,
  colors,
  isDocente,
}: {
  counts: Record<string, number>
  colors: Record<string, string>
  isDocente: boolean
}) {
  const allLevels = ["1", "2", "3", "4", "5"] as const
  const nonZeroLevels = allLevels.filter((s) => (counts[s] ?? 0) > 0)
  // Si hay 1 o 2 niveles con datos, mostrar solo esos como chips compactos en
  // vez de la grid de 5 barras (la mayoria vacias se ven feas con N chico).
  const compact = isDocente && nonZeroLevels.length > 0 && nonZeroLevels.length <= 2
  if (compact) {
    return (
      <div className="flex flex-wrap gap-2">
        {nonZeroLevels.map((sev) => (
          <div
            key={sev}
            className="inline-flex items-center gap-2 rounded-full border border-border bg-canvas px-3 py-1.5"
          >
            <span
              aria-hidden="true"
              className="inline-block w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: colors[sev] }}
            />
            <span className="text-sm text-ink">
              {SEVERITY_DOCENTE[sev] ?? `Sev. ${sev}`}
            </span>
            <span className="text-sm font-semibold text-ink">{counts[sev] ?? 0}</span>
          </div>
        ))}
        {isDocente && nonZeroLevels.length < 5 && (
          <span className="inline-flex items-center text-xs text-muted px-1">
            (Sin casos en los otros niveles)
          </span>
        )}
      </div>
    )
  }
  const max = Math.max(...Object.values(counts), 1)
  return (
    <div className="grid grid-cols-5 gap-3">
      {allLevels.map((sev) => {
        const count = counts[sev] ?? 0
        const ratio = count / max
        return (
          <div key={sev} className="flex flex-col items-center gap-1">
            <div className="text-xs font-medium text-muted">
              {isDocente ? (SEVERITY_DOCENTE[sev] ?? `Sev. ${sev}`) : `Sev. ${sev}`}
            </div>
            <div className="h-20 w-full flex items-end rounded-lg bg-border overflow-hidden">
              <div
                className="w-full transition-all rounded-lg"
                style={{
                  height: `${Math.max(ratio * 100, count > 0 ? 4 : 0)}%`,
                  backgroundColor: colors[sev],
                }}
              />
            </div>
            <div className="text-sm font-semibold text-ink">{count}</div>
          </div>
        )
      })}
    </div>
  )
}

function topStudentInsight(data: CohortAdversarialEvents): string | null {
  // Con menos de 5 eventos cualquier proporcion (50%, 100%) es engañosa:
  // "1 de 2 = 50%" no significa nada estadisticamente. Evitamos hablar de
  // concentracion hasta tener volumen suficiente.
  if (data.n_events_total < MIN_EVENTS_FOR_CONCENTRATION_INSIGHT) return null
  if (data.top_students_by_n_events.length === 0) return null
  const top = data.top_students_by_n_events[0]
  if (!top) return null
  const pct = Math.round((top.n_events / data.n_events_total) * 100)
  if (pct < 30) return null
  return `Un alumno concentra el ${pct}% de los intentos. Considerá hablar con el/ella.`
}

function lowVolumeNotice(data: CohortAdversarialEvents, isDocente: boolean): string | null {
  if (data.n_events_total === 0) return null
  if (data.n_events_total >= MIN_EVENTS_FOR_CONCENTRATION_INSIGHT) return null
  // Con pocos eventos no se pueden sacar conclusiones de cohorte, pero igual
  // vale la pena informar al docente del volumen.
  if (!isDocente) return null
  const plural = data.n_events_total !== 1
  return (
    `Se detectaron ${data.n_events_total} intento${plural ? "s" : ""} en total. ` +
    "Con tan pocos casos no se pueden sacar conclusiones de la comisión — " +
    "miralos uno por uno abajo si querés conversar con esos estudiantes."
  )
}

export function CohortAdversarialView({ getToken, initialComisionId }: Props) {
  const comisionId = initialComisionId ?? null
  const [data, setData] = useState<CohortAdversarialEvents | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [viewMode] = useViewMode()
  const isDocente = viewMode === "docente"

  const catColors = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(CATEGORY_TOKEN_VAR).map(([k, v]) => [
          k,
          resolveCssVar(v, CATEGORY_FALLBACK[k] ?? "#64748b"),
        ]),
      ),
    [],
  )
  const sevColors = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(SEVERITY_TOKEN_VAR).map(([k, v]) => [
          k,
          resolveCssVar(v, SEVERITY_FALLBACK[k] ?? "#64748b"),
        ]),
      ),
    [],
  )

  useEffect(() => {
    if (!comisionId) {
      setData(null)
      return
    }
    setLoading(true)
    setError(null)
    let cancelled = false
    getCohortAdversarialEvents(comisionId, getToken)
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

  return (
    <PageContainer
      title={isDocente ? "Uso inapropiado del tutor IA" : "Intentos adversos detectados"}
      description={
        isDocente
          ? "Muestra cuando los alumnos intentaron hacer trampa o manipular al tutor IA. El sistema los detecta automaticamente."
          : "Visibilidad pedagogica de los matches del corpus de guardrails (ADR-019, Seccion 8.5 de la tesis). Deteccion preprocesamiento del prompt, el flujo NO se bloquea."
      }
      helpContent={helpContent.cohortAdversarial}
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
              ? "Elegi una comision para ver si hubo intentos de uso inapropiado."
              : "Elegi una comision desde la barra lateral para ver los intentos adversos detectados."}
          </div>
        )}

        {loading && <StateMessage variant="loading" title="Cargando eventos adversos..." />}

        {error && (
          <StateMessage variant="error" title="Error consultando la cohorte" description={error} />
        )}

        {data && !loading && (
          <>
            <div className="rounded-xl border border-border bg-white px-6 py-4">
              <div className="flex flex-wrap gap-x-8 gap-y-3 items-start">
                <div>
                  <div className="text-3xl font-semibold text-ink">{data.n_events_total}</div>
                  <div className="text-xs text-muted mt-0.5">
                    {isDocente
                      ? `intento${data.n_events_total !== 1 ? "s" : ""} detectado${data.n_events_total !== 1 ? "s" : ""}`
                      : "eventos totales"}
                  </div>
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-2 items-center pt-1">
                  {Object.entries(data.counts_by_category)
                    .sort((a, b) => b[1] - a[1])
                    .map(([cat, count]) => (
                      <span
                        key={cat}
                        className="inline-flex items-center gap-1.5 text-xs text-muted"
                      >
                        <span
                          aria-hidden="true"
                          className="inline-block w-2 h-2 rounded-full shrink-0"
                          style={{ backgroundColor: catColors[cat] ?? "#64748b" }}
                        />
                        <span className="font-medium text-ink">{count}</span>{" "}
                        {resolveCategoryLabel(cat, isDocente)}
                      </span>
                    ))}
                </div>
              </div>
            </div>

            {isDocente &&
              data.n_events_total > 0 &&
              (() => {
                const insight = topStudentInsight(data)
                if (insight) {
                  return (
                    <div className="rounded-xl border border-warning/30 bg-warning-soft px-6 py-4 text-sm text-warning flex items-start gap-2.5">
                      <Info className="h-5 w-5 flex-shrink-0 mt-0.5" />
                      <span>{insight}</span>
                    </div>
                  )
                }
                const lowVolume = lowVolumeNotice(data, isDocente)
                if (lowVolume) {
                  return (
                    <div className="rounded-xl border border-border bg-canvas px-6 py-4 text-sm text-muted flex items-start gap-2.5">
                      <Info className="h-5 w-5 flex-shrink-0 mt-0.5" />
                      <span>{lowVolume}</span>
                    </div>
                  )
                }
                return null
              })()}

            <div className="rounded-xl border border-border bg-white p-6 space-y-5">
              <div>
                <div className="text-xs font-medium uppercase tracking-wider text-muted mb-3">
                  {isDocente ? "Tipo de intento" : "Por categoria"}
                </div>
                <CategoryBars
                  counts={data.counts_by_category}
                  colors={catColors}
                  isDocente={isDocente}
                />
              </div>
              <div className="border-t border-border pt-5">
                <div className="text-xs font-medium uppercase tracking-wider text-muted mb-3">
                  {isDocente ? "Nivel de riesgo" : "Por severidad (1-5, ordinal)"}
                </div>
                <SeverityBars
                  counts={data.counts_by_severity}
                  colors={sevColors}
                  isDocente={isDocente}
                />
              </div>
            </div>

            {data.top_students_by_n_events.length > 0 && (
              <div className="rounded-xl border border-border bg-white overflow-hidden">
                <div className="border-b border-border px-6 py-3">
                  <span className="text-xs font-semibold text-ink uppercase tracking-wider">
                    {isDocente
                      ? "Alumnos con mas intentos"
                      : "Top estudiantes por numero de eventos"}
                  </span>
                </div>
                <ul className="divide-y divide-[#EAEAEA]">
                  {data.top_students_by_n_events.map((s) => (
                    <li key={s.student_pseudonym}>
                      {comisionId ? (
                        <Link
                          to="/student-longitudinal"
                          search={{ comisionId, studentId: s.student_pseudonym }}
                          className="flex items-center justify-between px-6 py-3 hover:bg-canvas transition-colors"
                          data-testid="adversarial-top-student-link"
                        >
                          <span className="font-mono text-xs text-muted">
                            {isDocente
                              ? studentShortLabel(s.student_pseudonym)
                              : `${s.student_pseudonym.slice(0, 8)}...${s.student_pseudonym.slice(-4)}`}
                          </span>
                          <span className="flex items-center gap-2">
                            <Badge className="bg-ink text-white">
                              {s.n_events}{" "}
                              {isDocente ? `intento${s.n_events !== 1 ? "s" : ""}` : "ev."}
                            </Badge>
                            <ChevronRight
                              aria-hidden="true"
                              className="h-4 w-4 text-muted"
                            />
                          </span>
                        </Link>
                      ) : (
                        <div className="flex items-center justify-between px-6 py-3">
                          <span className="font-mono text-xs text-muted">
                            {isDocente
                              ? studentShortLabel(s.student_pseudonym)
                              : `${s.student_pseudonym.slice(0, 8)}...${s.student_pseudonym.slice(-4)}`}
                          </span>
                          <Badge className="bg-ink text-white">
                            {s.n_events}{" "}
                            {isDocente ? `intento${s.n_events !== 1 ? "s" : ""}` : "ev."}
                          </Badge>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {!isDocente && data.recent_events.length > 0 && (
              <div className="overflow-hidden rounded-xl border border-border bg-white">
                <div className="border-b border-border bg-canvas px-6 py-3 text-xs font-semibold text-ink uppercase tracking-wider">
                  Eventos recientes ({data.recent_events.length})
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-canvas text-left text-xs uppercase tracking-wider text-muted border-b border-border">
                      <tr>
                        <th className="px-4 py-2.5 font-medium">Timestamp</th>
                        <th className="px-4 py-2.5 font-medium">Categoria</th>
                        <th className="px-4 py-2.5 font-medium">Sev.</th>
                        <th className="px-4 py-2.5 font-medium">Estudiante</th>
                        <th className="px-4 py-2.5 font-medium">Texto matcheado</th>
                        <th className="px-4 py-2.5 font-medium text-right">Drill-down</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.recent_events.map((ev, idx) => (
                        <RecentEventRow
                          key={`${ev.episode_id}-${idx}`}
                          event={ev}
                          catColors={catColors}
                          sevColors={sevColors}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {isDocente && data.recent_events.length > 0 && (
              <div className="overflow-hidden rounded-xl border border-border bg-white">
                <div className="border-b border-border bg-canvas px-6 py-3 flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-ink uppercase tracking-wider">
                    Ultimos intentos ({data.recent_events.length})
                  </span>
                  <span className="text-xs text-muted hidden sm:inline">
                    Click en cada uno para ver el episodio completo
                  </span>
                </div>
                <ul className="divide-y divide-[#EAEAEA]">
                  {data.recent_events.map((ev, idx) => (
                    <li key={`${ev.episode_id}-${idx}`}>
                      <Link
                        to="/episode-n-level"
                        search={{ episodeId: ev.episode_id }}
                        className="block px-6 py-3 hover:bg-canvas transition-colors"
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex items-start gap-3 min-w-0 flex-1">
                            <span
                              aria-hidden="true"
                              className="inline-block w-2.5 h-2.5 rounded-full shrink-0 mt-1.5"
                              style={{ backgroundColor: catColors[ev.category] ?? "#64748b" }}
                            />
                            <div className="min-w-0 flex-1">
                              <div className="text-sm text-ink font-medium">
                                {resolveCategoryLabel(ev.category, true)}
                              </div>
                              <div className="text-xs text-muted mt-0.5">
                                {studentShortLabel(ev.student_pseudonym)} · {ev.ts.slice(0, 10)}
                                <span className="mx-1.5">·</span>
                                Riesgo: {SEVERITY_DOCENTE[String(ev.severity)] ?? ev.severity}
                              </div>
                              {ev.matched_text && (
                                <div className="mt-2 text-xs text-muted bg-canvas border border-border rounded-md px-2.5 py-1.5 font-mono break-words">
                                  <span className="text-[10px] uppercase tracking-wider text-muted/70 mr-1">
                                    Texto detectado:
                                  </span>
                                  "
                                  {ev.matched_text.length > 200
                                    ? ev.matched_text.slice(0, 200) + "…"
                                    : ev.matched_text}
                                  "
                                </div>
                              )}
                            </div>
                          </div>
                          <div className="shrink-0 flex items-center gap-1 text-xs text-[var(--color-accent-brand)] mt-1">
                            ver sesión
                            <ExternalLink className="h-3.5 w-3.5" />
                          </div>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {data.n_events_total === 0 && (
              <div className="rounded-xl border border-green-200 bg-green-50 p-6 text-center">
                <div className="text-green-800 font-semibold">
                  {isDocente
                    ? "No se detectaron intentos de uso inapropiado."
                    : "Sin eventos adversos en esta cohorte."}
                </div>
                {!isDocente && (
                  <div className="mt-2 text-sm text-green-700">
                    Puede significar (a) los estudiantes no intentaron jailbreak, (b) los regex del
                    corpus v1.1.0 no detectan los intentos reales, o (c) el modo dev no tiene CTR
                    conectado. Ver <code className="font-mono">RN-129</code> para limitaciones
                    declaradas.
                  </div>
                )}
                {isDocente && (
                  <div className="mt-2 text-sm text-green-700">
                    Tus alumnos no intentaron engañar al tutor IA (o el sistema no detecto ningun
                    intento).
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </PageContainer>
  )
}

function RecentEventRow({
  event,
  catColors,
  sevColors,
}: {
  event: AdversarialRecentEvent
  catColors: Record<string, string>
  sevColors: Record<string, string>
}) {
  return (
    <tr className="border-b border-border last:border-0 hover:bg-canvas transition-colors">
      <td className="px-4 py-3 align-top text-xs text-muted whitespace-nowrap">
        {event.ts.slice(0, 19).replace("T", " ")}
      </td>
      <td className="px-4 py-3 align-top">
        <span className="inline-flex items-center gap-1.5 text-xs text-ink">
          <span
            aria-hidden="true"
            className="inline-block w-2 h-2 rounded-full shrink-0"
            style={{ backgroundColor: catColors[event.category] ?? "#64748b" }}
          />
          {CATEGORY_LABELS[event.category] ?? event.category}
        </span>
      </td>
      <td className="px-4 py-3 align-top">
        <span
          className="inline-block rounded-full w-6 h-6 text-xs font-bold text-white flex items-center justify-center"
          style={{ backgroundColor: sevColors[String(event.severity)] }}
        >
          {event.severity}
        </span>
      </td>
      <td className="px-4 py-3 align-top font-mono text-xs text-muted">
        {event.student_pseudonym.slice(0, 8)}...
      </td>
      <td className="px-4 py-3 align-top">
        <code className="block text-xs text-ink bg-canvas rounded px-2 py-1 break-all">
          {event.matched_text}
        </code>
      </td>
      <td className="px-4 py-3 align-top text-right whitespace-nowrap">
        <Link
          to="/episode-n-level"
          search={{ episodeId: event.episode_id }}
          className="text-xs text-[var(--color-accent-brand)] hover:underline"
        >
          ver episodio →
        </Link>
      </td>
    </tr>
  )
}
