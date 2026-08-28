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
