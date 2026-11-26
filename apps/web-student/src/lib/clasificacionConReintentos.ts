/**
 * HU-050 C04: la clasificación del cierre espera a que el CTR guarde la traza.
 *
 * El ctr-service persiste los eventos de forma asíncrona, así que el POST de
 * clasificación que sale apenas el alumno cierra puede encontrar la traza sin
 * el `episodio_cerrado`: el classifier responde 202 y no guarda nada. Acá se
 * reintenta con esperas crecientes. Todas suman 54 s, así que el último pedido
 * sale antes de los 60 s del criterio. Si al final sigue incompleta devuelve
 * `null` y la pantalla dice «Tu cierre se está procesando»; un error de verdad
 * (4xx/5xx o red) se propaga como antes, al panel de respaldo.
 */
import { type Classification, classifyEpisode } from "./api"

export const ESPERAS_REINTENTO_MS: readonly number[] = [2_000, 4_000, 8_000, 15_000, 25_000]

function esperar(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export async function clasificarConReintentos(
  episodeId: string,
  esperas: readonly number[] = ESPERAS_REINTENTO_MS,
): Promise<Classification | null> {
  let c = await classifyEpisode(episodeId)
  for (const ms of esperas) {
    if (c) return c
    await esperar(ms)
    c = await classifyEpisode(episodeId)
  }
  return c
}
