/**
 * Tope de salida del intérprete (fix sobre HU-030).
 *
 * Medido el 24/11/2026 en el editor real: un ciclo infinito con `Escribir`
 * llegaba al límite de pasos habiendo escrito ~11 MB, tardaba 78 s con la
 * pestaña congelada y mandaba los 11 MB enteros al CTR. Con el tope corta en
 * cuanto la salida pasa de `MAX_SALIDA_POR_DEFECTO` caracteres.
 *
 * T01  Un ciclo infinito con `Escribir` corta por salida, con la
 *      línea del `Escribir` y un mensaje en castellano.
 * T02  Se escribe exactamente lo que entra: ni un carácter más que el tope,
 *      y lo que recibe la consola es lo mismo que `salida`.
 * T03  Un algoritmo que escribe justo el tope no se corta.
 * T04  El ciclo infinito SIN `Escribir` sigue cortando por pasos (no cambia).
 * T05  El paso a paso termina igual que `ejecutar` (mismo resultado).
 * T06  El punto de entrada del servidor sale con código 1 y stdout acotado.
 */
import { describe, expect, it } from "vitest"
import { correrCli } from "../src/cli"
import { crearDepurador } from "../src/depurador"
import { MAX_SALIDA_POR_DEFECTO, ejecutar, ejecutarConEntrada } from "../src/index"

const INFINITO_ESCRIBE = `Algoritmo b
	Mientras Verdadero Hacer
		Escribir "hola mundo"
	FinMientras
FinAlgoritmo
`

const INFINITO_MUDO = `Algoritmo b
	Definir x Como Entero
	x <- 0
	Mientras Verdadero Hacer
		x <- x + 1
	FinMientras
FinAlgoritmo
`

describe("T01-T02 ciclo infinito con Escribir", () => {
  it("corta por salida, en la línea del Escribir y con mensaje claro", async () => {
    const consola: string[] = []
    const r = await ejecutar(INFINITO_ESCRIBE, { leer: () => "", escribir: (t) => consola.push(t) })
    expect(r.estado).toBe("limite_excedido")
    expect(r.error?.linea).toBe(3)
    expect(r.error?.mensaje).toMatch(/escribió más de 100\.000 caracteres/)
    // Sin el tope eran 1.000.000 de escrituras; con el tope, ~9.100.
    expect(consola.length).toBeLessThan(10_000)
  })

  it("escribe exactamente hasta el tope y la consola recibe lo mismo que salida", async () => {
    const consola: string[] = []
    const r = await ejecutar(INFINITO_ESCRIBE, { leer: () => "", escribir: (t) => consola.push(t) })
    expect(r.salida.length).toBe(MAX_SALIDA_POR_DEFECTO)
    expect(consola.join("")).toBe(r.salida)
  })

  it("Probar (ejecutarConEntrada) también corta", async () => {
    const r = await ejecutarConEntrada(INFINITO_ESCRIBE, "")
    expect(r.estado).toBe("limite_excedido")
    expect(r.salida.length).toBe(MAX_SALIDA_POR_DEFECTO)
  })
})

describe("T03 justo en el tope", () => {
  it("un algoritmo que escribe exactamente el tope termina bien", async () => {
    // 10.000 líneas de "123456789\n" = 100.000 caracteres.
    const fuente = `Algoritmo justo
	Definir i Como Entero
	Para i <- 1 Hasta 10000 Hacer
		Escribir "123456789"
	FinPara
FinAlgoritmo
`
    const r = await ejecutarConEntrada(fuente, "")
    expect(r.estado).toBe("ok")
    expect(r.salida.length).toBe(MAX_SALIDA_POR_DEFECTO)
  })

  it("un carácter más ya corta", async () => {
    const fuente = `Algoritmo pasado
	Definir i Como Entero
	Para i <- 1 Hasta 10000 Hacer
		Escribir "123456789"
	FinPara
	Escribir "x"
FinAlgoritmo
`
    const r = await ejecutarConEntrada(fuente, "")
    expect(r.estado).toBe("limite_excedido")
    expect(r.error?.linea).toBe(6)
    expect(r.salida.length).toBe(MAX_SALIDA_POR_DEFECTO)
  })
})

describe("T04 sin Escribir no cambia nada", () => {
  it("sigue cortando por pasos con el mensaje de instrucciones", async () => {
    const r = await ejecutarConEntrada(INFINITO_MUDO, "")
    expect(r.estado).toBe("limite_excedido")
    expect(r.error?.mensaje).toMatch(/instrucciones/)
  })
})

describe("T05 paso a paso", () => {
  it("Continuar sobre el ciclo infinito termina igual que ejecutar", async () => {
    const d = crearDepurador(INFINITO_ESCRIBE, {
      leer: () => "",
      escribir: () => {},
      maxPasos: 10_000_000,
    })
    expect(d.ok).toBe(true)
    if (!d.ok) return
    const fin = await d.depurador.continuar()
    const directo = await ejecutarConEntrada(INFINITO_ESCRIBE, "")
    expect(fin.resultado).toEqual(directo)
  })
})

describe("T06 servidor", () => {
  it("código 1 y stdout acotado al tope", async () => {
    const cli = await correrCli(INFINITO_ESCRIBE, "")
    expect(cli.codigo).toBe(1)
    expect(cli.stdout.length).toBe(MAX_SALIDA_POR_DEFECTO)
    expect(cli.stderr).toMatch(/100\.000 caracteres/)
  })
})
