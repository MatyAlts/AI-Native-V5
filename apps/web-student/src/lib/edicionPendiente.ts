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

/** De donde vino un paste, o `null` si no hubo ninguno en la ventana.
 *
 * "interno" = el portapapeles interno validó el contenido pegado contra algo
 * copiado DENTRO del episodio (consigna o editor propio — change
 * copiar-pegar-interno-en-el-episodio). "externo" es el camino legacy: hoy
 * es inalcanzable desde `CodeEditor.tsx` porque todo paste que NO valida
 * como interno se BLOQUEA antes de llegar al buffer (no hay tercer estado
 * "pegué algo externo y lo dejé pasar"). Se conserva el valor por la misma
 * razón que ya estaba escrita en el componente: si algún día se destraba el
 * pegado externo, esta es la costura correcta. */
export type PasteOrigen = "interno" | "externo" | null

/** Marcas acumuladas desde la ultima emision. */
export interface MarcasEdicion {
  /** Hubo un paste del clipboard en la ventana, y de donde vino. */
  paste: PasteOrigen
  /** Se expandio un snippet de ceremonia del editor en la ventana. */
  snippet: boolean
}

export interface EdicionPendiente {
  snapshot: string
  /** Delta de caracteres contra la ULTIMA emision (negativo si borro). */
  diffChars: number
  origin: OrigenEdicion
}

/**
 * Devuelve la edicion a emitir, o `null` si no hay nada que emitir.
 *
 * `null` cuando el buffer volvio al mismo contenido de la ultima emision (el
 * caso tipico: tecla y undo dentro de la misma ventana de debounce). Emitirlo
 * igual metaria un `edicion_codigo` con `diff_chars: 0` en la cadena.
 *
 * Precedencia del origen: paste (externo o interno) > snippet > tipeo. Si en
 * la misma ventana pasan las dos cosas gana el paste, que es la señal mas
 * fuerte — `pasted_external` es la unica que lleva override a N4 en el
 * labeler; `pasted_internal` no, pero sigue siendo mas informativa que un
 * snippet de ceremonia.
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
