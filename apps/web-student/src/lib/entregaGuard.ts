/**
 * Si al salir de un episodio cerrado hay que enviar la entrega automaticamente.
 *
 * Se saca a una funcion pura porque la decision vivia enterrada adentro de
 * `handleExit`, y por eso nadie la habia testeado nunca: para ejercitarla habia
 * que montar la ruta entera con el router y tres llamadas de red mockeadas.
 *
 * **`returned` NO se re-envia, y ese era el bug.** El guard aceptaba
 * `draft || returned`. Una entrega en `returned` es una que el docente devolvio
 * para corregir; volver a enviarla la pasa a `submitted` y **borra la
 * devolucion**. Y no hacia falta que el alumno apretara nada: basta con que
 * vuelva a entrar al episodio cerrado —la hidratacion de `EpisodePage` llama
 * `onExit()` sola al ver `estado === "closed"`— para que el ciclo se dispare.
 *
 * O sea: el alumno abre el episodio para LEER lo que el docente le escribio, y
 * el solo hecho de abrirlo le borra esa devolucion.
 *
 * `draft` si se envia: para la TP monolitica (sin `ejercicioContext`) cerrar el
 * episodio ES la entrega, y sin esto la card del selector se queda en "Empezar"
 * aunque el alumno haya terminado.
 */
export function debeEnviarLaEntrega(estadoEntrega: string): boolean {
  return estadoEntrega === "draft"
}

/**
 * Si el alumno todavia puede TRABAJAR sobre la entrega: abrir un ejercicio,
 * reabrir uno completado, y apretar "Entregar TP".
 *
 * Es otra pregunta que `debeEnviarLaEntrega`, y usar aquella para las dos era
 * un bug esperando (QA 2026-08-31). Las dos preguntas se parecen y la respuesta
 * difiere justo en `returned`:
 *
 *   - "¿mando la entrega SOLO porque el alumno salio del episodio?" -> `draft`.
 *     En `returned` NO, porque el envio automatico le borraria la devolucion
 *     que vino a leer.
 *   - "¿el alumno puede seguir laburando?" -> `draft` Y `returned`. Devolver un
 *     TP es justamente pedirle que lo retome; si `returned` no cuenta, el
 *     boton "Devolver al estudiante" le muestra un cartel que lo invita a
 *     revisar y le saca todas las herramientas para revisar.
 *
 * El backend ya validaba las dos por separado y bien: `submit_entrega` acepta
 * `draft` y `returned` como estados de origen, y `mark_ejercicio_completado`
 * tambien. El unico que las confundia era el frontend — y como el frontend es
 * el que dibuja los botones, era el que decidia.
 */
export function puedeEditarLaEntrega(estadoEntrega: string): boolean {
  return estadoEntrega === "draft" || estadoEntrega === "returned"
}
