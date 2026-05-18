/**
 * Selector de Trabajo Practico para el estudiante (shape alumno, brief 3.3).
 *
 * Reorganiza el render en 3 zonas tipograficas (Continuar / Proximas /
 * Vencidas) en lugar del card grid uniforme original. Cumple el ban
 * "identical card grids" con densidad y forma diferentes:
 *   - "CONTINUAR": card prominente con border + padding generoso. TODO:
 *     conectar al endpoint de "episodios abiertos" cuando exista. Por
 *     ahora detecta TPs en las que el alumno tiene episodios cerrados
 *     recientes (mismo template_id o id) y muestra trayectoria N4.
 *   - "PROXIMAS": list items densos sin box, divider tipografico.
 *   - "VENCIDAS": items compactos, color muted, sin CTA.
 *
 * "Trayectoria N4 historica" en CONTINUAR: 3 dots ordinales con color de
 * apropiacion (reflexiva=verde, superficial=ambar, delegacion=rojo) sobre
 * los ultimos 3 cierres del alumno en TPs con el mismo `template_id`.
 * Si <3 episodios analogos: "Tu primera vez con esta TP" (muted).
 *
 * Privacy: la trayectoria es per-student (el endpoint
 * /api/v1/analytics/student/{id}/episodes filtra por student_pseudonym
 * desde headers — el backend NO expone otros estudiantes).
 */
import { StateMessage } from "@platform/ui"
import { useEffect, useMemo, useState } from "react"
import {
  type AvailableTarea,
  type Entrega,
  type EntregaEstado,
  type StudentEpisode,
  entregasApi,
  listStudentEpisodes,
  tareasPracticasApi,
} from "../lib/api"
import { STUDENT_PSEUDONYM_DEV } from "../lib/dev-user"

export interface TareaSelectorProps {
  comisionId: string
  onSelect: (tarea: AvailableTarea) => void
  /**
   * Filtro opcional por unidad temática.
   * - `undefined`: sin filtro, muestra todas las TPs (comportamiento legacy).
   * - `null`: muestra solo las TPs sin unidad asignada ("huérfanas").
   * - `string`: muestra solo las TPs de esa unidad.
   */
  unidadId?: string | null
  /** Callback opcional para volver al selector de unidades. */
  onBack?: () => void
}

interface Zones {
  pendiente: AvailableTarea[]
  porCorregir: AvailableTarea[]
  listo: AvailableTarea[]
  vencidas: AvailableTarea[]
}

function partitionTareas(
  tareas: AvailableTarea[],
  _episodes: StudentEpisode[],
  entregasByTareaId: Record<string, Entrega>,
): Zones {
  const now = Date.now()

  const pendiente: AvailableTarea[] = []
  const porCorregir: AvailableTarea[] = []
  const listo: AvailableTarea[] = []
  const vencidas: AvailableTarea[] = []

  for (const t of tareas) {
    const fechaFin = t.fecha_fin ? new Date(t.fecha_fin).getTime() : null
    const isVencida = fechaFin !== null && fechaFin <= now
    if (isVencida) {
      vencidas.push(t)
      continue
    }

    const entrega = entregasByTareaId[t.id]
    if (entrega?.estado === "graded" || entrega?.estado === "returned") {
      listo.push(t)
    } else if (entrega?.estado === "submitted") {
      porCorregir.push(t)
    } else {
      pendiente.push(t)
    }
  }

  pendiente.sort(byDeadlineAsc)
  porCorregir.sort(byDeadlineAsc)
  listo.sort(byDeadlineAsc)
  vencidas.sort(byDeadlineDesc)

  return { pendiente, porCorregir, listo, vencidas }
}

function byDeadlineAsc(a: AvailableTarea, b: AvailableTarea): number {
  const da = a.fecha_fin ? new Date(a.fecha_fin).getTime() : Number.POSITIVE_INFINITY
  const db = b.fecha_fin ? new Date(b.fecha_fin).getTime() : Number.POSITIVE_INFINITY
  return da - db
}

function byDeadlineDesc(a: AvailableTarea, b: AvailableTarea): number {
  return -byDeadlineAsc(a, b)
}

export function TareaSelector({ comisionId, onSelect, unidadId, onBack }: TareaSelectorProps) {
  const [tareas, setTareas] = useState<AvailableTarea[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null)
  const [episodes, setEpisodes] = useState<StudentEpisode[]>([])
  // Map de tarea_practica_id → entrega (best-effort, no bloquea el selector)
  const [entregasByTareaId, setEntregasByTareaId] = useState<Record<string, Entrega>>({})

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setLoadMoreError(null)
    setTareas([])
    setNextCursor(null)
    setEpisodes([])
    tareasPracticasApi
      .listAvailable(comisionId)
      .then((page) => {
        if (cancelled) return
        setTareas(page.data)
        setNextCursor(page.meta.cursor_next)
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
  }, [comisionId])

  // Entregas del estudiante: best-effort, para clasificar en zonas.
  useEffect(() => {
    if (tareas.length === 0) return
    let cancelled = false

    void Promise.allSettled(
      tareas.map((t) =>
        entregasApi.getForTp(t.id, comisionId).then((entrega) => ({ tareaId: t.id, entrega })),
      ),
    ).then((results) => {
      if (cancelled) return
      const map: Record<string, Entrega> = {}
      for (const r of results) {
        if (r.status === "fulfilled" && r.value.entrega) {
          map[r.value.tareaId] = r.value.entrega
        }
      }
      setEntregasByTareaId(map)
    })

    return () => {
      cancelled = true
    }
  }, [tareas, comisionId])

  // Trayectoria N4 historica: best-effort. Si el endpoint no esta disponible
  // (analytics down, dev mode sin classifier), seguimos sin la zona Continuar.
  useEffect(() => {
    let cancelled = false
    // El backend filtra por X-User-Id, no por este path param — pero el
    // contrato pide UUID valido. En dev usamos STUDENT_PSEUDONYM_DEV
    // (mismo UUID que el vite.config inyecta como X-User-Id). En prod, el
    // sub del JWT proveera el verdadero `student_pseudonym`.
    listStudentEpisodes(STUDENT_PSEUDONYM_DEV, comisionId)
      .then((res) => {
        if (cancelled) return
        setEpisodes(res.episodes)
      })
      .catch(() => {
        // Best-effort: si analytics no responde, seguimos sin trayectoria.
      })
    return () => {
      cancelled = true
    }
  }, [comisionId])

  async function handleLoadMore() {
    if (!nextCursor || loadingMore) return
    setLoadingMore(true)
    setLoadMoreError(null)
    try {
      const page = await tareasPracticasApi.listAvailable(comisionId, nextCursor)
      setTareas((prev) => [...prev, ...page.data])
      setNextCursor(page.meta.cursor_next)
    } catch (e) {
      setLoadMoreError(String(e))
    } finally {
      setLoadingMore(false)
    }
  }

  const filteredTareas = useMemo(() => {
    if (unidadId === undefined) return tareas
    if (unidadId === null) return tareas.filter((t) => t.unidad_id === null)
    return tareas.filter((t) => t.unidad_id === unidadId)
  }, [tareas, unidadId])

  const zones = useMemo(
    () => partitionTareas(filteredTareas, episodes, entregasByTareaId),
    [filteredTareas, episodes, entregasByTareaId],
  )

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <StateMessage variant="loading" title="Cargando trabajos practicos..." />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center px-4">
        <StateMessage
          variant="error"
          title="No pudimos cargar los trabajos practicos."
          description={error}
          className="max-w-md"
        />
      </div>
    )
  }

  if (filteredTareas.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="max-w-md text-center px-6">
          {onBack && (
            <button
              type="button"
              onClick={onBack}
              className="mb-4 text-sm text-blue-600 hover:underline"
            >
              ← Volver a unidades
            </button>
          )}
          <p className="text-base font-medium text-body mb-2">
            {unidadId !== undefined
              ? "Esta unidad todavía no tiene trabajos prácticos."
              : "Tu comision todavia no tiene TPs publicadas."}
          </p>
          <p className="text-sm text-muted">
            Tu docente las publica desde el panel de gestion.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8">
      <div className="max-w-3xl mx-auto">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="mb-3 text-sm text-blue-600 hover:underline"
          >
            ← Volver a unidades
          </button>
        )}
        <p className="text-xs font-mono uppercase tracking-wider text-muted mb-2">
          Trabajos practicos
        </p>
        <h2 className="text-2xl font-semibold text-ink mb-8">
          Tu materia, esta semana.
        </h2>

        {zones.pendiente.length > 0 && (
          <ZonePendiente
            tareas={zones.pendiente}
            episodes={episodes}
            entregasByTareaId={entregasByTareaId}
            onSelect={onSelect}
          />
        )}

        {zones.porCorregir.length > 0 && (
          <ZonePorCorregir
            tareas={zones.porCorregir}
            entregasByTareaId={entregasByTareaId}
          />
        )}

        {zones.listo.length > 0 && (
          <ZoneListo
            tareas={zones.listo}
            entregasByTareaId={entregasByTareaId}
            onSelect={onSelect}
          />
        )}

        {zones.vencidas.length > 0 && (
          <ZoneVencidas tareas={zones.vencidas} episodes={episodes} />
        )}

        {nextCursor !== null && (
          <div className="mt-8 flex flex-col items-center gap-2">
            {loadMoreError && (
              <div
                role="alert"
                className="w-full max-w-md rounded-lg border border-danger/40 bg-danger-soft p-3 text-xs text-danger"
              >
                <p className="font-medium mb-1">No pudimos cargar mas trabajos practicos.</p>
                <p className="font-mono">{loadMoreError}</p>
              </div>
            )}
            <button
              type="button"
              onClick={handleLoadMore}
              disabled={loadingMore}
              className="px-4 py-2 rounded border border-border bg-surface text-sm font-medium text-body hover:bg-surface-alt disabled:opacity-60"
            >
              {loadingMore ? "Cargando..." : "Cargar mas"}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Badge de entrega ─────────────────────────────────────────────────

function EntregaBadge({ estado }: { estado: EntregaEstado }) {
  const labels: Record<EntregaEstado, string> = {
    draft: "En progreso",
    submitted: "Entregada",
    graded: "Calificada",
    returned: "Devuelta",
  }
  const classes: Record<EntregaEstado, string> = {
    draft: "bg-surface-alt text-muted",
    submitted: "bg-accent-brand-soft text-accent-brand-deep",
    graded: "bg-success-soft text-success",
    returned: "bg-warning-soft text-warning/85",
  }
  return (
    <span
      data-testid={`entrega-badge-${estado}`}
      className={`text-xs font-mono px-2 py-0.5 rounded ${classes[estado]}`}
    >
      {labels[estado]}
    </span>
  )
}

// ─── Zona PENDIENTE: TPs no empezadas o en draft ────────────────────

function ZonePendiente({
  tareas,
  episodes,
  entregasByTareaId,
  onSelect,
}: {
  tareas: AvailableTarea[]
  episodes: StudentEpisode[]
  entregasByTareaId: Record<string, Entrega>
  onSelect: (t: AvailableTarea) => void
}) {
  return (
    <section className="mb-10" data-testid="zone-pendiente">
      <div className="flex items-baseline justify-between mb-4">
        <p className="text-xs font-mono uppercase tracking-wider text-body">
          Pendiente
        </p>
        <span className="text-xs text-muted font-mono">
          {tareas.length} {tareas.length === 1 ? "TP" : "TPs"}
        </span>
      </div>
      <ul className="space-y-3">
        {tareas.map((t) => {
          const entrega = entregasByTareaId[t.id]
          const hasDraft = entrega?.estado === "draft"
          return (
            <li key={t.id}>
              <PendienteCard
                tarea={t}
                episodes={episodes}
                hasDraft={hasDraft}
                onSelect={() => onSelect(t)}
              />
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function PendienteCard({
  tarea,
  episodes,
  hasDraft,
  onSelect,
}: {
  tarea: AvailableTarea
  episodes: StudentEpisode[]
  hasDraft: boolean
  onSelect: () => void
}) {
  const trajectory = useMemo(() => {
    const matching = episodes
      .filter((ep) => ep.problema_id === tarea.id && ep.appropriation !== null)
      .sort((a, b) => {
        const da = a.classified_at ? new Date(a.classified_at).getTime() : 0
        const db = b.classified_at ? new Date(b.classified_at).getTime() : 0
        return db - da
      })
      .slice(0, 3)
      .reverse()
    return matching
  }, [episodes, tarea.id])

  const deadline = formatDeadline(tarea.fecha_fin)

  return (
    <article
      data-testid="tp-card"
      data-tp-codigo={tarea.codigo}
      className="rounded-lg border border-border bg-surface p-5"
    >
      <header className="flex items-start gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-mono text-muted mb-1">
            {tarea.codigo} (v{tarea.version})
          </p>
          <h3 className="text-lg font-semibold text-ink">
            {tarea.titulo}
          </h3>
        </div>
      </header>

      <div className="mb-4 text-xs text-muted">
        {trajectory.length === 0 ? (
          <p data-testid="trajectory-empty" className="italic">
            Tu primera vez con esta TP.
          </p>
        ) : (
          <div className="flex items-center gap-2 flex-wrap" data-testid="trajectory-dots">
            <span className="text-muted">
              Tu trayectoria en TPs analogas:
            </span>
            <span className="inline-flex items-center gap-1.5">
              {trajectory.map((ep, idx) => (
                <span
                  key={`${ep.episode_id}-${idx}`}
                  aria-label={appropriationAriaLabel(ep.appropriation)}
                  data-testid={`trajectory-dot-${ep.appropriation ?? "unknown"}`}
                  className="inline-block w-2 h-2 rounded-full"
                  style={{ backgroundColor: appropriationColor(ep.appropriation) }}
                />
              ))}
            </span>
          </div>
        )}
      </div>

      <footer className="flex items-center justify-between gap-3">
        {deadline && <p className={`text-xs ${deadline.colorClass}`}>{deadline.label}</p>}
        <button
          type="button"
          onClick={onSelect}
          className="ml-auto px-4 py-2 rounded text-sm font-medium text-white"
          style={{ backgroundColor: "var(--color-accent-brand)" }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = "var(--color-accent-brand-deep)"
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = "var(--color-accent-brand)"
          }}
        >
          {hasDraft ? "Continuar" : "Empezar"}
        </button>
      </footer>
    </article>
  )
}

// ─── Zona POR CORREGIR: entregadas, esperando al docente ────────────

function ZonePorCorregir({
  tareas,
  entregasByTareaId,
}: {
  tareas: AvailableTarea[]
  entregasByTareaId: Record<string, Entrega>
}) {
  return (
    <section className="mb-10" data-testid="zone-por-corregir">
      <div className="flex items-baseline gap-3 mb-3 border-b border-border-soft pb-1">
        <p className="text-xs font-mono uppercase tracking-wider text-accent-brand-deep">
          Por corregir
        </p>
        <span className="text-xs text-muted">
          esperando al docente
        </span>
      </div>
      <ul className="divide-y divide-slate-100">
        {tareas.map((t) => {
          const entrega = entregasByTareaId[t.id]
          return (
            <li key={t.id}>
              <div
                data-testid="tp-card"
                data-tp-codigo={t.codigo}
                className="py-3 flex items-start gap-4"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="text-xs font-mono text-muted">
                      {t.codigo}
                    </span>
                    <span className="text-xs font-mono text-muted-soft">v{t.version}</span>
                    <span className="text-sm font-medium text-ink truncate">
                      {t.titulo}
                    </span>
                  </div>
                  {entrega?.submitted_at && (
                    <p className="text-xs text-muted mt-1">
                      Entregada el{" "}
                      {new Date(entrega.submitted_at).toLocaleString("es-AR", {
                        day: "2-digit",
                        month: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </p>
                  )}
                </div>
                <span className="shrink-0 px-3 py-1.5 rounded text-xs font-medium bg-accent-brand-soft text-accent-brand-deep">
                  Esperando correccion
                </span>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

// ─── Zona LISTO: corregidas por el docente ───────────────────────────

function ZoneListo({
  tareas,
  entregasByTareaId,
  onSelect,
}: {
  tareas: AvailableTarea[]
  entregasByTareaId: Record<string, Entrega>
  onSelect: (t: AvailableTarea) => void
}) {
  return (
    <section className="mb-10" data-testid="zone-listo">
      <div className="flex items-baseline gap-3 mb-3 border-b border-border-soft pb-1">
        <p className="text-xs font-mono uppercase tracking-wider text-success">
          Listo
        </p>
        <span className="text-xs text-muted">
          corregidas por el docente
        </span>
      </div>
      <ul className="divide-y divide-slate-100">
        {tareas.map((t) => {
          const entrega = entregasByTareaId[t.id]
          return (
            <li key={t.id}>
              <div
                data-testid="tp-card"
                data-tp-codigo={t.codigo}
                className="py-3 flex items-start gap-4"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="text-xs font-mono text-muted">
                      {t.codigo}
                    </span>
                    <span className="text-xs font-mono text-muted-soft">v{t.version}</span>
                    <span className="text-sm font-medium text-ink truncate">
                      {t.titulo}
                    </span>
                    {entrega && <EntregaBadge estado={entrega.estado} />}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onSelect(t)}
                  className="shrink-0 px-3 py-1.5 rounded text-xs font-medium bg-success-soft text-success hover:bg-green-200"
                >
                  Ver calificacion
                </button>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

// ─── Zona VENCIDAS: items compactos, sin CTA, color muted ─────────────

function ZoneVencidas({
  tareas,
  episodes,
}: {
  tareas: AvailableTarea[]
  episodes: StudentEpisode[]
}) {
  return (
    <section className="mb-6" data-testid="zone-vencidas">
      <div className="flex items-baseline gap-3 mb-3 border-b border-border-soft pb-1">
        <p className="text-xs font-mono uppercase tracking-wider text-muted">
          Vencidas
        </p>
        <span className="text-xs text-muted-soft">acceso solo lectura</span>
      </div>
      <ul className="divide-y divide-slate-100">
        {tareas.map((t) => {
          const lastResult = episodes
            .filter((ep) => ep.problema_id === t.id && ep.appropriation !== null)
            .sort((a, b) => {
              const da = a.classified_at ? new Date(a.classified_at).getTime() : 0
              const db = b.classified_at ? new Date(b.classified_at).getTime() : 0
              return db - da
            })[0]
          return (
            <li key={t.id} className="py-2.5 text-xs text-muted">
              <div className="flex items-center gap-2">
                <span className="font-mono">{t.codigo}</span>
                <span className="text-muted-soft">v{t.version}</span>
                <span className="text-body truncate">{t.titulo}</span>
              </div>
              {lastResult && lastResult.appropriation && (
                <p className="mt-1 text-muted flex items-center gap-1.5">
                  <span
                    aria-hidden="true"
                    className="inline-block w-2 h-2 rounded-full"
                    style={{ backgroundColor: appropriationColor(lastResult.appropriation) }}
                  />
                  Tu episodio: {appropriationLabel(lastResult.appropriation)}
                </p>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

// ─── Helpers ──────────────────────────────────────────────────────────

function appropriationColor(
  a: StudentEpisode["appropriation"] | null,
): string {
  switch (a) {
    case "apropiacion_reflexiva":
      return "var(--color-appropriation-reflexiva)"
    case "apropiacion_superficial":
      return "var(--color-appropriation-superficial)"
    case "delegacion_pasiva":
      return "var(--color-appropriation-delegacion)"
    default:
      return "var(--color-level-meta)"
  }
}

function appropriationLabel(a: NonNullable<StudentEpisode["appropriation"]>): string {
  switch (a) {
    case "apropiacion_reflexiva":
      return "apropiacion reflexiva"
    case "apropiacion_superficial":
      return "apropiacion superficial"
    case "delegacion_pasiva":
      return "delegacion pasiva"
  }
}

function appropriationAriaLabel(
  a: StudentEpisode["appropriation"] | null,
): string {
  if (!a) return "resultado pendiente"
  return appropriationLabel(a)
}

interface DeadlineInfo {
  label: string
  colorClass: string
}

/**
 * Formatea fecha_fin como string relativo y le asigna color segun
 * urgencia: rojo <24h, ambar <72h, gris resto.
 */
function formatDeadline(fechaFin: string | null): DeadlineInfo | null {
  if (!fechaFin) return null
  const end = new Date(fechaFin)
  if (Number.isNaN(end.getTime())) return null

  const now = Date.now()
  const diffMs = end.getTime() - now
  const absoluteLabel = end.toLocaleString("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })

  if (diffMs <= 0) {
    return {
      label: `${absoluteLabel} (vencido)`,
      colorClass: "text-danger font-medium",
    }
  }

  const diffHours = diffMs / (1000 * 60 * 60)
  let relative: string
  if (diffHours < 1) {
    relative = "en menos de 1 hora"
  } else if (diffHours < 24) {
    relative = `en ${Math.floor(diffHours)}h`
  } else {
    const days = Math.floor(diffHours / 24)
    relative = `en ${days}d`
  }

  let colorClass = "text-muted"
  if (diffHours < 24) {
    colorClass = "text-danger font-medium"
  } else if (diffHours < 72) {
    colorClass = "text-warning"
  }

  return {
    label: `Cierra ${absoluteLabel} (${relative})`,
    colorClass,
  }
}
