/**
 * Página de la materia seleccionada (post-craft Fase 2): /materia/$id.
 *
 * Layout:
 *   - Header contextual: kicker mono `CODIGO_MATERIA · COMISION · PERIODO`.
 *   - <TareaSelector> con las 3 zonas (Continuar / Proximas / Vencidas)
 *     que ya existe — recibe `comisionId` derivado de la inscripcion.
 *
 * Single-flight per page: usamos useQuery con la misma key `mis-materias`
 * que la home. Si el alumno entra desde la home, el dato ya está en cache
 * y NO hay re-fetch (staleTime 5min). Acceso directo por URL → fetch
 * inicial (caso refresh / link compartido).
 *
 * Flujo multi-ejercicio (tp-entregas-correccion):
 *   click TP con ejercicios → mostrar ExerciseListView
 *   click ejercicio → POST /api/v1/episodes con ejercicio_orden → navegar
 *
 * Flujo monolitico (legacy):
 *   click TP → POST /api/v1/episodes (sin ejercicio_orden) → navegar
 */
import { useQuery } from "@tanstack/react-query"
import { Link, createFileRoute, useNavigate, useParams } from "@tanstack/react-router"
import { z } from "zod"
import { useEffect, useState } from "react"
import { ExerciseListView } from "../components/ExerciseListView"
import { GradeDetailView } from "../components/GradeDetailView"
import { OpeningStage } from "../components/OpeningStage"
import { TareaSelector } from "../components/TareaSelector"
import { UnidadSelector } from "../components/UnidadSelector"
import {
  type AvailableTarea,
  type Entrega,
  type MateriaInscripta,
  fetchConfigHashes,
  getEpisodeState,
  getTareaById,
  listEjerciciosTp,
  listMisMaterias,
  listStudentEpisodes,
  openEpisode,
  resumeEpisode,
} from "../lib/api"

/** Contexto que se persiste en sessionStorage cuando el alumno entra a un ejercicio. */
export const ACTIVE_EXERCISE_CONTEXT_KEY = "active-exercise-context"

export interface ActiveExerciseContext {
  materia_id: string
  tarea_id: string
  entrega_id: string
  ejercicio_id: string
  ejercicio_orden: number
}

const searchSchema = z.object({
  returnToExercise: z.boolean().optional(),
})

export const Route = createFileRoute("/materia/$id")({
  component: MateriaPage,
  validateSearch: searchSchema,
})

/** Estado de la navegacion dentro de la pagina de materia. */
type MateriaPageView =
  | { kind: "unidades" }
  | { kind: "selector"; unidadId: string | null | undefined }
  | { kind: "exercise-list"; tarea: AvailableTarea }
  | { kind: "grade-detail"; tarea: AvailableTarea; entrega: Entrega }
  | {
      kind: "opening"
      tarea: AvailableTarea
      ejercicioId: string | null
      ejercicioOrden: number | null
      error: string | null
    }

function MateriaPage() {
  const { id } = useParams({ from: "/materia/$id" })
  const { returnToExercise } = Route.useSearch()
  const navigate = useNavigate()
  const [view, setView] = useState<MateriaPageView>({ kind: "unidades" })

  const { data: materias, isLoading, error } = useQuery({
    queryKey: ["mis-materias"],
    queryFn: () => listMisMaterias(),
    staleTime: 5 * 60 * 1000,
  })

  const materia = (materias ?? []).find((m) => m.materia_id === id)

  // Si el alumno volvio de un ejercicio, recuperar el contexto y re-abrir el ExerciseListView.
  useEffect(() => {
    if (!returnToExercise) return
    if (!materia) return
    const raw = window.sessionStorage.getItem(ACTIVE_EXERCISE_CONTEXT_KEY)
    if (!raw) return
    let ctx: ActiveExerciseContext
    try {
      ctx = JSON.parse(raw) as ActiveExerciseContext
    } catch {
      window.sessionStorage.removeItem(ACTIVE_EXERCISE_CONTEXT_KEY)
      return
    }
    if (ctx.materia_id !== id) {
      window.sessionStorage.removeItem(ACTIVE_EXERCISE_CONTEXT_KEY)
      return
    }
    // Limpiar el contexto ya consumido
    window.sessionStorage.removeItem(ACTIVE_EXERCISE_CONTEXT_KEY)
    // Quitar el query param de la URL sin reemplazar la entrada de historial
    void navigate({ to: "/materia/$id", params: { id }, replace: true })
    // Fetch de la tarea y abrir el ExerciseListView
    getTareaById(ctx.tarea_id).then((tarea) => {
      if (tarea) setView({ kind: "exercise-list", tarea })
    }).catch(() => { /* best-effort */ })
  }, [returnToExercise, materia, id, navigate])

  if (isLoading) {
    return <PageLoading />
  }

  if (error) {
    return <PageError detail={String(error)} />
  }

  if (!materia) {
    return <MateriaNotFound id={id} />
  }

  /**
   * Abre un episodio para la TP (monolitica o ejercicio especifico).
   * Navega a /episodio/:id al completar.
   *
   * Para ejercicios de TPs multi-ejercicio, persiste el contexto en
   * sessionStorage para que EpisodePage sepa donde volver al cerrar.
   * El entregaId se resuelve aqui porque ExerciseListView ya creo/recupero
   * la entrega en su propio mount — lo recibimos via callback.
   */
  async function openEpisodeAndNavigate(
    tarea: AvailableTarea,
    ejercicio: { id: string; orden: number } | null,
    entregaId?: string,
  ) {
    setView({
      kind: "opening",
      tarea,
      ejercicioId: ejercicio?.id ?? null,
      ejercicioOrden: ejercicio?.orden ?? null,
      error: null,
    })
    try {
      // ADR-055 (fix 2026-06-10 #2): si el alumno tiene un episodio PAUSADO de
      // esta TP con el mismo contexto (mismo ejercicio, o ambos monolíticos),
      // lo retoma en vez de abrir uno nuevo. Best-effort: cualquier falla acá
      // cae al flujo normal de apertura.
      try {
        const my = await listStudentEpisodes(materia!.comision_id)
        const paused = my.episodes.filter(
          (e) => e.estado === "paused" && e.problema_id === tarea.id,
        )
        for (const candidate of paused) {
          const st = await getEpisodeState(candidate.episode_id)
          if ((st.ejercicio_id ?? null) !== (ejercicio?.id ?? null)) continue
          await resumeEpisode(candidate.episode_id)
          if (ejercicio != null && entregaId) {
            const ctx: ActiveExerciseContext = {
              materia_id: id,
              tarea_id: tarea.id,
              entrega_id: entregaId,
              ejercicio_id: ejercicio.id,
              ejercicio_orden: ejercicio.orden,
            }
            window.sessionStorage.setItem(ACTIVE_EXERCISE_CONTEXT_KEY, JSON.stringify(ctx))
          }
          navigate({ to: "/episodio/$id", params: { id: candidate.episode_id } })
          return
        }
      } catch (e) {
        console.warn("resume de episodio pausado fallo; se abre uno nuevo:", e)
      }

      // Bootstrap F9: resolver hashes vigentes desde el backend. Si falla,
      // caemos al fallback hardcoded del piloto para no bloquear apertura.
      let cursoHash = "c".repeat(64)
      let classifierHash = "d".repeat(64)
      try {
        const hashes = await fetchConfigHashes(materia!.comision_id)
        cursoHash = hashes.curso_config_hash
        classifierHash = hashes.classifier_config_hash
      } catch (e) {
        console.warn("fetchConfigHashes fallo, usando fallback hardcoded:", e)
      }
      const res = await openEpisode({
        comision_id: materia!.comision_id,
        problema_id: tarea.id,
        curso_config_hash: cursoHash,
        classifier_config_hash: classifierHash,
        ...(ejercicio != null ? { ejercicio_id: ejercicio.id } : {}),
      })
      // Persistir contexto si es un ejercicio de TP multi-ejercicio
      if (ejercicio != null && entregaId) {
        const ctx: ActiveExerciseContext = {
          materia_id: id,
          tarea_id: tarea.id,
          entrega_id: entregaId,
          ejercicio_id: ejercicio.id,
          ejercicio_orden: ejercicio.orden,
        }
        window.sessionStorage.setItem(ACTIVE_EXERCISE_CONTEXT_KEY, JSON.stringify(ctx))
      }
      navigate({ to: "/episodio/$id", params: { id: res.episode_id } })
    } catch (e) {
      setView({
        kind: "opening",
        tarea,
        ejercicioId: ejercicio?.id ?? null,
        ejercicioOrden: ejercicio?.orden ?? null,
        error: `Error abriendo episodio: ${e}`,
      })
    }
  }

  /**
   * Callback del TareaSelector.
   * - TP sin ejercicios asociados (tabla intermedia vacía): abre episodio monolítico.
   * - TP con ejercicios: muestra ExerciseListView.
   *
   * El check ahora es un roundtrip a `/tareas-practicas/{id}/ejercicios` porque
   * `AvailableTarea` ya no trae el array embebido (ADR-047 — los ejercicios
   * viven en la tabla intermedia tp_ejercicios).
   */
  async function handleSelectTarea(tarea: AvailableTarea) {
    try {
      const pairs = await listEjerciciosTp(tarea.id)
      if (pairs.length > 0) {
        setView({ kind: "exercise-list", tarea })
      } else {
        await openEpisodeAndNavigate(tarea, null)
      }
    } catch {
      // Fallback: si falla el check, intentar abrir como monolítica.
      await openEpisodeAndNavigate(tarea, null)
    }
  }

  const currentView = view

  return (
    <>
      <ContextualHeader materia={materia} />

      {currentView.kind === "opening" && currentView.error && (
        <div className="bg-danger-soft text-danger px-6 py-2 text-sm">
          {currentView.error}
        </div>
      )}

      {currentView.kind === "unidades" && (
        <div className="flex-1 overflow-y-auto px-6 py-8">
          <div className="max-w-3xl mx-auto">
            <UnidadSelector
              comisionId={materia.comision_id}
              onSelect={(unidadId) =>
                setView({ kind: "selector", unidadId: unidadId ?? null })
              }
            />
          </div>
        </div>
      )}

      {currentView.kind === "selector" && (
        <TareaSelector
          comisionId={materia.comision_id}
          onSelect={handleSelectTarea}
          unidadId={currentView.unidadId}
          onBack={() => setView({ kind: "unidades" })}
        />
      )}

      {currentView.kind === "exercise-list" && (
        <ExerciseListView
          tarea={currentView.tarea}
          comisionId={materia.comision_id}
          onSelectEjercicio={(tarea, ejercicio, entregaId) => {
            void openEpisodeAndNavigate(tarea, ejercicio, entregaId)
          }}
          onViewGrade={(entrega) =>
            setView({ kind: "grade-detail", tarea: currentView.tarea, entrega })
          }
          onBack={() => setView({ kind: "unidades" })}
        />
      )}

      {currentView.kind === "grade-detail" && (
        <GradeDetailView
          entrega={currentView.entrega}
          onBack={() => setView({ kind: "exercise-list", tarea: currentView.tarea })}
        />
      )}

      {currentView.kind === "opening" && (
        <OpeningStage
          tareaCodigo={currentView.tarea.codigo}
          tareaTitulo={currentView.tarea.titulo}
          episodeReady={false}
          {...(currentView.error ? { errorMessage: currentView.error } : {})}
          onShowError={() => {
            // El error ya esta visible en el banner rojo de arriba.
          }}
          onRetry={() => {
            const ej =
              currentView.ejercicioId && currentView.ejercicioOrden != null
                ? { id: currentView.ejercicioId, orden: currentView.ejercicioOrden }
                : null
            void openEpisodeAndNavigate(currentView.tarea, ej)
          }}
          onCancel={() => {
            // Si veniamos de un ejercicio dentro de TP multi, volvemos a
            // la lista de ejercicios; si no, al selector general.
            if (currentView.ejercicioId != null) {
              setView({ kind: "exercise-list", tarea: currentView.tarea })
            } else {
              setView({ kind: "unidades" })
            }
          }}
        />
      )}
    </>
  )
}

function ContextualHeader({ materia }: { materia: MateriaInscripta }) {
  return (
    <div
      data-testid="materia-context-header"
      className="border-b border-border-soft px-6 py-3 bg-white flex items-center gap-3 flex-wrap"
    >
      <Link
        to="/"
        className="text-xs text-muted hover:text-body"
        data-testid="materia-back-link"
      >
        ← Mis materias
      </Link>
      <span aria-hidden="true" className="text-muted-soft">
        |
      </span>
      <MateriaContextLine materia={materia} />
      <span className="text-sm font-medium text-ink truncate ml-auto">
        {materia.nombre}
      </span>
      <Link
        to="/instrumentos"
        search={{ comisionId: materia.comision_id }}
        className="text-xs px-2.5 py-1 rounded-md border border-border bg-canvas text-body hover:bg-accent-brand-soft hover:text-accent-brand-deep hover:border-accent-brand/40 transition-colors shrink-0"
        data-testid="materia-link-instrumentos"
      >
        Cuestionarios de investigación
      </Link>
    </div>
  )
}

/**
 * Linea pura del header contextual — kicker mono con codigo + comision + periodo.
 * Extraida del header para que pueda testearse sin RouterProvider.
 */
export function MateriaContextLine({ materia }: { materia: MateriaInscripta }) {
  const comisionLabel = materia.comision_nombre ?? `Comision ${materia.comision_codigo}`
  return (
    <p
      data-testid="materia-context-line"
      className="text-xs font-mono uppercase tracking-wider text-body"
    >
      <span data-testid="materia-header-codigo">{materia.codigo}</span>
      <span className="text-muted-soft mx-1.5">·</span>
      <span data-testid="materia-header-comision">{comisionLabel}</span>
      <span className="text-muted-soft mx-1.5">·</span>
      <span data-testid="materia-header-periodo">{materia.periodo_codigo}</span>
    </p>
  )
}

function PageLoading() {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div
        className="inline-block w-6 h-6 border-2 border-t-transparent rounded-full motion-safe:animate-spin"
        style={{ borderColor: "var(--color-accent-brand)", borderTopColor: "transparent" }}
      />
    </div>
  )
}

function PageError({ detail }: { detail: string }) {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-md text-center">
        <p className="text-sm font-medium text-danger mb-2">
          No pudimos cargar la materia.
        </p>
        <p className="text-xs font-mono text-muted">{detail}</p>
      </div>
    </div>
  )
}

function MateriaNotFound({ id }: { id: string }) {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-md text-center">
        <p className="text-sm font-medium text-body mb-2">
          Esta materia no esta entre tus inscripciones activas.
        </p>
        <p className="text-xs font-mono text-muted mb-4">id: {id}</p>
        <Link
          to="/"
          className="text-sm underline text-body"
          data-testid="materia-not-found-back"
        >
          Volver a mis materias
        </Link>
      </div>
    </div>
  )
}
