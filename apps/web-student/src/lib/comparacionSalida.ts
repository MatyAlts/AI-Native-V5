/**
 * JAVA-1: comparacion de la salida del programa contra la salida esperada.
 *
 * ⚠ GEMELO OBLIGADO — `normalize_output` / `outputs_match` en
 * `apps/execution-service/src/execution_service/services/docker_runner.py`.
 *
 * Hay DOS correctores porque hay dos runtimes: Python corre en el navegador
 * (Pyodide) y Java en el servidor (contenedor efimero, ADR-060). Si las dos
 * normalizaciones se separan, el MISMO codigo aprueba en un lenguaje y falla en
 * el otro, y los conteos `passed`/`failed` de la cadena CTR dejan de ser
 * comparables entre cohortes. Cualquier cambio acá va tambien allá, y al reves.
 *
 * Qué se normaliza (y por qué solo esto)
 * --------------------------------------
 * Antes la comparacion era `actual.strip() == expected.strip()`: recortaba los
 * bordes del texto entero y nada mas. Fallaba por tres motivos que no son del
 * alumno sino del medio:
 *
 *   1. **Fin de linea**: `\r\n` (Windows) o `\r` suelto contra `\n`. El alumno
 *      no elige el EOL; lo elige su sistema o el terminal del contenedor.
 *   2. **Espacios al final de una linea**: `print("hola ")` vs `"hola"`, o un
 *      `print()` con separador que deja un espacio colgando. Invisible en
 *      pantalla, letal para `==`.
 *   3. **Salto de linea final**: `print` siempre agrega uno; la salida esperada
 *      del banco casi nunca lo trae.
 *
 * Y qué NO se normaliza, a proposito: mayusculas/minusculas, tildes, espacios
 * INTERNOS de una linea y lineas en blanco INTERMEDIAS. Todo eso es contenido
 * que el alumno decidio imprimir — tolerarlo seria corregir mal, no corregir
 * menos literal.
 *
 * Ojo con lo que este cambio hace MAS estricto
 * --------------------------------------------
 * `strip()` sobre el texto entero tambien perdonaba lineas en blanco y espacios
 * INICIALES. La normalizacion nueva no: solo descarta las lineas en blanco del
 * final. Es deliberado — una linea de mas al principio de la salida es una
 * diferencia real y visible — pero significa que un caso que antes pasaba por
 * ese motivo ahora falla.
 */

/** Blancos horizontales que se recortan al final de cada linea.
 *
 * Set explicito y no `\s`: `\s` de JS y `str.rstrip()` de Python no cubren
 * exactamente los mismos code points (nbsp, \x85, ﻿, separadores unicode),
 * y una diferencia ahi seria justo la asimetria Java/Python que este modulo
 * existe para impedir. Estos cuatro son identicos en los dos lenguajes. */
/**
 * Los blancos que recortamos: EXACTAMENTE los de `str.isspace()` de Python,
 * menos `\n` (que ya se separó en lineas).
 *
 * Enumerados a mano y no `\s`, porque **`\s` de JS no es `isspace()` de
 * Python**: `\s` incluye `\ufeff` (que Python NO considera blanco) y le faltan
 * `\x1c-\x1f` y `\x85` (que Python SÍ). Con `\s` los dos correctores
 * divergirían, que es lo único que este módulo existe para evitar.
 *
 * Y es el set de `isspace()` y no uno mas chico porque **el corrector viejo era
 * `str.strip()`** — en los dos runners, incluido el del navegador, que corria
 * dentro de Pyodide. Recortar menos que eso ENDURECE: hace fallar casos que
 * pasaban, sobre conteos que ya viajaron al CTR. El caso realista no es
 * teorico: el docente pega el `expected_output` desde Word y le entra un
 * espacio duro (`\u00a0`).
 */
const CLASE_BLANCOS =
  "\\t\\v\\f\\r\\x1c\\x1d\\x1e\\x1f\\x20\\x85\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000"
const BLANCOS_FINALES = new RegExp(`[${CLASE_BLANCOS}]+$`)
const BLANCOS_INICIALES = new RegExp(`^[${CLASE_BLANCOS}]+`)

/**
 * Normaliza una salida para compararla. Funcion PURA.
 *
 * 1. Unifica los fines de linea (`\r\n` y `\r` sueltos) a `\n`.
 * 2. Recorta los blancos al final de CADA linea.
 * 3. Descarta las lineas en blanco del final.
 */
export function normalizarSalida(texto: string): string {
  const lineas = texto
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((linea) => linea.replace(BLANCOS_FINALES, ""))
  while (lineas.length > 0 && lineas[lineas.length - 1] === "") {
    lineas.pop()
  }
  // Tambien las INICIALES: el `strip()` viejo sobre el texto entero las
  // perdonaba, y no descartarlas endurecia el corrector — un caso que pasaba
  // solo por eso empezaba a fallar. Endurecer perjudica al alumno; mantener la
  // tolerancia no perjudica a nadie. Y hay conteos que ya viajaron al CTR con
  // el criterio viejo: cambiarlos re-corrigiendo seria reescribir evidencia.
  while (lineas.length > 0 && lineas[0] === "") {
    lineas.shift()
  }
  // Y los blancos al principio de la PRIMERA linea, que es lo ultimo que el
  // `strip()` viejo perdonaba y esta normalizacion no. Solo la primera: el
  // `strip()` actuaba sobre los extremos del texto entero, asi que la sangria
  // de las lineas siguientes SIEMPRE conto como contenido. Se replica esa
  // asimetria tal cual — el objetivo es no cambiar ningun veredicto, ni para
  // un lado ni para el otro.
  if (lineas.length > 0) {
    // `?? ""` y no un `!`: con `noUncheckedIndexedAccess`, TypeScript no
    // estrecha `lineas[0]` con el `length > 0` de arriba. Es inerte en runtime.
    lineas[0] = (lineas[0] ?? "").replace(BLANCOS_INICIALES, "")
  }
  return lineas.join("\n")
}

/**
 * `true` si la salida obtenida equivale a la esperada. Funcion PURA.
 *
 * `esperado` nulo se trata como cadena vacia — es la semantica que ya tenia el
 * runner del navegador (`expected or ""`), donde un caso sin salida esperada
 * significa "no imprime nada". El servidor usa otra convencion para el mismo
 * `None` (ahi significa "no hay nada que comparar, con terminar bien alcanza",
 * caso `junit_assert`), asi que esa decision se toma ANTES de llamar acá y no
 * se comparte: lo unico compartido, y lo unico que tiene que estar en paridad,
 * es la normalizacion.
 */
export function salidaCoincide(actual: string, esperado: string | null | undefined): boolean {
  return normalizarSalida(actual) === normalizarSalida(esperado ?? "")
}
