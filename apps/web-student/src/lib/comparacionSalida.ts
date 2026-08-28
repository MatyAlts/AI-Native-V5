/**
 * JAVA-1: comparacion de la salida del programa contra la salida esperada.
 *
 * La implementacion NO vive aca. Vive en
 * `packages/contracts/src/comparacionSalida.ts` (`@platform/contracts/comparacion-salida`)
 * y este archivo la re-exporta para no tocar los sitios de uso del web-student.
 *
 * Se movio porque los correctores no eran DOS sino TRES: al del alumno (este) y
 * al del servidor (`normalize_output` / `outputs_match` en
 * `apps/execution-service/src/execution_service/services/docker_runner.py`,
 * gemelo obligado en Python) se le sumaba una tercera copia con reglas propias
 * en `apps/web-teacher/src/lib/pyodideRunner.ts` — la de "Probar ejercicio", o
 * sea la pantalla donde el docente valida el ejercicio ANTES de asignarlo a la
 * cohorte. Los dos frontends importan ahora la MISMA funcion; el gemelo Python
 * se verifica contra la tabla compartida `tests/fixtures/paridad-salida.json`,
 * que leen los tres lados.
 *
 * El porqué de cada regla de normalizacion esta en el docstring del modulo
 * canonico. No lo dupliques aca: dos copias del razonamiento se separan igual
 * que dos copias del codigo.
 */

export { normalizarSalida, salidaCoincide } from "@platform/contracts/comparacion-salida"
