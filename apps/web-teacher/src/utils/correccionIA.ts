/**
 * La aritmetica del resumen de correcciones asistidas.
 *
 * Vive aparte del componente porque es lo unico de este epic que puede estar
 * MAL en silencio: una pantalla rota se ve, un promedio mal ponderado no.
 *
 * Tres reglas, y ninguna es de presentacion:
 *
 * 1. **Si falta una correccion, no se promedia.** Un promedio sobre 3 de 4
 *    ejercicios es un numero que parece la nota del TP y no lo es. Se muestra
 *    parcial y se nombran los que faltan.
 * 2. **El calculo se muestra, no solo el resultado.** El docente tiene que
 *    poder ver de donde sale el numero que va a usar como base.
 * 3. **Los criterios de Active-IA NO se mapean contra la rubrica local.** Van
 *    lado a lado. Emparejar por nombre pone el puntaje de un criterio en otro
 *    que se llama parecido, y eso no se ve.
 */
import type { CorreccionIA } from "../lib/api"

export interface EjercicioDelTP {
  orden: number
  titulo: string
  /** `peso_en_tp` del ejercicio, en la escala en que lo guarda la TP. */
  peso: number
}

export interface TerminoDelPromedio {
  orden: number
  titulo: string
  nota100: number
  peso: number
  /** El peso ya normalizado sobre la suma de pesos presentes. */
  pesoNormalizado: number
}

export interface ResumenCorrecciones {
  /** null cuando falta alguna correccion: no se promedia a medias. */
  promedio100: number | null
  /** La nota sobre 10 que propone el boton, con el redondeo ya aplicado. */
  propuesta10: number | null
  terminos: TerminoDelPromedio[]
  /** Ejercicios sin correccion terminada, por titulo. */
  faltantes: string[]
  /** Suma de los pesos usados, para poder mostrarla. */
  sumaPesos: number
}

/**
 * Arma el resumen. `correcciones` puede traer varias por ejercicio: se usa la
 * mas nueva que haya terminado bien.
 */
export function resumirCorrecciones(
  ejercicios: EjercicioDelTP[],
  correcciones: CorreccionIA[],
): ResumenCorrecciones {
  const porOrden = new Map<number, CorreccionIA>()
  for (const c of correcciones) {
    if (c.estado !== "done" || c.nota_100 === null) continue
    const previa = porOrden.get(c.orden)
    if (!previa || c.created_at > previa.created_at) porOrden.set(c.orden, c)
  }

  const terminos: TerminoDelPromedio[] = []
  const faltantes: string[] = []
  for (const ej of ejercicios) {
    const c = porOrden.get(ej.orden)
    if (!c || c.nota_100 === null) {
      faltantes.push(ej.titulo)
      continue
    }
    terminos.push({
      orden: ej.orden,
      titulo: ej.titulo,
      nota100: c.nota_100,
      peso: ej.peso,
      pesoNormalizado: 0,
    })
  }

  const sumaPesos = terminos.reduce((acc, t) => acc + t.peso, 0)
  for (const t of terminos) {
    t.pesoNormalizado = sumaPesos > 0 ? t.peso / sumaPesos : 0
  }

  // Falta alguno -> NO se promedia. Un promedio sobre 3 de 4 ejercicios se lee
  // como la nota del TP y no lo es.
  if (faltantes.length > 0 || terminos.length === 0 || sumaPesos <= 0) {
    return { promedio100: null, propuesta10: null, terminos, faltantes, sumaPesos }
  }

  const promedio100 = terminos.reduce((acc, t) => acc + t.nota100 * t.pesoNormalizado, 0)
  return {
    promedio100,
    propuesta10: redondearA10(promedio100),
    terminos,
    faltantes,
    sumaPesos,
  }
}

/**
 * Pasa una nota /100 a la escala /10 de la plataforma.
 *
 * Dos decimales porque la columna es `Numeric(5,2)`: proponer un valor con
 * mas precision de la que se puede guardar haria que el numero que el docente
 * ve y el que queda en la base sean distintos.
 */
export function redondearA10(nota100: number): number {
  return Math.round((nota100 / 10) * 100) / 100
}

export interface ChequeoAritmetico {
  /** Suma de los puntajes del desglose. */
  suma: number
  /** El total que declaro Active-IA. */
  total: number
  /** Difieren mas alla del error de redondeo. */
  difiere: boolean
}

/**
 * Suma los criterios del desglose y los compara con el total.
 *
 * No es paranoia: el 2026-08-17 una rubrica declaraba una reduccion del 30% y
 * el motor devolvio la suma limpia de los criterios (87) en vez de aplicarla
 * (~61). Ademas mostraba un criterio en 0/10 cuando sus subcriterios sumaban
 * 5. Si el desglose no cierra con el total, el numero de arriba no es de fiar
 * y hay que decirlo antes de que el docente lo use como base.
 *
 * Devuelve `null` cuando no hay desglose: no hay nada que chequear, y
 * reportar "no cierra" sobre una lista vacia seria una alarma falsa.
 */
export function chequearAritmetica(
  desglose: Array<Record<string, unknown>>,
  total: number | null,
): ChequeoAritmetico | null {
  if (total === null || desglose.length === 0) return null

  let suma = 0
  let encontroAlguno = false
  for (const criterio of desglose) {
    const valor = criterio.puntaje ?? criterio.puntos ?? criterio.score
    if (typeof valor === "number") {
      suma += valor
      encontroAlguno = true
    }
  }
  if (!encontroAlguno) return null

  // 0.5 de tolerancia: los motores redondean cada criterio por su cuenta y una
  // diferencia de decimas no es un error de calculo. 0.5 sobre 100 no tapa el
  // caso real, que fueron 26 puntos.
  return { suma, total, difiere: Math.abs(suma - total) > 0.5 }
}
