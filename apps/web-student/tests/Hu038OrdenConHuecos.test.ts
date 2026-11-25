/**
 * Aceptacion HU-038 (orquestador, antes de arreglar; el constructor no la
 * modifica). Bug que encontro Juani el 25/11 (previo: esta en `main`).
 *
 * Un TP con ejercicios de orden 1, 2, 3, 101, 102... (la API deja cualquier
 * `orden` unico; tambien quedan huecos al quitar un ejercicio del medio)
 * bloqueaba el 101 para siempre: `estaBloqueado` exigia que existieran y
 * estuvieran completos TODOS los numeros de 1 a n-1, y del 4 al 100 no
 * existen. El alumno no podia terminar el TP.
 *
 * Regla nueva: un ejercicio pendiente esta bloqueado si algun ejercicio QUE
 * EXISTE con `orden` menor no esta completado. Los numeros que no existen no
 * cuentan. Se mantiene la devolucion parcial (un completado nunca se bloquea).
 *
 * N13  Con huecos en la numeracion, el siguiente que existe se desbloquea.
 * N14  Sigue bloqueado si un ejercicio anterior que existe no se completo.
 * C13  Sin huecos se comporta igual que antes.
 */
import { describe, expect, it } from "vitest"
import { estaBloqueado } from "../src/lib/estaBloqueado"

const tp = (completos: number[]) =>
  [1, 2, 3, 101, 102, 103, 110, 117].map((orden) => ({
    orden,
    completado: completos.includes(orden),
  }))

describe("HU-038 · el orden con huecos no bloquea para siempre", () => {
  it("N13: completados 1, 2 y 3, el 101 se desbloquea", () => {
    expect(estaBloqueado(101, tp([1, 2, 3]))).toBe(false)
  })

  it("N13: el 110 se desbloquea cuando 101, 102 y 103 estan completos", () => {
    expect(estaBloqueado(110, tp([1, 2, 3, 101, 102, 103]))).toBe(false)
  })

  it("N14: el 102 sigue bloqueado si el 101 no se completo", () => {
    expect(estaBloqueado(102, tp([1, 2, 3]))).toBe(true)
  })

  it("N14: el 101 sigue bloqueado si falta el 2", () => {
    expect(estaBloqueado(101, tp([1, 3]))).toBe(true)
  })

  it("N13: un TP que arranca en 5 deja abrir el 5", () => {
    expect(
      estaBloqueado(5, [
        { orden: 5, completado: false },
        { orden: 9, completado: false },
      ]),
    ).toBe(false)
    expect(
      estaBloqueado(9, [
        { orden: 5, completado: false },
        { orden: 9, completado: false },
      ]),
    ).toBe(true)
  })

  it("C13: sin huecos, igual que siempre", () => {
    const seguidos = [1, 2, 3].map((orden) => ({ orden, completado: orden === 1 }))
    expect(estaBloqueado(1, seguidos)).toBe(false)
    expect(estaBloqueado(2, seguidos)).toBe(false)
    expect(estaBloqueado(3, seguidos)).toBe(true)
  })

  it("C13: un completado nunca se bloquea (devolucion parcial)", () => {
    expect(estaBloqueado(103, tp([103]))).toBe(false)
  })
})
