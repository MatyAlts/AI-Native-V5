// BUG-20 (QA 2026-09-23): en "Evolucion por estudiante", la cabecera decia
// "3 trabajos completados · 1 tipo de trabajo" mientras el detalle de abajo
// listaba ~10 TPs con ~20 sesiones y "Evolucion por unidad" sumaba 6+3=9
// intentos. No es el mismo numero desactualizado: son dos calculos legitimos
// sobre poblaciones distintas.
//
// `n_episodes_total`/`n_groups_evaluated` (backend, `cii_longitudinal.py`)
// cuentan solo los grupos por Unidad que entran al calculo de tendencia
// longitudinal (excluyen la Unidad "sin_unidad" y agregan por grupo) — no
// son "todos los trabajos del alumno". El detalle de abajo
// (`episodesData.episodes`, endpoint `/student/{id}/episodes`) lista TODOS
// los episodios cerrados del alumno en la comision, sin ese filtro.
//
// No se fuerza que los dos numeros coincidan (forzarlo exigiria tocar el
// calculo del backend, que mide algo distinto a proposito). En su lugar, la
// cabecera se aclara: si el detalle tiene MAS trabajos o sesiones que el
// resumen de tendencia, se agrega una linea que dice el total real y remite
// al detalle de abajo.

interface EpisodeLike {
  problema_id: string
}

export interface DocenteWorkSummary {
  /** = `n_episodes_total` del backend (episodios agrupados por Unidad, sin "sin_unidad"). */
  episodiosAnalizables: number
  /** = `n_groups_evaluated` del backend (Unidades con N>=3, con tendencia calculable). */
  gruposConTendencia: number
  /** Total de episodios cerrados del alumno (detalle de abajo). `null` si aun no cargo. */
  totalEpisodiosCerrados: number | null
  /** Cantidad de TPs (`problema_id`) distintas en el detalle de abajo. `null` si aun no cargo. */
  totalTrabajosDistintos: number | null
  /** Aclaracion a mostrar debajo del resumen cuando el detalle tiene mas datos. `null` si no aplica. */
  caption: string | null
}

/**
 * Decide si la cabecera docente ("N trabajos completados · M tipos de
 * trabajo") necesita una aclaracion porque el detalle de abajo (todos los
 * episodios cerrados del alumno) tiene mas trabajos o sesiones que el
 * resumen de tendencia longitudinal.
 */
export function computeDocenteWorkSummary(
  episodiosAnalizables: number,
  gruposConTendencia: number,
  episodes: readonly EpisodeLike[] | null,
): DocenteWorkSummary {
  if (episodes === null) {
    return {
      episodiosAnalizables,
      gruposConTendencia,
      totalEpisodiosCerrados: null,
      totalTrabajosDistintos: null,
      caption: null,
    }
  }

  const totalEpisodiosCerrados = episodes.length
  const totalTrabajosDistintos = new Set(episodes.map((e) => e.problema_id)).size

  const hayDiscrepancia =
    totalEpisodiosCerrados > episodiosAnalizables || totalTrabajosDistintos > gruposConTendencia

  const caption = hayDiscrepancia
    ? `Este resumen cuenta solo los trabajos agrupados por unidad con tendencia calculable. En total el alumno tiene ${totalTrabajosDistintos} trabajo${totalTrabajosDistintos !== 1 ? "s" : ""} practico${totalTrabajosDistintos !== 1 ? "s" : ""} (${totalEpisodiosCerrados} sesion${totalEpisodiosCerrados !== 1 ? "es" : ""}) — ver el detalle abajo.`
    : null

  return {
    episodiosAnalizables,
    gruposConTendencia,
    totalEpisodiosCerrados,
    totalTrabajosDistintos,
    caption,
  }
}
