/**
 * Elige, del artefacto sellado de la entrega, el codigo que el alumno ya
 * entrego PARA ESTE EJERCICIO (change `editor-muestra-codigo-entregado-al-reabrir`).
 *
 * Match por `orden` Y, cuando los dos lados lo traen, por `ejercicio_id`: un
 * artefacto de otro ejercicio jamas se usa (seria el arrastre de ED-4, eliminado
 * el 2026-09-28). Una entrega `legacy`, sin fila para el orden o con codigo
 * vacio no da candidato: la cascada sigue como antes.
 */
import type { EntregaArtefacto } from "./api"

export function codigoEntregadoDe(
  artefacto: EntregaArtefacto | null | undefined,
  orden: number,
  ejercicioId: string | null | undefined,
): string | null {
  if (!artefacto || artefacto.legacy) return null
  const fila = artefacto.artefactos.find(
    (a) =>
      a.orden === orden &&
      (a.ejercicio_id == null || ejercicioId == null || a.ejercicio_id === ejercicioId),
  )
  const codigo = fila?.codigo
  return codigo && codigo.trim() !== "" ? codigo : null
}
