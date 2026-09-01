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
import { enviarEntregaAlSalir } from "../lib/entregaAlSalir"
import { debeEnviarLaEntrega } from "../lib/entregaGuard"
import { type EjercicioContext, EpisodeView } from "../pages/EpisodePage"
import { ACTIVE_EXERCISE_CONTEXT_KEY, type ActiveExerciseContext } from "./materia.$id"

// Se re-exporta desde acá porque es donde vivía y donde lo importa su test.
// La definición se mudó a `lib/` para que `ExerciseListView` —que también
// necesita el guard— no tenga que importar una RUTA: eso cerraba un ciclo
// (`ExerciseListView` -> `episodio.$id` -> `materia.$id` -> `ExerciseListView`).
export { debeEnviarLaEntrega }

export const Route = createFileRoute("/episodio/$id")({
  component: EpisodioPage,
})

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
    // TP monolitica (sin ejercicioContext). Cerrar el episodio ES la entrega:
    // si quedo `closed`, se crea y se envia para que la card del selector diga
    // "Entregada" en vez de seguir en "Empezar".
    //
    // La logica vive en `lib/entregaAlSalir` y no aca: enterrada adentro de esta
    // ruta nadie podia testearla, y es el camino por el que una entrega en
    // `returned` se re-enviaria borrandole la devolucion al docente.
    await enviarEntregaAlSalir(id, getToken)
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
