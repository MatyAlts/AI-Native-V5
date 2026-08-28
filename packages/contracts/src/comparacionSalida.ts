/**
 * JAVA-1: comparacion de la salida del programa contra la salida esperada.
 *
 * IMPLEMENTACION CANONICA. Vive en `@platform/contracts` y no dentro de un
 * frontend porque tiene TRES consumidores, no dos:
 *
 *   1. `apps/web-student` — el alumno corre Python en el navegador (Pyodide).
 *   2. `apps/execution-service` — el servidor corre Java en un contenedor
 *      efimero (ADR-060). Es Python, no puede importar esto: es un GEMELO
 *      OBLIGADO (`normalize_output` / `outputs_match` en
 *      `services/docker_runner.py`) verificado contra la misma tabla de casos.
 *   3. `apps/web-teacher` — "Probar ejercicio", donde el docente valida el
 *      ejercicio ANTES de asignarselo a la cohorte (`lib/pyodideRunner.ts`).
 *
 * El tercero existia desde el principio y no estaba en la cuenta: tenia su
 * propia `normalize()` con el `\s` de JavaScript, que este modulo prohibe con
 * nombre y apellido. Divergia en 5 code points y en el `\r` suelto, y el camino
 * que abria no es teorico: el docente pega el `expected_output` desde un
 * archivo con BOM (`U+FEFF`) → "Probar" da VERDE porque el `\s` de JS recorta
 * el BOM → asigna el ejercicio → la cohorte entera recibe WRONG_ANSWER con
 * codigo correcto, en silencio. Y eso mueve `test_count_passed/failed`, que es
 * el evento que alimenta la clasificacion N1–N4.
 *
 * Por eso hay UNA sola implementacion en TypeScript y los dos frontends la
 * importan. La paridad con el gemelo Python se verifica con la tabla compartida
 * `tests/fixtures/paridad-salida.json`, que leen los TRES lados.
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

/**
 * Los blancos que recortamos: EXACTAMENTE los de `str.isspace()` de Python,
 * menos `\n` (que ya se separó en lineas). Son 28.
 *
 * Enumerados a mano y no `\s`, porque **`\s` de JS no es `isspace()` de
 * Python**: `\s` incluye `﻿` (que Python NO considera blanco) y le faltan
 * `\x1c`–`\x1f` y `\x85` (que Python SÍ). Con `\s` los correctores divergen,
 * que es lo unico que este modulo existe para evitar — y es exactamente lo que
 * le pasaba al de web-teacher: 24 code points contra 28.
 *
 * Y es el set de `isspace()` y no uno mas chico porque **el corrector viejo era
 * `str.strip()`** — en los dos runners, incluido el del navegador, que corria
 * dentro de Pyodide. Recortar menos que eso ENDURECE: hace fallar casos que
 * pasaban, sobre conteos que ya viajaron al CTR. El caso realista no es
 * teorico: el docente pega el `expected_output` desde Word y le entra un
 * espacio duro (` `).
 *
 * Todos son BMP (< `U+10000`), asi que `charCodeAt` los identifica exacto y no
 * hace falta iterar por code point.
 */
const CODIGOS_BLANCOS: ReadonlySet<number> = new Set([
  0x09, // \t  tabulacion
  0x0b, // \v  tabulacion vertical
  0x0c, // \f  form feed
  0x0d, // \r  retorno de carro
  0x1c, // separador de archivo
  0x1d, // separador de grupo
  0x1e, // separador de registro
  0x1f, // separador de unidad
  0x20, // espacio
  0x85, // NEL (next line)
  0xa0, // espacio duro (nbsp) — el que entra al copiar desde Word
  0x1680, // OGHAM SPACE MARK
  0x2000, // EN QUAD
  0x2001, // EM QUAD
  0x2002, // EN SPACE
  0x2003, // EM SPACE
  0x2004, // THREE-PER-EM SPACE
  0x2005, // FOUR-PER-EM SPACE
  0x2006, // SIX-PER-EM SPACE
  0x2007, // FIGURE SPACE
  0x2008, // PUNCTUATION SPACE
  0x2009, // THIN SPACE
  0x200a, // HAIR SPACE
  0x2028, // LINE SEPARATOR
  0x2029, // PARAGRAPH SEPARATOR
  0x202f, // NARROW NO-BREAK SPACE
  0x205f, // MEDIUM MATHEMATICAL SPACE
  0x3000, // IDEOGRAPHIC SPACE
])

/** Cuantos code points recorta el corrector. Publico para que un test pueda
 * afirmar el numero sin re-derivar el set (y para que bajarlo por accidente no
 * pase en silencio: recortar menos ENDURECE la correccion). */
export const CANTIDAD_BLANCOS_RECORTADOS = CODIGOS_BLANCOS.size

/**
 * Recorta los blancos del final de una linea. `str.rstrip()`, O(n).
 *
 * A mano y no con un regex `[...]+$`: **ese regex no tiene ancla izquierda**,
 * asi que ante una corrida larga de blancos que NO termina la linea el motor
 * reintenta desde cada indice y el costo es O(n²). Medido en este repo, sobre
 * una sola linea y en el main thread del navegador, despues de Pyodide y FUERA
 * del watchdog de 5 s:
 *
 *   `"x" + " "*50000 + "y"`  → 1.996 ms
 *   `" "*200000 + "fin"`     → 32.184 ms
 *
 * Un `s += " "` dentro de un bucle —el error clasico del alumno— congelaba el
 * tab 32 segundos, multiplicado por cada caso de prueba. Con este recorte los
 * dos casos bajan a 0,1 ms. El `str.rstrip()` de Python siempre fue O(n); la
 * asimetria era nuestra.
 */
function recortarFinal(linea: string): string {
  let fin = linea.length
  while (fin > 0 && CODIGOS_BLANCOS.has(linea.charCodeAt(fin - 1))) fin--
  return fin === linea.length ? linea : linea.slice(0, fin)
}

/** Recorta los blancos del principio de una linea. `str.lstrip()`, O(n).
 * El regex equivalente (`^[...]+`) sí estaba anclado y no backtrackeaba, pero
 * se hace igual a mano: una sola forma de recortar, un solo set que mantener. */
function recortarInicio(linea: string): string {
  let ini = 0
  while (ini < linea.length && CODIGOS_BLANCOS.has(linea.charCodeAt(ini))) ini++
  return ini === 0 ? linea : linea.slice(ini)
}

/**
 * Normaliza una salida para compararla. Funcion PURA.
 *
 * 1. Unifica los fines de linea (`\r\n` y `\r` sueltos) a `\n`.
 * 2. Recorta los blancos al final de CADA linea.
 * 3. Descarta las lineas en blanco de los DOS extremos.
 * 4. Recorta los blancos iniciales de la PRIMERA linea.
 */
export function normalizarSalida(texto: string): string {
  const lineas = texto.replace(/\r\n?/g, "\n").split("\n").map(recortarFinal)
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
    lineas[0] = recortarInicio(lineas[0] ?? "")
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
