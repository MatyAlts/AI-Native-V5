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

export type OrigenEdicion = "student_typed" | "pasted_external" | "snippet_expanded"

export interface EdicionPendiente {
  snapshot: string
  /** Delta de caracteres contra la ULTIMA emision (negativo si borro). */
  diffChars: number
  origin: OrigenEdicion
}

/** Marcas acumuladas desde la ultima emision. */
export interface MarcasEdicion {
  /** Hubo un paste del clipboard en la ventana. */
  paste: boolean
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
 * Precedencia del origen: paste > snippet > tipeo. Si en la misma ventana pasan
 * las dos cosas gana el paste, que es la señal mas fuerte — es la unica que
 * lleva override a N4 en el labeler.
 */
export function resolverEdicionPendiente(
  snapshot: string,
  ultimoEmitido: string,
  marcas: MarcasEdicion,
): EdicionPendiente | null {
  if (snapshot === ultimoEmitido) return null
  const origin: OrigenEdicion = marcas.paste
    ? "pasted_external"
    : marcas.snippet
      ? "snippet_expanded"
      : "student_typed"
  return {
    snapshot,
    diffChars: snapshot.length - ultimoEmitido.length,
    origin,
  }
}
