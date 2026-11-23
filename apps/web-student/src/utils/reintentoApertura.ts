/**
 * Argumentos del "Reintentar" de la pantalla de apertura (HU-020, F21).
 *
 * Antes el reintento llamaba a `openEpisodeAndNavigate` sin `entregaId`, asi
 * que no se guardaba el contexto del ejercicio y el episodio nuevo quedaba
 * suelto. La vista "opening" guarda ejercicio y entrega; esto los arma para
 * volver a abrir exactamente lo mismo.
 */
export interface VistaApertura {
  ejercicioId: string | null
  ejercicioOrden: number | null
  entregaId?: string | null
}

export interface ArgumentosDeReintento {
  ejercicio: { id: string; orden: number } | null
  entregaId: string | null
}

export function argumentosDeReintento(v: VistaApertura): ArgumentosDeReintento {
  const ejercicio =
    v.ejercicioId && v.ejercicioOrden != null
      ? { id: v.ejercicioId, orden: v.ejercicioOrden }
      : null
  return { ejercicio, entregaId: v.entregaId ?? null }
}
