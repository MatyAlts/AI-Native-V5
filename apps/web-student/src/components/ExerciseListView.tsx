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
  DEFAULT_LANGUAGE,
  type Entrega,
  type EntregaEstado,
  type TpEjercicio,
  entregasApi,
  getEpisodeState,
  listEjerciciosTp,
  reabrirEjercicio,
} from "../lib/api"
import {
  type ArtefactoDraft,
  clearArtefactoDrafts,
  collectArtefactoDrafts,
} from "../lib/artefactos"
import { puedeEditarLaEntrega } from "../lib/entregaGuard"

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

/**
 * Junta el código a entregar: primero el borrador local, y para el ejercicio
 * que no lo tenga, el último snapshot que el episodio alcanzó a registrar.
 *
 * El fallback existe porque el borrador vive en `localStorage`, o sea en ESTE
 * navegador: un alumno que hizo el ejercicio 1 en la facultad y el 2 en casa
 * no tendría el 1, y el submit lo rechazaría por un ejercicio que sí hizo.
 * El snapshot del episodio es peor evidencia (es lo último que el editor
 * alcanzó a reportar, no lo que el alumno tenía en pantalla), pero se sella
 * con hash en el submit igual que el resto: entra como lo entregado, no como
 * una reconstrucción hecha al corregir.
 */
async function recuperarArtefactos(
  entrega: Entrega,
  ejercicios: Array<{ ejercicio_id: string; orden: number }>,
  ordenes: number[],
  language: string,
): Promise<ArtefactoDraft[]> {
  const locales = collectArtefactoDrafts(entrega.id, ordenes)
  const tengo = new Set(locales.map((a) => a.orden))
  const faltantes = ejercicios.filter((e) => !tengo.has(e.orden))
  if (faltantes.length === 0) return locales

  const estados = entrega.ejercicio_estados ?? []
  const recuperados = await Promise.all(
    faltantes.map(async (ej): Promise<ArtefactoDraft | null> => {
      const episodeId = estados.find((e) => e.orden === ej.orden)?.episode_id
      if (!episodeId) return null
      try {
        const state = await getEpisodeState(episodeId)
        if (!state.last_code_snapshot?.trim()) return null
        return {
          orden: ej.orden,
          ejercicio_id: ej.ejercicio_id,
          episode_id: episodeId,
          codigo: state.last_code_snapshot,
          language,
        }
      } catch {
        // Si no se puede recuperar, el submit va a rechazar nombrando el
        // ejercicio. Es mejor eso que entregar un ejercicio vacío.
        return null
      }
    }),
  )

  return [...locales, ...recuperados.filter((a): a is ArtefactoDraft => a !== null)].sort(
    (a, b) => a.orden - b.orden,
  )
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
  // `orden` del ejercicio que se esta reabriendo, o null. Se guarda el orden y
  // no un booleano para que el spinner quede en SU boton: con un flag global,
  // apretar uno pone "Abriendo..." en los cinco.
  const [reabriendo, setReabriendo] = useState<number | null>(null)

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

  /**
   * Devuelve un ejercicio completado al estado pendiente para que el alumno
   * pueda volver a entrar.
   *
   * Es la salida del callejon de BUG-1 (QA 2026-08-31) y no necesita ni al
   * docente ni un deploy: el endpoint existe desde junio. Al reabrir, el
   * alumno aprieta el boton normal y `openEpisodeAndNavigate` abre un episodio
   * NUEVO — el viejo esta `closed` y sigue cerrado, firmado y atestado. No se
   * reabre ningun episodio: se reabre el ejercicio, que es un flag de
   * progreso, no un hecho firmado.
   *
   * Se relee la entrega del server en vez de mutar la de memoria: el PATCH
   * devuelve la entrega entera y ese es el estado autoritativo, incluida la
   * reconciliacion que el backend pueda haber hecho de paso.
   */
  async function handleReabrir(ejercicio: { ejercicio_id: string; orden: number }) {
    if (!entrega) return
    setReabriendo(ejercicio.orden)
    setSubmitError(null)
    try {
      const actualizada = await reabrirEjercicio(
        entrega.id,
        ejercicio.orden,
        ejercicio.ejercicio_id,
      )
      setEntrega(actualizada)
    } catch (e) {
      setSubmitError(`No se pudo reabrir el ejercicio ${ejercicio.orden}: ${String(e)}`)
    } finally {
      setReabriendo(null)
    }
  }

  async function handleSubmit() {
    if (!entrega) return
    const confirmed = window.confirm(
      "Una vez entregada, tu docente sera notificado para corregirla. ¿Confirmas?",
    )
    if (!confirmed) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      // Se relee el estado ANTES de enviar, y no se confia en el que quedo en
      // memoria. `canSubmit` gatea el boton con `entrega.estado === "draft"`,
      // pero ese valor lo trae un `useEffect` que corre UNA sola vez al montar
      // y nunca repolla: una pestana vieja abierta en el celular sigue diciendo
      // "draft" horas despues de que el docente devolvio la entrega.
      //
      // Y el backend no salva: `submit_entrega` acepta `returned` como estado
      // de origen a proposito (es una feature legitima para cuando el alumno
      // corrige). Asi que el guard del frontend es la UNICA defensa, y uno que
      // mira estado cacheado es la mas debil de las dos que tiene la app —
      // `handleExit` en `episodio.$id.tsx` si hace fetch fresco.
      //
      // Sin esto queda la misma perdida de la devolucion que este PR cierra,
      // por otra puerta: `returned -> submitted` y el alumno deja de ver lo que
      // su docente le escribio.
      // `puedeEditarLaEntrega` y NO `debeEnviarLaEntrega`: son dos preguntas
      // distintas y difieren justo en `returned`. Aquella contesta "¿la mando
      // SOLO porque el alumno salio del episodio?" —y ahi `returned` tiene que
      // dar false, porque el envio automatico le borraria la devolucion. Esta
      // contesta "¿el alumno puede entregar?", y un TP devuelto se re-entrega:
      // es todo el punto de devolverlo. Usar aquella para las dos dejaba el
      // boton "Entregar TP" muerto justo despues de una devolucion (QA 31/08).
      const fresca = await entregasApi.getById(entrega.id)
      if (!puedeEditarLaEntrega(fresca.estado)) {
        setEntrega(fresca)
        setSubmitError("Esta entrega ya no admite cambios. Actualiza la pagina para ver su estado.")
        return
      }
      const ordenes = ejercicios.map((e) => e.orden)
      const artefactos = await recuperarArtefactos(
        entrega,
        ejercicios,
        ordenes,
        tarea.language ?? DEFAULT_LANGUAGE,
      )
      const updated = await entregasApi.submit(entrega.id, artefactos)
      setEntrega(updated)
      clearArtefactoDrafts(entrega.id, ordenes)
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

  // `draft` Y `returned`. Antes solo `draft`, y eso hacia que devolver un TP
  // le sacara al alumno el boton de entregar (QA 2026-08-31): el docente le
  // pedia que corrigiera y le tapaba la unica forma de devolverlo corregido.
  const editable = puedeEditarLaEntrega(entrega?.estado ?? "")
  const canSubmit = todosCompletos && editable

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
          <p className="text-sm font-medium text-danger mb-2">No pudimos cargar la entrega.</p>
          <p className="text-xs font-mono text-muted mb-4">{error}</p>
          <button type="button" onClick={onBack} className="text-sm underline text-body">
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
          <h2 className="text-xl font-semibold text-ink mb-2">{tarea.titulo}</h2>
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
          <div className="mb-6" data-testid="entrega-progress" data-tour="entrega-progreso">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-muted">Ejercicios completados</span>
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
                <span className="font-medium">Pendiente de correccion.</span> Tu docente revisara la
                entrega proximamente.
              </p>
            )}
            {(entrega.estado === "graded" || entrega.estado === "returned") && (
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <p className="text-sm text-body">
                  {entrega.estado === "graded" ? (
                    <>
                      <span className="font-medium">Calificada.</span> Tu docente ya corrigio la
                      entrega.
                    </>
                  ) : (
                    <>
                      <span className="font-medium">Devuelta para revisar.</span> Tu docente
                      devolvio la entrega con observaciones.
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
            const canStart = !locked && !completed && editable
            // La puerta de vuelta. Marcar completado era de una sola direccion:
            // `canStart` no DESHABILITA el boton de un ejercicio completado, no
            // lo renderiza — y un alumno cuyo codigo no quedo guardado se comia
            // "Falta el codigo de los ejercicios: [2,3,4,5]. Abri cada ejercicio
            // una vez antes de entregar", que le pide justo lo que la pantalla
            // le hizo imposible. El backend siempre supo des-marcar; no habia
            // ninguna puerta que llevara ahi.
            const canReopen = completed && editable
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
                        locked ? "text-muted" : completed ? "text-success" : "text-ink"
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
                      onClick={() => {
                        if (!entrega) return
                        onSelectEjercicio(
                          tarea,
                          { id: ejercicio.ejercicio_id, orden: ejercicio.orden },
                          entrega.id,
                        )
                      }}
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
                    <span className="shrink-0 text-xs text-success font-medium">Completado</span>
                  )}
                  {canReopen && (
                    <button
                      type="button"
                      onClick={() => void handleReabrir(ejercicio)}
                      disabled={reabriendo === ejercicio.orden}
                      data-testid={`ejercicio-reabrir-${ejercicio.orden}`}
                      className="shrink-0 rounded border border-border bg-surface px-3 py-1.5 text-xs font-medium text-body hover:bg-surface-alt disabled:opacity-60"
                    >
                      {reabriendo === ejercicio.orden ? "Abriendo..." : "Volver a abrir"}
                    </button>
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
