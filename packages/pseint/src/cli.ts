/**
 * Punto de entrada del sandbox del servidor (HU-030, C07). La imagen corre
 * `node /opt/pseint/run.js` (este archivo empaquetado con `pnpm build`) con el
 * fuente en la variable `SRC` y la entrada por stdin, igual que Python y Java.
 * Es el mismo intérprete que corre en el navegador.
 *
 * Códigos de salida (los lee `docker_runner`):
 *   0   terminó bien;
 *   101 error de sintaxis ("no compila", como Java);
 *   1   error de ejecución o límite de pasos.
 * La salida del algoritmo va a stdout; el mensaje de error, a stderr.
 */

import { pathToFileURL } from "node:url"
import { ejecutarConEntrada } from "./index"

export interface ResultadoCli {
  stdout: string
  stderr: string
  codigo: number
}

export const CODIGO_NO_COMPILA = 101

export async function correrCli(fuente: string, stdin: string): Promise<ResultadoCli> {
  const r = await ejecutarConEntrada(fuente, stdin)
  if (r.estado === "ok") return { stdout: r.salida, stderr: "", codigo: 0 }
  const stderr = `Línea ${r.error!.linea}: ${r.error!.mensaje}\n`
  if (r.estado === "error_sintaxis") return { stdout: "", stderr, codigo: CODIGO_NO_COMPILA }
  return { stdout: r.salida, stderr, codigo: 1 }
}

async function leerStdin(): Promise<string> {
  const partes: Buffer[] = []
  for await (const parte of process.stdin) partes.push(parte as Buffer)
  return Buffer.concat(partes).toString("utf-8")
}

async function main(): Promise<void> {
  const r = await correrCli(process.env.SRC ?? "", await leerStdin())
  process.stdout.write(r.stdout)
  process.stderr.write(r.stderr)
  process.exitCode = r.codigo
}

const esProgramaPrincipal =
  typeof process !== "undefined" &&
  process.argv[1] !== undefined &&
  import.meta.url === pathToFileURL(process.argv[1]).href

if (esProgramaPrincipal) void main()
