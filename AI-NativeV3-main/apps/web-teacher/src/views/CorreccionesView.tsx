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
import { useInfiniteQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import {
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  FileCheck,
  Inbox,
  Layers,
  Search,
  SkipForward,
  X,
} from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
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

// Un item de la cola de corrección en lote (F5): la entrega + su TP ya
// resuelta (para el título/código en la cabecera del form). El `tarea` puede ser
// `null` si el enriquecimiento best-effort de la TP falló en la lista.
interface QueueItem {
  entrega: EntregaDocente
  tarea: TareaPractica | null
}

type CorreccionesPageView =
  | { kind: "list" }
  | { kind: "grading"; entrega: EntregaDocente; tarea: TareaPractica | null }
  // Corrección en lote (F5): recorre una cola de entregas pendientes con
  // auto-avance tras cada calificación. La cola es un snapshot armado en el
  // cliente desde la lista ya filtrada (comisión + estado + búsqueda alumno).
  | { kind: "queue"; queue: QueueItem[] }

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
          onStartBatch={(queue) => setView({ kind: "queue", queue })}
        />
      </PageContainer>
    )
  }

  if (view.kind === "queue") {
    return (
      <PageContainer
        title="Corregir en lote"
        description="Cola de corrección: calificá cada entrega pendiente y avanzá automáticamente a la siguiente sin volver a la lista."
        eyebrow="Inicio · Correcciones · Lote"
        helpContent={helpContent.correcciones}
      >
        <BatchGradingView
          queue={view.queue}
          getToken={getToken}
          onExit={() => setView({ kind: "list" })}
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
  // Arranca la cola de corrección en lote (F5) con el snapshot de pendientes.
  onStartBatch: (queue: QueueItem[]) => void
}

function EntregasListView({
  comisionId,
  getToken,
  onSelectEntrega,
  onStartBatch,
}: EntregasListViewProps) {
  const [tareasByID, setTareasByID] = useState<Record<string, TareaPractica>>({})
  const [estadoFilter, setEstadoFilter] = useState<EntregaEstado | "">("")
  // Búsqueda por alumno (FR-5): filtra la lista en vivo por el dato de alumno
  // que la fila ya muestra — el nombre real (si el alumno se logueó) o el
  // pseudónimo corto (`Est. xxxxxx`). Se busca también contra el pseudónimo
  // completo por si el docente pega/escribe el UUID.
  const [studentQuery, setStudentQuery] = useState("")
  const profilesMap = useStudentProfiles(comisionId, getToken)
  // TPs que ya intentamos cargar (ok o falladas) para no re-pedirlas en cada
  // render / página nueva. Enriquecimiento best-effort; una TP que falla no se
  // reintenta. Keyeado por `tarea_practica_id` (UUID único por instancia,
  // ADR-016) → no colisiona entre comisiones, no necesita reset.
  const attemptedTareaIds = useRef<Set<string>>(new Set())

  // Paginación real (FR-3): `entregasDocenteApi.list` pagina server-side por
  // cursor. `useInfiniteQuery` sigue `meta.cursor_next` y acumula las páginas;
  // el botón "Cargar más" hace append sin pisar lo previo. El filtro por estado
  // es server-side (parte de la queryKey → resetea la cache al cambiar); la
  // búsqueda por alumno (FR-5) es client-side sobre TODO el set acumulado.
  const query = useInfiniteQuery({
    queryKey: ["entregas-docente", comisionId, estadoFilter],
    queryFn: ({ pageParam }) =>
      entregasDocenteApi.list(
        {
          comision_id: comisionId,
          ...(estadoFilter ? { estado: estadoFilter as EntregaEstado } : {}),
          ...(pageParam ? { cursor: pageParam } : {}),
        },
        getToken,
      ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.meta.cursor_next ?? undefined,
    enabled: !!comisionId,
  })

  // Entregas acumuladas across todas las páginas cargadas. El filtro de estado y
  // la búsqueda operan sobre este set (que crece con cada "Cargar más").
  const entregas = useMemo<EntregaDocente[]>(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  )

  // `loading` = primer fetch sin datos aún (muestra skeletons). Los fetch de
  // páginas siguientes NO reemplazan la lista (van al botón "Cargar más").
  const loading = query.isLoading && !!comisionId
  const error = query.error ? String(query.error) : null

  // Enriquecimiento de TPs (best-effort): por cada tarea_practica_id nuevo en el
  // set acumulado que aún no intentamos, pedimos la TP para mostrar código +
  // título en la fila. Marcamos el id como intentado antes de disparar para no
  // duplicar pedidos entre páginas.
  useEffect(() => {
    if (entregas.length === 0) return
    const missing = [...new Set(entregas.map((e) => e.tarea_practica_id))].filter(
      (id) => !attemptedTareaIds.current.has(id),
    )
    if (missing.length === 0) return
    for (const id of missing) attemptedTareaIds.current.add(id)
    let cancelled = false
    Promise.allSettled(
      missing.map((id) => tareasPracticasApi.get(id, getToken).then((t) => ({ id, t }))),
    ).then((results) => {
      if (cancelled) return
      const map: Record<string, TareaPractica> = {}
      for (const r of results) {
        if (r.status === "fulfilled") map[r.value.id] = r.value.t
        // Si una TP falla, la fila cae al fallback "TP: {id}", pero dejamos
        // rastro en consola (no lo tragamos).
        else console.error("[CorreccionesView] no se pudo cargar una TP:", r.reason)
      }
      if (Object.keys(map).length > 0) setTareasByID((prev) => ({ ...prev, ...map }))
    })
    return () => {
      cancelled = true
    }
  }, [entregas, getToken])

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

  // Filtro client-side por alumno sobre TODO lo cargado (FR-5). La vista ahora
  // acumula páginas vía "Cargar más" (FR-3), así que la búsqueda alcanza cada
  // entrega ya traída; para cubrir el resto de la comisión, el docente carga
  // más páginas. Emparejamos contra el label visible (`studentShortLabel`:
  // nombre real o `Est. xxxxxx`) y también contra el pseudónimo crudo.
  // FOLLOW-UP: pasar el término al backend para búsqueda paginada server-side
  // cuando `list` acepte un filtro por alumno.
  const q = studentQuery.trim().toLowerCase()
  const filteredEntregas = q
    ? entregas.filter(
        (e) =>
          studentShortLabel(e.student_pseudonym, profilesMap).toLowerCase().includes(q) ||
          e.student_pseudonym.toLowerCase().includes(q),
      )
    : entregas

  // Cola de corrección en lote (F5): las entregas pendientes (`submitted`) del
  // set ya filtrado — respeta comisión (prop), estado y búsqueda por alumno, o
  // sea "lo que el docente ya tenía seleccionado". Orden de cola client-side por
  // `submitted_at` ascendente (la más vieja primero) — el backend no garantiza
  // ese orden. `tarea` se toma del enriquecimiento best-effort ya cargado.
  // FOLLOW-UP: cuando existan filtros de TP/ejercicio en la lista (FR-1/FR-3),
  // la cola los heredará automáticamente al derivarse de `filteredEntregas`.
  const pendientesQueue: QueueItem[] = filteredEntregas
    .filter((e) => e.estado === "submitted")
    .slice()
    .sort(
      (a, b) => new Date(a.submitted_at ?? 0).getTime() - new Date(b.submitted_at ?? 0).getTime(),
    )
    .map((e) => ({ entrega: e, tarea: tareasByID[e.tarea_practica_id] ?? null }))

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

        {/* Acciones a la derecha: corregir en lote (F5) + búsqueda por alumno (FR-5) */}
        {entregas.length > 0 && (
          <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
            {/* Corregir en lote (F5): visible sólo si hay pendientes en el set
                filtrado. Arranca la cola con ese snapshot de pendientes. */}
            {pendientesQueue.length > 0 && (
              <button
                type="button"
                onClick={() => onStartBatch(pendientesQueue)}
                data-testid="corregir-en-lote-btn"
                className="press-shrink inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium text-white transition-colors animate-fade-in-up"
                style={{ backgroundColor: "var(--color-accent-brand)" }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = "var(--color-accent-brand-deep)"
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = "var(--color-accent-brand)"
                }}
              >
                <Layers className="h-4 w-4" aria-hidden="true" />
                Corregir en lote
                <span className="font-mono tabular-nums text-xs text-white/75">
                  {pendientesQueue.length}
                </span>
              </button>
            )}

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
              {query.hasNextPage
                ? "La búsqueda alcanza las entregas ya cargadas. Cargá más para ampliarla."
                : "La búsqueda alcanza todas las entregas cargadas de esta comisión."}
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

      {/* Cargar más (FR-3): sigue `meta.cursor_next`. Se oculta cuando el backend
          no devuelve más cursor (no hay más páginas). Mientras hay una búsqueda
          activa, cargar más amplía el set sobre el que corre el filtro (FR-5). */}
      {!loading && !error && query.hasNextPage && (
        <div className="flex justify-center pt-1">
          <button
            type="button"
            onClick={() => {
              if (!query.isFetchingNextPage) void query.fetchNextPage()
            }}
            disabled={query.isFetchingNextPage}
            data-testid="entregas-load-more"
            className="press-shrink inline-flex items-center gap-2 rounded-md border border-border bg-surface px-4 py-2 text-sm font-medium text-ink hover:bg-surface-alt disabled:cursor-not-allowed disabled:opacity-60 transition-colors"
          >
            {query.isFetchingNextPage ? (
              <>
                <span
                  aria-hidden="true"
                  className="inline-block w-4 h-4 border-2 border-t-transparent rounded-full motion-safe:animate-spin"
                  style={{
                    borderColor: "var(--color-accent-brand)",
                    borderTopColor: "transparent",
                  }}
                />
                Cargando…
              </>
            ) : (
              "Cargar más"
            )}
          </button>
        </div>
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

// ─── Rubrica por criterio en la correccion (F4) ────────────────────────
//
// El backend acepta `detalle_criterios` tanto en el POST /calificar como en el
// PATCH /calificacion. El shape que espera el schema `CriterioCalificacion`
// (evaluation-service) es `{ criterio, puntaje, max_puntaje, comentario }` —
// OJO: NO coincide con el tipo `CalificacionCriterio` de `lib/api.ts`
// (`{ nombre, puntaje, peso, comentario }`), que esta desalineado con el
// contrato real. Como no podemos tocar api.ts en este cambio, serializamos el
// shape correcto con un tipo local y casteamos al pasar por el metodo tipado.
// FOLLOW-UP: corregir `CalificacionCriterio` en lib/api.ts para que matchee
// `criterio`/`max_puntaje` (hoy dice `nombre`/`peso`).
interface DetalleCriterioPayload {
  criterio: string
  puntaje: number
  max_puntaje: number
  comentario: string | null
}

// Shape de vuelta desde el backend (CalificacionOut.detalle_criterios: list[dict]).
// `puntaje`/`max_puntaje` vuelven como string (Pydantic serializa Decimal como
// string en modo JSON), por eso los tipamos laxos y normalizamos al leer.
interface SavedCriterio {
  criterio: string
  puntaje: number | string
  max_puntaje: number | string
  comentario: string | null
}

// Body de calificacion con el shape correcto de criterios (para el PATCH local).
interface CalificacionBody {
  nota_final: number
  feedback_general: string
  detalle_criterios?: DetalleCriterioPayload[]
}

// Una fila de rubrica a calificar: aplana los criterios de cada ejercicio de la
// TP. `criterioLabel` es la identidad estable que se persiste como `criterio` y
// se usa para re-emparejar la calificacion guardada al re-editar. Si hay mas de
// un ejercicio con rubrica, se prefija con el titulo para desambiguar.
interface RubricaRow {
  key: string
  ejercicioTitulo: string
  nombre: string
  descripcion: string
  puntajeMax: number
  criterioLabel: string
}

function buildRubricaRows(tpEjercicios: TpEjercicio[]): RubricaRow[] {
  const conRubrica = tpEjercicios
    .slice()
    .sort((a, b) => a.orden - b.orden)
    .filter((t) => (t.ejercicio.rubrica?.criterios?.length ?? 0) > 0)
  const multi = conRubrica.length > 1
  const rows: RubricaRow[] = []
  for (const t of conRubrica) {
    const criterios = t.ejercicio.rubrica?.criterios ?? []
    criterios.forEach((c, i) => {
      rows.push({
        key: `${t.ejercicio_id}#${i}`,
        ejercicioTitulo: t.ejercicio.titulo,
        nombre: c.nombre,
        descripcion: c.descripcion,
        puntajeMax: Number.parseFloat(c.puntaje_max) || 0,
        criterioLabel: multi ? `${t.ejercicio.titulo}: ${c.nombre}` : c.nombre,
      })
    })
  }
  return rows
}

// Empareja una calificacion guardada a las filas de rubrica actuales para
// pre-llenar los inputs. Primero por `criterioLabel` (identidad estable), luego
// por `nombre` como fallback si la rubrica cambio desde que se califico.
function mapSavedToInputs(
  rows: RubricaRow[],
  saved: SavedCriterio[],
): { scores: Record<string, string>; comments: Record<string, string> } {
  const scores: Record<string, string> = {}
  const comments: Record<string, string> = {}
  for (const row of rows) {
    const match =
      saved.find((s) => s.criterio === row.criterioLabel) ??
      saved.find((s) => s.criterio === row.nombre)
    if (match) {
      scores[row.key] = String(match.puntaje)
      comments[row.key] = match.comentario ?? ""
    }
  }
  return { scores, comments }
}

// Serializa las filas al shape que espera el backend. Puntaje vacio = 0.
function serializeCriterios(
  rows: RubricaRow[],
  scores: Record<string, string>,
  comments: Record<string, string>,
): DetalleCriterioPayload[] {
  return rows.map((row) => ({
    criterio: row.criterioLabel,
    puntaje: Number.parseFloat(scores[row.key] ?? "") || 0,
    max_puntaje: row.puntajeMax,
    comentario: (comments[row.key] ?? "").trim() || null,
  }))
}

// Nota total sugerida desde los criterios: proporcion del puntaje asignado sobre
// el maximo posible, escalada a 0-10 y redondeada a 0.5 (el step del input). El
// docente sigue gobernando la nota — esto solo la sugiere.
function suggestNota(rows: RubricaRow[], scores: Record<string, string>): number | null {
  const sumMax = rows.reduce((acc, r) => acc + r.puntajeMax, 0)
  if (sumMax <= 0) return null
  const sumP = rows.reduce((acc, r) => acc + (Number.parseFloat(scores[r.key] ?? "") || 0), 0)
  const clamped = Math.max(0, Math.min(10, (sumP / sumMax) * 10))
  return Math.round(clamped * 2) / 2
}

// Valida los puntajes ingresados: cada valor no-vacio debe ser numerico y estar
// entre 0 y el maximo del criterio. Devuelve el mensaje de error o null.
function validateCriterios(rows: RubricaRow[], scores: Record<string, string>): string | null {
  for (const row of rows) {
    const raw = (scores[row.key] ?? "").trim()
    if (raw === "") continue
    const v = Number.parseFloat(raw)
    if (Number.isNaN(v) || v < 0 || v > row.puntajeMax) {
      return `El puntaje de "${row.nombre}" debe estar entre 0 y ${row.puntajeMax}.`
    }
  }
  return null
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
  body: CalificacionBody,
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

// ─── BatchGradingView (F5 · corrección en lote con auto-avance) ────────
//
// Recorre una cola (snapshot) de entregas pendientes reusando `GradingFormView`.
// El auto-avance ocurre vía `onUpdated`: cuando el form califica con éxito, el
// padre incrementa el contador y pasa a la siguiente entrega. "Saltar" avanza
// sin calificar; "Salir de la cola" vuelve a la lista. Al terminar, muestra el
// estado de éxito con cuántas entregas se corrigieron.
//
// Bordes cubiertos:
//   - Cola vacía → empty state (defensivo; el botón que la abre ya se oculta si
//     no hay pendientes).
//   - Error al guardar → `GradingFormView` no llama `onUpdated`, así que NO se
//     avanza y el error queda visible en el form.
//   - Entrega ya calificada → `GradingFormView` en modo cola arranca editable
//     (re-corregir permitido, NB-4).

interface BatchGradingViewProps {
  queue: QueueItem[]
  getToken: () => Promise<string | null>
  onExit: () => void
}

function BatchGradingView({ queue, getToken, onExit }: BatchGradingViewProps) {
  const total = queue.length
  // Posición en la cola (0-based). `gradedCount` cuenta sólo las que se
  // calificaron con éxito (no las saltadas), para el resumen final.
  const [index, setIndex] = useState(0)
  const [gradedCount, setGradedCount] = useState(0)

  const advance = () => setIndex((i) => i + 1)
  const handleGraded = () => {
    setGradedCount((c) => c + 1)
    advance()
  }

  // Cola vacía (defensivo).
  if (total === 0) {
    return (
      <div
        className="rounded-2xl border border-dashed border-border bg-surface p-10 text-center animate-fade-in-up"
        data-testid="batch-empty"
      >
        <div className="inline-flex items-center justify-center rounded-full bg-surface-alt p-4 mb-4">
          <FileCheck className="h-7 w-7 text-muted" />
        </div>
        <p className="text-sm text-muted leading-relaxed max-w-md mx-auto">
          No hay entregas pendientes para corregir en lote.
        </p>
        <button
          type="button"
          onClick={onExit}
          className="press-shrink mt-5 inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-4 py-2 text-sm font-medium text-ink hover:bg-surface-alt transition-colors"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          Volver a entregas
        </button>
      </div>
    )
  }

  // Cola terminada → estado de éxito.
  if (index >= total) {
    return (
      <div
        className="rounded-2xl border border-success/30 bg-success-soft p-10 text-center animate-fade-in-up"
        data-testid="batch-done"
      >
        <div className="inline-flex items-center justify-center rounded-full bg-success/15 p-4 mb-4">
          <CheckCircle2 className="h-8 w-8 text-success" />
        </div>
        <h3 className="text-base font-semibold text-ink mb-1">Cola terminada</h3>
        <p className="text-sm text-muted leading-relaxed max-w-md mx-auto">
          {gradedCount === 0
            ? "No calificaste ninguna entrega en esta cola."
            : `Corregiste ${gradedCount} ${gradedCount === 1 ? "entrega" : "entregas"} de ${total}.`}
        </p>
        <button
          type="button"
          onClick={onExit}
          data-testid="batch-done-back"
          className="press-shrink mt-5 inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-4 py-2 text-sm font-medium text-ink hover:bg-surface-alt transition-colors"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          Volver a entregas
        </button>
      </div>
    )
  }

  const current = queue[index]
  if (!current) return null
  // Progreso: posición 1-based y porcentaje de avance sobre el total.
  const position = index + 1
  const pct = Math.round((index / total) * 100)

  return (
    <div className="space-y-5" data-testid="batch-grading-view">
      {/* Cabecera de progreso: contador "X de N" + barra + calificadas. */}
      <div className="rounded-xl border border-border bg-surface p-4 shadow-[0_1px_2px_0_rgba(0,0,0,0.04)] animate-fade-in-up">
        <div className="flex items-center justify-between gap-3 flex-wrap mb-2.5">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-accent-brand" aria-hidden="true" />
            <span className="text-sm font-semibold text-ink">Corrección en lote</span>
          </div>
          <span className="text-xs text-muted tabular-nums" data-testid="batch-progress-counter">
            Entrega <span className="font-mono text-ink">{position}</span> de{" "}
            <span className="font-mono text-ink">{total}</span>
            {gradedCount > 0 && (
              <span className="ml-2 text-success">· {gradedCount} calificadas</span>
            )}
          </span>
        </div>
        {/* Barra decorativa: el progreso lo anuncia el contador textual de
            arriba ("Entrega X de N"), por eso la barra va aria-hidden. */}
        <div
          aria-hidden="true"
          className="h-1.5 w-full overflow-hidden rounded-full bg-surface-alt"
        >
          <div
            className="h-full rounded-full transition-[width] duration-300"
            style={{ width: `${pct}%`, backgroundColor: "var(--color-accent-brand)" }}
          />
        </div>
      </div>

      {/* Form de calificación reusado en modo cola. `key` por entrega fuerza el
          remount al avanzar (limpia estado interno del form). */}
      <GradingFormView
        key={current.entrega.id}
        entrega={current.entrega}
        tarea={current.tarea}
        getToken={getToken}
        onBack={onExit}
        onUpdated={handleGraded}
        queueControls={{ onSkip: advance, onExit }}
      />
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
  // Controles de la cola de corrección en lote (F5). Presencia = modo cola:
  // el botón de guardar pasa a "Guardar y siguiente" (el auto-avance lo hace
  // el padre vía `onUpdated`), se agregan "Saltar" y "Salir de la cola", y se
  // ocultan el back propio y "Devolver" (los provee la cola).
  queueControls?: { onSkip: () => void; onExit: () => void }
}

function GradingFormView({
  entrega,
  tarea,
  getToken,
  onBack,
  onUpdated,
  queueControls,
}: GradingFormViewProps) {
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
  const queueMode = !!queueControls
  // Reapertura del form para re-calificar una entrega ya calificada (BUG-3).
  // Mientras es `false`, los campos quedan `disabled` (solo lectura de la nota).
  // En modo cola (F5), si la entrega ya viene calificada (border NB-4: permitir
  // re-corregir), arrancamos en modo edición para que el docente pueda ajustar
  // y "Guardar y siguiente" directo sin un click extra en "Re-calificar".
  const [reediting, setReediting] = useState(
    () => queueMode && (entrega.estado === "graded" || entrega.estado === "returned"),
  )
  // Rubrica por criterio (F4). `criterioScores`/`criterioComments` son los
  // inputs editables por fila de rubrica; `savedCriterios` es lo que vino
  // guardado en la calificacion (para pre-llenar y para restaurar al cancelar).
  const [criterioScores, setCriterioScores] = useState<Record<string, string>>({})
  const [criterioComments, setCriterioComments] = useState<Record<string, string>>({})
  const [savedCriterios, setSavedCriterios] = useState<SavedCriterio[]>([])

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

  // Filas de rubrica a calificar (F4): se derivan de la composicion de la TP.
  // `useMemo` mantiene identidad estable entre renders para que el effect de
  // pre-llenado no se dispare en cada render.
  const rubricaRows = useMemo(() => buildRubricaRows(tpEjercicios), [tpEjercicios])
  const tieneRubrica = rubricaRows.length > 0
  const notaSugerida = tieneRubrica ? suggestNota(rubricaRows, criterioScores) : null

  // Pre-llena los inputs de criterios desde la calificacion guardada una vez que
  // la rubrica y el detalle guardado estan disponibles. Para una entrega aun no
  // calificada, `savedCriterios` es `[]` → inputs vacios.
  useEffect(() => {
    const { scores, comments } = mapSavedToInputs(rubricaRows, savedCriterios)
    setCriterioScores(scores)
    setCriterioComments(comments)
  }, [rubricaRows, savedCriterios])

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
        // Detalle por criterio (F4): el tipo de `lib/api.ts` esta desalineado
        // con el contrato real, por eso lo leemos via `SavedCriterio`.
        setSavedCriterios((c.detalle_criterios ?? []) as unknown as SavedCriterio[])
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
    if (tieneRubrica) {
      const critError = validateCriterios(rubricaRows, criterioScores)
      if (critError) {
        setSubmitError(critError)
        return
      }
    }
    setSubmitting(true)
    setSubmitError(null)
    try {
      const detalle = tieneRubrica
        ? serializeCriterios(rubricaRows, criterioScores, criterioComments)
        : undefined
      const body: CalificacionCreate = {
        nota_final: notaNum,
        feedback_general: feedback.trim(),
        // El shape correcto es el del backend (`criterio`/`max_puntaje`); el tipo
        // `CalificacionCriterio` de api.ts esta desalineado, por eso el cast.
        ...(detalle
          ? {
              detalle_criterios: detalle as unknown as NonNullable<
                CalificacionCreate["detalle_criterios"]
              >,
            }
          : {}),
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
    if (tieneRubrica) {
      const critError = validateCriterios(rubricaRows, criterioScores)
      if (critError) {
        setSubmitError(critError)
        return
      }
    }
    setSubmitting(true)
    setSubmitError(null)
    try {
      const detalle = tieneRubrica
        ? serializeCriterios(rubricaRows, criterioScores, criterioComments)
        : undefined
      await recalificarEntrega(
        entrega.id,
        {
          nota_final: notaNum,
          feedback_general: feedback.trim(),
          ...(detalle ? { detalle_criterios: detalle } : {}),
        },
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
    // Restaura los criterios a lo guardado (F4).
    const { scores, comments } = mapSavedToInputs(rubricaRows, savedCriterios)
    setCriterioScores(scores)
    setCriterioComments(comments)
  }

  return (
    <div className="space-y-6 max-w-3xl" data-testid="grading-form-view">
      {/* En modo cola el back lo provee el header de la cola (Salir de la cola). */}
      {!queueMode && (
        <button
          type="button"
          onClick={onBack}
          className="press-shrink text-xs text-muted hover:text-ink inline-flex items-center gap-1.5 transition-colors"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          Volver a entregas
        </button>
      )}

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

            {/* Rúbrica por criterio (F4): solo si la TP tiene ejercicios con
                rúbrica. El docente asigna puntaje + comentario por criterio y
                puede aplicar la nota sugerida (que igual puede ajustar). */}
            {tieneRubrica && (
              <div data-testid="rubrica-criterios" className="space-y-3">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <p className="text-sm font-medium text-ink">Rúbrica por criterio</p>
                  {notaSugerida !== null && !(yaCalificada && !reediting) && (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted">
                        Nota sugerida:{" "}
                        <span className="font-mono tabular-nums text-ink">
                          {notaSugerida.toFixed(1)}
                        </span>
                      </span>
                      <button
                        type="button"
                        onClick={() => setNota(String(notaSugerida))}
                        data-testid="aplicar-nota-sugerida-btn"
                        className="press-shrink px-2.5 py-1 rounded-md text-xs font-medium border border-border bg-surface text-ink hover:bg-surface-alt transition-colors"
                      >
                        Aplicar
                      </button>
                    </div>
                  )}
                </div>

                <div className="space-y-2.5">
                  {rubricaRows.map((row) => (
                    <div
                      key={row.key}
                      data-testid={`criterio-row-${row.key}`}
                      className="rounded-lg border border-border-soft bg-canvas p-3"
                    >
                      <div className="flex items-start justify-between gap-3 flex-wrap">
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-ink">{row.nombre}</p>
                          {row.descripcion && (
                            <p className="text-xs text-muted mt-0.5 leading-relaxed">
                              {row.descripcion}
                            </p>
                          )}
                          {row.ejercicioTitulo && rubricaRows.length > 1 && (
                            <p className="text-[10px] uppercase tracking-wider text-muted-soft mt-1">
                              {row.ejercicioTitulo}
                            </p>
                          )}
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <input
                            type="number"
                            min="0"
                            max={row.puntajeMax}
                            step="0.5"
                            value={criterioScores[row.key] ?? ""}
                            onChange={(e) =>
                              setCriterioScores((prev) => ({ ...prev, [row.key]: e.target.value }))
                            }
                            disabled={yaCalificada && !reediting}
                            data-testid={`criterio-puntaje-${row.key}`}
                            aria-label={`Puntaje de ${row.nombre}`}
                            className="w-16 border border-border rounded px-2 py-1.5 text-sm text-ink bg-surface focus:outline-none focus:ring-1 focus:ring-ink disabled:bg-surface-alt disabled:text-muted tabular-nums"
                            placeholder="0"
                          />
                          <span className="text-xs text-muted font-mono tabular-nums">
                            / {row.puntajeMax}
                          </span>
                        </div>
                      </div>
                      <input
                        type="text"
                        value={criterioComments[row.key] ?? ""}
                        onChange={(e) =>
                          setCriterioComments((prev) => ({ ...prev, [row.key]: e.target.value }))
                        }
                        disabled={yaCalificada && !reediting}
                        data-testid={`criterio-comentario-${row.key}`}
                        aria-label={`Comentario de ${row.nombre}`}
                        className="mt-2 w-full border border-border rounded px-2.5 py-1.5 text-xs text-ink bg-surface focus:outline-none focus:ring-1 focus:ring-ink disabled:bg-surface-alt disabled:text-muted"
                        placeholder="Comentario del criterio (opcional)"
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

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
                  {submitting ? "Guardando..." : queueMode ? "Guardar y siguiente" : "Calificar"}
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
                    {submitting
                      ? "Guardando..."
                      : queueMode
                        ? "Guardar y siguiente"
                        : "Guardar cambios"}
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
                  esta re-calificando (evita acciones ambiguas mid-edit). En modo
                  cola se oculta: devolver es una acción aparte del flujo de
                  avance; el docente la hace desde la lista una vez cerrada la cola. */}
              {entrega.estado === "graded" && !reediting && !queueMode && (
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

              {/* Controles de la cola (F5): saltar esta entrega sin calificar y
                  salir de la cola. El auto-avance tras guardar lo dispara
                  `onUpdated` (lo maneja `BatchGradingView`). */}
              {queueControls && (
                <>
                  <button
                    type="button"
                    onClick={queueControls.onSkip}
                    disabled={submitting}
                    data-testid="saltar-entrega-btn"
                    className="press-shrink inline-flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium border border-border bg-surface text-ink hover:bg-surface-alt disabled:opacity-60 transition-colors"
                  >
                    <SkipForward className="h-3.5 w-3.5" aria-hidden="true" />
                    Saltar
                  </button>
                  <button
                    type="button"
                    onClick={queueControls.onExit}
                    data-testid="salir-cola-btn"
                    className="press-shrink ml-auto px-4 py-2 rounded-md text-sm font-medium text-muted hover:text-ink hover:bg-surface-alt transition-colors"
                  >
                    Salir de la cola
                  </button>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
