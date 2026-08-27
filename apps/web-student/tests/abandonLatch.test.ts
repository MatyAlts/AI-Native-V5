/**
 * Latch de `episodio_abandonado` (BUG-8).
 *
 * El defecto original: `beforeunload` seteaba un booleano en `true` y no lo
 * bajaba nunca. Como ese evento dispara ANTES de saber si el alumno se va o se
 * queda, el primer "Quedarse" dejaba el guard trabado y el cierre REAL de la
 * pestaña ya no emitia nada. El episodio se cerraba recien a los 30 minutos por
 * el worker server-side, con `reason="timeout"` — el CTR terminaba diciendo
 * "el sistema lo dio por abandonado" con media hora de retraso sobre un cierre
 * que el alumno hizo a mano.
 */
import { describe, expect, it, vi } from "vitest"
import { crearLatchAbandono } from "../src/lib/abandonLatch"

/** Programador manual: `correr()` simula "la pagina siguio viva". No llamarlo
 * simula que la navegacion se concreto y el callback murio con la pagina. */
function programadorManual() {
  const pendientes: (() => void)[] = []
  return {
    programar: (fn: () => void) => {
      pendientes.push(fn)
    },
    correr: () => {
      const copia = [...pendientes]
      pendientes.length = 0
      for (const fn of copia) fn()
    },
  }
}

describe("crearLatchAbandono", () => {
  it("emite en el primer beforeunload", () => {
    const emitir = vi.fn()
    const latch = crearLatchAbandono(() => {})
    expect(latch.intentarPorUnload(emitir)).toBe(true)
    expect(emitir).toHaveBeenCalledTimes(1)
  })

  it("no re-emite en beforeunloads encadenados del mismo intento de salida", () => {
    // El anti-spam original sigue valiendo: `beforeunload` y
    // `visibilitychange`→hidden disparan en sucesion (fix QA #9).
    const emitir = vi.fn()
    const latch = crearLatchAbandono(() => {})
    latch.intentarPorUnload(emitir)
    latch.intentarPorUnload(emitir)
    latch.intentarPorUnload(emitir)
    expect(emitir).toHaveBeenCalledTimes(1)
  })

  it("si el alumno clickea 'Quedarse', el cierre REAL vuelve a emitir", () => {
    // Este es el bug: antes, el guard quedaba trabado para siempre.
    const emitir = vi.fn()
    const p = programadorManual()
    const latch = crearLatchAbandono(p.programar)

    latch.intentarPorUnload(emitir) // el alumno roza el cierre...
    p.correr() // ...y se queda: la pagina sigue viva

    expect(latch.intentarPorUnload(emitir)).toBe(true)
    expect(emitir).toHaveBeenCalledTimes(2)
  })

  it("si la salida se concreta, la liberacion nunca corre y el latch no importa", () => {
    // La pagina murio: el callback programado no llega a ejecutarse.
    const emitir = vi.fn()
    const p = programadorManual()
    const latch = crearLatchAbandono(p.programar)

    latch.intentarPorUnload(emitir)
    // sin `p.correr()`
    expect(latch.intentarPorUnload(emitir)).toBe(false)
    expect(emitir).toHaveBeenCalledTimes(1)
  })

  it("tras una pausa explicita, el unload posterior NO emite", () => {
    // "Pausar" cierra el episodio de verdad; el `beforeunload` del unmount que
    // viene despues no debe duplicar el abandono.
    const emitir = vi.fn()
    const p = programadorManual()
    const latch = crearLatchAbandono(p.programar)

    latch.marcarDefinitivo()
    expect(latch.intentarPorUnload(emitir)).toBe(false)
    p.correr()
    expect(latch.intentarPorUnload(emitir)).toBe(false)
    expect(emitir).not.toHaveBeenCalled()
  })

  it("una pausa explicita que gana la carrera al beforeunload no se destraba sola", () => {
    // Orden posible: beforeunload emite y programa la liberacion, el alumno
    // cancela y aprieta "Pausar" antes de que corra el macrotask.
    const emitir = vi.fn()
    const p = programadorManual()
    const latch = crearLatchAbandono(p.programar)

    latch.intentarPorUnload(emitir)
    latch.marcarDefinitivo()
    p.correr()

    expect(latch.intentarPorUnload(emitir)).toBe(false)
    expect(emitir).toHaveBeenCalledTimes(1)
  })

  it("por default programa la liberacion en un macrotask, no en un microtask", async () => {
    // Un microtask drena dentro del propio `beforeunload` y liberaria el latch
    // antes de saber que decidio el alumno.
    const emitir = vi.fn()
    const latch = crearLatchAbandono()
    latch.intentarPorUnload(emitir)
    await Promise.resolve()
    expect(latch.intentarPorUnload(emitir)).toBe(false)

    await new Promise((r) => setTimeout(r, 0))
    expect(latch.intentarPorUnload(emitir)).toBe(true)
  })
})
