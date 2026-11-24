/**
 * Aceptación HU-030 (orquestador, antes de construir; el constructor no la
 * modifica).
 *
 * C07  El punto de entrada del sandbox corre el mismo intérprete que el
 *      navegador y respeta el contrato de códigos de salida que lee
 *      `docker_runner`: 0 bien, 101 error de sintaxis, 1 error de ejecución
 *      o límite. La salida del algoritmo va a stdout y el error a stderr.
 */
import { describe, expect, it } from "vitest"
import { correrCli } from "../src/cli"
import { ejecutarConEntrada } from "../src/index"

const DOBLE = `Algoritmo doble
	Definir n Como Entero
	Leer n
	Escribir n * 2
FinAlgoritmo
`

describe("C07 punto de entrada del servidor", () => {
  it("bien: código 0 y la misma salida que el navegador", async () => {
    const cli = await correrCli(DOBLE, "21\n")
    const nav = await ejecutarConEntrada(DOBLE, "21\n")
    expect(cli.codigo).toBe(0)
    expect(cli.stdout).toBe("42\n")
    expect(cli.stdout).toBe(nav.salida)
    expect(cli.stderr).toBe("")
  })

  it("error de sintaxis: código 101 y nada en stdout", async () => {
    const cli = await correrCli("Algoritmo roto\n\tEscribir \"hola\nFinAlgoritmo\n", "")
    expect(cli.codigo).toBe(101)
    expect(cli.stdout).toBe("")
    expect(cli.stderr).toMatch(/2/)
  })

  it("error de ejecución: código 1, lo escrito antes queda en stdout", async () => {
    const fuente = `Algoritmo divcero
	Definir r Como Real
	Escribir "antes"
	r <- 5 / 0
FinAlgoritmo
`
    const cli = await correrCli(fuente, "")
    expect(cli.codigo).toBe(1)
    expect(cli.stdout).toBe("antes\n")
    expect(cli.stderr.length).toBeGreaterThan(0)
  })

  it("bucle infinito: código 1, no se cuelga", async () => {
    const cli = await correrCli("Algoritmo inf\n\tMientras Verdadero Hacer\n\tFinMientras\nFinAlgoritmo\n", "")
    expect(cli.codigo).toBe(1)
  })
})
