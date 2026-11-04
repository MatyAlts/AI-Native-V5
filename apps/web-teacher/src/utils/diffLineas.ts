// Diff de lineas entre dos estados de codigo consecutivos de la traza ciega
// (change cibse-codificacion-ciega, design D13). NO reimplementa el LCS: usa el
// de `lineDiff.ts` (mismo algoritmo, mismo clamp de tamano, sin dependencias).
// Lo propio de este modulo:
//   - normaliza CRLF a LF antes de comparar: un alumno que pega desde Windows no
//     tiene que aparecer en la traza como si hubiera reescrito todas las lineas;
//   - devuelve la forma que consume `TrazaCiega` (tipo + texto, en espanol).

import { diffLines } from "./lineDiff"

export interface LineaDiff {
  tipo: "igual" | "agregada" | "quitada"
  texto: string
}

export interface ResultadoDiff {
  lineas: LineaDiff[]
  agregadas: number
  quitadas: number
  /** false si el snapshot excede el limite del LCS: la vista muestra el codigo sin diff. */
  disponible: boolean
}

const TIPO = { equal: "igual", add: "agregada", remove: "quitada" } as const

function normalizar(texto: string): string {
  return texto.replace(/\r\n?/g, "\n")
}

export function diffLineas(anterior: string, actual: string): ResultadoDiff {
  const r = diffLines(normalizar(anterior), normalizar(actual))
  return {
    lineas: r.lines.map((l) => ({ tipo: TIPO[l.type], texto: l.text })),
    agregadas: r.stats.added,
    quitadas: r.stats.removed,
    disponible: !r.truncated,
  }
}
