// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
import { useQuery } from "@tanstack/react-query"
import { useMemo } from "react"
import {
  type MateriaInscripta,
  listAvailableTareas,
  listMisEntregas,
  listMisMaterias,
  listStudentEpisodes,
} from "../lib/api"

/**
 * ============================================================================
 * ESTADO DEL ALUMNO — la entrada del onboarding progresivo.
 * ============================================================================
 *
 * El onboarding del alumno NO lleva contador propio: cada cartel se desbloquea
 * y se da por cumplido segun lo que el alumno YA HIZO de verdad. Todo lo que
 * hay aca sale de datos que la app ya pide en otras pantallas:
 *
 *   - inscripciones   -> GET /api/v1/materias/mias      (listMisMaterias)
 *   - TPs publicadas  -> GET /api/v1/tareas-practicas   (listAvailableTareas)
 *   - episodios       -> GET /api/v1/analytics/student/me/episodes
 *   - entregas        -> GET /api/v1/entregas           (listMisEntregas)
 *
 * Ninguno de esos endpoints es nuevo. Eso es deliberado: si el estado saliera
 * de un contador de tutorial, un alumno que se inscribio por otro lado veria
 * pasos que ya cumplio. Derivandolo de los datos reales el paso nace cumplido.
 *
 * EL ESTADO "TODAVIA NO SE": mientras alguna de esas consultas no resolvio
 * (o fallo, que para nosotros es lo mismo: no sabemos), `cargando` queda en
 * true y NINGUN cartel se muestra. Un cartel que aparece y desaparece cuando
 * llega el fetch es peor que ninguno.
 */
export interface EstadoAlumno {
  /**
   * True mientras no sepamos la respuesta. Incluye el caso de error de red:
   * si la consulta fallo tampoco sabemos, asi que tampoco mostramos nada.
   * Los `unlockWhen` del flow ya arrancan todos con esta guarda (ver
   * `alumnoOnboarding.tsx`), no hace falta repetirla en cada hint.
   */
  cargando: boolean
  /** Tiene al menos una inscripcion activa. */
  tieneInscripcion: boolean
  /**
   * Su comision tiene al menos una TP publicada. Sin esto no tiene sentido
   * pedirle que abra su primer TP: el docente todavia no publico ninguna.
   */
  hayTpsDisponibles: boolean
  /** Tiene al menos un episodio registrado (abierto, pausado o cerrado). */
  tieneEpisodios: boolean
  /**
   * Cuantos episodios registrados tiene. Lo usan los carteles del episodio
   * para distinguir "es su primera vez" de "ya paso por aca": el episodio que
   * el alumno tiene abierto AHORA ya cuenta en esta lista, asi que preguntar
   * por `tieneEpisodios` los apagaria apenas entra, que es justo cuando hay
   * que mostrarlos.
   */
  cantidadEpisodios: number
  /** Entrego al menos una vez (cualquier entrega que no siga en borrador). */
  entregoAlgunaVez: boolean
}

/** Lo que devolvemos mientras no sabemos. Con esto ningun hint se desbloquea. */
export const ESTADO_ALUMNO_DESCONOCIDO: EstadoAlumno = {
  cargando: true,
  tieneInscripcion: false,
  hayTpsDisponibles: false,
  tieneEpisodios: false,
  cantidadEpisodios: 0,
  entregoAlgunaVez: false,
}

/**
 * Clave que `routes/__root.tsx` usa para recordar la comision del alumno.
 * Se replica aca (en vez de importarla) para no crear un ciclo de imports:
 * `__root` monta el provider de onboarding, que a su vez usa este modulo.
 */
const ENROLLED_COMISION_KEY = "enrolledComisionId"

/**
 * La comision sobre la que miramos TPs, episodios y entregas.
 *
 * Un alumno puede cursar varias materias; el onboarding no necesita mirarlas
 * todas, le alcanza con la que la app ya considera "la suya". Preferimos la
 * cacheada por `__root` si sigue vigente, y si no la primera inscripcion.
 */
/**
 * `localStorage` puede TIRAR al acceder, no solo devolver null: Safari privado,
 * cookies bloqueadas, iframe con storage restringido. Y esto corre durante el
 * render de `useEstadoAlumno`, que cuelga del root: una excepcion aca es la
 * pantalla en blanco de TODA la app del alumno, no un onboarding que no aparece.
 * El motor ya envuelve cada acceso en `persistencia.ts`; aca faltaba.
 */
function comisionGuardada(): string | null {
  if (typeof window === "undefined") return null
  try {
    return window.localStorage.getItem(ENROLLED_COMISION_KEY)
  } catch {
    return null
  }
}

function comisionActiva(materias: MateriaInscripta[]): string | null {
  if (materias.length === 0) return null
  const guardada = comisionGuardada()
  if (guardada && materias.some((m) => m.comision_id === guardada)) return guardada
  return materias[0]?.comision_id ?? null
}

/**
 * Calcula el estado del alumno.
 *
 * No sabe nada de rutas a proposito: donde corresponde mostrar cada cartel lo
 * decide el `route` del hint, que el motor matchea por segmento. Este modulo
 * responde solo "que hizo el alumno".
 */
export function useEstadoAlumno(): EstadoAlumno {
  // Misma key que la home y /progreso: si el alumno ya paso por ahi, esto no
  // dispara un fetch nuevo.
  const materiasQuery = useQuery({
    queryKey: ["mis-materias"],
    queryFn: () => listMisMaterias(),
    staleTime: 5 * 60 * 1000,
  })

  const materias = materiasQuery.data ?? []
  const comisionId = comisionActiva(materias)

  // Primera pagina nomas: para saber si el docente publico ALGO no hace falta
  // recorrer el cursor entero como si fuera el selector de TPs.
  const tareasQuery = useQuery({
    queryKey: ["onboarding", "tareas", comisionId],
    queryFn: () => listAvailableTareas(comisionId as string),
    enabled: comisionId !== null,
    staleTime: 5 * 60 * 1000,
  })

  // Key compartida con MiProgresoPage a proposito: es exactamente la misma
  // consulta, y asi el alumno que entra a "Mi progreso" no la paga dos veces.
  const episodiosQuery = useQuery({
    queryKey: ["mi-progreso", "episodes", comisionId],
    queryFn: () => listStudentEpisodes(comisionId as string),
    enabled: comisionId !== null,
    staleTime: 60 * 1000,
  })

  const entregasQuery = useQuery({
    queryKey: ["onboarding", "entregas", comisionId],
    queryFn: () => listMisEntregas(comisionId as string),
    enabled: comisionId !== null,
    staleTime: 60 * 1000,
  })

  // `isPending` y no `isLoading`: `isLoading` es `isPending && isFetching`, y
  // hay un frame entre "la consulta quedo habilitada" y "arranco el fetch" en
  // el que `isFetching` todavia es false. En ese frame `isLoading` diria que ya
  // sabemos, con los datos todavia en undefined.
  //
  // El guard por `comisionId` es lo que evita el otro extremo: una consulta
  // deshabilitada queda `isPending` para siempre, y sin el guard el alumno sin
  // inscripcion nunca saldria del estado "todavia no se".
  const dependientes = [tareasQuery, episodiosQuery, entregasQuery]
  const desconocido =
    materiasQuery.isPending ||
    materiasQuery.isError ||
    (comisionId !== null && dependientes.some((q) => q.isPending || q.isError))

  const cantidadMaterias = materias.length
  const tareas = tareasQuery.data
  const episodios = episodiosQuery.data
  const entregas = entregasQuery.data

  return useMemo<EstadoAlumno>(() => {
    if (desconocido) return ESTADO_ALUMNO_DESCONOCIDO
    const cantidadEpisodios = episodios?.episodes.length ?? 0
    return {
      cargando: false,
      tieneInscripcion: cantidadMaterias > 0,
      hayTpsDisponibles: (tareas?.data.length ?? 0) > 0,
      tieneEpisodios: cantidadEpisodios > 0,
      cantidadEpisodios,
      entregoAlgunaVez: (entregas ?? []).some((e) => e.estado !== "draft"),
    }
    // `cantidadMaterias` en vez del array: el array se recrea en cada render.
  }, [desconocido, cantidadMaterias, tareas, episodios, entregas])
}
