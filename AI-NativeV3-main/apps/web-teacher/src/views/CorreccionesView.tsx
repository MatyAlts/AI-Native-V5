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
import { Badge, Input, PageContainer } from "@platform/ui"
import { Link } from "@tanstack/react-router"
import { ArrowRight, ChevronLeft, FileCheck, Inbox, Search, X } from "lucide-react"
import { useEffect, useState } from "react"
import { useStudentProfiles } from "../hooks/useStudentProfiles"
import {
  type CalificacionCreate,
  type EjercicioEstado,
  type EntregaDocente,
  type EntregaEstado,
  type StudentEpisode,
  type TareaPractica,
  type TpEjercicio,
  entregasDocenteApi,
  extractFinalCode,
  getEpisodeEvents,
  getStudentEpisodes,
  tareasPracticasApi,
  tpEjerciciosApi,
} from "../lib/api"
import { studentShortLabel } from "../utils/docenteLabels"
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
  // Búsqueda por alumno (FR-5): filtra la lista en vivo por el dato de alumno
  // que la fila ya muestra — el nombre real (si el alumno se logueó) o el
  // pseudónimo corto (`Est. xxxxxx`). Se busca también contra el pseudónimo
  // completo por si el docente pega/escribe el UUID.
  const [studentQuery, setStudentQuery] = useState("")
  const profilesMap = useStudentProfiles(comisionId, getToken)

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
          // Enriquecimiento best-effort: si una TP falla, la fila cae al
          // fallback "TP: {id}", pero dejamos rastro en consola (no lo tragamos).
          else console.error("[CorreccionesView] no se pudo cargar una TP:", r.reason)
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

  // Filtro client-side por alumno sobre lo YA cargado. LIMITACIÓN: el listado
  // pagina server-side (cursor/limit en `entregasDocenteApi.list`) pero esta
  // vista sólo trae la primera página, así que la búsqueda alcanza únicamente
  // a las entregas cargadas. Emparejamos contra el label visible
  // (`studentShortLabel`: nombre real o `Est. xxxxxx`) y también contra el
  // pseudónimo crudo. FOLLOW-UP: pasar el término al backend para búsqueda
  // paginada real cuando `list` acepte un filtro por alumno.
  const q = studentQuery.trim().toLowerCase()
  const filteredEntregas = q
    ? entregas.filter(
        (e) =>
          studentShortLabel(e.student_pseudonym, profilesMap).toLowerCase().includes(q) ||
          e.student_pseudonym.toLowerCase().includes(q),
      )
    : entregas

  return (
    <div className="space-y-5" data-testid="entregas-list-view">
      {/* Toolbar: filtro por estado + búsqueda por alumno */}
      <div className="flex flex-wrap items-center justify-between gap-3">
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

        {/* Búsqueda por alumno (FR-5) */}
        {entregas.length > 0 && (
          <div className="relative w-full sm:w-64 animate-fade-in-up">
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-soft"
            />
            <Input
              type="text"
              value={studentQuery}
              onChange={(e) => setStudentQuery(e.target.value)}
              placeholder="Buscar por alumno..."
              aria-label="Buscar entregas por alumno"
              data-testid="entregas-student-search"
              className="pl-9 pr-9"
            />
            {studentQuery && (
              <button
                type="button"
                onClick={() => setStudentQuery("")}
                aria-label="Limpiar busqueda"
                data-testid="entregas-student-search-clear"
                className="press-shrink absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-soft hover:text-ink hover:bg-surface-alt transition-colors"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        )}
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

      {/* Búsqueda sin resultados: hay entregas cargadas pero ninguna coincide. */}
      {!loading && !error && entregas.length > 0 && filteredEntregas.length === 0 && (
        <div
          className="rounded-2xl border border-dashed border-border bg-surface p-10 text-center animate-fade-in-up"
          data-testid="entregas-search-empty"
        >
          <div className="inline-flex items-center justify-center rounded-full bg-surface-alt p-4 mb-4">
            <Search className="h-7 w-7 text-muted" />
          </div>
          <p className="text-sm text-muted leading-relaxed max-w-md mx-auto">
            Ningún alumno coincide con “{studentQuery.trim()}”.
            <span className="block mt-1 text-xs text-muted-soft">
              La búsqueda alcanza solo a las entregas ya cargadas en esta página.
            </span>
          </p>
        </div>
      )}

      {!loading && !error && filteredEntregas.length > 0 && (
        <ul
          className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
          data-testid="entregas-table"
        >
          {filteredEntregas.map((entrega, idx) => {
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
                      <span
                        className="text-[11px] font-semibold tracking-wide text-ink px-2 py-0.5 rounded bg-surface-alt border border-border-soft"
                        title={entrega.student_pseudonym}
                      >
                        {studentShortLabel(entrega.student_pseudonym, profilesMap)}
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

// Resuelve el titulo real de un ejercicio de la entrega contra la composicion
// de la TP (tp_ejercicios, ADR-047). Empareja por `ejercicio_id` (identidad
// estable): si el orden cambio, el feedback sigue apuntando al ejercicio
// correcto. Fallback a `orden` solo para entregas legacy sin `ejercicio_id`.
function resolveTituloEjercicio(ej: EjercicioEstado, tpEjercicios: TpEjercicio[]): string | null {
  const match = ej.ejercicio_id
    ? tpEjercicios.find((t) => t.ejercicio_id === ej.ejercicio_id)
    : tpEjercicios.find((t) => t.orden === ej.orden)
  return match?.ejercicio.titulo ?? null
}

// ─── EjercicioPanel (codigo del estudiante por episodio) ───────────────

interface EjercicioPanelProps {
  ej: { orden: number; completado: boolean; completed_at: string | null }
  resolvedEpisodeId: string | null
  // Titulo real del ejercicio, ya resuelto por el padre (match por ejercicio_id).
  // `null` = no se pudo resolver → cae al fallback "Ejercicio {orden}".
  titulo: string | null
  getToken: () => Promise<string | null>
}

function EjercicioPanel({ ej, resolvedEpisodeId, titulo, getToken }: EjercicioPanelProps) {
  const [expanded, setExpanded] = useState(false)
  const [code, setCode] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)

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
        <span className="text-ink flex-1">{titulo ?? `Ejercicio ${ej.orden}`}</span>
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

// Re-calificacion in-place (NB-4 / BUG-3). El backend ya expone
// `PATCH /api/v1/entregas/{id}/calificacion` para actualizar la nota ya puesta
// (el `POST /calificar` responde 409 si ya existe y el UNIQUE(entrega_id) bloquea
// insertar una segunda). `lib/api.ts` todavia NO tiene un metodo para este PATCH
// y en este cambio no podemos tocar api.ts; por eso el fetch va inline aca,
// replicando el minimo de authHeaders/throwIfNotOk del API layer.
// FOLLOW-UP: mover esto a `entregasDocenteApi.recalificar` en `lib/api.ts`.
async function recalificarEntrega(
  entregaId: string,
  body: CalificacionCreate,
  getToken: () => Promise<string | null>,
): Promise<void> {
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  const token = await getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const r = await fetch(`/api/v1/entregas/${entregaId}/calificacion`, {
    method: "PATCH",
    headers,
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    const raw = await r.text()
    let detail = raw
    try {
      const parsed = JSON.parse(raw)
      detail = parsed.detail ?? parsed.title ?? raw
    } catch {
      /* respuesta no-JSON: usamos el texto crudo */
    }
    throw new Error(`${r.status}: ${detail}`)
  }
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
  const profilesMap = useStudentProfiles(entrega.comision_id, getToken)
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
  const [calificacionError, setCalificacionError] = useState<string | null>(null)
  const [episodeResolveError, setEpisodeResolveError] = useState<string | null>(null)
  const [devolviendo, setDevolviendo] = useState(false)
  // Reapertura del form para re-calificar una entrega ya calificada (BUG-3).
  // Mientras es `false`, los campos quedan `disabled` (solo lectura de la nota).
  const [reediting, setReediting] = useState(false)

  const yaCalificada = entrega.estado === "graded" || entrega.estado === "returned"

  // Resolver episode_ids: primero de ejercicio_estados, fallback a analytics (por orden temporal)
  const [resolvedEpisodeMap, setResolvedEpisodeMap] = useState<Record<number, string>>({})

  // Composicion de la TP (tp_ejercicios, ADR-047): fuente del titulo real de
  // cada ejercicio + su `ejercicio_id` estable. `getTareaPractica` no popula
  // `tarea.ejercicios`, por eso se carga aca aparte (best-effort).
  const [tpEjercicios, setTpEjercicios] = useState<TpEjercicio[]>([])

  useEffect(() => {
    let cancelled = false
    tpEjerciciosApi
      .list(entrega.tarea_practica_id, getToken)
      .then((items) => {
        if (!cancelled) setTpEjercicios(items)
      })
      .catch((e) => {
        // Sin la composicion no resolvemos titulos → caemos al fallback
        // "Ejercicio {orden}". Es degradacion aceptable, pero la reportamos.
        if (!cancelled) setTpEjercicios([])
        console.error("[CorreccionesView] no se pudo cargar la composicion de la TP:", e)
      })
    return () => {
      cancelled = true
    }
  }, [entrega.tarea_practica_id, getToken])

  useEffect(() => {
    const estados = entrega.ejercicio_estados ?? []
    setEpisodeResolveError(null)
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
      .catch((e) => {
        // Fallback: mapear al menos los episode_id que ya venian en los estados,
        // asi no perdemos los enlaces que si teniamos. Y avisamos al docente que
        // la resolucion quedo incompleta en vez de tragar el error.
        const fallback: Record<number, string> = {}
        for (const est of estados) {
          if (est.episode_id) fallback[est.orden] = est.episode_id
        }
        setResolvedEpisodeMap(fallback)
        setEpisodeResolveError(
          "No pudimos resolver todos los episodios de esta entrega; algunos ejercicios pueden aparecer sin enlace al detalle.",
        )
        console.error("[CorreccionesView] no se pudieron resolver los episodios:", e)
      })
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
    setCalificacionError(null)
    entregasDocenteApi
      .getCalificacion(entrega.id, getToken)
      .then((c) => {
        if (cancelled) return
        if (!c) {
          // La entrega figura como calificada pero no vino la calificacion:
          // NO dejar el form vacio en silencio (bug NB-21).
          setCalificacionError(
            "Esta entrega figura como calificada pero no pudimos recuperar la nota y el feedback guardados. Recargá la página o volvé a intentar.",
          )
          return
        }
        setCalificacion(c)
        setNota(String(c.nota_final))
        setFeedback(c.feedback_general)
      })
      .catch((e) => {
        if (!cancelled) setCalificacionError(String(e))
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

  // Guardar una re-calificacion (PATCH in-place, NB-4). Mismo criterio de
  // validacion que `handleCalificar` + guard anti doble-submit por `submitting`.
  // El docente sigue gobernando la nota: solo se llega aca desde el web-teacher
  // y el backend exige permiso calificacion:update.
  async function handleRecalificar() {
    if (submitting) return
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
      await recalificarEntrega(
        entrega.id,
        { nota_final: notaNum, feedback_general: feedback.trim() },
        getToken,
      )
      // Refetch para reflejar la nota vigente y normalizar estado a 'graded'.
      const updated = await entregasDocenteApi.get(entrega.id, getToken)
      setReediting(false)
      onUpdated(updated)
    } catch (e) {
      setSubmitError(String(e))
    } finally {
      setSubmitting(false)
    }
  }

  // Cancelar la reapertura: restaura los campos a la calificacion cargada y
  // vuelve a modo solo-lectura sin persistir nada.
  function handleCancelReedit() {
    setReediting(false)
    setSubmitError(null)
    if (calificacion) {
      setNota(String(calificacion.nota_final))
      setFeedback(calificacion.feedback_general)
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
            <p className="text-xs text-muted" title={entrega.student_pseudonym}>
              Estudiante: {studentShortLabel(entrega.student_pseudonym, profilesMap)}
            </p>
          </div>
          <Badge variant={ESTADO_VARIANT[entrega.estado]}>{ESTADO_LABEL[entrega.estado]}</Badge>
        </div>
      </div>

      {/* Ejercicios con codigo */}
      {entrega.ejercicio_estados && entrega.ejercicio_estados.length > 0 && (
        <div className="rounded-xl border border-border bg-surface p-5 shadow-[0_1px_2px_0_rgba(0,0,0,0.04)]">
          <p className="text-xs font-mono uppercase tracking-wider text-muted mb-4">Ejercicios</p>
          {episodeResolveError && (
            <div
              className="mb-4 rounded-lg border border-warning/30 bg-warning-soft p-3 text-xs text-warning"
              data-testid="episode-resolve-error"
            >
              {episodeResolveError}
            </div>
          )}
          <div className="space-y-3" data-testid="ejercicios-estados-list">
            {entrega.ejercicio_estados
              .slice()
              .sort((a, b) => a.orden - b.orden)
              .map((ej) => (
                <EjercicioPanel
                  key={ej.ejercicio_id ?? ej.orden}
                  ej={ej}
                  resolvedEpisodeId={resolvedEpisodeMap[ej.orden] ?? null}
                  titulo={resolveTituloEjercicio(ej, tpEjercicios)}
                  getToken={getToken}
                />
              ))}
          </div>
        </div>
      )}

      {/* Formulario de calificacion */}
      <div className="rounded-xl border border-border bg-surface p-5 shadow-[0_1px_2px_0_rgba(0,0,0,0.04)]">
        <p className="text-xs font-mono uppercase tracking-wider text-muted mb-4">
          {reediting
            ? "Re-calificar entrega"
            : yaCalificada && !loadingCalificacion
              ? "Calificacion"
              : "Calificar entrega"}
        </p>

        {loadingCalificacion && (
          <div className="flex items-center justify-center py-6">
            <div
              className="inline-block w-5 h-5 border-2 border-t-transparent rounded-full motion-safe:animate-spin"
              style={{ borderColor: "var(--color-accent-brand)", borderTopColor: "transparent" }}
            />
          </div>
        )}

        {!loadingCalificacion && calificacionError && (
          <div
            className="mb-4 rounded-lg border border-danger/30 bg-danger-soft p-3 text-xs text-danger"
            data-testid="calificacion-load-error"
          >
            {calificacionError}
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
                disabled={yaCalificada && !reediting}
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
                disabled={yaCalificada && !reediting}
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

              {/* Boton Re-calificar — reabre el form de una entrega ya
                  calificada con la nota/feedback actuales (BUG-3 / NB-4) */}
              {yaCalificada && !reediting && (
                <button
                  type="button"
                  onClick={() => {
                    setReediting(true)
                    setSubmitError(null)
                  }}
                  data-testid="reeditar-btn"
                  className="press-shrink px-4 py-2 rounded-md text-sm font-medium border border-border bg-surface text-ink hover:bg-surface-alt transition-colors"
                >
                  Re-calificar
                </button>
              )}

              {/* Modo re-calificacion: guardar (PATCH) + cancelar */}
              {reediting && (
                <>
                  <button
                    type="button"
                    onClick={() => void handleRecalificar()}
                    disabled={submitting}
                    data-testid="guardar-recalificacion-btn"
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
                    {submitting ? "Guardando..." : "Guardar cambios"}
                  </button>
                  <button
                    type="button"
                    onClick={handleCancelReedit}
                    disabled={submitting}
                    data-testid="cancelar-recalificacion-btn"
                    className="press-shrink px-4 py-2 rounded-md text-sm font-medium border border-border bg-surface text-ink hover:bg-surface-alt disabled:opacity-60 transition-colors"
                  >
                    Cancelar
                  </button>
                </>
              )}

              {/* Boton Devolver — solo si ya fue calificada (graded) y no se
                  esta re-calificando (evita acciones ambiguas mid-edit) */}
              {entrega.estado === "graded" && !reediting && (
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
