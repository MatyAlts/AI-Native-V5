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
  /** Identidad estable del ejercicio (`tp_ejercicios.ejercicio_id`). */
  ejercicioId: string | null
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
  // Se indexa por la identidad ESTABLE del ejercicio, y por `orden` sólo
  // cuando no hay otra cosa. `orden` es la posición al momento de corregir: si
  // la TP se reordenó en el medio, emparejar por ahí pondera la nota de un
  // ejercicio con el peso de otro — y el "cálculo a la vista" muestra una
  // línea coherente y falsa, con el título equivocado al lado.
  const porId = new Map<string, CorreccionIA>()
  const porOrden = new Map<number, CorreccionIA>()

  const masNueva = (a: CorreccionIA, b: CorreccionIA | undefined): boolean => {
    if (!b) return true
    // El desempate por `id` no es cosmético: con dos correcciones del mismo
    // `created_at`, sin él el resultado dependía del orden del array que
    // devolviera el backend.
    return a.created_at !== b.created_at ? a.created_at > b.created_at : a.id > b.id
  }

  for (const c of correcciones) {
    if (c.estado !== "done" || c.nota_100 === null) continue
    if (c.tp_ejercicio_id) {
      if (masNueva(c, porId.get(c.tp_ejercicio_id))) porId.set(c.tp_ejercicio_id, c)
    }
    if (masNueva(c, porOrden.get(c.orden))) porOrden.set(c.orden, c)
  }

  const terminos: TerminoDelPromedio[] = []
  const faltantes: string[] = []
  for (const ej of ejercicios) {
    // El `??` de antes caia al emparejamiento por `orden` INCLUSO cuando el
    // ejercicio tiene identidad estable y lo unico que le falta es la
    // correccion. Era justo el bug que el comentario de arriba dice evitar.
    //
    // El caso: TP con A (dificil, peso 0.1) y B (facil, peso 0.9). El docente
    // corrige solo A, cuando A era `orden 1`. Despues se reordena la TP y B
    // pasa a ser `orden 1`. Para B, `porId` no encuentra nada y el fallback
    // devolvia la correccion de A: el panel mostraba el TP como COMPLETO,
    // proponia la nota de A para los dos, y el "calculo a la vista" imprimia
    // una linea perfectamente coherente y falsa, con el titulo equivocado al
    // lado. `faltantes` salia vacio y tapaba que faltaba una correccion.
    //
    // Con identidad estable, la ausencia en `porId` significa que ESE ejercicio
    // no esta corregido — y eso es un faltante, no una invitacion a adivinar.
    // El emparejamiento por `orden` queda solo para los ejercicios que no
    // tienen `ejercicioId`, que es para lo que existia.
    const porIdentidad = ej.ejercicioId ? porId.get(ej.ejercicioId) : undefined
    const porPosicion = porOrden.get(ej.orden)
    // El fallback por `orden` NO puede tomar una correccion que se declara de
    // OTRO ejercicio. Si trae `tp_ejercicio_id`, ya sabemos a quien pertenece:
    // no matchear por identidad significa que no es de este, y eso es un
    // FALTANTE, no una invitacion a adivinar por posicion.
    //
    // Sin esa condicion, el `??` tomaba la nota del vecino en cuanto la TP se
    // reordenaba entre la correccion y la lectura. El panel mostraba el TP
    // como completo, proponia una nota, e imprimia el "calculo a la vista" con
    // el titulo equivocado al lado — coherente y falso.
    //
    // El fallback sigue vivo para lo que existia: la TP monolitica y las
    // correcciones viejas, que no tienen `tp_ejercicio_id` y por lo tanto no
    // pueden ser de otro.
    const c = porIdentidad ?? (porPosicion?.tp_ejercicio_id ? undefined : porPosicion)
    if (!c || c.nota_100 === null) {
      faltantes.push(ej.titulo)
      continue
    }
    // `nota_100` sale de un `Numeric(5,2)` de Postgres y viaja como STRING
    // ("87.00") aunque el tipo de TS diga `number`. Hoy la aritmetica anda de
    // casualidad porque JS coacciona en `*`, pero un `+` concatenaria en
    // silencio. Se normaliza en la frontera.
    const nota = Number(c.nota_100)
    if (!Number.isFinite(nota)) {
      faltantes.push(ej.titulo)
      continue
    }
    terminos.push({
      orden: ej.orden,
      titulo: ej.titulo,
      nota100: nota,
      peso: ej.peso,
      pesoNormalizado: 0,
    })
  }

  // Un peso que no es un numero positivo y finito NO puede tratarse como 0.
  // Con `pesoNormalizado = 0` el ejercicio cuenta como presente y aporta nada:
  // un TP donde uno saco 0/100 daria 100/100 como sugerencia, y el docente
  // veria un promedio completo que le falta un termino. Es la misma trampa que
  // el backend evita al no convertir un fallo en un cero.
  const pesosInvalidos = terminos.some((t) => !Number.isFinite(t.peso) || t.peso <= 0)

  const sumaPesos = terminos.reduce((acc, t) => acc + t.peso, 0)
  for (const t of terminos) {
    t.pesoNormalizado = Number.isFinite(sumaPesos) && sumaPesos > 0 ? t.peso / sumaPesos : 0
  }

  // Falta alguno -> NO se promedia. Un promedio sobre 3 de 4 ejercicios se lee
  // como la nota del TP y no lo es.
  if (
    faltantes.length > 0 ||
    terminos.length === 0 ||
    pesosInvalidos ||
    !Number.isFinite(sumaPesos) ||
    sumaPesos <= 0
  ) {
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
  /**
   * No se pudo chequear: hay desglose pero ningun puntaje legible.
   *
   * Es distinto de "no hay nada que chequear" (que devuelve `null`) y de
   * "chequee y cierra" (`difiere: false`). Colapsarlos hacia que un desglose
   * en un formato que no conocemos apagara la unica defensa de la pantalla
   * sin decir nada — y el formato real de Active-IA nadie lo vio todavia,
   * porque los endpoints de escritura de rubricas no existen.
   */
  indeterminado: boolean
}

/**
 * Suma los criterios del desglose y los compara con el total.
 *
 * **Lo que este chequeo NO detecta, y hay que decirlo:** el incidente del
 * 2026-08-17 —una rubrica que declaraba una reduccion del 30% y un motor que
 * devolvio la suma limpia (87) en vez de aplicarla (~61)— tenia los criterios
 * sumando EXACTO el total. El error no era aritmetico: era una regla de la
 * rubrica que no se aplico, y eso no se puede ver desde el desglose.
 *
 * Lo que si detecta es la otra mitad del mismo incidente y su familia: un
 * total que no es la suma de sus partes. La pantalla dice las dos cosas — que
 * chequea la suma, y que un desglose que cierra no prueba que la nota sea
 * correcta. Un guardrail que se presenta como mas de lo que es da seguridad
 * falsa, que es peor que no tenerlo.
 *
 * Devuelve `null` cuando no hay NADA que chequear (sin desglose o sin total).
 * Con desglose pero sin puntajes legibles devuelve `indeterminado: true`:
 * "no pude chequear" y "no habia nada" son cosas distintas.
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
    // Acepta el numero y tambien el string numerico: el formato real de
    // Active-IA nadie lo vio, y un `"48"` en vez de `48` no puede apagar la
    // defensa en silencio.
    const num = typeof valor === "number" ? valor : Number.parseFloat(String(valor ?? ""))
    if (Number.isFinite(num)) {
      suma += num
      encontroAlguno = true
    }
  }
  if (!encontroAlguno) {
    return { suma: 0, total, difiere: false, indeterminado: true }
  }

  // 0.5 de tolerancia: los motores redondean cada criterio por su cuenta y una
  // diferencia de decimas no es un error de calculo. 0.5 sobre 100 no tapa el
  // caso real, que fueron 26 puntos.
  return { suma, total, difiere: Math.abs(suma - total) > 0.5, indeterminado: false }
}

/**
 * Lo que devuelve `GET /tareas-practicas/{id}/ejercicios`, en crudo.
 *
 * `peso_en_tp` es un string: sale de un `Numeric(5,4)` de Postgres. Igual que
 * `nota_100`, cruza el cable como texto aunque el nombre sugiera un numero.
 */
export interface TpEjercicioCrudo {
  ejercicio_id: string
  orden: number
  peso_en_tp: string
  ejercicio: { titulo: string }
}

/**
 * Traduce la respuesta de la API a lo que espera `resumirCorrecciones`.
 *
 * Vive aca y no inline en el JSX porque es una frontera de tipos, y las
 * fronteras de tipos son donde se esconden los bugs de esta pantalla: el
 * `peso_en_tp` es un string, y un `|| 0` puesto de apuro convertia un peso
 * ilegible en cero — con lo cual el ejercicio contaba como presente, aportaba
 * nada, y un TP con un 0/100 daba 100/100 de sugerencia.
 *
 * **Sin `|| 0` a proposito**: un peso que no parsea tiene que llegar como
 * `NaN` para que `resumirCorrecciones` se niegue a promediar. Es la misma
 * regla que el backend aplica con los fallos: un valor que falta no es un
 * cero.
 */
export function ejerciciosParaResumen(tpEjercicios: TpEjercicioCrudo[]): EjercicioDelTP[] {
  return tpEjercicios.map((tp) => ({
    ejercicioId: tp.ejercicio_id,
    orden: tp.orden,
    titulo: tp.ejercicio.titulo,
    peso: Number.parseFloat(tp.peso_en_tp),
  }))
}
