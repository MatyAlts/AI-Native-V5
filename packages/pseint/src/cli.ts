/**
 * Punto de entrada del sandbox del servidor (HU-030, C07). ESQUELETO DE
 * ACEPTACIÓN. La imagen corre `node run.js` con el fuente en la variable `SRC`
 * y la entrada por stdin, igual que Python y Java.
 *
 * Códigos de salida (los lee `docker_runner`):
 *   0   terminó bien;
 *   101 error de sintaxis ("no compila", como Java);
 *   1   error de ejecución o límite de pasos.
 * La salida del algoritmo va a stdout; el mensaje de error, a stderr.
 */

export interface ResultadoCli {
  stdout: string
  stderr: string
  codigo: number
}

export async function correrCli(_fuente: string, _stdin: string): Promise<ResultadoCli> {
  return { stdout: "", stderr: "", codigo: 0 }
}
