/**
 * Actividad del alumno en el editor / chat del tutor, para que
 * `lectura_enunciado` NO cuente como "lectura" el tiempo en que el alumno
 * esta escribiendo codigo o conversando con el tutor (hallazgo #6-B).
 *
 * Antes el hook sumaba todo el tiempo con el panel visible y la pestana en
 * foco: un alumno programando 10 minutos con el enunciado a la vista
 * reportaba 10 minutos de "lectura", contaminando la senal N1.
 */

/**
 * Ventana de quietud: tras la ultima actividad (tecla en el editor, mensaje o
 * tecla en el chat, ejecutar codigo/tests) el tiempo NO se cuenta como lectura
 * durante estos ms. 5 s cubre las pausas naturales entre teclas/ráfagas sin
 * penalizar a quien deja de escribir para releer la consigna: pasados 5 s sin
 * tocar nada, se asume que volvio a leer.
 */
export const ACTIVIDAD_QUIETA_MS = 5_000

let ultimaActividad: number | null = null

/** Registra actividad en editor/chat. `ahora` inyectable para tests. */
export function marcarActividad(ahora: number = Date.now()): void {
  ultimaActividad = ahora
}

export function ultimaActividadMs(): number | null {
  return ultimaActividad
}

/** Solo para tests. */
export function resetActividad(): void {
  ultimaActividad = null
}

/**
 * Cuantos de los `deltaMs` transcurridos hasta `ahora` cuentan como lectura:
 * todos si no hubo actividad reciente, ninguno si la hubo dentro de la ventana.
 */
export function msDeLecturaContables(
  deltaMs: number,
  ahora: number,
  ultimaActividadAt: number | null,
  quietaMs: number = ACTIVIDAD_QUIETA_MS,
): number {
  if (deltaMs <= 0) return 0
  if (ultimaActividadAt != null && ahora - ultimaActividadAt < quietaMs) return 0
  return deltaMs
}
