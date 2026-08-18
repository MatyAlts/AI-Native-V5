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
  ejerciciosParaResumen,
  redondearA10,
  resumirCorrecciones,
} from "../src/utils/correccionIA"

function correccion(orden: number, nota: number | null, over: Partial<CorreccionIA> = {}) {
  return {
    id: `c${orden}`,
    entrega_id: "e1",
    tp_ejercicio_id: `ej-${orden}`,
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
    tiene_pdf: false,
    created_at: "2026-08-18T10:00:00Z",
    finished_at: "2026-08-18T10:02:00Z",
    ...over,
  } as CorreccionIA
}

const DOS: EjercicioDelTP[] = [
  { ejercicioId: "ej-1", orden: 1, titulo: "Ejercicio 1", peso: 0.5 },
  { ejercicioId: "ej-2", orden: 2, titulo: "Ejercicio 2", peso: 0.5 },
]

describe("resumirCorrecciones", () => {
  test("promedia ponderando por peso", () => {
    const r = resumirCorrecciones(
      [
        { ejercicioId: "a", orden: 1, titulo: "E1", peso: 0.75 },
        { ejercicioId: "b", orden: 2, titulo: "E2", peso: 0.25 },
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
      [{ ejercicioId: "a", orden: 1, titulo: "E1", peso: 1 }],
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
        { ejercicioId: "a", orden: 1, titulo: "E1", peso: 3 },
        { ejercicioId: "b", orden: 2, titulo: "E2", peso: 1 },
      ],
      [correccion(1, 100), correccion(2, 0)],
    )
    expect(r.promedio100).toBe(75)
  })

  test("sin ejercicios no inventa un promedio", () => {
    expect(resumirCorrecciones([], []).promedio100).toBeNull()
  })

  test("con todos los pesos en cero no divide por cero", () => {
    const r = resumirCorrecciones(
      [{ ejercicioId: "a", orden: 1, titulo: "E1", peso: 0 }],
      [correccion(1, 90)],
    )
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

  test("un desglose sin puntajes legibles se reporta INDETERMINADO, no como que cierra", () => {
    // "No pude chequear" y "no habia nada que chequear" son cosas distintas.
    // Colapsarlas hacia que un desglose en un formato desconocido apagara la
    // unica defensa de la pantalla sin decir nada — y el formato real de
    // Active-IA nadie lo vio todavia.
    const r = chequearAritmetica([{ comentario: "bien" }], 87)
    expect(r?.indeterminado).toBe(true)
    expect(r?.difiere).toBe(false)
  })

  test("un puntaje que viene como STRING igual se suma", () => {
    // El formato de Active-IA es una conjetura nuestra. Un `"48"` en vez de
    // `48` no puede desactivar el guardrail en silencio.
    const r = chequearAritmetica([{ puntaje: "48" }, { puntaje: "14" }], 87)
    expect(r?.suma).toBe(62)
    expect(r?.difiere).toBe(true)
    expect(r?.indeterminado).toBe(false)
  })

  test("NO detecta el caso del 2026-08-17, y eso esta documentado", () => {
    // Los criterios sumaban EXACTO el total (87): el error no era aritmetico,
    // era una regla de la rubrica que no se aplico. Este test existe para que
    // nadie crea que el guardrail cubre ese caso — la pantalla lo dice.
    const r = chequearAritmetica(
      [{ puntaje: 48 }, { puntaje: 14 }, { puntaje: 15 }, { puntaje: 10 }, { puntaje: 0 }],
      87,
    )
    expect(r?.suma).toBe(87)
    expect(r?.difiere).toBe(false)
  })

  test("acepta las tres claves que usan los motores", () => {
    expect(chequearAritmetica([{ puntos: 40 }, { score: 47 }], 87)?.suma).toBe(87)
  })
})

describe("los tipos que cruzan el cable", () => {
  test("`nota_100` llega como STRING desde Postgres y se normaliza", () => {
    // `Numeric(5,2)` viaja como "87.00" aunque el tipo de TS diga `number`.
    // Hoy la aritmetica andaba de casualidad porque JS coacciona en `*`; un
    // `+` habria concatenado en silencio.
    const r = resumirCorrecciones(DOS, [
      correccion(1, "90.00" as unknown as number),
      correccion(2, "70.00" as unknown as number),
    ])
    expect(r.promedio100).toBe(80)
    expect(typeof r.promedio100).toBe("number")
  })

  test("un peso que no parsea NO se trata como cero: no se promedia", () => {
    // Con `pesoNormalizado = 0` el ejercicio contaba como presente y aportaba
    // nada: un TP donde uno saco 0/100 daba 100/100 de sugerencia.
    const r = resumirCorrecciones(
      [
        { ejercicioId: "a", orden: 1, titulo: "E1", peso: 1 },
        { ejercicioId: "b", orden: 2, titulo: "E2", peso: Number.NaN },
      ],
      [correccion(1, 100), correccion(2, 0)],
    )
    expect(r.promedio100).toBeNull()
    expect(r.propuesta10).toBeNull()
  })

  test("un peso negativo tampoco pasa", () => {
    const r = resumirCorrecciones(
      [
        { ejercicioId: "a", orden: 1, titulo: "E1", peso: 2 },
        { ejercicioId: "b", orden: 2, titulo: "E2", peso: -1 },
      ],
      [correccion(1, 100), correccion(2, 0)],
    )
    expect(r.promedio100).toBeNull()
  })
})

describe("emparejamiento estable", () => {
  test("si la TP se reordena, cada nota va con SU peso", () => {
    // El escenario: un ejercicio dificil (peso 0.1) que era el orden 1 y hoy
    // es el 2, y uno facil (peso 0.9) que hoy es el 1. Emparejando por
    // `orden`, la nota del dificil se ponderaba con el peso del facil y el
    // promedio daba 90 en vez de 10 — con el titulo equivocado al lado.
    const hoy: EjercicioDelTP[] = [
      { ejercicioId: "facil", orden: 1, titulo: "B (facil)", peso: 0.9 },
      { ejercicioId: "dificil", orden: 2, titulo: "A (dificil)", peso: 0.1 },
    ]
    const correcciones = [
      // Se corrigieron cuando el dificil era el 1.
      correccion(1, 100, { tp_ejercicio_id: "dificil" }),
      correccion(2, 0, { tp_ejercicio_id: "facil" }),
    ]

    const r = resumirCorrecciones(hoy, correcciones)
    expect(r.promedio100).toBe(10)
    expect(r.terminos.find((t) => t.titulo === "A (dificil)")?.nota100).toBe(100)
    expect(r.terminos.find((t) => t.titulo === "B (facil)")?.nota100).toBe(0)
  })

  test("sin identidad estable cae al orden, como antes", () => {
    // Correcciones viejas, de antes de que el backend expusiera
    // `tp_ejercicio_id`. Tienen que seguir funcionando.
    const r = resumirCorrecciones(
      [{ ejercicioId: null, orden: 1, titulo: "E1", peso: 1 }],
      [correccion(1, 80, { tp_ejercicio_id: null })],
    )
    expect(r.promedio100).toBe(80)
  })

  test("con el mismo `created_at` el resultado no depende del orden del array", () => {
    // Antes ganaba la primera del array, o sea que dependia de como ordenara
    // el backend. Ahora desempata por `id`, que es estable.
    const mismos = { created_at: "2026-08-18T10:00:00Z" }
    const a = correccion(1, 50, { ...mismos, id: "aaa" })
    const b = correccion(1, 90, { ...mismos, id: "bbb" })
    const ej = [{ ejercicioId: "ej-1", orden: 1, titulo: "E1", peso: 1 }]

    expect(resumirCorrecciones(ej, [a, b]).promedio100).toBe(
      resumirCorrecciones(ej, [b, a]).promedio100,
    )
  })
})

describe("con los payloads que la API produce de verdad", () => {
  // Los tres bugs serios de este epic vivian en la frontera de tipos: el
  // `nota_100` que llega como "87.00", el `peso_en_tp` que llega como
  // "0.2500", y el emparejamiento cuando la TP se reordena. Los fixtures con
  // numeros literales escritos a mano no los ven, porque el fixture lo
  // escribe el mismo que escribio el codigo.
  const TP_EJERCICIOS = [
    { ejercicio_id: "ej-a", orden: 1, peso_en_tp: "0.7500", ejercicio: { titulo: "E1" } },
    { ejercicio_id: "ej-b", orden: 2, peso_en_tp: "0.2500", ejercicio: { titulo: "E2" } },
  ]

  // Lo que sale de `CorreccionIAOut.model_dump_json()`: `nota_100` es string.
  const CORRECCIONES_API = [
    { ...correccion(1, 0), tp_ejercicio_id: "ej-a", nota_100: "100.00" },
    { ...correccion(2, 0), tp_ejercicio_id: "ej-b", nota_100: "0.00" },
  ] as unknown as CorreccionIA[]

  test("el mapeo + el promedio dan el numero correcto de punta a punta", () => {
    const r = resumirCorrecciones(ejerciciosParaResumen(TP_EJERCICIOS), CORRECCIONES_API)
    expect(r.promedio100).toBe(75)
    expect(r.propuesta10).toBe(7.5)
  })

  test("un `peso_en_tp` ilegible NO se convierte en cero", () => {
    const roto = [{ ...TP_EJERCICIOS[0]!, peso_en_tp: "" }, TP_EJERCICIOS[1]!]
    const r = resumirCorrecciones(ejerciciosParaResumen(roto), CORRECCIONES_API)
    expect(r.promedio100).toBeNull()
  })

  test("el mapeo conserva la identidad estable", () => {
    expect(ejerciciosParaResumen(TP_EJERCICIOS)[0]?.ejercicioId).toBe("ej-a")
  })
})
