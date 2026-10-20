/**
 * Change `alumno-mis-trabajos-corregidos` — logica pura de "Mi trabajo corregido".
 * Sin red ni efectos: solo transforma lo que la vista ya leyo.
 */
import type { ArtefactoEntregado, Entrega } from "../lib/api"
import {
  type EpisodioMensaje,
  type EpisodioSourceFile,
  type EpisodioSourceMeta,
  buildEpisodioSourceFile,
} from "./episodioDownload"

/** Solo una entrega ya corregida (o devuelta) tiene "trabajo corregido". */
export function esTrabajoCorregido(entrega: Pick<Entrega, "estado">): boolean {
  return entrega.estado === "graded" || entrega.estado === "returned"
}

export interface EjercicioDelTrabajo {
  titulo: string
  artefacto: ArtefactoEntregado
}

/** Artefactos ordenados por `orden`, rotulados "Ejercicio N" (D2-a: sin titulos). */
export function ejerciciosDelTrabajo(artefactos: ArtefactoEntregado[]): EjercicioDelTrabajo[] {
  return [...artefactos]
    .sort((a, b) => a.orden - b.orden)
    .map((artefacto) => ({ titulo: `Ejercicio ${artefacto.orden}`, artefacto }))
}

/** Archivo a descargar: el codigo SELLADO del artefacto + la charla si se pudo traer. */
export function archivoDeDescarga(
  artefacto: ArtefactoEntregado,
  messages: EpisodioMensaje[] | null,
  meta: EpisodioSourceMeta,
): EpisodioSourceFile {
  return buildEpisodioSourceFile({
    code: artefacto.codigo,
    messages: messages ?? [],
    language: artefacto.language,
    meta,
  })
}
