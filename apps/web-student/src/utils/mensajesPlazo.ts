/**
 * Lo que ve el alumno cuando falla abrir un ejercicio o entregar la TP (HU-016,
 * hallazgo F17 de HU-014). Reciben el error que tiran `openEpisode` y
 * `submitEntrega` de `lib/api.ts` (un `ApiError` con `status` y `detail`) y
 * devuelven una frase en espanol, sin codigos HTTP ni el texto crudo.
 */
import { ApiError } from "../lib/api"

export const MENSAJE_PLAZO_VENCIDO = "Venció el plazo de esta TP. Ya no se puede trabajar en ella."
export const MENSAJE_NO_SE_PUDO_ABRIR = "No se pudo abrir el ejercicio. Probá de nuevo en un rato."
/** Aviso en la home cuando la entrega automatica al salir se rechazo por plazo. */
export const MENSAJE_ENTREGA_VENCIDA =
  "Venció el plazo de entrega de esta TP, así que no se entregó. Si necesitás entregarla, consultalo con tu docente."
export const MENSAJE_NO_SE_PUDO_ENTREGAR = "No se pudo entregar la TP. Probá de nuevo en un rato."

// El tutor-service responde 403 "Tarea práctica fuera de plazo (deadline
// pasado)" al abrir; el evaluation-service, 409 "Venció el plazo de entrega de
// esta TP." al entregar. Se mira el texto y no solo el status porque el 403 del
// tutor tambien sale cuando la TP todavia no empezo.
const PLAZO = /fuera de plazo|deadline|venci[oó] el plazo/i

// El tutor-service responde 403 "Tarea práctica no ha comenzado todavía" si
// todavia no llego `fecha_inicio`: mismo status que el plazo vencido.
const NO_EMPEZO = /no ha comenzado/i
export const MENSAJE_NO_EMPEZO =
  "Esta TP todavía no empezó. Vas a poder abrirla desde su fecha de inicio."

function esPlazoVencido(e: unknown): boolean {
  return e instanceof ApiError && e.detail !== null && PLAZO.test(e.detail)
}

/**
 * Antes el panel de apertura (`OpeningStage`) recibia el texto crudo y le
 * sumaba una pista buscando el codigo adentro ("403", "422"...). Como el texto
 * ya no lleva codigos, esas pistas se deciden aca por `status`: la de 422 es la
 * que le dice al alumno que complete el ejercicio anterior.
 */
export function mensajeAlAbrirEpisodio(e: unknown): string {
  if (esPlazoVencido(e)) return MENSAJE_PLAZO_VENCIDO
  if (e instanceof ApiError && e.detail && NO_EMPEZO.test(e.detail)) return MENSAJE_NO_EMPEZO
  if (e instanceof ApiError) {
    switch (e.status) {
      case 403:
        return "No se pudo abrir el ejercicio: no tenés permiso para abrirlo en esta comisión. Consultalo con tu docente."
      case 404:
        return "No se pudo abrir el ejercicio: no se encontró la tarea. Volvé a la lista y actualizá la página."
      case 422:
        return "No se pudo abrir el ejercicio. Si la TP pide hacerlos en orden, completá primero el anterior."
      case 429:
        return "No se pudo abrir el ejercicio: hubo muchos pedidos seguidos. Esperá unos segundos y probá de nuevo."
    }
  }
  return MENSAJE_NO_SE_PUDO_ABRIR
}

/**
 * Textos del evaluation-service que estan escritos para el alumno y se muestran
 * tal cual. Lista blanca a proposito: el resto de los rechazos del submit
 * ("No se puede enviar una entrega en estado 'graded'", "Permiso denegado...",
 * "Missing auth headers...") hablan de estados internos o de autorizacion y no
 * le dicen nada util al alumno.
 */
const DETAIL_PARA_EL_ALUMNO = /^(venci[oó] el plazo|ejercicios incompletos|falta el c[oó]digo)/i

/**
 * Sin un `detail` de la lista (red caida, 500, 422 de pydantic, rechazos
 * internos) va la frase generica.
 */
export function mensajeAlEntregar(e: unknown): string {
  if (e instanceof ApiError && e.detail && DETAIL_PARA_EL_ALUMNO.test(e.detail.trim())) {
    return e.detail
  }
  return MENSAJE_NO_SE_PUDO_ENTREGAR
}

/** La entrega fue rechazada por plazo vencido (409 del evaluation-service). */
export function esEntregaVencida(e: unknown): boolean {
  return e instanceof ApiError && e.status === 409 && esPlazoVencido(e)
}
