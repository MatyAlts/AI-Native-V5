/**
 * Que ejercicios pidio corregir el docente, para la tarjeta de una re-entrega
 * (change reentregas-marcadas-en-pendientes, D5). Lectura tolerante: devuelve
 * `null` si no hay marca, y no inventa el detalle.
 */
export interface EstadoConMarca {
  orden: number
  reabierto_por_docente?: boolean | undefined
}

export function textoPedidosReentrega(estados: readonly EstadoConMarca[]): string | null {
  const marcados = estados
    .filter((e) => e.reabierto_por_docente)
    .map((e) => e.orden)
    .sort((a, b) => a - b)
  if (marcados.length === 0) return null
  if (marcados.length === estados.length) return "todos"
  if (marcados.length === 1) return `ej. ${marcados[0]}`
  return `ej. ${marcados.slice(0, -1).join(", ")} y ${marcados[marcados.length - 1]}`
}
