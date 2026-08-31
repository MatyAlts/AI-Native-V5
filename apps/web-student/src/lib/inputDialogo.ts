/**
 * El texto del diálogo con el que `input()` le pide un dato al alumno.
 *
 * Se saca a una función pura porque la decisión vivía enterrada adentro del
 * `useEffect` que carga Pyodide, dentro de un closure que sólo existe después
 * de bajar 30 MB de CDN. Para ejercitarla había que montar el editor entero con
 * Monaco y Pyodide reales — o sea que nadie la ejercitó nunca, y por eso el bug
 * de abajo vivió meses en producción.
 *
 * EL BUG (QA 2026-08-31)
 * ----------------------
 * Acá había un `||`:
 *
 *     const guia = inline || outputBufferRef.current.trim()
 *
 * Un `||` es una ALTERNATIVA, no una suma. Y `inline` es el texto que el alumno
 * le pasa a `input("...")` — que TODO alumno pasa; nadie escribe `input()`
 * pelado. Así que `inline` siempre ganaba el cortocircuito y el output pendiente
 * NO SE MOSTRABA NUNCA. La mitigación estaba escrita, era la correcta, y sólo
 * funcionaba en el único caso que no ocurre.
 *
 * POR QUÉ IMPORTA
 * ---------------
 * `window.prompt` es SÍNCRONO: congela el event loop, React no repinta el panel
 * SALIDA, y todo lo que el programa imprimió queda invisible hasta que la
 * corrida termina. Sobre el patrón que enseña la cátedra:
 *
 *     while True:
 *         try:
 *             nombre = input("Ingrese su nombre (Solo letras): ")
 *             if nombre == "":
 *                 raise ValueError("Error: El nombre no puede quedar vacio.")
 *             break
 *         except ValueError as e:
 *             print(e)
 *             continue
 *
 * el `try/except` corría PERFECTO y el alumno no veía un solo mensaje. Se
 * reportó como "pide todos los inputs de una y se saltea el try", que es
 * exactamente cómo se ve desde afuera.
 */

/** Lo que se le muestra al alumno cuando el programa no dijo nada. */
export const MENSAJE_SIN_GUIA = "El programa pide un dato de entrada (input):"

const PIE = "↳ Ingresá el dato que pide el programa:"

/**
 * Arma el texto del diálogo.
 *
 * @param pendiente Lo que el programa imprimió DESDE EL ÚLTIMO input. No todo
 *   el buffer: repetir la salida entera en cada diálogo sepulta el mensaje que
 *   importa —el `print(e)` de esta vuelta del bucle— bajo las diez iteraciones
 *   anteriores.
 * @param inline El texto que viajó como argumento de `input("...")`.
 *
 * Los dos se CONCATENAN, en ese orden: primero lo que el programa dijo, después
 * lo que está pidiendo. Es el orden en que aparecerían en una consola real.
 */
export function armarMensajeDeInput(pendiente: string, inline: string): string {
  const partes = [pendiente.trim(), inline.trim()].filter((t) => t.length > 0)
  if (partes.length === 0) return MENSAJE_SIN_GUIA
  return `${partes.join("\n\n")}\n\n${PIE}`
}
