/**
 * Estado de un trabajo practico visto por el alumno en el campus (HU-035).
 *
 * Sale SOLO de su entrega (`GET /entregas?propias=true`), sin pedir nada mas:
 *  - sin entrega, o borrador sin ningun ejercicio completado -> Pendiente
 *  - borrador con al menos un ejercicio completado, o devuelta  -> En curso
 *  - entregada                                                  -> Esperando corrección
 *  - calificada                                                 -> Calificado · <nota>
 *
 * "En curso" no mira episodios abiertos: un alumno que abrio el TP y no
 * termino ningun ejercicio sigue en Pendiente. Es la regla del contrato.
 */
import type { Entrega } from "./api"

export type TipoEstadoTp = "pendiente" | "en_curso" | "esperando" | "calificado"

export interface EstadoTp {
  tipo: TipoEstadoTp
  etiqueta: string
}

type EntregaParaEstado = Pick<Entrega, "estado" | "ejercicio_estados" | "nota_final">

const NOTA = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 })

export function estadoTp(entrega: EntregaParaEstado | null | undefined): EstadoTp {
  if (!entrega) return { tipo: "pendiente", etiqueta: "Pendiente" }
  switch (entrega.estado) {
    case "graded": {
      const nota = entrega.nota_final
      return {
        tipo: "calificado",
        etiqueta: nota == null ? "Calificado" : `Calificado · ${NOTA.format(nota)}`,
      }
    }
    case "submitted":
      return { tipo: "esperando", etiqueta: "Esperando corrección" }
    case "returned":
      return { tipo: "en_curso", etiqueta: "En curso" }
    default: {
      const algunoCompleto = (entrega.ejercicio_estados ?? []).some((e) => e.completado)
      return algunoCompleto
        ? { tipo: "en_curso", etiqueta: "En curso" }
        : { tipo: "pendiente", etiqueta: "Pendiente" }
    }
  }
}
