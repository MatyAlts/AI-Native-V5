// Puerta de entrada del panel docente (change cibse-codificacion-ciega, design D13).
//
// Dos consultas independientes deciden el acceso: las comisiones del docente
// (academic-service) y las membresias de estudio (classifier-service). La regla
// central es que la falla de UNA no le cierre la puerta a quien entra por la OTRA:
//   - con comisiones se entra al panel completo, aunque `mis-membresias` falle
//     (las dos secciones del estudio muestran su error, el resto del panel no);
//   - sin comisiones (o con esa consulta caida) y con membresia, modo restringido;
//   - sin nada que acredite acceso, al panel de alumno, como antes del change.
//
// Funcion pura a proposito: `main.tsx` solo hace las dos consultas y aplica esto.

import type { Membresia } from "../lib/estudioApi"

export type ModoAcceso = "completo" | "restringido" | "redirigir"

export type ResultadoComisiones = { ok: true; cantidad: number } | { ok: false }
export type ResultadoMembresias = { ok: true; datos: Membresia[] } | { ok: false }

export function resolverAcceso(entrada: {
  comisiones: ResultadoComisiones
  membresias: ResultadoMembresias
}): { modo: ModoAcceso } {
  const { comisiones, membresias } = entrada
  if (comisiones.ok && comisiones.cantidad > 0) return { modo: "completo" }
  if (membresias.ok && membresias.datos.length > 0) return { modo: "restringido" }
  return { modo: "redirigir" }
}

/**
 * Hace las dos consultas EN PARALELO y resuelve el modo. Una consulta que tira
 * cuenta como `{ ok: false }`, no como falla de la otra: `Promise.allSettled`
 * a proposito, para que academic-service caido no tape una membresia valida ni
 * classifier-service caido le cierre el panel a un docente con comisiones.
 */
export async function consultarAcceso(consultas: {
  listarComisiones: () => Promise<number>
  listarMembresias: () => Promise<Membresia[]>
}): Promise<{ modo: ModoAcceso }> {
  const [comisiones, membresias] = await Promise.allSettled([
    consultas.listarComisiones(),
    consultas.listarMembresias(),
  ])
  return resolverAcceso({
    comisiones:
      comisiones.status === "fulfilled" ? { ok: true, cantidad: comisiones.value } : { ok: false },
    membresias:
      membresias.status === "fulfilled" ? { ok: true, datos: membresias.value } : { ok: false },
  })
}
