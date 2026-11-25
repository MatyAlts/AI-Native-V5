/**
 * Avance del alumno en el campus (HU-035, vuelta de diseño): cuantos TPs de
 * una unidad entrego, en que estado esta cada unidad y como se muestra su
 * nombre en la tarjeta. Reglas puras; las vistas solo las pintan.
 */
import type { AvailableTarea, Entrega } from "./api"
import { unidadAbierta } from "./fechaCampus"

/** La entrega mas reciente de cada TP (por `updated_at`, si viene). */
export function entregaPorTp(entregas: Entrega[]): Map<string, Entrega> {
  const porTp = new Map<string, Entrega>()
  for (const e of entregas) {
    const previa = porTp.get(e.tarea_practica_id)
    if (!previa || (e.updated_at ?? "") > (previa.updated_at ?? "")) {
      porTp.set(e.tarea_practica_id, e)
    }
  }
  return porTp
}

/** Entregado = el alumno ya lo mando (esperando correccion o calificado). */
export function estaEntregada(entrega: Pick<Entrega, "estado"> | null | undefined): boolean {
  return entrega?.estado === "submitted" || entrega?.estado === "graded"
}

/** Cuantos de estos TPs tienen su ultima entrega mandada. */
export function cantidadEntregados(tps: AvailableTarea[], porTp: Map<string, Entrega>): number {
  return tps.filter((t) => estaEntregada(porTp.get(t.id))).length
}

/**
 * El nombre de la unidad sin el prefijo "Unidad N · " (el numero ya va arriba
 * de la tarjeta). Si el nombre no lo trae, o quitarlo lo deja vacio, queda
 * igual.
 */
export function tituloSinPrefijo(nombre: string): string {
  const sin = nombre.replace(/^\s*unidad\s+\d+\s*[·:.\-–—|]\s*/i, "").trim()
  return sin || nombre
}

export type EstadoUnidad = "completa" | "en_curso" | "proxima"

/**
 * Proxima: todavia no abrio. Completa: abierta, con TPs y todos entregados.
 * En curso: el resto de las abiertas.
 */
export function estadoUnidad(
  fechaApertura: string | null | undefined,
  hoy: string,
  totalTps: number,
  entregados: number,
): EstadoUnidad {
  if (!unidadAbierta(fechaApertura, hoy)) return "proxima"
  if (totalTps > 0 && entregados >= totalTps) return "completa"
  return "en_curso"
}
