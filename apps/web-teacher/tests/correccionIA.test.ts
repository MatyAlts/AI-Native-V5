/**
 * La aritmetica del resumen de correcciones asistidas.
 *
 * Es lo unico de este epic que puede estar mal EN SILENCIO: una pantalla rota
 * se ve, un promedio mal ponderado no — y el numero que sale de aca es el que
 * el docente va a usar como base de una nota que termina en un legajo.
 */
import { describe, expect, test } from "vitest"
import type { CorreccionIA } from "../src/lib/api"
import {
  type EjercicioDelTP,
  chequearAritmetica,
  redondearA10,
  resumirCorrecciones,
} from "../src/utils/correccionIA"

function correccion(orden: number, nota: number | null, over: Partial<CorreccionIA> = {}) {
  return {
    id: `c${orden}`,
    entrega_id: "e1",
    orden,
    estado: nota === null ? "error" : "done",
    rubrica_id: "r1",
    nota_100: nota,
    desglose: [],
    tests_snapshot: {},
    artefacto_sha256: "s",
    error_code: null,
    error_detail: null,
    es_infraestructura: false,
    external_correccion_id: null,
    created_at: "2026-08-18T10:00:00Z",
    finished_at: "2026-08-18T10:02:00Z",
    ...over,
  } as CorreccionIA
}

const DOS: EjercicioDelTP[] = [
  { orden: 1, titulo: "Ejercicio 1", peso: 0.5 },
  { orden: 2, titulo: "Ejercicio 2", peso: 0.5 },
]

describe("resumirCorrecciones", () => {
  test("promedia ponderando por peso", () => {
    const r = resumirCorrecciones(
      [
        { orden: 1, titulo: "E1", peso: 0.75 },
        { orden: 2, titulo: "E2", peso: 0.25 },
      ],
      [correccion(1, 100), correccion(2, 0)],
    )
    expect(r.promedio100).toBe(75)
    expect(r.propuesta10).toBe(7.5)
  })

  test("NO promedia si falta la correccion de un ejercicio", () => {
    // Un promedio sobre 3 de 4 se lee como la nota del TP y no lo es.
    const r = resumirCorrecciones(DOS, [correccion(1, 90)])
    expect(r.promedio100).toBeNull()
    expect(r.propuesta10).toBeNull()
    expect(r.faltantes).toEqual(["Ejercicio 2"])
  })

  test("una correccion FALLIDA cuenta como faltante, no como cero", () => {
    // Tratarla como 0 seria convertir "el servicio no respondio" en una nota.
    const r = resumirCorrecciones(DOS, [correccion(1, 90), correccion(2, null)])
    expect(r.promedio100).toBeNull()
    expect(r.faltantes).toEqual(["Ejercicio 2"])
  })

  test("una fallida CON nota no cuenta: el estado manda sobre el numero", () => {
    // El backend no puede producir esto (el CHECK lo impide), pero el
    // frontend recibe JSON y el tipo lo permite. Si el filtro mirara solo
    // `nota_100 !== null`, una respuesta malformada meteria en el promedio la
    // nota de una correccion que fallo — que es exactamente lo que todo el
    // epic existe para evitar.
    const r = resumirCorrecciones(DOS, [
      correccion(1, 90),
      correccion(2, 40, { estado: "error", error_code: "GEMINI_OVERLOADED" }),
    ])
    expect(r.promedio100).toBeNull()
    expect(r.faltantes).toEqual(["Ejercicio 2"])
  })

  test("una correccion en curso tambien cuenta como faltante", () => {
    const r = resumirCorrecciones(DOS, [
      correccion(1, 90),
      correccion(2, null, { estado: "running" }),
    ])
    expect(r.promedio100).toBeNull()
  })

  test("con varias del mismo ejercicio usa la mas nueva", () => {
    const r = resumirCorrecciones(
      [{ orden: 1, titulo: "E1", peso: 1 }],
      [
        correccion(1, 40, { created_at: "2026-08-18T09:00:00Z" }),
        correccion(1, 80, { created_at: "2026-08-18T11:00:00Z" }),
      ],
    )
    expect(r.promedio100).toBe(80)
  })

  test("expone los terminos para poder mostrar el calculo", () => {
    // El docente tiene que ver de donde sale el numero, no solo el numero.
    const r = resumirCorrecciones(DOS, [correccion(1, 80), correccion(2, 60)])
    expect(r.terminos).toHaveLength(2)
    expect(r.terminos[0]?.pesoNormalizado).toBeCloseTo(0.5)
    expect(r.sumaPesos).toBeCloseTo(1)
  })

  test("pesos que no suman 1 se normalizan", () => {
    // `peso_en_tp` es un Numeric(5,4) por ejercicio; nada garantiza que la
    // suma de 1 exacto.
    const r = resumirCorrecciones(
      [
        { orden: 1, titulo: "E1", peso: 3 },
        { orden: 2, titulo: "E2", peso: 1 },
      ],
      [correccion(1, 100), correccion(2, 0)],
    )
    expect(r.promedio100).toBe(75)
  })

  test("sin ejercicios no inventa un promedio", () => {
    expect(resumirCorrecciones([], []).promedio100).toBeNull()
  })

  test("con todos los pesos en cero no divide por cero", () => {
    const r = resumirCorrecciones([{ orden: 1, titulo: "E1", peso: 0 }], [correccion(1, 90)])
    expect(r.promedio100).toBeNull()
  })
})

describe("redondearA10", () => {
  test("respeta los dos decimales de la columna", () => {
    // `Numeric(5,2)`: proponer mas precision de la que se puede guardar hace
    // que el numero que el docente ve y el que queda en la base difieran.
    expect(redondearA10(87)).toBe(8.7)
    expect(redondearA10(86.666)).toBe(8.67)
    expect(redondearA10(100)).toBe(10)
    expect(redondearA10(0)).toBe(0)
  })
})

describe("chequearAritmetica", () => {
  test("marca cuando el desglose no cierra con el total", () => {
    // El caso real del 2026-08-17: la rubrica declaraba una reduccion del 30%
    // y el motor devolvio la suma limpia de los criterios.
    const r = chequearAritmetica(
      [{ puntaje: 48 }, { puntaje: 14 }, { puntaje: 15 }, { puntaje: 10 }, { puntaje: 0 }],
      61,
    )
    expect(r?.suma).toBe(87)
    expect(r?.difiere).toBe(true)
  })

  test("no marca cuando cierra", () => {
    expect(chequearAritmetica([{ puntaje: 50 }, { puntaje: 37 }], 87)?.difiere).toBe(false)
  })

  test("tolera decimas de redondeo", () => {
    // Cada criterio se redondea por su cuenta; una decima no es un error.
    expect(chequearAritmetica([{ puntaje: 43.3 }, { puntaje: 43.4 }], 87)?.difiere).toBe(false)
  })

  test("sin desglose no dice nada", () => {
    // Reportar "no cierra" sobre una lista vacia seria una alarma falsa.
    expect(chequearAritmetica([], 87)).toBeNull()
  })

  test("sin total no dice nada", () => {
    expect(chequearAritmetica([{ puntaje: 10 }], null)).toBeNull()
  })

  test("con un desglose sin puntajes numericos no dice nada", () => {
    expect(chequearAritmetica([{ comentario: "bien" }], 87)).toBeNull()
  })

  test("acepta las tres claves que usan los motores", () => {
    expect(chequearAritmetica([{ puntos: 40 }, { score: 47 }], 87)?.suma).toBe(87)
  })
})
