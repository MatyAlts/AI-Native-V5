/**
 * Lock secuencial de los ejercicios de una TP, y alcance de una devolucion.
 *
 * Reglas (change publicar-nota-y-pedir-correccion, D6):
 *  - Un ejercicio COMPLETADO nunca esta bloqueado.
 *  - Uno pendiente esta bloqueado si ALGUN ejercicio de `orden` menor no esta
 *    completado (un orden anterior sin estado cuenta como pendiente).
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
  for (let o = 1; o < orden; o++) {
    if (!estados.find((e) => e.orden === o)?.completado) return true
  }
  return false
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
