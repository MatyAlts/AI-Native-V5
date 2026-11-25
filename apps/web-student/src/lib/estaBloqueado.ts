/**
 * Lock secuencial de los ejercicios de una TP, y alcance de una devolucion.
 *
 * Reglas (change publicar-nota-y-pedir-correccion, D6):
 *  - Un ejercicio COMPLETADO nunca esta bloqueado.
 *  - Uno pendiente esta bloqueado si ALGUN ejercicio QUE EXISTE en `estados`
 *    con `orden` menor no esta completado. Los numeros que no existen no
 *    cuentan (HU-038): un TP con ordenes 1, 2, 3, 101 deja abrir el 101 con
 *    el 1, el 2 y el 3 completos. Antes se exigia todo 1..n-1 y un hueco en
 *    la numeracion trababa el TP para siempre. El tutor-service aplica la
 *    misma regla al abrir el episodio (`services/orden_ejercicios.py`).
 *
 * Con una devolucion parcial ("2 y 4" de 5) el 2 se habilita, el 4 espera al 2
 * y el 1/3/5 siguen completados. Con avance normal o devolucion total es
 * identico al lock de siempre ("el anterior tiene que estar completado").
 */
export interface EstadoEjercicioLike {
  orden: number
  completado: boolean
  reabierto_por_docente?: boolean | undefined
}

export function estaBloqueado(orden: number, estados: readonly EstadoEjercicioLike[]): boolean {
  const propio = estados.find((e) => e.orden === orden)
  if (propio?.completado) return false
  return estados.some((e) => e.orden < orden && !e.completado)
}

/** Espejo de `ordenes_a_corregir` del backend: marcados, o todos si no hay marcas. */
export function ordenesACorregir(estados: readonly EstadoEjercicioLike[]): Set<number> {
  const marcados = estados.filter((e) => e.reabierto_por_docente).map((e) => e.orden)
  if (marcados.length > 0) return new Set(marcados)
  return new Set(estados.map((e) => e.orden))
}

/** True si la entrega fue devuelta con un subconjunto de ejercicios. */
export function esDevolucionParcial(estados: readonly EstadoEjercicioLike[]): boolean {
  return estados.some((e) => e.reabierto_por_docente)
}

/**
 * La marca `reabierto_por_docente` persiste despues de re-entregar (para que el
 * docente vea que ejercicios pidio), asi que solo manda para el alumno cuando
 * la entrega esta `returned`. En `submitted`/`graded` es historia.
 */
export function devolucionParcialVigente(
  estadoEntrega: string,
  estados: readonly EstadoEjercicioLike[],
): boolean {
  return estadoEntrega === "returned" && esDevolucionParcial(estados)
}
