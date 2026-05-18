/**
 * Vista de lista de ejercicios de una TP multi-ejercicio.
 *
 * Muestra los ejercicios en orden con estados:
 *   - bloqueado: ejercicios anteriores no completados
 *   - disponible: puede ser iniciado
 *   - completado: episodio cerrado asociado
 *   - entrega: badge de estado (draft/submitted/graded/returned)
 *
 * Flujo:
 *   1. Al montar, crea/recupera la entrega (idempotente).
 *   2. Muestra ejercicios con lock/unlock segun ejercicio_estados.
 *   3. Click en ejercicio disponible → onSelectEjercicio(tarea, orden).
 *   4. Cuando todos completos, muestra "Entregar TP" button.
 *   5. Cuando estado=submitted o graded, muestra badge informativo.
 */
import { useEffect, useState } from "react"
import {
  type AvailableTarea,
  type Entrega,
  type EntregaEstado,
  type TpEjercicio,
  entregasApi,
  listEjerciciosTp,
} from "../lib/api"

export interface ExerciseListViewProps {
  tarea: AvailableTarea
  comisionId: string
  /** entregaId se pasa para que el caller pueda persistir el contexto de ejercicio. */
  onSelectEjercicio: (
    tarea: AvailableTarea,
    ejercicio: { id: string; orden: number },
    entregaId: string,
  ) => void
  onViewGrade: (entrega: Entrega) => void
  onBack: () => void
}

function entregaEstadoLabel(estado: EntregaEstado): string {
  switch (estado) {
    case "draft":
      return "En progreso"
    case "submitted":
      return "Entregada"
    case "graded":
      return "Calificada"
    case "returned":
      return "Devuelta"
  }
}

function entregaEstadoBadgeClass(estado: EntregaEstado): string {
  switch (estado) {
    case "draft":
      return "bg-surface-alt text-body"
    case "submitted":
      return "bg-accent-brand-soft text-accent-brand-deep"
    case "graded":
      return "bg-success-soft text-success"
    case "returned":
      return "bg-warning-soft text-warning/85"
  }
}

export function ExerciseListView({
  tarea,
  comisionId,
  onSelectEjercicio,
  onViewGrade,
  onBack,
}: ExerciseListViewProps) {
  const [entrega, setEntrega] = useState<Entrega | null>(null)
  const [pairs, setPairs] = useState<TpEjercicio[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // ADR-047: cargar entrega + composicion de ejercicios (tabla intermedia)
  // en paralelo. tarea.ejercicios ya no viene embebido — lo resolvemos via
  // GET /tareas-practicas/{id}/ejercicios.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([
      entregasApi.createOrGet({ tarea_practica_id: tarea.id, comision_id: comisionId }),
      listEjerciciosTp(tarea.id),
    ])
      .then(([e, p]) => {
        if (!cancelled) {
          setEntrega(e)
          setPairs(p)
        }
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
  }, [tarea.id, comisionId])

  async function handleSubmit() {
    if (!entrega) return
    const confirmed = window.confirm(
      "Una vez entregada, tu docente sera notificado para corregirla. ¿Confirmas?",
    )
    if (!confirmed) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const updated = await entregasApi.submit(entrega.id)
      setEntrega(updated)
    } catch (e) {
      setSubmitError(String(e))
    } finally {
      setSubmitting(false)
    }
  }

  // Vista normalizada: orden + titulo + peso(decimal) + ejercicio_id permanente.
  const ejercicios = [...pairs]
    .sort((a, b) => a.orden - b.orden)
    .map((p) => ({
      ejercicio_id: p.ejercicio_id,
      orden: p.orden,
      titulo: p.ejercicio.titulo,
      peso: Number.parseFloat(p.peso_en_tp),
    }))
  const ejercicioEstados = entrega?.ejercicio_estados ?? []
  const completados = ejercicioEstados.filter((e) => e.completado).length
  const totalEjercicios = ejercicios.length
  const todosCompletos = completados === totalEjercicios && totalEjercicios > 0

  const canSubmit =
    todosCompletos && entrega?.estado === "draft"

  const isLocked = (orden: number): boolean => {
    if (orden === 1) return false
    // Los ejercicios son secuenciales: el anterior debe estar completado
    const prevEstado = ejercicioEstados.find((e) => e.orden === orden - 1)
    return !prevEstado?.completado
  }

  const isCompleted = (orden: number): boolean => {
    return ejercicioEstados.find((e) => e.orden === orden)?.completado ?? false
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div
          className="inline-block w-6 h-6 border-2 border-t-transparent rounded-full motion-safe:animate-spin"
          style={{ borderColor: "var(--color-accent-brand)", borderTopColor: "transparent" }}
        />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center px-4">
        <div className="max-w-md text-center">
          <p className="text-sm font-medium text-danger mb-2">
            No pudimos cargar la entrega.
          </p>
          <p className="text-xs font-mono text-muted mb-4">{error}</p>
          <button
            type="button"
            onClick={onBack}
            className="text-sm underline text-body"
          >
            Volver
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8" data-testid="exercise-list-view">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <button
            type="button"
            onClick={onBack}
            className="text-xs text-muted hover:text-body mb-3 inline-flex items-center gap-1"
          >
            <span aria-hidden="true">←</span>
            Volver a TPs
          </button>
          <p className="text-xs font-mono text-muted mb-1">
            {tarea.codigo} (v{tarea.version})
          </p>
          <h2 className="text-xl font-semibold text-ink mb-2">
            {tarea.titulo}
          </h2>
          {entrega && (
            <span
              data-testid="entrega-estado-badge"
              className={`inline-block text-xs font-mono px-2 py-0.5 rounded ${entregaEstadoBadgeClass(entrega.estado)}`}
            >
              {entregaEstadoLabel(entrega.estado)}
            </span>
          )}
        </div>

        {/* Barra de progreso */}
        {totalEjercicios > 0 && (
          <div className="mb-6" data-testid="entrega-progress">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-muted">
                Ejercicios completados
              </span>
              <span className="text-xs font-mono text-body">
                {completados}/{totalEjercicios}
              </span>
            </div>
            <div className="w-full h-1.5 bg-surface-alt rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${totalEjercicios > 0 ? (completados / totalEjercicios) * 100 : 0}%`,
                  backgroundColor: todosCompletos
                    ? "var(--color-appropriation-reflexiva)"
                    : "var(--color-accent-brand)",
                }}
                data-testid="progress-bar-fill"
              />
            </div>
          </div>
        )}

        {/* Estado submitted/graded/returned — info block */}
        {entrega && entrega.estado !== "draft" && (
          <div className="mb-6 rounded-lg border border-border-soft bg-surface-alt p-4">
            {entrega.estado === "submitted" && (
              <p className="text-sm text-body">
                <span className="font-medium">Pendiente de correccion.</span>{" "}
                Tu docente revisara la entrega proximamente.
              </p>
            )}
            {(entrega.estado === "graded" || entrega.estado === "returned") && (
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <p className="text-sm text-body">
                  {entrega.estado === "graded" ? (
                    <>
                      <span className="font-medium">Calificada.</span>{" "}
                      Tu docente ya corrigio la entrega.
                    </>
                  ) : (
                    <>
                      <span className="font-medium">Devuelta para revisar.</span>{" "}
                      Tu docente devolvio la entrega con observaciones.
                    </>
                  )}
                </p>
                <button
                  type="button"
                  data-testid="ver-calificacion-btn"
                  onClick={() => onViewGrade(entrega)}
                  className="shrink-0 px-3 py-1.5 rounded border border-border bg-surface text-xs font-medium text-body hover:bg-surface-alt"
                >
                  Ver calificacion →
                </button>
              </div>
            )}
          </div>
        )}

        {/* Lista de ejercicios */}
        <ul className="space-y-3" data-testid="ejercicios-list">
          {ejercicios.map((ejercicio, idx) => {
            const locked = isLocked(ejercicio.orden)
            const completed = isCompleted(ejercicio.orden)
            const canStart = !locked && !completed && entrega?.estado === "draft"
            const isFirst = idx === 0

            return (
              <li
                key={ejercicio.orden}
                data-testid={`ejercicio-item-${ejercicio.orden}`}
                className={`rounded-lg border p-4 transition-colors ${
                  completed
                    ? "border-success/30 bg-success-soft"
                    : locked
                      ? "border-border-soft bg-surface-alt opacity-60"
                      : "border-border bg-surface"
                }`}
              >
                <div className="flex items-center gap-3">
                  {/* Indicador visual */}
                  <div
                    aria-hidden="true"
                    className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-mono font-medium ${
                      completed
                        ? "bg-green-600 text-white"
                        : locked
                          ? "bg-surface-alt text-muted"
                          : "border-2 border-border-strong text-muted"
                    }`}
                  >
                    {completed ? "✓" : ejercicio.orden}
                  </div>

                  <div className="flex-1 min-w-0">
                    <p
                      className={`text-sm font-medium truncate ${
                        locked
                          ? "text-muted"
                          : completed
                            ? "text-success"
                            : "text-ink"
                      }`}
                    >
                      Ejercicio {ejercicio.orden}: {ejercicio.titulo}
                    </p>
                    <p className="text-xs text-muted mt-0.5">
                      Peso: {Math.round(ejercicio.peso * 100)}%
                      {locked && !isFirst && (
                        <span className="ml-2 text-muted-soft">
                          · Completar ejercicio anterior primero
                        </span>
                      )}
                    </p>
                  </div>

                  {canStart && (
                    <button
                      type="button"
                      onClick={() =>
                        onSelectEjercicio(
                          tarea,
                          { id: ejercicio.ejercicio_id, orden: ejercicio.orden },
                          entrega!.id,
                        )
                      }
                      data-testid={`ejercicio-start-${ejercicio.orden}`}
                      className="shrink-0 px-3 py-1.5 rounded text-xs font-medium text-white"
                      style={{ backgroundColor: "var(--color-accent-brand)" }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor = "var(--color-accent-brand-deep)"
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = "var(--color-accent-brand)"
                      }}
                    >
                      {idx === 0 && completados === 0 ? "Empezar" : "Continuar"}
                    </button>
                  )}
                  {completed && (
                    <span className="shrink-0 text-xs text-success font-medium">
                      Completado
                    </span>
                  )}
                </div>
              </li>
            )
          })}
        </ul>

        {/* Boton Entregar TP */}
        {canSubmit && (
          <div className="mt-6">
            {submitError && (
              <div className="mb-3 rounded-lg border border-danger/40 bg-danger-soft p-3 text-xs text-danger">
                {submitError}
              </div>
            )}
            <button
              type="button"
              onClick={() => void handleSubmit()}
              disabled={submitting}
              data-testid="submit-entrega-btn"
              className="w-full py-3 rounded-lg text-sm font-semibold text-white disabled:opacity-60 transition-opacity"
              style={{ backgroundColor: "var(--color-accent-brand)" }}
              onMouseEnter={(e) => {
                if (!submitting)
                  e.currentTarget.style.backgroundColor = "var(--color-accent-brand-deep)"
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = "var(--color-accent-brand)"
              }}
            >
              {submitting ? "Enviando..." : "Entregar TP"}
            </button>
            <p className="text-xs text-center text-muted mt-2">
              Al entregar, tu docente recibira notificacion para corregirla.
            </p>
          </div>
        )}

        {/* Estado: ya entregada — no puede re-entregar */}
        {entrega && entrega.estado === "submitted" && (
          <div className="mt-6 py-3 rounded-lg text-center text-sm text-muted border border-border-soft">
            TP entregada. Esperando correccion del docente.
          </div>
        )}
      </div>
    </div>
  )
}
