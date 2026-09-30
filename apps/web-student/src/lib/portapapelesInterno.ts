/**
 * Portapapeles interno del editor (change `copiar-pegar-interno-en-el-episodio`).
 *
 * El portapapeles del sistema operativo no guarda procedencia: no hay forma
 * de saber de donde vino un texto. Pero si hay forma de saber otra cosa, que
 * alcanza: "¿eso lo puse yo aca?". Al copiar o cortar dentro de la pagina se
 * guarda `{texto, origen}` en memoria. Al pegar se compara el contenido real
 * del clipboard contra lo guardado: coincide -> se permite, no coincide -> se
 * bloquea (como hoy).
 *
 * Vive fuera de `CodeEditor.tsx`, igual que `lib/edicionPendiente.ts`, porque
 * es logica con sus propias reglas (que normalizar, que cuenta como "el mismo
 * texto") y separarla la hace testeable sin montar Monaco.
 */

export interface PortapapelesInterno {
  texto: string
  /** "editor" = copiado/cortado dentro del editor de codigo. "pagina" =
   * copiado de cualquier otro lugar permitido de la pagina (la consigna,
   * hoy). El panel del tutor y el panel de salida/pruebas del propio editor
   * NUNCA llegan a setear esto (ADR-026 y la tabla del proposal) — quien
   * decide eso es el caller, no esta funcion. */
  origen: "editor" | "pagina"
}

/**
 * Normaliza fin de linea para la comparacion (CRLF -> LF).
 *
 * DECISION (pregunta abierta del proposal): Monaco/el SO pueden normalizar
 * el fin de linea entre el copiado y el pegado. El separador de linea es un
 * detalle de TRANSPORTE, no de contenido: dos copias del mismo texto con
 * distinto separador son la misma señal para la tesis. Comparar crudo
 * (byte a byte) produciria falsos negativos sobre copiados multilinea
 * legitimos — exactamente el error que este change existe para evitar.
 */
export function normalizarFinDeLinea(texto: string): string {
  return texto.replace(/\r\n/g, "\n")
}

/** Compara el texto que se esta por pegar contra lo guardado en el
 * portapapeles interno, con fin de linea normalizado de los dos lados. */
export function esPegadoValido(pegado: string, guardado: PortapapelesInterno | null): boolean {
  if (guardado === null) return false
  return normalizarFinDeLinea(pegado) === normalizarFinDeLinea(guardado.texto)
}
