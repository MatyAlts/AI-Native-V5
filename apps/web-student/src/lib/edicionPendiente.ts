/**
 * Resolucion del evento `edicion_codigo` que el debounce del editor tiene
 * pendiente.
 *
 * Vive aca, fuera del componente, por dos razones. La primera es que la logica
 * tiene reglas propias (cuando NO hay evento, como se mide el delta, que origen
 * gana) y estaba enterrada adentro de un `setTimeout` dentro de un `useEffect`
 * dentro de `CodeEditor`, o sea inobservable. La segunda es que ahora tiene DOS
 * llamadores —el vencimiento del debounce y el flush forzado antes de una
 * corrida— y duplicar estas reglas seria la forma mas facil de que las dos
 * ramas se desincronicen.
 */

export type OrigenEdicion =
  | "student_typed"
  | "pasted_external"
  | "pasted_internal"
  | "snippet_expanded"

/** De donde vino un pegado, o `null` si no hubo ninguno en la ventana.
 *
 * "interno" = el alumno reordenando SU PROPIO codigo dentro del editor
 * (change `portapapeles-interno-editor`). No sale de una interaccion con la
 * IA ni de una fuente externa, asi que NO lleva override a N4 — pero tampoco
 * es tipeo, y decir que lo es seria afirmar que elaboro caracter por caracter
 * algo que movio de lugar.
 *
 * "externo" = un pegado nativo que llego al modelo sin pasar por el
 * portapapeles interno. Con el bloqueo puesto no deberia ocurrir; se conserva
 * como la costura por la que cae cualquier camino de pegado imprevisto, que es
 * el lado seguro (SI lleva override a N4). */
export type PasteOrigen = "interno" | "externo" | null

export interface EdicionPendiente {
  snapshot: string
  /** Delta de caracteres contra la ULTIMA emision (negativo si borro). */
  diffChars: number
  origin: OrigenEdicion
}

/** Marcas acumuladas desde la ultima emision. */
export interface MarcasEdicion {
  /** Hubo un paste en la ventana, y de donde vino. */
  paste: PasteOrigen
  /** Se expandio un snippet de ceremonia del editor en la ventana. */
  snippet: boolean
}

/**
 * Devuelve la edicion a emitir, o `null` si no hay nada que emitir.
 *
 * `null` cuando el buffer volvio al mismo contenido de la ultima emision (el
 * caso tipico: tecla y undo dentro de la misma ventana de debounce). Emitirlo
 * igual metaria un `edicion_codigo` con `diff_chars: 0` en la cadena.
 *
 * Precedencia del origen: paste externo > paste interno > snippet > tipeo.
 *
 * El paste le gana al snippet porque es la señal mas fuerte. Y entre los dos
 * pastes gana el EXTERNO, que es el unico que lleva override a N4 en el
 * labeler: si en la misma ventana entraron los dos, perderlo subestima la
 * dependencia del alumno. De los dos errores posibles, ese es el caro.
 *
 * OJO con el orden de la comparacion: `marcas.paste` ya no es un booleano.
 * Preguntar por su veracidad en vez de por su valor mandaba todo pegado
 * interno a `pasted_external` —"interno" es truthy— y con eso el alumno que
 * reordena su propio codigo quedaba etiquetado N4.
 */
export function resolverEdicionPendiente(
  snapshot: string,
  ultimoEmitido: string,
  marcas: MarcasEdicion,
): EdicionPendiente | null {
  if (snapshot === ultimoEmitido) return null
  const origin: OrigenEdicion =
    marcas.paste === "externo"
      ? "pasted_external"
      : marcas.paste === "interno"
        ? "pasted_internal"
        : marcas.snippet
          ? "snippet_expanded"
          : "student_typed"
  return {
    snapshot,
    diffChars: snapshot.length - ultimoEmitido.length,
    origin,
  }
}
