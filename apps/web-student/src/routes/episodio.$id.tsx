/**
 * Pagina del episodio activo (post-craft Fase 2): /episodio/$id.
 *
 * Es la EpisodePage original refactoreada para que `episodeId` venga del
 * path param (typed by TanStack Router) en vez del state. Mantiene TODA la
 * logica interna del episodio activo: chat, editor, classifier panel,
 * reflexion modal, audit footer pollado.
 *
 * Recovery on-mount: leemos `getEpisodeState({episodeId})` para hidratar
 * la TP, mensajes y codigo. Si el episodio ya cerro, redirigimos a la
 * home del materia (o a "/" si no podemos derivar la materia). Si el
 * episodio no existe, volvemos a "/" con sessionStorage limpio.
 *
 * Flujo multi-ejercicio: si hay `active-exercise-context` en sessionStorage,
 * se pasa el contexto a EpisodeView y al salir se navega de vuelta al
 * ExerciseListView de la TP correspondiente.
 */
import { createFileRoute, useNavigate, useParams } from "@tanstack/react-router"
import { createOrGetEntrega, getEpisodeState, submitEntrega } from "../lib/api"
import { type EjercicioContext, EpisodeView } from "../pages/EpisodePage"
import { ACTIVE_EXERCISE_CONTEXT_KEY, type ActiveExerciseContext } from "./materia.$id"

export const Route = createFileRoute("/episodio/$id")({
  component: EpisodioPage,
})

/**
 * Si al salir de un episodio cerrado hay que enviar la entrega automaticamente.
 *
 * Se saca a una funcion pura porque la decision vivia enterrada adentro de
 * `handleExit`, y por eso nadie la habia testeado nunca: para ejercitarla habia
 * que montar la ruta entera con el router y tres llamadas de red mockeadas.
 *
 * **`returned` NO se re-envia, y ese era el bug.** El guard aceptaba
 * `draft || returned`. Una entrega en `returned` es una que el docente devolvio
 * para corregir; volver a enviarla la pasa a `submitted` y **borra la
 * devolucion**. Y no hacia falta que el alumno apretara nada: basta con que
 * vuelva a entrar al episodio cerrado —la hidratacion de `EpisodePage` llama
 * `onExit()` sola al ver `estado === "closed"`— para que el ciclo se dispare.
 *
 * O sea: el alumno abre el episodio para LEER lo que el docente le escribio, y
 * el solo hecho de abrirlo le borra esa devolucion.
 *
 * `draft` si se envia: para la TP monolitica (sin `ejercicioContext`) cerrar el
 * episodio ES la entrega, y sin esto la card del selector se queda en "Empezar"
 * aunque el alumno haya terminado.
 */
export function debeEnviarLaEntrega(estadoEntrega: string): boolean {
  return estadoEntrega === "draft"
}

function EpisodioPage() {
  const { id } = useParams({ from: "/episodio/$id" })
  const navigate = useNavigate()
  // getToken viene del router context (seteado desde useAuth() de Clerk en
  // main.tsx; en dev sin Clerk devuelve null). Se lo pasamos a EpisodeView
  // para que el emit de abandono use fetch(keepalive) con Bearer en vez de
  // sendBeacon (que no pasa por el override de window.fetch y llega sin token
  // → 401 → el evento nunca se appendea). Fix QA 2026-06-15 #9.
  const { getToken } = Route.useRouteContext()

  // Leer contexto de ejercicio del sessionStorage (si existe).
  // NB-6: el contexto solo aplica si fue guardado para ESTE episodio.
  // sessionStorage usa una unica clave global — sin scope por episodio, un
  // contexto viejo (de otro episodio) se leia como si fuera el actual y hacia
  // que al cerrar el episodio se marcara como completo un ejercicio ajeno.
  const ejercicioContext = readEjercicioContext(id)

  async function handleExit() {
    if (ejercicioContext) {
      navigate({
        to: "/materia/$id",
        params: { id: ejercicioContext.materiaId },
        search: { returnToExercise: true },
      })
      return
    }
    // TP monolitica (sin ejercicioContext). Cerrar el episodio ES la entrega.
    // Si el episodio quedo "closed" (el alumno finalizo, no pauso), creamos y
    // enviamos la Entrega para que la card del selector refleje "Entregada" en
    // vez de seguir en "Empezar". El refetch lo hace el TareaSelector al
    // remontar cuando el alumno vuelve a la materia.
    // Best-effort: si algo falla, no bloqueamos la salida.
    try {
      const state = await getEpisodeState(id, getToken)
      if (state.estado === "closed") {
        const entrega = await createOrGetEntrega(
          {
            tarea_practica_id: state.tarea_practica_id,
            comision_id: state.comision_id,
          },
          getToken,
        )
        if (debeEnviarLaEntrega(entrega.estado)) {
          await submitEntrega(entrega.id, getToken)
        }
      }
    } catch {
      // best-effort: no bloquear la navegacion si falla la creacion/envio.
    }
    navigate({ to: "/" })
  }

  return (
    <EpisodeView
      episodeId={id}
      onExit={handleExit}
      getToken={getToken}
      {...(ejercicioContext
        ? {
            ejercicioContext: {
              entregaId: ejercicioContext.entregaId,
              ejercicioId: ejercicioContext.ejercicioId,
              ejercicioOrden: ejercicioContext.ejercicioOrden,
            } satisfies EjercicioContext,
          }
        : {})}
    />
  )
}

function readEjercicioContext(episodeId: string): {
  materiaId: string
  entregaId: string
  ejercicioId: string
  ejercicioOrden: number
} | null {
  if (typeof window === "undefined") return null
  const raw = window.sessionStorage.getItem(ACTIVE_EXERCISE_CONTEXT_KEY)
  if (!raw) return null
  try {
    const ctx = JSON.parse(raw) as ActiveExerciseContext
    // NB-6: descartar el contexto si no fue guardado para este episodio.
    // Contextos de episodios previos (o pre-migracion, sin `episode_id`) NO
    // deben aplicarse al actual — sino se marca completo el ejercicio ajeno.
    if (ctx.episode_id !== episodeId) return null
    return {
      materiaId: ctx.materia_id,
      entregaId: ctx.entrega_id,
      ejercicioId: ctx.ejercicio_id,
      ejercicioOrden: ctx.ejercicio_orden,
    }
  } catch {
    return null
  }
}
