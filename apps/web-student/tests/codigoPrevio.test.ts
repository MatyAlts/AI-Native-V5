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
  resolverCodigoAPersistir,
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

/**
 * La mitad de ESCRITURA de ED-4, que estaba sin cubrir.
 *
 * `resolverSiembra` (arriba) decide QUE se lee; `resolverCodigoAPersistir`
 * decide QUE se guarda al dejar un ejercicio. Las dos mitades tienen que
 * cerrar: una escritura que no ocurre es INVISIBLE — nadie ve el momento en que
 * no se guardo nada, se nota un ejercicio despues como un arrastre que no
 * llego, y para entonces ya no hay forma de saber de que lado se rompio.
 *
 * Por eso los tests de abajo cierran el circuito con `resolverSiembra` en vez
 * de solo mirar el objeto devuelto: lo que importa no es el shape, es que lo
 * que la escritura produce sea exactamente lo que la lectura acepta.
 */

/** Lo que el episodio que se esta dejando sabe de si mismo. */
const ORIGEN_OK = {
  tareaId: TAREA,
  ejercicioOrden: 1,
  language: "python",
  code: GUARDADO.code,
  placeholder: "# Escribi tu solucion aca\n",
}

describe("resolverCodigoAPersistir — cuando SI se guarda", () => {
  it("guarda el buffer del ejercicio que se deja, con su TP, orden y lenguaje", () => {
    expect(resolverCodigoAPersistir(ORIGEN_OK)).toEqual({
      tareaId: TAREA,
      ejercicioOrden: 1,
      language: "python",
      code: GUARDADO.code,
    })
  })

  it("lo que produce es exactamente lo que `resolverSiembra` acepta", () => {
    // El circuito cerrado: escritura -> lectura. Si la escritura guardara el
    // orden del ejercicio DESTINO en vez del de origen, o el lenguaje
    // equivocado, el objeto seguiria siendo valido y `resolverSiembra`
    // devolveria `null` — el arrastre no llegaria y nada fallaria.
    const entrada = resolverCodigoAPersistir(ORIGEN_OK)
    expect(entrada).not.toBeNull()
    expect(
      resolverSiembra(entrada, { tareaId: TAREA, ejercicioOrden: 2, language: "python" }),
    ).toBe(GUARDADO.code)
  })

  it("guarda el orden del ejercicio de ORIGEN, no un valor cualquiera", () => {
    // Anclado contra el `>=` de `resolverSiembra`: guardar el orden de mas
    // haria que el ejercicio siguiente se descarte a si mismo.
    const entrada = resolverCodigoAPersistir({ ...ORIGEN_OK, ejercicioOrden: 3 })
    expect(entrada?.ejercicioOrden).toBe(3)
    expect(resolverSiembra(entrada, { ...DESTINO_OK, ejercicioOrden: 4 })).toBe(GUARDADO.code)
    expect(resolverSiembra(entrada, { ...DESTINO_OK, ejercicioOrden: 3 })).toBeNull()
  })

  it("guarda el lenguaje del ejercicio de origen", () => {
    // Si guardara siempre "python", un ejercicio Java se sembraria en uno
    // Python y el editor abriria con el archivo roto — que es justo lo que la
    // condicion de lenguaje de `resolverSiembra` existe para impedir.
    const entrada = resolverCodigoAPersistir({
      ...ORIGEN_OK,
      language: "java",
      code: "class Main {}",
      placeholder: "// Escribi tu solucion aca\n",
    })
    expect(entrada?.language).toBe("java")
    expect(resolverSiembra(entrada, { ...DESTINO_OK, language: "python" })).toBeNull()
  })

  it("guarda codigo que apenas se diferencia del andamio", () => {
    // La condicion es igualdad EXACTA con el placeholder, no "se parece": una
    // linea agregada al andamio ya es trabajo del alumno.
    const entrada = resolverCodigoAPersistir({
      ...ORIGEN_OK,
      code: `${ORIGEN_OK.placeholder}print('hola')\n`,
    })
    expect(entrada).not.toBeNull()
  })
})

describe("resolverCodigoAPersistir — cuando NO se guarda", () => {
  it("no guarda si la TP todavia no hidrato", () => {
    // `tarea?.id` es `undefined` mientras el GET de la TP esta en vuelo. Sin
    // este recorte se guardaria una entrada con `tareaId: undefined`, que
    // ademas rompe la clave del almacen.
    expect(resolverCodigoAPersistir({ ...ORIGEN_OK, tareaId: undefined })).toBeNull()
    expect(resolverCodigoAPersistir({ ...ORIGEN_OK, tareaId: null })).toBeNull()
    expect(resolverCodigoAPersistir({ ...ORIGEN_OK, tareaId: "" })).toBeNull()
  })

  it("no guarda desde una TP monolitica", () => {
    // No hay "proximo ejercicio" al que arrastrarle nada. Y si se guardara,
    // `resolverSiembra` lo descartaria igual — pero dejaria basura en el
    // almacen con la clave de la TP.
    expect(resolverCodigoAPersistir({ ...ORIGEN_OK, ejercicioOrden: null })).toBeNull()
  })

  it("no guarda el andamio del lenguaje sin tocar", () => {
    // El alumno no escribio nada propio, y el ejercicio siguiente va a poner
    // ese mismo andamio solo. Guardarlo haria que el arrastre "funcione"
    // trayendo exactamente lo que ya iba a estar ahi.
    expect(resolverCodigoAPersistir({ ...ORIGEN_OK, code: ORIGEN_OK.placeholder })).toBeNull()
  })

  it("el orden 0 SI se guarda (no confundir con `null`)", () => {
    // Anti-falsy: `if (!origen.ejercicioOrden)` en vez de `== null` dejaria
    // afuera al ejercicio de orden 0. Hoy el banco empieza en 1, pero el
    // recorte tiene que ser por nulidad, no por falsy.
    expect(resolverCodigoAPersistir({ ...ORIGEN_OK, ejercicioOrden: 0 })?.ejercicioOrden).toBe(0)
  })
})
