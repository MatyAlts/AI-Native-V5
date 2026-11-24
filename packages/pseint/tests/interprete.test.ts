/**
 * Aceptación HU-030 (orquestador, antes de construir; el constructor no la
 * modifica). Criterios acordados con Juani el 24/11/2026.
 *
 * C03  `Leer` interactivo: se pide un valor por vez, en orden, y lo escrito
 *      antes de cada `Leer` ya llegó a la consola cuando se pide el dato.
 * C04  Un error de sintaxis no ejecuta nada y da un mensaje en castellano con
 *      la línea.
 * C09  El runtime que va al CTR se arma con `VERSION`.
 * N02  Un bucle infinito no cuelga: corta por pasos con un aviso.
 */
import { describe, expect, it } from "vitest"
import { MAX_PASOS_POR_DEFECTO, VERSION, ejecutar, ejecutarConEntrada, verificarSintaxis } from "../src/index"

const DOBLE = `Algoritmo doble
	Definir n Como Entero
	Escribir "Ingrese un numero:"
	Leer n
	Escribir "El doble es ", n * 2
FinAlgoritmo
`

const DOS_LECTURAS = `Algoritmo dos
	Definir p, q Como Entero
	Escribir "Primero:"
	Leer p
	Escribir "Segundo:"
	Leer q
	Escribir p - q
FinAlgoritmo
`

const SIN_FINSI = `Algoritmo roto
	Escribir "no tiene que aparecer"
	Si 3 > 2 Entonces
		Escribir "mayor"
FinAlgoritmo
`

const INFINITO = `Algoritmo infinito
	Definir i Como Entero
	i <- 0
	Mientras Verdadero Hacer
		i <- i + 1
	FinMientras
FinAlgoritmo
`

describe("C03 Leer interactivo", () => {
  it("pide cada valor en orden y escribe antes de pedir", async () => {
    const eventos: string[] = []
    const valores = ["10", "4"]
    const r = await ejecutar(DOS_LECTURAS, {
      leer: async () => {
        eventos.push("leer")
        return valores.shift() ?? ""
      },
      escribir: (t) => eventos.push(`escribir:${t}`),
    })
    expect(r.estado).toBe("ok")
    expect(r.salida).toBe("Primero:\nSegundo:\n6\n")
    const primerLeer = eventos.indexOf("leer")
    const segundoLeer = eventos.indexOf("leer", primerLeer + 1)
    expect(primerLeer).toBeGreaterThan(-1)
    expect(segundoLeer).toBeGreaterThan(primerLeer)
    expect(eventos.slice(0, primerLeer).join("")).toContain("Primero:")
    expect(eventos.slice(primerLeer, segundoLeer).join("")).toContain("Segundo:")
    expect(eventos.slice(primerLeer, segundoLeer).join("")).not.toContain("6")
  })

  it("acepta un leer sincrónico", async () => {
    const r = await ejecutar(DOBLE, { leer: () => "21" })
    expect(r).toEqual({ estado: "ok", salida: "Ingrese un numero:\nEl doble es 42\n", error: null })
  })

  it("sin entrada suficiente, la ejecución con entrada por adelantado da error de ejecución", async () => {
    const r = await ejecutarConEntrada(DOS_LECTURAS, "10\n")
    expect(r.estado).toBe("error_ejecucion")
    expect(r.salida).toBe("Primero:\nSegundo:\n")
    expect(r.error?.linea).toBe(6)
  })
})

describe("C04 errores de sintaxis", () => {
  it("no ejecuta nada ni pide datos", async () => {
    let pidio = false
    let escribio = ""
    const r = await ejecutar(SIN_FINSI, {
      leer: () => {
        pidio = true
        return ""
      },
      escribir: (t) => {
        escribio += t
      },
    })
    expect(r.estado).toBe("error_sintaxis")
    expect(r.salida).toBe("")
    expect(escribio).toBe("")
    expect(pidio).toBe(false)
  })

  it("verificarSintaxis da la línea y un mensaje en castellano", () => {
    const errores = verificarSintaxis(SIN_FINSI)
    expect(errores.length).toBeGreaterThan(0)
    expect(errores[0]!.linea).toBe(3)
    const m = errores[0]!.mensaje
    expect(m).toMatch(/[a-záéíóúñ]{3,}/i)
    expect(m).not.toMatch(/unexpected|expected|token|undefined|null|NaN|Error:/)
  })

  it("un algoritmo correcto no tiene errores", () => {
    expect(verificarSintaxis(DOBLE)).toEqual([])
  })
})

describe("N02 bucle infinito", () => {
  it("corta por límite de pasos, sin colgarse, con aviso en castellano", async () => {
    const inicio = Date.now()
    const r = await ejecutar(INFINITO, { leer: () => "", maxPasos: 50_000 })
    expect(Date.now() - inicio).toBeLessThan(5_000)
    expect(r.estado).toBe("limite_excedido")
    expect(r.error?.mensaje).toMatch(/[a-záéíóúñ]{3,}/i)
  })

  it("el límite por defecto existe y también corta", async () => {
    expect(MAX_PASOS_POR_DEFECTO).toBeGreaterThan(0)
    expect(MAX_PASOS_POR_DEFECTO).toBeLessThanOrEqual(10_000_000)
    const r = await ejecutarConEntrada(INFINITO, "")
    expect(r.estado).toBe("limite_excedido")
  })

  it("un algoritmo largo pero finito no se corta", async () => {
    const largo = `Algoritmo largo
	Definir i, s Como Entero
	s <- 0
	Para i <- 1 Hasta 20000 Hacer
		s <- s + i
	FinPara
	Escribir s
FinAlgoritmo
`
    const r = await ejecutarConEntrada(largo, "")
    expect(r).toEqual({ estado: "ok", salida: "200010000\n", error: null })
  })
})

describe("C09 versión del intérprete", () => {
  it("VERSION es semver y no es el esqueleto", () => {
    expect(VERSION).toMatch(/^\d+\.\d+\.\d+$/)
    expect(VERSION).not.toBe("0.0.0")
  })
})
