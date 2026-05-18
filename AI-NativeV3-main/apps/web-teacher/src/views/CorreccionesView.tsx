/**
 * Vista de Correcciones — el docente ve y corrige entregas de los estudiantes.
 *
 * Layout:
 *   - EntregasListView: tabla de entregas filtrada por comision + estado.
 *     Columnas: estudiante (pseudonimo), TP, estado, submitted_at.
 *     Click en fila → drill-down a GradingFormView.
 *
 *   - GradingFormView: drill-down desde una entrega. Muestra:
 *     - Estado actual de ejercicios (lista ordenada con episode_id links).
 *     - Formulario de rubrica con campos: nota_final (0-10), feedback_general,
 *       criterios opcionales (puntaje + comentario).
 *     - Boton "Calificar" → POST /api/v1/entregas/{id}/calificar.
 *     - Boton "Devolver" (visible si ya fue calificada) → POST .../return.
 */
import { Badge, PageContainer } from "@platform/ui"
import { Link } from "@tanstack/react-router"
import { ArrowRight, ChevronLeft, FileCheck, Inbox } from "lucide-react"
import { useEffect, useState } from "react"
import {
  type CalificacionCreate,
  type EntregaDocente,
  type EntregaEstado,
  type StudentEpisode,
  type TareaPractica,
  entregasDocenteApi,
  extractFinalCode,
  getEpisodeEvents,
  getStudentEpisodes,
  tareasPracticasApi,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

interface Props {
  comisionId: string
  getToken: () => Promise<string | null>
}

const ESTADO_LABEL: Record<EntregaEstado, string> = {
  draft: "En progreso",
  submitted: "Enviada",
  graded: "Calificada",
  returned: "Devuelta",
}

const ESTADO_VARIANT: Record<EntregaEstado, "default" | "info" | "success" | "warning"> = {
  draft: "default",
  submitted: "info",
  graded: "success",
  returned: "warning",
}

// ─── Tipos internos ────────────────────────────────────────────────────

type CorreccionesPageView =
  | { kind: "list" }
  | { kind: "grading"; entrega: EntregaDocente; tarea: TareaPractica | null }

// ─── Componente principal ──────────────────────────────────────────────

export function CorreccionesView({ comisionId, getToken }: Props) {
  const [view, setView] = useState<CorreccionesPageView>({ kind: "list" })

  if (view.kind === "list") {
    return (
      <PageContainer
        title="Correcciones"
        description="Listado de entregas de la comisión. Filtrá por estado y abrí cada entrega para revisar el código del estudiante y aplicar la rúbrica."
        eyebrow="Inicio · Correcciones"
        helpContent={helpContent.correcciones}
      >
        <EntregasListView
          comisionId={comisionId}
          getToken={getToken}
          onSelectEntrega={(entrega, tarea) => setView({ kind: "grading", entrega, tarea })}
        />
      </PageContainer>
    )
  }

  return (
    <PageContainer
      title="Corregir entrega"
      description="Detalle del trabajo del estudiante por ejercicio. Cargá la nota y el feedback para devolverla."
      eyebrow="Inicio · Correcciones · Detalle"
      helpContent={helpContent.correcciones}
    >
      <GradingFormView
        entrega={view.entrega}
        tarea={view.tarea}
        getToken={getToken}
        onBack={() => setView({ kind: "list" })}
        onUpdated={(updated) => setView({ kind: "grading", entrega: updated, tarea: view.tarea })}
      />
    </PageContainer>
  )
}

// ─── EntregasListView (task 10.2) ──────────────────────────────────────

interface EntregasListViewProps {
  comisionId: string
  getToken: () => Promise<string | null>
  onSelectEntrega: (entrega: EntregaDocente, tarea: TareaPractica | null) => void
}

function EntregasListView({ comisionId, getToken, onSelectEntrega }: EntregasListViewProps) {
  const [entregas, setEntregas] = useState<EntregaDocente[]>([])
  const [tareasByID, setTareasByID] = useState<Record<string, TareaPractica>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [estadoFilter, setEstadoFilter] = useState<EntregaEstado | "">("")

  useEffect(() => {
    if (!comisionId) return
    let cancelled = false
    setLoading(true)
    setError(null)
    setEntregas([])

    entregasDocenteApi
      .list(
        {
          comision_id: comisionId,
          ...(estadoFilter ? { estado: estadoFilter as EntregaEstado } : {}),
        },
        getToken,
      )
      .then(async (resp) => {
        if (cancelled) return
        const data = resp.data
        setEntregas(data)

        // Fetch TPs para enriquecer la tabla (best-effort, no bloqueamos)
        const tareaIds = [...new Set(data.map((e) => e.tarea_practica_id))]
        const results = await Promise.allSettled(
          tareaIds.map((id) => tareasPracticasApi.get(id, getToken).then((t) => ({ id, t }))),
        )
        if (cancelled) return
        const map: Record<string, TareaPractica> = {}
        for (const r of results) {
          if (r.status === "fulfilled") map[r.value.id] = r.value.t
        }
        setTareasByID(map)
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
  }, [comisionId, estadoFilter, getToken])

  if (!comisionId) {
    return (
      <div className="rounded-2xl border border-dashed border-border bg-surface p-10 text-center animate-fade-in-up">
        <div className="inline-flex items-center justify-center rounded-full bg-surface-alt p-4 mb-4">
          <Inbox className="h-7 w-7 text-muted" />
        </div>
        <p className="text-sm text-muted">Seleccioná una comisión para ver las entregas.</p>
      </div>
    )
  }

  const counts: Record<EntregaEstado | "all", number> = {
    all: entregas.length,
    draft: entregas.filter((e) => e.estado === "draft").length,
    submitted: entregas.filter((e) => e.estado === "submitted").length,
    graded: entregas.filter((e) => e.estado === "graded").length,
    returned: entregas.filter((e) => e.estado === "returned").length,
  }

  return (
    <div className="space-y-5" data-testid="entregas-list-view">
      {/* Filter chips */}
      <div
        role="tablist"
        aria-label="Filtro por estado"
        className="flex items-center gap-1 bg-surface border border-border rounded-lg p-1 w-fit shadow-[0_1px_2px_0_rgba(0,0,0,0.04)] animate-fade-in-up"
      >
        {(["", "draft", "submitted", "graded", "returned"] as const).map((f) => {
          const label = f === "" ? "Todos" : ESTADO_LABEL[f as EntregaEstado]
          const key = f === "" ? "all" : (f as EntregaEstado)
          const active = estadoFilter === f
          return (
            <button
              key={f || "all"}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setEstadoFilter(f)}
              className={`press-shrink px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                active ? "bg-ink text-white" : "text-muted hover:text-ink hover:bg-surface-alt"
              }`}
            >
              {label}
              <span
                className={`ml-1.5 font-mono tabular-nums text-[10px] ${active ? "text-white/70" : "text-muted-soft"}`}
              >
                {counts[key]}
              </span>
            </button>
          )
        })}
      </div>

      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 animate-fade-in">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-32 rounded-xl" />
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-danger/30 bg-danger-soft p-4 animate-fade-in-up">
          <div className="text-sm font-semibold text-danger">No pudimos cargar las entregas</div>
          <div className="mt-1.5 font-mono text-xs text-danger/85 break-all">{error}</div>
        </div>
      )}

      {!loading && !error && entregas.length === 0 && (
        <div className="rounded-2xl border border-dashed border-border bg-surface p-10 text-center animate-fade-in-up">
          <div className="inline-flex items-center justify-center rounded-full bg-surface-alt p-4 mb-4">
            <FileCheck className="h-7 w-7 text-muted" />
          </div>
          <p className="text-sm text-muted leading-relaxed max-w-md mx-auto">
            {estadoFilter
              ? `No hay entregas con estado "${ESTADO_LABEL[estadoFilter as EntregaEstado]}".`
              : "Esta comision aun no tiene entregas registradas."}
          </p>
        </div>
      )}

      {!loading && !error && entregas.length > 0 && (
        <ul
          className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
          data-testid="entregas-table"
        >
          {entregas.map((entrega, idx) => {
            const tarea = tareasByID[entrega.tarea_practica_id]
            const isSubmitted = entrega.estado === "submitted"
            return (
              <li
                key={entrega.id}
                data-testid="entrega-row"
                className="animate-fade-in-up"
                style={{ animationDelay: `${Math.min(idx, 6) * 50}ms` }}
              >
                <button
                  type="button"
                  data-testid="entrega-drill-btn"
                  onClick={() => onSelectEntrega(entrega, tarea ?? null)}
                  className="hover-lift press-shrink group relative w-full overflow-hidden rounded-xl border border-border bg-surface flex flex-col h-full text-left shadow-[0_1px_2px_0_rgba(0,0,0,0.04)]"
                >
                  <div
                    aria-hidden="true"
                    className={`absolute left-0 top-0 bottom-0 w-1 transition-opacity ${
                      isSubmitted
                        ? "bg-accent-brand opacity-70 group-hover:opacity-100"
                        : "bg-border-strong opacity-30 group-hover:opacity-60"
                    }`}
                  />
                  <div className="p-4 flex-1 flex flex-col gap-3">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <span className="font-mono text-[11px] uppercase tracking-wider text-muted px-2 py-0.5 rounded bg-surface-alt border border-border-soft">
                        {entrega.student_pseudonym.slice(0, 8)}…
                      </span>
                      <span data-testid={`entrega-estado-${entrega.estado}`}>
                        <Badge variant={ESTADO_VARIANT[entrega.estado]}>
                          {ESTADO_LABEL[entrega.estado]}
                        </Badge>
                      </span>
                    </div>
                    <div className="min-w-0">
                      {tarea ? (
                        <>
                          <div className="text-[11px] font-mono text-muted mb-0.5">
                            {tarea.codigo}
                          </div>
                          <h3
                            className="text-[14px] font-semibold text-ink leading-tight tracking-tight line-clamp-2"
                            title={tarea.titulo}
                          >
                            {tarea.titulo}
                          </h3>
                        </>
                      ) : (
                        <span className="font-mono text-xs text-muted">
                          TP: {entrega.tarea_practica_id.slice(0, 8)}…
                        </span>
                      )}
                    </div>
                    <div className="flex items-center justify-between gap-2 mt-auto pt-2 border-t border-border-soft">
                      <span className="text-[10px] uppercase tracking-wider text-muted-soft">
                        Enviada
                      </span>
                      <span className="text-xs text-body tabular-nums font-mono">
                        {entrega.submitted_at
                          ? new Date(entrega.submitted_at).toLocaleString("es-AR", {
                              day: "2-digit",
                              month: "2-digit",
                              year: "2-digit",
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : "—"}
                      </span>
                    </div>
                  </div>
                  <footer
                    className={`flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium border-t border-border-soft ${
                      isSubmitted
                        ? "text-accent-brand-deep bg-accent-brand-soft/40 group-hover:bg-accent-brand-soft"
                        : "text-muted group-hover:bg-surface-alt"
                    } transition-colors`}
                  >
                    {isSubmitted ? "Corregir" : "Ver detalle"}
                    <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                  </footer>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

// ─── EjercicioPanel (codigo del estudiante por episodio) ───────────────

interface EjercicioPanelProps {
  ej: { orden: number; completado: boolean; completado_at: string | null }
  resolvedEpisodeId: string | null
  tarea: TareaPractica | null
  getToken: () => Promise<string | null>
}

function EjercicioPanel({ ej, resolvedEpisodeId, tarea, getToken }: EjercicioPanelProps) {
  const [expanded, setExpanded] = useState(false)
  const [code, setCode] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)

  const ejercicioInfo = tarea?.ejercicios?.find((e) => e.orden === ej.orden)

  function handleToggle() {
    const next = !expanded
    setExpanded(next)
    if (next && code === null && !loading && resolvedEpisodeId) {
      setLoading(true)
      setFetchError(null)
      getEpisodeEvents(resolvedEpisodeId, getToken)
        .then((ep) => {
          const finalCode = extractFinalCode(ep.events)
          setCode(finalCode ?? "// Sin codigo registrado")
        })
        .catch((e) => setFetchError(String(e)))
        .finally(() => setLoading(false))
    }
  }

  return (
    <div
      className="border border-border rounded-lg overflow-hidden"
      data-testid={`ej-estado-${ej.orden}`}
    >
      <button
        type="button"
        onClick={handleToggle}
        className="w-full flex items-center gap-3 px-4 py-3 text-sm hover:bg-canvas transition-colors text-left"
      >
        <span
          className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-mono ${
            ej.completado ? "bg-success text-white" : "bg-surface-alt text-muted"
          }`}
        >
          {ej.completado ? "✓" : ej.orden}
        </span>
        <span className="text-ink flex-1">
          {ejercicioInfo ? ejercicioInfo.titulo : `Ejercicio ${ej.orden}`}
        </span>
        {resolvedEpisodeId && (
          <span className="text-xs font-mono text-muted">ep: {resolvedEpisodeId.slice(0, 8)}…</span>
        )}
        <span className="text-muted text-xs">{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div className="border-t border-border bg-canvas">
          {!resolvedEpisodeId && (
            <p className="px-4 py-3 text-xs text-muted">Sin episodio asociado a este ejercicio.</p>
          )}

          {resolvedEpisodeId && loading && (
            <div className="flex items-center justify-center py-6">
              <div
                className="inline-block w-4 h-4 border-2 border-t-transparent rounded-full motion-safe:animate-spin"
                style={{ borderColor: "var(--color-accent-brand)", borderTopColor: "transparent" }}
              />
            </div>
          )}

          {fetchError && <p className="px-4 py-3 text-xs text-danger">{fetchError}</p>}

          {code !== null && !loading && (
            <pre className="px-4 py-3 text-xs font-mono text-ink overflow-x-auto whitespace-pre max-h-[400px] overflow-y-auto">
              {code}
            </pre>
          )}

          {resolvedEpisodeId && (
            <div className="px-4 py-2 border-t border-border flex items-center gap-3">
              <Link
                to="/episode-n-level"
                search={{ episodeId: resolvedEpisodeId }}
                className="text-xs font-mono text-muted hover:text-ink hover:underline"
                data-testid={`ep-link-${ej.orden}`}
              >
                Ver niveles N1-N4 →
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── GradingFormView (tasks 10.3, 10.4, 10.5) ─────────────────────────

interface GradingFormViewProps {
  entrega: EntregaDocente
  tarea: TareaPractica | null
  getToken: () => Promise<string | null>
  onBack: () => void
  onUpdated: (updated: EntregaDocente) => void
}

function GradingFormView({ entrega, tarea, getToken, onBack, onUpdated }: GradingFormViewProps) {
  const [nota, setNota] = useState<string>("")
  const [feedback, setFeedback] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [calificacion, setCalificacion] = useState<{
    nota_final: number
    feedback_general: string
    graded_at: string
  } | null>(null)
  const [loadingCalificacion, setLoadingCalificacion] = useState(false)
  const [devolviendo, setDevolviendo] = useState(false)

  const yaCalificada = entrega.estado === "graded" || entrega.estado === "returned"

  // Resolver episode_ids: primero de ejercicio_estados, fallback a analytics (por orden temporal)
  const [resolvedEpisodeMap, setResolvedEpisodeMap] = useState<Record<number, string>>({})

  useEffect(() => {
    const estados = entrega.ejercicio_estados ?? []
    const allHaveEpisodeId = estados.every((e) => e.episode_id)
    if (allHaveEpisodeId && estados.length > 0) {
      const map: Record<number, string> = {}
      for (const e of estados) {
        if (e.episode_id) map[e.orden] = e.episode_id
      }
      setResolvedEpisodeMap(map)
      return
    }

    if (!tarea) return
    getStudentEpisodes(entrega.student_pseudonym, entrega.comision_id, getToken)
      .then((payload) => {
        const tpEpisodes = (payload.episodes ?? [])
          .filter(
            (ep: StudentEpisode) => ep.problema_id === entrega.tarea_practica_id && ep.closed_at,
          )
          .sort(
            (a: StudentEpisode, b: StudentEpisode) =>
              new Date(a.opened_at ?? 0).getTime() - new Date(b.opened_at ?? 0).getTime(),
          )

        const map: Record<number, string> = {}
        for (const e of estados) {
          if (e.episode_id) {
            map[e.orden] = e.episode_id
          }
        }
        // Fill missing from temporal order
        let epIdx = 0
        for (const e of estados.slice().sort((a, b) => a.orden - b.orden)) {
          if (!map[e.orden] && epIdx < tpEpisodes.length) {
            const ep = tpEpisodes[epIdx]
            if (ep) map[e.orden] = ep.episode_id
            epIdx++
          }
        }
        setResolvedEpisodeMap(map)
      })
      .catch(() => {})
  }, [
    entrega.id,
    entrega.student_pseudonym,
    entrega.comision_id,
    entrega.tarea_practica_id,
    tarea,
    getToken,
  ])

  // Cargar calificacion existente si la hay
  useEffect(() => {
    if (!yaCalificada) return
    let cancelled = false
    setLoadingCalificacion(true)
    entregasDocenteApi
      .getCalificacion(entrega.id, getToken)
      .then((c) => {
        if (cancelled || !c) return
        setCalificacion(c)
        setNota(String(c.nota_final))
        setFeedback(c.feedback_general)
      })
      .finally(() => {
        if (!cancelled) setLoadingCalificacion(false)
      })
    return () => {
      cancelled = true
    }
  }, [entrega.id, yaCalificada, getToken])

  async function handleCalificar() {
    const notaNum = Number.parseFloat(nota)
    if (Number.isNaN(notaNum) || notaNum < 0 || notaNum > 10) {
      setSubmitError("La nota debe ser un numero entre 0 y 10.")
      return
    }
    if (!feedback.trim()) {
      setSubmitError("El feedback general es obligatorio.")
      return
    }
    setSubmitting(true)
    setSubmitError(null)
    try {
      const body: CalificacionCreate = {
        nota_final: notaNum,
        feedback_general: feedback.trim(),
      }
      await entregasDocenteApi.calificar(entrega.id, body, getToken)
      // Refetch entrega para tener estado=graded actualizado
      const updated = await entregasDocenteApi.get(entrega.id, getToken)
      onUpdated(updated)
    } catch (e) {
      setSubmitError(String(e))
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDevolver() {
    setDevolviendo(true)
    setSubmitError(null)
    try {
      const updated = await entregasDocenteApi.devolver(entrega.id, getToken)
      onUpdated(updated)
    } catch (e) {
      setSubmitError(String(e))
    } finally {
      setDevolviendo(false)
    }
  }

  return (
    <div className="space-y-6 max-w-3xl" data-testid="grading-form-view">
      <button
        type="button"
        onClick={onBack}
        className="press-shrink text-xs text-muted hover:text-ink inline-flex items-center gap-1.5 transition-colors"
      >
        <ChevronLeft className="h-3.5 w-3.5" />
        Volver a entregas
      </button>

      {/* Cabecera de la entrega */}
      <div className="rounded-xl border border-border bg-surface p-5 shadow-[0_1px_2px_0_rgba(0,0,0,0.04)] animate-fade-in-up">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <p className="text-xs font-mono text-muted mb-1">Entrega #{entrega.id.slice(0, 8)}</p>
            {tarea && (
              <h3 className="text-base font-semibold text-ink mb-1">
                <span className="text-muted mr-1.5 font-mono text-sm">{tarea.codigo}</span>
                {tarea.titulo}
              </h3>
            )}
            <p className="text-xs text-muted font-mono">
              Estudiante: {entrega.student_pseudonym.slice(0, 12)}…
            </p>
          </div>
          <Badge variant={ESTADO_VARIANT[entrega.estado]}>{ESTADO_LABEL[entrega.estado]}</Badge>
        </div>
      </div>

      {/* Ejercicios con codigo */}
      {entrega.ejercicio_estados && entrega.ejercicio_estados.length > 0 && (
        <div className="rounded-xl border border-border bg-surface p-5 shadow-[0_1px_2px_0_rgba(0,0,0,0.04)]">
          <p className="text-xs font-mono uppercase tracking-wider text-muted mb-4">Ejercicios</p>
          <div className="space-y-3" data-testid="ejercicios-estados-list">
            {entrega.ejercicio_estados
              .slice()
              .sort((a, b) => a.orden - b.orden)
              .map((ej) => (
                <EjercicioPanel
                  key={ej.orden}
                  ej={ej}
                  resolvedEpisodeId={resolvedEpisodeMap[ej.orden] ?? null}
                  tarea={tarea}
                  getToken={getToken}
                />
              ))}
          </div>
        </div>
      )}

      {/* Formulario de calificacion */}
      <div className="rounded-xl border border-border bg-surface p-5 shadow-[0_1px_2px_0_rgba(0,0,0,0.04)]">
        <p className="text-xs font-mono uppercase tracking-wider text-muted mb-4">
          {yaCalificada && !loadingCalificacion ? "Calificacion" : "Calificar entrega"}
        </p>

        {loadingCalificacion && (
          <div className="flex items-center justify-center py-6">
            <div
              className="inline-block w-5 h-5 border-2 border-t-transparent rounded-full motion-safe:animate-spin"
              style={{ borderColor: "var(--color-accent-brand)", borderTopColor: "transparent" }}
            />
          </div>
        )}

        {!loadingCalificacion && (
          <div className="space-y-4">
            {/* Nota final */}
            <div>
              <label htmlFor="nota-final" className="block text-sm font-medium text-ink mb-1.5">
                Nota final <span className="font-normal text-muted">(0 a 10)</span>
              </label>
              <input
                id="nota-final"
                type="number"
                min="0"
                max="10"
                step="0.5"
                value={nota}
                onChange={(e) => setNota(e.target.value)}
                disabled={yaCalificada}
                data-testid="nota-final-input"
                className="w-28 border border-border rounded px-3 py-2 text-sm text-ink bg-surface focus:outline-none focus:ring-1 focus:ring-ink disabled:bg-surface-alt disabled:text-muted"
                placeholder="ej. 7.5"
              />
            </div>

            {/* Feedback general */}
            <div>
              <label htmlFor="feedback" className="block text-sm font-medium text-ink mb-1.5">
                Feedback general
              </label>
              <textarea
                id="feedback"
                rows={5}
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                disabled={yaCalificada}
                data-testid="feedback-input"
                className="w-full border border-border rounded px-3 py-2 text-sm text-ink bg-surface focus:outline-none focus:ring-1 focus:ring-ink disabled:bg-surface-alt disabled:text-muted resize-none"
                placeholder="Describe los puntos fuertes y de mejora de la entrega..."
              />
            </div>

            {calificacion && (
              <p className="text-xs text-muted font-mono">
                Calificado el{" "}
                {new Date(calificacion.graded_at).toLocaleString("es-AR", {
                  day: "2-digit",
                  month: "2-digit",
                  year: "2-digit",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </p>
            )}

            {submitError && (
              <div className="rounded-lg border border-danger/30 bg-danger-soft p-3 text-xs text-danger">
                {submitError}
              </div>
            )}

            {/* Acciones */}
            <div className="flex items-center gap-3 pt-2 flex-wrap">
              {/* Boton Calificar — solo si aun no fue calificada */}
              {entrega.estado === "submitted" && (
                <button
                  type="button"
                  onClick={() => void handleCalificar()}
                  disabled={submitting}
                  data-testid="calificar-btn"
                  className="px-4 py-2 rounded text-sm font-medium text-white disabled:opacity-60"
                  style={{ backgroundColor: "var(--color-accent-brand)" }}
                  onMouseEnter={(e) => {
                    if (!submitting)
                      e.currentTarget.style.backgroundColor = "var(--color-accent-brand-deep)"
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = "var(--color-accent-brand)"
                  }}
                >
                  {submitting ? "Guardando..." : "Calificar"}
                </button>
              )}

              {/* Boton Devolver — solo si ya fue calificada (graded) */}
              {entrega.estado === "graded" && (
                <button
                  type="button"
                  onClick={() => void handleDevolver()}
                  disabled={devolviendo}
                  data-testid="devolver-btn"
                  className="press-shrink px-4 py-2 rounded-md text-sm font-medium border border-border bg-surface text-ink hover:bg-surface-alt disabled:opacity-60 transition-colors"
                >
                  {devolviendo ? "Devolviendo..." : "Devolver al estudiante"}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
