/**
 * Change `descargas-borrador-y-entregado` — logica pura, sin red ni efectos.
 * Un solo lugar para los rotulos y para la regla de que boton se ofrece,
 * asi las pantallas del alumno no vuelven a divergir.
 */
import type { EntregaEstado } from "../lib/api"

export type TipoDescarga = "borrador" | "entregado"

/** `.java` para Java; cualquier otro valor (o nulo) es `.py`. */
export function rotuloDescarga(tipo: TipoDescarga, language: string | null | undefined): string {
  const ext = language === "java" ? ".java" : ".py"
  const que = tipo === "borrador" ? "borrador" : "lo entregado"
  return `Descargar ${que} (${ext})`
}

export interface EntradaBotonesDescarga {
  estado: EntregaEstado
  legacy: boolean
  submittedAt: string | null
  completado: boolean
}

/**
 * Que botones se ofrecen para un ejercicio (design D2). El borrador solo se
 * ofrece cuando puede diferir de lo entregado; lo entregado, solo si hay un
 * artefacto sellado (entrega alguna vez enviada y no legacy).
 */
export function botonesDeDescarga({
  estado,
  legacy,
  submittedAt,
  completado,
}: EntradaBotonesDescarga): { borrador: boolean; entregado: boolean } {
  if (legacy) return { borrador: completado, entregado: false }
  const hayArtefacto = submittedAt != null && estado !== "draft"
  const entregaCerrada = estado === "submitted" || estado === "graded"
  return { borrador: completado && !entregaCerrada, entregado: hayArtefacto }
}
