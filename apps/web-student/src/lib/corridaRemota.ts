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
 */

/** La parte del resultado que esta decisión mira. */
export interface CorridaRemotaResumen {
  timed_out?: boolean | undefined
  /** Ya viene traducido por `parseJavaError`; `null` si no hubo. */
  errorJava?: string | null | undefined
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
  if (r.timed_out) return MENSAJE_TIMEOUT
  return null
}

/**
 * Se menciona la entrada a propósito.
 *
 * En Java el stdin viaja entero y por adelantado: no hay `input()` interactivo
 * como en Python, porque un contenedor efímero no tiene canal de vuelta. El
 * bucle infinito más común de quien recién arranca es el que valida la entrada
 * sin consumirla:
 *
 *     while (!sc.hasNextInt()) { System.out.println("Ingresá un número"); }
 *
 * Con la caja "Entrada" vacía, `hasNextInt()` devuelve false para siempre y el
 * bucle gira sin leer nada. Sin esta pista el alumno busca el error en la
 * condición del while —que está bien— y no en la entrada, que es lo que falta.
 */
export const MENSAJE_TIMEOUT =
  "Tu programa supero el limite de tiempo y se interrumpio. Suele ser un bucle que nunca " +
  "termina: revisa si la condicion del while llega a cambiar alguna vez. Si tu programa lee " +
  'datos con Scanner, fijate que la caja "Entrada" tenga los valores que espera — sin ellos, ' +
  "un bucle que valida la entrada gira para siempre."
