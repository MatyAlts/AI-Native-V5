/**
 * Arnes de ejecucion Python del editor del alumno — lado TypeScript.
 *
 * El Python NO vive aca: vive en `arnes.py`, y este modulo lo importa como
 * texto. Un solo archivo, un solo texto, dos interpretes — Pyodide en el
 * navegador y CPython en `apps/web-student/tests/unit/test_arnes_python.py`.
 * No hay copia que mantener sincronizada porque no hay copia.
 *
 * Antes eran cuatro literales de plantilla adentro de `CodeEditor.tsx`. El
 * override de `input()`, el watchdog por opcode y el runner de casos publicos
 * —lo que decide si al alumno le corta la corrida o si su `input()` le
 * devuelve lo que escribio— no tenian un solo test, y no por olvido: para
 * llegar habia que montar el componente entero con Pyodide real.
 */
import ARNES_PYTHON from "./arnes.py?raw"

export { ARNES_PYTHON }

/**
 * Presupuesto de ejecucion del codigo del alumno, en segundos.
 *
 * Se PARSEA del `.py` en vez de declararse de este lado: si estuviera escrito
 * en los dos, el dia que alguien cambie uno el otro miente en silencio (el
 * numero solo aparece en un mensaje de error). El regex esta anclado a la
 * linea completa y tira si no encuentra exactamente una — un rename del
 * simbolo rompe el import, no el runtime del alumno.
 *
 * IMPORTANTE: es presupuesto de COMPUTO, no de tiempo real. Mientras el
 * programa espera input() (tiempo humano) el watchdog se pausa por completo y
 * al volver arranca un presupuesto fresco (ver `__tutor_input` en el `.py`).
 */
export const TIMEOUT_EJECUCION_SEGUNDOS: number = (() => {
  const matches = [...ARNES_PYTHON.matchAll(/^_TUTOR_TIMEOUT_SECONDS = ([0-9]+(?:\.[0-9]+)?)$/gm)]
  if (matches.length !== 1) {
    throw new Error(
      `arnes.py deberia declarar _TUTOR_TIMEOUT_SECONDS exactamente una vez; se encontraron ${matches.length}`,
    )
  }
  return Number(matches[0]?.[1])
})()
