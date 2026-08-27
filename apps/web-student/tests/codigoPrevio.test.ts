/**
 * ED-4 — arrastre del codigo entre ejercicios de una misma TP.
 *
 * Todo el criterio de la siembra vive en `resolverSiembra`, funcion pura. Lo
 * que se protege aca no es "que ande el arrastre" sino lo contrario: las cinco
 * condiciones bajo las cuales NO hay que sembrar. Sembrar de mas es peor que no
 * sembrar — pisa el buffer que el alumno ya tenia, o le abre el editor con un
 * archivo de otro lenguaje que no compila.
 *
 * El invariante de trazabilidad (la siembra NO emite `edicion_codigo`) se cubre
 * aparte, en `CodigoPrevioSiembra.test.tsx`, porque exige montar el componente.
 */

import { describe, expect, it, vi } from "vitest"
import {
  type AlmacenLike,
  type CodigoPrevio,
  claveCodigoPrevio,
  guardarCodigoPrevio,
  leerCodigoPrevio,
  parseCodigoPrevio,
  resolverSiembra,
} from "../src/lib/codigoPrevio"

/** Almacen en memoria: `guardarCodigoPrevio`/`leerCodigoPrevio` toman un
 * `AlmacenLike` inyectable justamente para no depender de `window`. */
function almacenEnMemoria(inicial: Record<string, string> = {}) {
  const datos = new Map(Object.entries(inicial))
  return {
    datos,
    getItem: (k: string) => datos.get(k) ?? null,
    setItem: (k: string, v: string) => {
      datos.set(k, v)
    },
    removeItem: (k: string) => {
      datos.delete(k)
    },
  } satisfies AlmacenLike & { datos: Map<string, string> }
}

const TAREA = "tp-2f1c9c2e"

/** Lo que el alumno dejo en el ejercicio 1 de la TP. */
const GUARDADO: CodigoPrevio = {
  tareaId: TAREA,
  ejercicioOrden: 1,
  language: "python",
  code: "def saludar(nombre):\n    print('Hola', nombre)\n",
}

/** El ejercicio 2 de la MISMA TP, que es el caso que el arrastre existe para
 * resolver (el banco PID-UTN encadena E1 -> E2). */
const DESTINO_OK = { tareaId: TAREA, ejercicioOrden: 2, language: "python" }

describe("claveCodigoPrevio", () => {
  it("da una clave por TP: dos TPs abiertas en la misma sesion no se pisan", () => {
    expect(claveCodigoPrevio("tp-a")).not.toBe(claveCodigoPrevio("tp-b"))
  })

  it("la clave lleva el id de la TP y un prefijo propio del web-student", () => {
    // El prefijo importa: `sessionStorage` esta compartido con
    // `active-episode-id` y `active-exercise-context`.
    expect(claveCodigoPrevio(TAREA)).toBe(`web-student.codigo-previo.${TAREA}`)
  })
})

describe("resolverSiembra — cuando SI se siembra", () => {
  it("siembra el ejercicio siguiente de la misma TP y el mismo lenguaje", () => {
    expect(resolverSiembra(GUARDADO, DESTINO_OK)).toBe(GUARDADO.code)
  })

  it("siembra aunque el salto de orden no sea de a uno", () => {
    // El almacen guarda UNA entrada por TP ("lo ultimo que dejaste"), no un
    // historial: si el alumno salta del 1 al 4, el 4 hereda del 1.
    expect(resolverSiembra(GUARDADO, { ...DESTINO_OK, ejercicioOrden: 4 })).toBe(GUARDADO.code)
  })
})

describe("resolverSiembra — cuando NO se siembra", () => {
  it("TP monolitica (ejercicioOrden null): no existe 'el ejercicio anterior'", () => {
    expect(resolverSiembra(GUARDADO, { ...DESTINO_OK, ejercicioOrden: null })).toBeNull()
  })

  it("orden undefined (backend viejo sin ejercicio_orden) tampoco siembra", () => {
    // El `== null` de la guarda atrapa `undefined` ademas de `null`, y eso es lo
    // que sostiene el caso: con `===` la comparacion de orden que sigue seria
    // `1 >= undefined` -> `1 >= NaN` -> false, y la TP monolitica se sembraria
    // con el codigo de otro ejercicio. (Con `null` la guarda es redundante: el
    // `>=` ya lo resuelve porque `null` coacciona a 0.)
    const destinoSinOrden = { ...DESTINO_OK, ejercicioOrden: undefined as unknown as null }
    expect(resolverSiembra(GUARDADO, destinoSinOrden)).toBeNull()
  })

  it("misma orden (F5 sobre el mismo ejercicio): no se re-siembra a si mismo", () => {
    // Con `>` en vez de `>=`, un F5 pisaria lo que el episodio ya hidrato con
    // su propio `last_code_snapshot`.
    expect(resolverSiembra(GUARDADO, { ...DESTINO_OK, ejercicioOrden: 1 })).toBeNull()
  })

  it("orden anterior a la guardada: no trae codigo del futuro", () => {
    const guardadoDelTres = { ...GUARDADO, ejercicioOrden: 3 }
    expect(resolverSiembra(guardadoDelTres, { ...DESTINO_OK, ejercicioOrden: 2 })).toBeNull()
  })

  it("otra TP: el arrastre nunca cruza de una TP a otra", () => {
    expect(resolverSiembra(GUARDADO, { ...DESTINO_OK, tareaId: "tp-otra" })).toBeNull()
  })

  it("otro lenguaje: sembrar Python en un ejercicio Java abre el archivo roto", () => {
    expect(resolverSiembra(GUARDADO, { ...DESTINO_OK, language: "java" })).toBeNull()
  })

  it("codigo vacio o solo espacios: no hay nada que sembrar", () => {
    expect(resolverSiembra({ ...GUARDADO, code: "" }, DESTINO_OK)).toBeNull()
    expect(resolverSiembra({ ...GUARDADO, code: "   \n\t\n" }, DESTINO_OK)).toBeNull()
  })

  it("sin nada guardado", () => {
    expect(resolverSiembra(null, DESTINO_OK)).toBeNull()
  })
})

describe("parseCodigoPrevio — nada mal formado puede sembrar el editor", () => {
  it("acepta una entrada completa y bien tipada", () => {
    expect(parseCodigoPrevio(JSON.stringify(GUARDADO))).toEqual(GUARDADO)
  })

  it("null y cadena vacia", () => {
    expect(parseCodigoPrevio(null)).toBeNull()
    expect(parseCodigoPrevio("")).toBeNull()
  })

  it("JSON corrupto (escritura cortada a la mitad)", () => {
    expect(parseCodigoPrevio('{"tareaId":"tp-1","ejercicio')).toBeNull()
  })

  it("JSON valido que no es un objeto", () => {
    expect(parseCodigoPrevio('"solo un string"')).toBeNull()
    expect(parseCodigoPrevio("42")).toBeNull()
    expect(parseCodigoPrevio("null")).toBeNull()
    expect(parseCodigoPrevio("[1,2,3]")).toBeNull()
  })

  it("entrada incompleta: falta cualquiera de los cuatro campos", () => {
    for (const campo of ["tareaId", "ejercicioOrden", "language", "code"] as const) {
      const parcial: Record<string, unknown> = { ...GUARDADO }
      delete parcial[campo]
      expect(parseCodigoPrevio(JSON.stringify(parcial)), `sin ${campo}`).toBeNull()
    }
  })

  it("campos con el tipo equivocado", () => {
    expect(parseCodigoPrevio(JSON.stringify({ ...GUARDADO, ejercicioOrden: "2" }))).toBeNull()
    expect(parseCodigoPrevio(JSON.stringify({ ...GUARDADO, code: 123 }))).toBeNull()
    expect(parseCodigoPrevio(JSON.stringify({ ...GUARDADO, tareaId: "" }))).toBeNull()
    expect(parseCodigoPrevio(JSON.stringify({ ...GUARDADO, language: "" }))).toBeNull()
  })

  it("orden no finita: NaN e Infinity romperian la comparacion de orden", () => {
    // `JSON.stringify` los serializa como `null`, asi que hay que armarlos a
    // mano — es exactamente lo que llegaria de un almacen escrito por otra
    // version del codigo.
    expect(
      parseCodigoPrevio('{"tareaId":"t","ejercicioOrden":null,"language":"py","code":"x"}'),
    ).toBeNull()
    expect(
      parseCodigoPrevio('{"tareaId":"t","ejercicioOrden":1e999,"language":"py","code":"x"}'),
    ).toBeNull()
  })
})

describe("guardarCodigoPrevio", () => {
  it("guarda una entrada releible por leerCodigoPrevio", () => {
    const almacen = almacenEnMemoria()
    guardarCodigoPrevio(almacen, GUARDADO)
    expect(leerCodigoPrevio(almacen, DESTINO_OK)).toBe(GUARDADO.code)
  })

  it("no guarda si el buffer esta vacio o es solo espacios", () => {
    const almacen = almacenEnMemoria()
    guardarCodigoPrevio(almacen, { ...GUARDADO, code: "  \n  " })
    expect(almacen.datos.size).toBe(0)
  })

  it("un setItem que tira (Safari privado, cuota llena) NO rompe la salida", () => {
    // Se llama desde `handleClose` DESPUES de que el episodio cerro de verdad:
    // si esto propagara, una excepcion de cuota abortaria el flujo de cierre.
    const almacen: AlmacenLike = {
      getItem: () => null,
      setItem: vi.fn(() => {
        throw new DOMException("QuotaExceededError")
      }),
      removeItem: () => {},
    }
    expect(() => guardarCodigoPrevio(almacen, GUARDADO)).not.toThrow()
  })

  it("la entrada nueva pisa la anterior de la misma TP", () => {
    const almacen = almacenEnMemoria()
    guardarCodigoPrevio(almacen, GUARDADO)
    guardarCodigoPrevio(almacen, { ...GUARDADO, ejercicioOrden: 2, code: "print('dos')" })
    expect(almacen.datos.size).toBe(1)
    expect(leerCodigoPrevio(almacen, { ...DESTINO_OK, ejercicioOrden: 3 })).toBe("print('dos')")
  })
})

describe("leerCodigoPrevio", () => {
  it("devuelve null si no hay nada guardado para esa TP", () => {
    expect(leerCodigoPrevio(almacenEnMemoria(), DESTINO_OK)).toBeNull()
  })

  it("un getItem que tira NO rompe la hidratacion del episodio", () => {
    const almacen: AlmacenLike = {
      getItem: vi.fn(() => {
        throw new DOMException("SecurityError")
      }),
      setItem: () => {},
      removeItem: () => {},
    }
    expect(leerCodigoPrevio(almacen, DESTINO_OK)).toBeNull()
  })

  it("basura en el almacen no siembra el editor", () => {
    const almacen = almacenEnMemoria({ [claveCodigoPrevio(TAREA)]: "no soy json" })
    expect(leerCodigoPrevio(almacen, DESTINO_OK)).toBeNull()
  })

  it("lee de la clave de SU TP, no de cualquiera", () => {
    const almacen = almacenEnMemoria({
      [claveCodigoPrevio("tp-otra")]: JSON.stringify({ ...GUARDADO, tareaId: "tp-otra" }),
    })
    expect(leerCodigoPrevio(almacen, DESTINO_OK)).toBeNull()
  })
})
