/**
 * Latch de emision de `episodio_abandonado` desde el navegador (ADR-025, G10-A).
 *
 * EL PROBLEMA QUE RESUELVE
 * ------------------------
 * El handler de `beforeunload` emite el abandono y ademas hace `preventDefault`
 * para que el browser pregunte "¿seguro que querés salir?". O sea: `beforeunload`
 * dispara ANTES de saber si el alumno se va o se queda, y puede dispararse
 * muchas veces en una misma sesion.
 *
 * Con un `boolean` plano —que es lo que habia— la primera vez que el alumno
 * roza el cierre y clickea "Quedarse", el guard queda en `true` PARA SIEMPRE:
 * el cierre real, media hora despues, ya no emite nada. El episodio recien se
 * cierra cuando el worker server-side lo barre a los 30 minutos, y lo hace con
 * `reason="timeout"` — o sea que el CTR registra "el sistema lo dio por
 * abandonado" cuando en realidad el alumno cerro la pestaña, y con media hora
 * de retraso en el `ts`. Sobre eso se calculan los tiempos de la tesis.
 *
 * LA DISTINCION QUE HACE FALTA
 * ----------------------------
 * Hay dos clases de emision y NO comparten latch:
 *
 *  - Por `beforeunload`: PROVISORIA. Si la pagina sigue viva despues del
 *    evento, el alumno cancelo la salida y el latch tiene que liberarse.
 *  - Por pausa explicita (el boton "Pausar"): DEFINITIVA. El episodio se
 *    cerro de verdad; el `beforeunload` que viene con el unmount posterior no
 *    debe volver a emitir.
 *
 * COMO SE DETECTA "SE QUEDO"
 * --------------------------
 * Programando la liberacion en un macrotask. Si la navegacion se concreta, la
 * pagina muere y ese callback nunca corre; si el alumno se queda (o el dialogo
 * nativo se cancela), el event loop sigue vivo y libera el latch. Es
 * inyectable para poder testearlo sin depender de timers reales.
 *
 * Emitir de mas no es el riesgo: el backend es idempotente por estado de sesion
 * (la primera emision borra la sesion Redis, la segunda encuentra `None` y
 * devuelve sin emitir). El riesgo es NO emitir, que es lo que pasaba.
 */

/** Programa la liberacion del latch. Inyectable para tests deterministas. */
export type ProgramadorLiberacion = (fn: () => void) => void

export interface LatchAbandono {
  /** Intenta emitir por `beforeunload`. Devuelve `true` si emitio.
   *
   * El latch se libera solo si la pagina sobrevive al evento — o sea, si el
   * alumno cancelo la salida. */
  intentarPorUnload(emitir: () => void): boolean
  /** Cierra el latch para siempre: el episodio ya se pauso explicitamente y
   * no hay nada mas que emitir. */
  marcarDefinitivo(): void
}

const programadorPorDefecto: ProgramadorLiberacion = (fn) => {
  // Macrotask, no microtask: los microtasks drenan dentro del propio
  // `beforeunload` y liberarian el latch antes de saber que decidio el alumno.
  setTimeout(fn, 0)
}

export function crearLatchAbandono(
  programarLiberacion: ProgramadorLiberacion = programadorPorDefecto,
): LatchAbandono {
  let emitido = false
  let definitivo = false

  return {
    intentarPorUnload(emitir: () => void): boolean {
      if (definitivo || emitido) return false
      emitido = true
      emitir()
      programarLiberacion(() => {
        // Una pausa explicita puede haber ganado la carrera mientras tanto.
        if (!definitivo) emitido = false
      })
      return true
    },
    marcarDefinitivo(): void {
      emitido = true
      definitivo = true
    },
  }
}
