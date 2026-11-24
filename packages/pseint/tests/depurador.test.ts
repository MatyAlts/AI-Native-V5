/**
 * Aceptación HU-032 (orquestador, antes de construir; el constructor no la
 * modifica). Juani: "empeza con la proxima vos tranquilo" (24/11), con la
 * misma delegación de criterios y aceptación que en HU-031.
 *
 * C01  Paso a paso: cada paso ejecuta una instrucción y dice cuál sigue.
 * C02  Las variables del ámbito se ven con su valor en cada momento.
 * C03  La prueba de escritorio tiene una fila por paso con los valores.
 * C04  `Leer` pide el dato en su paso; los bloques que no se ejecutan no se pisan.
 * C05  Entrar a una función cambia el ámbito y vuelve al terminar.
 * C06  Llegar al final paso a paso da EXACTAMENTE el mismo resultado que
 *      ejecutar de una (todo el corpus de paridad).
 * N01  Un bucle infinito en "continuar" corta por límite de pasos.
 * N02  Con un error de sintaxis no arranca y dice la línea.
 */
import { readFileSync, readdirSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { type Depurador, crearDepurador } from "../src/depurador"
import { ejecutarConEntrada, lineasDeEntrada } from "../src/index"

function depurar(
  fuente: string,
  entradas: string[] = [],
  escritos: string[] = [],
  maxPasos?: number,
): Depurador {
  const cola = [...entradas]
  const r = crearDepurador(fuente, {
    leer: () => cola.shift() ?? "",
    escribir: (t) => escritos.push(t),
    ...(maxPasos ? { maxPasos } : {}),
  })
  expect(r.ok, JSON.stringify(r)).toBe(true)
  if (!r.ok) throw new Error("sin depurador")
  return r.depurador
}

async function lineasRecorridas(d: Depurador, tope = 500): Promise<number[]> {
  const lineas: number[] = []
  let e = d.estado()
  while (!e.terminado && lineas.length < tope) {
    lineas.push(e.linea!)
    e = await d.paso()
  }
  return lineas
}

const valor = (d: Depurador, nombre: string) =>
  d.estado().variables.find((v) => v.nombre === nombre)?.valor

const DOBLE = `Algoritmo doble
	Definir n Como Entero
	Escribir "Ingrese un numero:"
	Leer n
	Escribir "El doble es ", n * 2
FinAlgoritmo
`

describe("C01/C02/C04 paso a paso", () => {
  it("arranca en la primera instrucción y avanza de a una", async () => {
    const d = depurar(DOBLE, ["21"])
    expect(d.estado()).toMatchObject({
      linea: 2,
      ambito: "doble",
      terminado: false,
      resultado: null,
    })
    expect((await d.paso()).linea).toBe(3)
    expect(valor(d, "n")).toBe("")
    expect((await d.paso()).linea).toBe(4)
    expect((await d.paso()).linea).toBe(5)
    expect(valor(d, "n")).toBe("21")
    const fin = await d.paso()
    expect(fin.terminado).toBe(true)
    expect(fin.linea).toBeNull()
    expect(fin.resultado).toEqual({
      estado: "ok",
      salida: "Ingrese un numero:\nEl doble es 42\n",
      error: null,
    })
    // Ya terminó: otro paso no cambia nada.
    expect((await d.paso()).resultado).toEqual(fin.resultado)
  })

  it("Leer pide el dato recién en su paso y la salida previa ya se escribió", async () => {
    const escritos: string[] = []
    let pedidos = 0
    const r = crearDepurador(DOBLE, {
      leer: () => {
        pedidos++
        expect(escritos.join("")).toContain("Ingrese un numero:")
        return "5"
      },
      escribir: (t) => escritos.push(t),
    })
    expect(r.ok).toBe(true)
    if (!r.ok) return
    await r.depurador.paso()
    await r.depurador.paso()
    expect(pedidos).toBe(0)
    await r.depurador.paso()
    expect(pedidos).toBe(1)
  })

  it("el Si evalúa su condición en un paso y saltea la rama que no corre", async () => {
    const d = depurar(`Algoritmo signo
	Definir x Como Entero
	x <- -3
	Si x > 0 Entonces
		Escribir "positivo"
	SiNo
		Escribir "no positivo"
	FinSi
	Escribir "fin"
FinAlgoritmo
`)
    expect(await lineasRecorridas(d)).toEqual([2, 3, 4, 7, 9])
  })

  it("el Mientras evalúa la condición en cada vuelta", async () => {
    const d = depurar(`Algoritmo cuenta
	Definir i Como Entero
	i <- 1
	Mientras i <= 3 Hacer
		i <- i + 1
	FinMientras
	Escribir i
FinAlgoritmo
`)
    expect(await lineasRecorridas(d)).toEqual([2, 3, 4, 5, 4, 5, 4, 5, 4, 7])
  })

  it("el Para cuenta su cabecera una vez por vuelta y muestra la variable", async () => {
    const d = depurar(`Algoritmo vueltas
	Definir i, s Como Entero
	s <- 0
	Para i <- 1 Hasta 2 Hacer
		s <- s + i
	FinPara
	Escribir s
FinAlgoritmo
`)
    await d.paso() // Definir
    await d.paso() // s <- 0
    await d.paso() // cabecera: i <- 1
    expect(valor(d, "i")).toBe("1")
    expect(d.estado().linea).toBe(5)
    expect(await lineasRecorridas(d)).toEqual([5, 4, 5, 4, 7])
  })

  it("los arreglos se ven con todos sus valores", async () => {
    const d = depurar(`Algoritmo arr
	Definir v Como Entero
	Dimension v[3]
	v[1] <- 4
	v[3] <- 7
	Escribir v[1]
FinAlgoritmo
`)
    await d.continuar()
    // El elemento sin asignar se ve vacío, en su lugar.
    expect(d.filas().length).toBeGreaterThan(0)
    expect(d.filas().at(-1)?.valores.v).toBe("[4, , 7]")
  })
})

describe("C05 funciones y subprocesos", () => {
  it("entra a la función, cambia el ámbito y vuelve", async () => {
    const d = depurar(`Funcion r <- doble(x)
	Definir r Como Entero
	r <- x * 2
FinFuncion

Algoritmo principal
	Definir a Como Entero
	a <- doble(5)
	Escribir a
FinAlgoritmo
`)
    expect(d.estado()).toMatchObject({ linea: 7, ambito: "principal" })
    await d.paso() // Definir a
    expect(d.estado().linea).toBe(8)
    await d.paso() // entra a doble
    expect(d.estado()).toMatchObject({ ambito: "doble", linea: 2 })
    expect(valor(d, "x")).toBe("5")
    await d.paso()
    await d.paso()
    expect(d.estado().ambito).toBe("principal")
    expect(valor(d, "a")).toBe("10")
  })
})

describe("C03 prueba de escritorio", () => {
  it("una fila por paso con los valores después de cada uno", async () => {
    const d = depurar(`Algoritmo acumula
	Definir i, s Como Entero
	s <- 0
	Para i <- 1 Hasta 3 Hacer
		s <- s + i
	FinPara
	Escribir "s = ", s
FinAlgoritmo
`)
    await d.continuar()
    const filas = d.filas()
    expect(filas.map((f) => f.paso)).toEqual(filas.map((_, i) => i + 1))
    const sumas = filas.filter((f) => f.linea === 5).map((f) => [f.valores.i, f.valores.s])
    expect(sumas).toEqual([
      ["1", "1"],
      ["2", "3"],
      ["3", "6"],
    ])
    const ultima = filas.at(-1)!
    expect(ultima.linea).toBe(7)
    expect(ultima.salida).toBe("s = 6\n")
    expect(filas.filter((f) => f.salida !== "").length).toBe(1)
  })
})

describe("C06 paridad con la ejecución normal", () => {
  const dir = join(__dirname, "paridad")
  const esperados = JSON.parse(readFileSync(join(dir, "esperados.json"), "utf-8")) as Record<
    string,
    { tipo: string }
  >
  const casos = readdirSync(join(dir, "casos"))
    .filter((f) => f.endsWith(".psc"))
    .map((f) => f.replace(/\.psc$/, ""))
    .filter((n) => esperados[n]?.tipo !== "error_sintaxis")
    .sort()

  for (const nombre of casos) {
    it(`${nombre}: de a un paso llega al mismo resultado`, async () => {
      const fuente = readFileSync(join(dir, "casos", `${nombre}.psc`), "utf-8")
      let entrada = ""
      try {
        entrada = readFileSync(join(dir, "casos", `${nombre}.entrada`), "utf-8")
      } catch {
        entrada = ""
      }
      const normal = await ejecutarConEntrada(fuente, entrada)
      const d = depurar(fuente, lineasDeEntrada(entrada))
      let e = d.estado()
      let vueltas = 0
      while (!e.terminado && vueltas++ < 100_000) e = await d.paso()
      expect(e.terminado, nombre).toBe(true)
      expect(e.resultado?.estado, nombre).toBe(normal.estado)
      expect(e.resultado?.salida, nombre).toBe(normal.salida)
      expect(e.resultado?.error?.linea ?? null, nombre).toBe(normal.error?.linea ?? null)
      expect(d.filas().length, nombre).toBeGreaterThan(0)
    })
  }
})

describe("N01/N02", () => {
  it("continuar con un bucle infinito corta por límite de pasos", async () => {
    const d = depurar(
      "Algoritmo inf\n\tMientras Verdadero Hacer\n\tFinMientras\nFinAlgoritmo\n",
      [],
      [],
      5_000,
    )
    const inicio = Date.now()
    const e = await d.continuar()
    expect(Date.now() - inicio).toBeLessThan(5_000)
    expect(e.terminado).toBe(true)
    expect(e.resultado?.estado).toBe("limite_excedido")
  })

  it("con un error de sintaxis no arranca y dice la línea", () => {
    const r = crearDepurador('Algoritmo roto\n\tEscribir "hola\nFinAlgoritmo\n', { leer: () => "" })
    expect(r.ok).toBe(false)
    if (r.ok) return
    expect(r.error.linea).toBe(2)
  })
})
