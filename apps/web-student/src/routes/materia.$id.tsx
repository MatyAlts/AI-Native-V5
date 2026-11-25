/**
 * Página de la materia seleccionada (post-craft Fase 2): /materia/$id.
 *
 * Desde el campus (HU-035) se entra siempre con `?tareaId=<tp>`: la pagina
 * abre ese TP y deja el parametro en la URL, asi recargar vuelve al mismo TP.
 * Sin `tareaId` ni `returnToExercise` no hay nada que mostrar aca: se redirige
 * al campus del curso (`/curso/$comisionId`). El viejo selector de unidades y
 * de TPs ya no se muestra.
 *
 * Layout:
 *   - Header contextual: kicker mono `CODIGO_MATERIA · COMISION · PERIODO`.
 *
 * Single-flight per page: usamos useQuery con la misma key `mis-materias`
 * que la home. Si el alumno entra desde la home, el dato ya está en cache
 * y NO hay re-fetch (staleTime 5min). Acceso directo por URL → fetch
 * inicial (caso refresh / link compartido).
 *
 * Flujo multi-ejercicio (tp-entregas-correccion):
 *   TP con ejercicios → mostrar ExerciseListView
 *   click ejercicio → POST /api/v1/episodes con ejercicio_orden → navegar
 *
 * Flujo monolitico (legacy):
 *   TP sin ejercicios → POST /api/v1/episodes (sin ejercicio_orden) → navegar
 */
import { useQuery } from "@tanstack/react-query"
import { Link, createFileRoute, useNavigate, useParams } from "@tanstack/react-router"
import { useEffect, useRef, useState } from "react"
import { z } from "zod"
import { ExerciseListView } from "../components/ExerciseListView"
import { GradeDetailView } from "../components/GradeDetailView"
import { OpeningStage } from "../components/OpeningStage"
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
import { mensajeAlAbrirEpisodio } from "../utils/mensajesPlazo"
import { argumentosDeReintento } from "../utils/reintentoApertura"

/** Contexto que se persiste en sessionStorage cuando el alumno entra a un ejercicio. */
export const ACTIVE_EXERCISE_CONTEXT_KEY = "active-exercise-context"

export interface ActiveExerciseContext {
  materia_id: string
  tarea_id: string
  entrega_id: string
  ejercicio_id: string
  ejercicio_orden: number
  /** Episodio al que pertenece este contexto (NB-6). Se usa para descartar el
   * contexto cuando el episodio abierto NO es este, evitando marcar como
   * completo un ejercicio de otro episodio (cross-contamination). */
  episode_id: string
}

const searchSchema = z.object({
  returnToExercise: z.boolean().optional(),
  // HU-035: el campus (pestaña Trabajos practicos de la unidad) entra con el
  // TP elegido; se abre directo (`handleSelectTarea`) y queda en la URL.
  tareaId: z.string().optional(),
})

export const Route = createFileRoute("/materia/$id")({
  component: MateriaPage,
  validateSearch: searchSchema,
})

/** Estado de la navegacion dentro de la pagina de materia. */
type MateriaPageView =
  /** Mientras se resuelve el TP de la URL (o se redirige al campus). */
  | { kind: "cargando" }
  | { kind: "exercise-list"; tarea: AvailableTarea }
  | {
      kind: "grade-detail"
      tarea: AvailableTarea
      entrega: Entrega
      /** Vista a la que vuelve "← Volver" (hoy, el ExerciseListView). */
      back: MateriaPageView
    }
  | {
      kind: "opening"
      tarea: AvailableTarea
      ejercicioId: string | null
      ejercicioOrden: number | null
      /** Se guarda para que "Reintentar" vuelva a atar el episodio al
       * ejercicio (HU-020, F21). */
      entregaId: string | null
      error: string | null
    }

function MateriaPage() {
  const { id } = useParams({ from: "/materia/$id" })
  const { returnToExercise, tareaId } = Route.useSearch()
  const navigate = useNavigate()
  const [view, setView] = useState<MateriaPageView>({ kind: "cargando" })
  // NB-10: guard anti doble-submit. Un doble-click en "Empezar" disparaba dos
  // POST /episodes → dos episodios. La ref es sincronica (a diferencia de un
  // useState) asi que el segundo click ve el flag ya seteado y aborta.
  const openingRef = useRef(false)

  const {
    data: materias,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["mis-materias"],
    queryFn: () => listMisMaterias(),
    staleTime: 5 * 60 * 1000,
  })

  const materia = (materias ?? []).find((m) => m.materia_id === id)

  // HU-035: `?tareaId=` abre ese TP directo y QUEDA en la URL: recargar vuelve
  // al mismo TP. Se abre una sola vez por `tareaId` (ref; sobrevive al doble
  // efecto de StrictMode). Un TP sin ejercicios abre el episodio enseguida y
  // ahi la URL se reemplaza por la del episodio (ver `openEpisodeAndNavigate`),
  // para que el "atras" desde el episodio no abra otro.
  const tareaIdConsumida = useRef<string | null>(null)

  // Si el alumno volvio de un ejercicio, recuperar el contexto y re-abrir el
  // ExerciseListView, dejando la URL en `?tareaId=<tp>` (sobrevive a recargar).
  const vueltaConsumida = useRef(false)
  // El ref garantiza que la vuelta se procese una sola vez.
  useEffect(() => {
    if (!returnToExercise) return
    if (!materia) return
    if (vueltaConsumida.current) return
    vueltaConsumida.current = true
    const raw = window.sessionStorage.getItem(ACTIVE_EXERCISE_CONTEXT_KEY)
    let ctx: ActiveExerciseContext | null = null
    try {
      ctx = raw ? (JSON.parse(raw) as ActiveExerciseContext) : null
    } catch {
      ctx = null
    }
    window.sessionStorage.removeItem(ACTIVE_EXERCISE_CONTEXT_KEY)
    if (!ctx || ctx.materia_id !== id) {
      irAlCampus(navigate, materia.comision_id, null, true)
      return
    }
    const tareaVuelta = ctx.tarea_id
    // El TP ya se abre aca: que el efecto de `tareaId` no lo vuelva a abrir.
    tareaIdConsumida.current = tareaVuelta
    void navigate({
      to: "/materia/$id",
      params: { id },
      search: { tareaId: tareaVuelta },
      replace: true,
    })
    getTareaById(tareaVuelta)
      .then((tarea) => {
        if (tarea) setView({ kind: "exercise-list", tarea })
        else irAlCampus(navigate, materia.comision_id, null, true)
      })
      .catch(() => irAlCampus(navigate, materia.comision_id, null, true))
  }, [returnToExercise, materia, id, navigate])

  // `handleSelectTarea` (funcion del render, no memoizada) queda fuera de las
  // deps a proposito: el ref garantiza una sola apertura por `tareaId`.
  useEffect(() => {
    if (!tareaId || !materia) return
    if (tareaIdConsumida.current === tareaId) return
    tareaIdConsumida.current = tareaId
    getTareaById(tareaId)
      .then((tarea) => {
        if (tarea) void handleSelectTarea(tarea)
        else irAlCampus(navigate, materia.comision_id, null, true)
      })
      .catch(() => irAlCampus(navigate, materia.comision_id, null, true))
  }, [tareaId, materia, navigate])

  // HU-035: la materia sola no tiene pantalla propia; va al campus del curso.
  useEffect(() => {
    if (tareaId || returnToExercise || !materia) return
    void navigate({
      to: "/curso/$comisionId",
      params: { comisionId: materia.comision_id },
      replace: true,
    })
  }, [tareaId, returnToExercise, materia, navigate])

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
    // NB-10: abortar si ya hay una apertura en curso (doble-click).
    if (openingRef.current) return
    // Guard defensivo: esta función solo se invoca desde botones renderizados
    // después del `if (!materia) return <MateriaNotFound />` de arriba, pero
    // TS no propaga esa narrowing a esta closure.
    if (!materia) return
    openingRef.current = true
    setView({
      kind: "opening",
      tarea,
      ejercicioId: ejercicio?.id ?? null,
      ejercicioOrden: ejercicio?.orden ?? null,
      entregaId: entregaId ?? null,
      error: null,
    })
    try {
      // ADR-055 (fix 2026-06-10 #2): si el alumno tiene un episodio SIN CERRAR de
      // esta TP con el mismo contexto (mismo ejercicio, o ambos monolíticos),
      // lo retoma en vez de abrir uno nuevo. Best-effort: cualquier falla acá
      // cae al flujo normal de apertura.
      //
      // Fix episodios fantasma (2026-06-17): considerar también episodios en
      // estado "open", no solo "paused". El alumno puede reabrir el ejercicio
      // antes de que el worker server-side pase el episodio anterior de "open"
      // a "paused" (race del worker de abandono). Filtrar solo "paused" dejaba
      // ese episodio sin matchear y abría uno nuevo → fantasmas. El backend
      // (tutor_core.open_episode) tiene la red de seguridad real e idempotente;
      // este filtro evita el round-trip de apertura cuando ya es detectable acá.
      try {
        const my = await listStudentEpisodes(materia.comision_id)
        const reanudables = my.episodes.filter(
          (e) => (e.estado === "paused" || e.estado === "open") && e.problema_id === tarea.id,
        )
        for (const candidate of reanudables) {
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
              episode_id: candidate.episode_id,
            }
            window.sessionStorage.setItem(ACTIVE_EXERCISE_CONTEXT_KEY, JSON.stringify(ctx))
          } else {
            // NB-6: TP monolitica → limpiar cualquier contexto de ejercicio
            // previo para que episodio.$id no lo aplique a este episodio.
            window.sessionStorage.removeItem(ACTIVE_EXERCISE_CONTEXT_KEY)
          }
          navigate({
            to: "/episodio/$id",
            params: { id: candidate.episode_id },
            replace: ejercicio == null,
          })
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
        const hashes = await fetchConfigHashes(materia.comision_id)
        cursoHash = hashes.curso_config_hash
        classifierHash = hashes.classifier_config_hash
      } catch (e) {
        console.warn("fetchConfigHashes fallo, usando fallback hardcoded:", e)
      }
      const res = await openEpisode({
        comision_id: materia.comision_id,
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
          episode_id: res.episode_id,
        }
        window.sessionStorage.setItem(ACTIVE_EXERCISE_CONTEXT_KEY, JSON.stringify(ctx))
      } else {
        // NB-6: TP monolitica → limpiar cualquier contexto de ejercicio previo.
        window.sessionStorage.removeItem(ACTIVE_EXERCISE_CONTEXT_KEY)
      }
      // TP monolitica: se llega con `?tareaId=` y el episodio REEMPLAZA esa
      // entrada; si quedara, el "atras" desde el episodio abriria otro.
      navigate({ to: "/episodio/$id", params: { id: res.episode_id }, replace: ejercicio == null })
    } catch (e) {
      setView({
        kind: "opening",
        tarea,
        ejercicioId: ejercicio?.id ?? null,
        ejercicioOrden: ejercicio?.orden ?? null,
        entregaId: entregaId ?? null,
        error: mensajeAlAbrirEpisodio(e),
      })
    } finally {
      // NB-10: liberar el guard. En el camino feliz ya navegamos (unmount),
      // asi que esto solo importa cuando hubo error y el alumno reintenta.
      openingRef.current = false
    }
  }

  /**
   * Abre el TP que vino en `?tareaId=`.
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
        <div className="bg-danger-soft text-danger px-6 py-2 text-sm">{currentView.error}</div>
      )}

      {currentView.kind === "cargando" && <PageLoading />}

      {currentView.kind === "exercise-list" && (
        <ExerciseListView
          tarea={currentView.tarea}
          comisionId={materia.comision_id}
          onSelectEjercicio={(tarea, ejercicio, entregaId) => {
            void openEpisodeAndNavigate(tarea, ejercicio, entregaId)
          }}
          onViewGrade={(entrega) =>
            setView({
              kind: "grade-detail",
              tarea: currentView.tarea,
              entrega,
              back: currentView,
            })
          }
          onBack={() => irAlCampus(navigate, materia.comision_id, currentView.tarea, false)}
        />
      )}

      {currentView.kind === "grade-detail" && (
        <GradeDetailView entrega={currentView.entrega} onBack={() => setView(currentView.back)} />
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
            const { ejercicio, entregaId } = argumentosDeReintento(currentView)
            void openEpisodeAndNavigate(currentView.tarea, ejercicio, entregaId ?? undefined)
          }}
          onCancel={() => {
            // Si veniamos de un ejercicio dentro de TP multi, volvemos a
            // la lista de ejercicios; si no, al campus.
            if (currentView.ejercicioId != null) {
              setView({ kind: "exercise-list", tarea: currentView.tarea })
            } else {
              irAlCampus(navigate, materia.comision_id, currentView.tarea, false)
            }
          }}
        />
      )}
    </>
  )
}

/**
 * Vuelve al campus: a la pestaña de TPs de la unidad del TP si se conoce, si
 * no a la pagina del curso. `replace` cuando la pagina de materia no tiene
 * nada que mostrar (no tiene sentido volver a ella con "atras").
 */
function irAlCampus(
  navigate: ReturnType<typeof useNavigate>,
  comisionId: string,
  tarea: AvailableTarea | null,
  replace: boolean,
) {
  if (tarea?.unidad_id) {
    void navigate({
      to: "/curso/$comisionId/unidad/$unidadId",
      params: { comisionId, unidadId: tarea.unidad_id },
      search: { pestana: "tps" },
      replace,
    })
    return
  }
  void navigate({ to: "/curso/$comisionId", params: { comisionId }, replace })
}

function ContextualHeader({ materia }: { materia: MateriaInscripta }) {
  return (
    <div
      data-testid="materia-context-header"
      className="border-b border-border-soft px-6 py-3 bg-white flex items-center gap-3 flex-wrap"
    >
      <Link
        to="/curso/$comisionId"
        params={{ comisionId: materia.comision_id }}
        className="text-xs text-muted hover:text-body"
        data-testid="materia-back-link"
      >
        ← Volver al curso
      </Link>
      <span aria-hidden="true" className="text-muted-soft">
        |
      </span>
      <MateriaContextLine materia={materia} />
      <span className="text-sm font-medium text-ink truncate ml-auto">{materia.nombre}</span>
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
        <p className="text-sm font-medium text-danger mb-2">No pudimos cargar la materia.</p>
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
        <Link to="/" className="text-sm underline text-body" data-testid="materia-not-found-back">
          Volver a mis materias
        </Link>
      </div>
    </div>
  )
}
