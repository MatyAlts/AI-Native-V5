/**
 * Qué mensaje merece una corrida remota que terminó "bien" pero no anduvo.
 *
 * Se saca a una función pura por el mismo motivo que `entregaGuard.ts` y
 * `pyodideError.ts`: la decisión vivía enterrada en el handler `async` de
 * "Ejecutar", donde para ejercitarla hay que montar Monaco y mockear tres
 * llamadas de red. O sea que nadie la ejercitaba — y por eso el campo
 * `timed_out` pudo existir en el tipo, viajar en cada respuesta, y no tener un
 * solo lector.
 *
 * EL BUG (reporte de una alumna de Prog 2, 2026-09-01)
 * ----------------------------------------------------
 * En un lenguaje remoto (Java), un bucle infinito del alumno terminaba así:
 *
 *   1. el contenedor se mata a los 10 s de wall-time;
 *   2. el payload de modo libre manda `outcome: "completed"` SIEMPRE, así que
 *      no entra por la rama de `infrastructure_failure`;
 *   3. `stderr` viene vacío —lo matamos nosotros, no hubo excepción Java— así
 *      que `parseJavaError` no encuentra nada y no se setea ningún error;
 *   4. el alumno ve su salida parcial y NINGÚN mensaje.
 *
 * Desde su lado el programa "anduvo". Entonces vuelve a apretar Ejecutar. Y
 * otra vez. Lo que se reporta como *"se queda en un bucle infinito y no puede
 * avanzar"* es ese bucle: el de los intentos.
 *
 * Y la plataforma YA SABÍA decirlo, en los otros dos caminos:
 *   - Python: el watchdog levanta *"La ejecución superó los 5 segundos… Revisá
 *     si tenés un bucle infinito"*.
 *   - Java modo "Probar": `_ERROR_MESSAGE[TIME_LIMIT_EXCEEDED]` dice *"posible
 *     bucle infinito"*.
 *
 * El único mudo era "Ejecutar" en un lenguaje remoto — justo el botón que se
 * aprieta mientras se escribe el programa.
 *
 * CAMBIO DE SEMÁNTICA SOBRE DATOS YA GRABADOS — leer antes de analizar el CTR
 * ---------------------------------------------------------------------------
 * `CodigoEjecutadoPayload` NO tiene campo de éxito: el éxito se infiere aguas
 * abajo de si `stderr` viene vacío. Este arreglo cambia qué significa vacío:
 *
 *     ANTES:    timeout de Java  →  stderr = ""   (idéntico a una corrida limpia)
 *     DESPUÉS:  timeout de Java  →  stderr = mensaje
 *
 * La cadena es append-only. Los eventos `codigo_ejecutado` emitidos ANTES de
 * este deploy, con timeout, quedan con `stderr = ""` para siempre: no hay
 * migración posible y son indistinguibles de una ejecución exitosa.
 *
 * Y hay consumidores reales, no hipotéticos, en `classifier-service`:
 *
 *   - `subgrupo.py::dim_persistencia` cuenta fallos con `stderr != ""`. Un
 *     timeout NUNCA contó como fallo.
 *   - `subgrupo.py::dim_experimentacion` lee "resolvió limpio" como
 *     `stdout != "" and stderr == ""`. Un timeout con salida parcial se leía
 *     como que resolvió bien.
 *
 * Las dos alimentan el eje de apropiación. O sea que un alumno cuyo programa
 * entró en bucle infinito y fue matado a los 10 s quedó registrado como alguien
 * que ejecutó su código sin errores — y si esa señal alimentó una clasificación,
 * lo clasificó con un dato falso.
 *
 * Re-clasificar hoy NO lo arregla: el código de `subgrupo.py` está bien, el dato
 * de entrada quedó mal grabado. Cualquier análisis longitudinal que cruce el
 * antes y el después de este deploy tiene que declararlo.
 */

/** La parte del resultado que esta decisión mira. */
export interface CorridaRemotaResumen {
  timed_out?: boolean | undefined
  /** Ya viene traducido por `parseJavaError`; `null` si no hubo. */
  errorJava?: string | null | undefined
  /**
   * ¿La caja "Entrada" estaba vacía? Decide si se da la pista del Scanner.
   *
   * `undefined` significa "no lo sé", y ahí NO se da: una pista específica
   * equivocada es peor que ninguna, porque manda a revisar lo que está bien.
   */
  stdinVacio?: boolean | undefined
}

/**
 * Mensaje sobre por qué la corrida no sirvió, o `null` si no hay nada que decir.
 *
 * El error de Java gana sobre el timeout cuando están los dos: una excepción
 * con línea y causa es información concreta; el timeout es una hipótesis. Pero
 * en la práctica no coexisten — un programa que revienta no llega a agotar el
 * wall-time — así que el orden importa más como regla declarada que como caso
 * frecuente.
 */
export function mensajeDeCorrida(r: CorridaRemotaResumen): string | null {
  if (r.errorJava) return r.errorJava
  if (!r.timed_out) return null
  return r.stdinVacio === true ? `${MENSAJE_TIMEOUT} ${PISTA_ENTRADA_VACIA}` : MENSAJE_TIMEOUT
}

/** Lo que siempre es cierto de un timeout, sin adivinar la causa. */
export const MENSAJE_TIMEOUT =
  "Tu programa supero el limite de tiempo y se interrumpio. Suele ser un bucle que nunca " +
  "termina: revisa si la condicion del while llega a cambiar alguna vez."

/**
 * La pista del Scanner, y por que va SEPARADA y condicionada.
 *
 * En Java el stdin viaja entero y por adelantado: no hay `input()` interactivo
 * como en Python, porque un contenedor efimero no tiene canal de vuelta. El
 * bucle infinito mas comun de quien recien arranca es el que valida la entrada
 * sin consumirla:
 *
 *     while (!sc.hasNextInt()) { System.out.println("Ingresa un numero"); }
 *
 * Con la caja "Entrada" VACIA, `hasNextInt()` devuelve false para siempre y el
 * bucle gira sin leer nada. Ahi la pista vale oro.
 *
 * Con la caja LLENA no vale nada, y cuesta: el alumno se va a revisar su
 * entrada, que esta bien, mientras el bucle de verdad sigue en otro lado. Un
 * mensaje que manda a la persona en la direccion equivocada es peor que uno
 * generico — el generico te hace preguntar, este te hace perder la tarde.
 *
 * Es el mismo defecto que el "Abri cada ejercicio una vez antes de entregar"
 * del PR #86: una instruccion precisa, dicha con seguridad, sobre algo que el
 * sistema no verifico.
 */
export const PISTA_ENTRADA_VACIA =
  'La caja "Entrada" esta vacia: si tu programa lee datos con Scanner, un bucle que valida ' +
  "la entrada gira para siempre cuando no hay nada que leer."
