/**
 * Vista de detalle de calificacion de una entrega.
 *
 * Muestra:
 *   - nota_final (0-10)
 *   - feedback_general del docente
 *   - detalle_criterios con puntaje y comentario por criterio
 *
 * Se usa desde ExerciseListView cuando estado=graded y el estudiante
 * hace click en "Ver calificacion".
 *
 * Si estado=submitted (entrega pendiente de correccion), muestra el
 * mensaje de espera y NO intenta cargar calificacion.
 */
import { useEffect, useState } from "react"
import { type Calificacion, type Entrega, entregasApi } from "../lib/api"

export interface GradeDetailViewProps {
  entrega: Entrega
  onBack: () => void
}

export function GradeDetailView({ entrega, onBack }: GradeDetailViewProps) {
  const [calificacion, setCalificacion] = useState<Calificacion | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    if (entrega.estado !== "graded" && entrega.estado !== "returned") {
      setLoading(false)
      return
    }

    entregasApi
      .getCalificacion(entrega.id)
      .then((c) => {
        if (!cancelled) setCalificacion(c)
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
  }, [entrega.id, entrega.estado])

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8" data-testid="grade-detail-view">
      <div className="max-w-2xl mx-auto">
        <button
          type="button"
          onClick={onBack}
          className="text-xs text-muted hover:text-body mb-6 inline-flex items-center gap-1"
        >
          <span aria-hidden="true">←</span>
          Volver a la TP
        </button>

        <h2 className="text-xl font-semibold text-ink mb-6">
          Resultado de tu entrega
        </h2>

        {/* Estado: esperando correccion */}
        {(entrega.estado === "submitted") && (
          <div
            data-testid="pending-correction-state"
            className="rounded-lg border border-accent-brand/30 bg-accent-brand-soft p-6 text-center"
          >
            <p className="text-base font-medium text-accent-brand-deep mb-2">
              Pendiente de correccion
            </p>
            <p className="text-sm text-accent-brand-deep">
              Tu docente revisara la entrega proximamente. Te notificaremos cuando este lista.
            </p>
          </div>
        )}

        {/* Estado: cargando calificacion */}
        {loading && entrega.estado === "graded" && (
          <div className="flex items-center justify-center py-12">
            <div
              className="inline-block w-6 h-6 border-2 border-t-transparent rounded-full motion-safe:animate-spin"
              style={{ borderColor: "var(--color-accent-brand)", borderTopColor: "transparent" }}
            />
          </div>
        )}

        {/* Error cargando calificacion */}
        {error && (
          <div className="rounded-lg border border-danger/30 bg-danger-soft p-4">
            <p className="text-sm text-danger">{error}</p>
          </div>
        )}

        {/* Calificacion cargada */}
        {!loading && calificacion && (
          <div className="space-y-6" data-testid="calificacion-detail">
            {/* Nota final */}
            <div className="rounded-lg border border-border-soft bg-surface p-6 flex items-center gap-6">
              <div className="text-center">
                <p className="text-xs font-mono text-muted mb-1">
                  NOTA FINAL
                </p>
                <p
                  data-testid="nota-final"
                  className="text-5xl font-bold"
                  style={{
                    color:
                      calificacion.nota_final >= 6
                        ? "var(--color-appropriation-reflexiva)"
                        : calificacion.nota_final >= 4
                          ? "var(--color-appropriation-superficial)"
                          : "var(--color-appropriation-delegacion)",
                  }}
                >
                  {calificacion.nota_final}
                </p>
                <p className="text-xs text-muted-soft mt-0.5">/ 10</p>
              </div>
              {entrega.estado === "returned" && (
                <div className="flex-1 rounded-lg bg-warning-soft border border-warning/30 px-4 py-3">
                  <p className="text-xs font-medium text-warning/90 mb-1">
                    Tu docente devolvio la entrega
                  </p>
                  <p className="text-xs text-warning/85">
                    Revisa el feedback para entender los puntos a mejorar.
                  </p>
                </div>
              )}
            </div>

            {/* Feedback general */}
            {calificacion.feedback_general && (
              <div
                data-testid="feedback-general"
                className="rounded-lg border border-border-soft bg-surface p-5"
              >
                <p className="text-xs font-mono uppercase tracking-wider text-muted mb-3">
                  Feedback del docente
                </p>
                <p className="text-sm text-body whitespace-pre-wrap leading-relaxed">
                  {calificacion.feedback_general}
                </p>
              </div>
            )}

            {/* Detalle por criterio */}
            {calificacion.detalle_criterios && calificacion.detalle_criterios.length > 0 && (
              <div className="rounded-lg border border-border-soft bg-surface p-5">
                <p className="text-xs font-mono uppercase tracking-wider text-muted mb-4">
                  Criterios de evaluacion
                </p>
                <ul className="space-y-3" data-testid="criterios-list">
                  {calificacion.detalle_criterios.map((criterio, idx) => (
                    <li
                      key={`${criterio.nombre}-${idx}`}
                      data-testid="criterio-item"
                      className="border-b border-border-soft pb-3 last:border-0 last:pb-0"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium text-body">
                          {criterio.nombre}
                        </span>
                        <span className="text-xs font-mono text-muted">
                          {criterio.puntaje} / {Math.round(criterio.peso * 10)}
                        </span>
                      </div>
                      {criterio.comentario && (
                        <p className="text-xs text-muted leading-relaxed">
                          {criterio.comentario}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
