/**
 * Pagina del historial de reflexiones metacognitivas del estudiante (ADR-035).
 *
 * Cierra el gap: hasta hoy la reflexion solo era visible inmediatamente
 * post-cierre dentro de EpisodePage. Ahora el alumno puede revisar todas
 * sus reflexiones pasadas en lectura tranquila — sin acciones, sin
 * calificacion, sin tutor respondiendo. Es para el.
 *
 * Privacy:
 *   - El endpoint backend filtra por `student_pseudonym = X-User-Id`. El
 *     estudiante SOLO ve sus propias reflexiones.
 *   - Las reflexiones siguen excluidas del feature extraction del classifier
 *     (ADR-027) — leerlas no afecta la clasificacion N4 del episodio.
 *   - El export academico sigue redactando los 3 campos por default.
 *
 * UX: lectura tranquila. Cards con titulo de TP + fecha + las 3 respuestas
 * en bloques separados. Sin botones de "editar" o "borrar" — la reflexion
 * es append-only en el CTR (ADR-010).
 */
import { HelpButton } from "@platform/ui"
import { useInfiniteQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { ArrowLeft, BookOpenText, Clock } from "lucide-react"
import { type ReflectionEntry, getMyReflections } from "../lib/api"
import { helpContent } from "../utils/helpContent"

const PAGE_SIZE = 20

export function MisReflexionesPage() {
  const navigate = useNavigate()

  const { data, isLoading, error, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery({
      queryKey: ["mis-reflexiones"],
      queryFn: ({ pageParam }) => getMyReflections(PAGE_SIZE, pageParam),
      initialPageParam: undefined as string | undefined,
      getNextPageParam: (lastPage) => lastPage.cursor_next ?? undefined,
      staleTime: 60 * 1000,
    })

  const reflections: ReflectionEntry[] = data?.pages.flatMap((p) => p.reflections) ?? []

  return (
    <div className="page-enter flex-1 overflow-y-auto px-6 py-10">
      <div className="max-w-3xl mx-auto">
        <button
          type="button"
          onClick={() => navigate({ to: "/" })}
          className="press-shrink inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink mb-6"
          data-testid="mis-reflexiones-back"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Volver a mis materias
        </button>

        <header className="animate-fade-in-down mb-8 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[11px] font-mono uppercase tracking-[0.12em] text-muted mb-2">
              Tus reflexiones · ADR-035
            </p>
            <h1 className="text-3xl font-semibold tracking-tight text-ink leading-none">
              Mis reflexiones
            </h1>
            <p className="text-sm text-muted leading-relaxed mt-2 max-w-xl">
              Todo lo que pensaste cuando cerraste cada episodio. Son tuyas — nadie
              te calificó, nadie te respondió. Releerlas mientras todavía esta
              fresco es parte del proceso.
            </p>
          </div>
          <HelpButton title="Mis reflexiones" content={helpContent.reflexiones} />
        </header>

        {isLoading && <LoadingSkeleton />}
        {error && <ErrorPanel error={String(error)} />}
        {!isLoading && !error && reflections.length === 0 && <EmptyState />}
        {!isLoading && !error && reflections.length > 0 && (
          <>
            <ul className="space-y-5">
              {reflections.map((r, idx) => (
                <li
                  key={r.episode_id}
                  className="animate-fade-in-up"
                  style={{ animationDelay: `${50 + idx * 40}ms` }}
                >
                  <ReflectionCard reflection={r} />
                </li>
              ))}
            </ul>
            {hasNextPage && (
              <div className="flex justify-center mt-8">
                <button
                  type="button"
                  onClick={() => fetchNextPage()}
                  disabled={isFetchingNextPage}
                  className="press-shrink px-4 py-2 rounded-md border border-border bg-surface text-sm font-medium text-body hover:bg-surface-alt disabled:opacity-50"
                  data-testid="mis-reflexiones-load-more"
                >
                  {isFetchingNextPage ? "Cargando..." : "Cargar mas reflexiones"}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ─── Card individual de una reflexion ─────────────────────────────────

interface ReflectionCardProps {
  reflection: ReflectionEntry
}

function ReflectionCard({ reflection }: ReflectionCardProps) {
  const closedAt = reflection.closed_at ? formatDateTime(reflection.closed_at) : null
  const tareaLabel =
    reflection.tarea_codigo && reflection.tarea_titulo
      ? `${reflection.tarea_codigo} · ${reflection.tarea_titulo}`
      : reflection.tarea_titulo ?? reflection.tarea_codigo ?? "TP (sin titulo)"

  return (
    <article
      data-testid="reflection-card"
      data-episode-id={reflection.episode_id}
      className="rounded-xl border border-border bg-surface p-6 shadow-[0_1px_2px_0_rgba(0,0,0,0.04)] hover-lift"
    >
      <header className="mb-4">
        <div className="flex items-center gap-2 mb-2">
          <BookOpenText className="h-3.5 w-3.5 text-accent-brand" aria-hidden="true" />
          <p className="text-xs font-mono uppercase tracking-wider text-muted">
            {tareaLabel}
          </p>
        </div>
        {closedAt && (
          <p className="text-xs text-muted-soft inline-flex items-center gap-1.5">
            <Clock className="h-3 w-3" aria-hidden="true" />
            Cerrado el {closedAt}
          </p>
        )}
      </header>

      <div className="space-y-4">
        <ReflectionField
          label="¿En que momento del episodio sentiste que algo hizo click?"
          value={reflection.answers.que_aprendiste}
        />
        <ReflectionField
          label="Si alguien viniera a hacer el mismo ejercicio manana, ¿que le contarias sobre como encararlo?"
          value={reflection.answers.dificultad_encontrada}
        />
        <ReflectionField
          label="¿Te quedaste con alguna pregunta sin responder?"
          value={reflection.answers.que_haria_distinto}
        />
      </div>
    </article>
  )
}

interface ReflectionFieldProps {
  label: string
  value: string
}

function ReflectionField({ label, value }: ReflectionFieldProps) {
  const hasContent = value.trim().length > 0
  return (
    <div>
      <p className="text-xs font-medium text-muted mb-1.5">{label}</p>
      {hasContent ? (
        <p className="text-sm text-ink leading-relaxed whitespace-pre-wrap">{value}</p>
      ) : (
        <p className="text-sm text-muted-soft italic">(En blanco)</p>
      )}
    </div>
  )
}

// ─── Estados auxiliares ───────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div className="space-y-4" data-testid="mis-reflexiones-loading">
      {[0, 1, 2].map((i) => (
        <div key={i} className="skeleton h-44 rounded-xl" />
      ))}
    </div>
  )
}

function ErrorPanel({ error }: { error: string }) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-danger/30 bg-danger-soft p-6"
      data-testid="mis-reflexiones-error"
    >
      <p className="text-sm font-semibold text-danger mb-2">
        No pudimos cargar tus reflexiones.
      </p>
      <p className="text-xs font-mono text-danger/80 break-all">{error}</p>
    </div>
  )
}

function EmptyState() {
  return (
    <div
      data-testid="mis-reflexiones-empty"
      className="rounded-xl border border-border bg-surface p-8 text-center"
    >
      <p className="text-base font-medium text-ink mb-2">Todavia no escribiste reflexiones</p>
      <p className="text-sm text-muted max-w-md mx-auto leading-relaxed">
        Cuando cerres un episodio del tutor, vas a poder dejar una reflexion
        sobre lo que pensaste mientras lo resolvias. Las vas a poder releer
        aca cuando quieras.
      </p>
    </div>
  )
}

// ─── Helpers ──────────────────────────────────────────────────────────

function formatDateTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString("es-AR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return iso
  }
}
