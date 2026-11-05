// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
/**
 * Puerta de entrada del panel docente (design D13, spec estudio-codificacion-acceso:
 * "Entrada al panel docente para miembros sin comisiones" y "Disponibilidad del
 * panel ante fallas del servicio del estudio").
 *
 * Lo que se blinda: que la falla de UN servicio no deje afuera a quien tiene
 * acceso por el OTRO, y que nadie entre sin ninguno de los dos.
 */
import { describe, expect, it } from "vitest"
import { resolverAcceso } from "../src/utils/accesoPanel"

const MEMBRESIA = { clave: "cibse-2027", titulo: "T", rol: "codificador" as const, cerrada: false }

describe("resolverAcceso", () => {
  it("docente con comisiones y sin membresias: completo", () => {
    expect(
      resolverAcceso({
        comisiones: { ok: true, cantidad: 2 },
        membresias: { ok: true, datos: [] },
      }),
    ).toEqual({ modo: "completo" })
  })

  it("miembro sin comisiones: restringido", () => {
    expect(
      resolverAcceso({
        comisiones: { ok: true, cantidad: 0 },
        membresias: { ok: true, datos: [MEMBRESIA] },
      }),
    ).toEqual({ modo: "restringido" })
  })

  it("ni comisiones ni membresias: redirige al panel de alumno", () => {
    expect(
      resolverAcceso({
        comisiones: { ok: true, cantidad: 0 },
        membresias: { ok: true, datos: [] },
      }),
    ).toEqual({ modo: "redirigir" })
  })

  it("con comisiones y membresia: completo (el modo restringido es solo para quien no tiene otra cosa)", () => {
    expect(
      resolverAcceso({
        comisiones: { ok: true, cantidad: 1 },
        membresias: { ok: true, datos: [MEMBRESIA] },
      }),
    ).toEqual({ modo: "completo" })
  })

  it("falla mis-membresias pero tiene comisiones: completo igual", () => {
    expect(
      resolverAcceso({
        comisiones: { ok: true, cantidad: 3 },
        membresias: { ok: false },
      }),
    ).toEqual({ modo: "completo" })
  })

  it("fallan las comisiones pero tiene membresia: restringido", () => {
    expect(
      resolverAcceso({
        comisiones: { ok: false },
        membresias: { ok: true, datos: [MEMBRESIA] },
      }),
    ).toEqual({ modo: "restringido" })
  })

  it("fallan las dos consultas: redirige", () => {
    expect(
      resolverAcceso({
        comisiones: { ok: false },
        membresias: { ok: false },
      }),
    ).toEqual({ modo: "redirigir" })
  })

  it("fallan las comisiones y no tiene membresias: redirige", () => {
    expect(
      resolverAcceso({
        comisiones: { ok: false },
        membresias: { ok: true, datos: [] },
      }),
    ).toEqual({ modo: "redirigir" })
  })

  it("sin comisiones y con mis-membresias caido: redirige (no hay nada que acredite acceso)", () => {
    expect(
      resolverAcceso({
        comisiones: { ok: true, cantidad: 0 },
        membresias: { ok: false },
      }),
    ).toEqual({ modo: "redirigir" })
  })
})

describe("consultarAcceso: las dos consultas en paralelo, cada falla aislada", () => {
  it("una consulta que tira no impide resolver con la otra", async () => {
    const { consultarAcceso } = await import("../src/utils/accesoPanel")
    const modo = await consultarAcceso({
      listarComisiones: () => Promise.reject(new Error("academic caido")),
      listarMembresias: () => Promise.resolve([MEMBRESIA]),
    })
    expect(modo).toEqual({ modo: "restringido" })
  })

  it("mis-membresias caido con comisiones: completo", async () => {
    const { consultarAcceso } = await import("../src/utils/accesoPanel")
    const modo = await consultarAcceso({
      listarComisiones: () => Promise.resolve(2),
      listarMembresias: () => Promise.reject(new Error("classifier caido")),
    })
    expect(modo).toEqual({ modo: "completo" })
  })

  it("las dos consultas salen antes de que vuelva cualquiera (paralelo, no en serie)", async () => {
    const { consultarAcceso } = await import("../src/utils/accesoPanel")
    const arrancadas: string[] = []
    let soltarComisiones: (n: number) => void = () => {}
    const pendiente = consultarAcceso({
      listarComisiones: () => {
        arrancadas.push("comisiones")
        return new Promise<number>((r) => {
          soltarComisiones = r
        })
      },
      listarMembresias: () => {
        arrancadas.push("membresias")
        return Promise.resolve([])
      },
    })
    await Promise.resolve()
    expect(arrancadas.sort()).toEqual(["comisiones", "membresias"])
    soltarComisiones(1)
    expect(await pendiente).toEqual({ modo: "completo" })
  })
})
