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
import { type EjercicioContext, EpisodeView } from "../pages/EpisodePage"
import {
  ACTIVE_EXERCISE_CONTEXT_KEY,
  type ActiveExerciseContext,
} from "./materia.$id"

export const Route = createFileRoute("/episodio/$id")({
  component: EpisodioPage,
})

function EpisodioPage() {
  const { id } = useParams({ from: "/episodio/$id" })
  const navigate = useNavigate()

  // Leer contexto de ejercicio del sessionStorage (si existe).
  const ejercicioContext = readEjercicioContext()

  function handleExit() {
    if (ejercicioContext) {
      navigate({
        to: "/materia/$id",
        params: { id: ejercicioContext.materiaId },
        search: { returnToExercise: true },
      })
    } else {
      navigate({ to: "/" })
    }
  }

  return (
    <EpisodeView
      episodeId={id}
      onExit={handleExit}
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

function readEjercicioContext(): {
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
