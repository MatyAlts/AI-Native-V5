/**
 * Contexto del ejercicio de un episodio, reconstruido desde el servidor (HU-042).
 *
 * El contexto (entrega, ejercicio, orden) se guarda en sessionStorage al
 * entrar desde la lista de ejercicios. Si el alumno retoma el episodio en otra
 * pestaña o después de reiniciar el navegador, ese contexto no está, y sin él
 * el cierre no marcaba el ejercicio, la consigna mostraba la del TP y la
 * pantalla de cierre mandaba a "mis materias". El servidor sí lo sabe: el
 * estado del episodio trae `ejercicio_id`, `ejercicio_orden` y
 * `tarea_practica_id`, y la entrega propia sale de
 * `GET /entregas?tarea_practica_id=&propias=true`.
 */
import {
  type MateriaInscripta,
  type TokenGetter,
  getEntregaForTp,
  getEpisodeState,
  listMisMaterias,
} from "./api"
import { puedeEditarLaEntrega } from "./entregaGuard"

export interface ContextoEjercicioServidor {
  /** Null si la materia no aparece entre las del alumno: la salida la deriva aparte. */
  materiaId: string | null
  tareaId: string
  entregaId: string
  ejercicioId: string
  ejercicioOrden: number
}

/**
 * Devuelve el contexto del ejercicio del episodio, o null si el episodio no es
 * de un ejercicio, si el alumno no tiene una entrega propia que se pueda
 * trabajar (`draft` o `returned`), o si algo falla. Best-effort: con null el
 * episodio sigue como hasta ahora.
 */
export async function resolverContextoEjercicio(
  episodeId: string,
  getToken?: TokenGetter,
  materiasEnCache?: ReadonlyArray<MateriaInscripta>,
): Promise<ContextoEjercicioServidor | null> {
  try {
    const estado = await getEpisodeState(episodeId, getToken)
    if (!estado.ejercicio_id || estado.ejercicio_orden === null) return null
    const entrega = await getEntregaForTp(estado.tarea_practica_id, estado.comision_id, getToken)
    if (!entrega || !puedeEditarLaEntrega(entrega.estado)) return null
    let materiaId: string | null = null
    try {
      const materias = materiasEnCache ?? (await listMisMaterias(getToken))
      materiaId = materias.find((m) => m.comision_id === estado.comision_id)?.materia_id ?? null
    } catch {
      materiaId = null
    }
    return {
      materiaId,
      tareaId: estado.tarea_practica_id,
      entregaId: entrega.id,
      ejercicioId: estado.ejercicio_id,
      ejercicioOrden: estado.ejercicio_orden,
    }
  } catch {
    return null
  }
}
