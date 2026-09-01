/**
 * Auto-envio de la entrega monolitica al salir de un episodio cerrado.
 *
 * POR QUE VIVE ACA Y NO ADENTRO DE `handleExit`
 * ---------------------------------------------
 * Estaba enterrado en la ruta, y por eso NADIE lo habia testeado: para
 * ejercitarlo habia que montar el router entero con tres llamadas de red
 * mockeadas. Es el mismo motivo por el que `debeEnviarLaEntrega` se saco a
 * `entregaGuard.ts` — y la misma leccion, un escalon mas arriba.
 *
 * La auditoria del PR #86 mostro que hacia falta: reintroduciendo a mano el bug
 * de `debeEnviarLaEntrega` —que acepte `returned`— sobre las 529 pruebas de
 * `web-student` solo se ponian rojos los 3 asserts del unit test de la propia
 * funcion. Ningun test montaba este flujo. O sea que un refactor que "unifique"
 * las dos funciones y toque su test de paso reintroduce, sin una sola alarma,
 * el bug que BORRA LA DEVOLUCION DEL DOCENTE: una entrega en `returned` que se
 * re-envia pasa a `submitted` y se lleva puestas las observaciones.
 *
 * Con la logica aca, el test se escribe contra el comportamiento —"¿se llamo a
 * submit?"— y no contra el nombre de una funcion. Sobrevive al refactor.
 */

import {
  DEFAULT_LANGUAGE,
  type TokenGetter,
  createOrGetEntrega,
  getEpisodeState,
  getTareaById,
  submitEntrega,
} from "./api"
import { MONOLITHIC_ORDEN, clearArtefactoDrafts, collectArtefactoDrafts } from "./artefactos"
import { debeEnviarLaEntrega } from "./entregaGuard"

/** Que paso, para que el caller (y el test) puedan distinguirlo del silencio. */
export type ResultadoDeSalida = "enviada" | "episodio-no-cerrado" | "entrega-no-enviable" | "error"

/**
 * Si el episodio quedo cerrado y su entrega admite envio, la manda.
 *
 * Best-effort por diseño: cualquier fallo devuelve `"error"` y NO propaga, para
 * no dejar al alumno atrapado en el episodio por un problema de red. El caller
 * navega igual.
 */
export async function enviarEntregaAlSalir(
  episodeId: string,
  getToken?: TokenGetter,
): Promise<ResultadoDeSalida> {
  try {
    const state = await getEpisodeState(episodeId, getToken)
    if (state.estado !== "closed") return "episodio-no-cerrado"

    const entrega = await createOrGetEntrega(
      {
        tarea_practica_id: state.tarea_practica_id,
        comision_id: state.comision_id,
      },
      getToken,
    )

    // El guard del envio, NO el de edicion. Son dos preguntas distintas y
    // difieren justo en `returned`: el alumno puede TRABAJAR una entrega
    // devuelta, pero mandarla sola al salir le borra la devolucion.
    if (!debeEnviarLaEntrega(entrega.estado)) return "entrega-no-enviable"

    // El borrador de la TP monolitica esta keyeado por episodio: cuando el
    // alumno lo escribio, esta entrega todavia no existia.
    //
    // Si no hay borrador (otra maquina, o una re-entrega en la que no volvio a
    // tocar el editor) cae al ultimo snapshot del episodio, que ya tenemos en
    // `state`. Sin este fallback el backend rechaza la re-entrega sin codigo y
    // el alumno queda trabado.
    let artefactos = collectArtefactoDrafts(episodeId, [MONOLITHIC_ORDEN])
    if (artefactos.length === 0 && state.last_code_snapshot?.trim()) {
      // El lenguaje sale de la TP, no de un default: rotularlo mal hace que el
      // Epic 3 elija el runtime equivocado para correr los tests.
      const tarea = await getTareaById(state.tarea_practica_id, getToken)
      artefactos = [
        {
          orden: MONOLITHIC_ORDEN,
          ejercicio_id: null,
          episode_id: episodeId,
          codigo: state.last_code_snapshot,
          language: tarea?.language ?? DEFAULT_LANGUAGE,
        },
      ]
    }

    await submitEntrega(entrega.id, artefactos, getToken)
    clearArtefactoDrafts(episodeId, [MONOLITHIC_ORDEN])
    return "enviada"
  } catch {
    // best-effort: no bloquear la navegacion si falla la creacion/envio.
    return "error"
  }
}
