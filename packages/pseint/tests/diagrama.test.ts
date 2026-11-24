/**
 * Aceptación HU-031 (orquestador, antes de construir; el constructor no la
 * modifica). Criterios acordados el 24/11/2026 (Juani delegó criterios y
 * aceptación: "arma los criterios y aceptación vos").
 *
 * C02  Cada instrucción tiene su forma (convención de PSeInt) y las ramas y
 *      vueltas están conectadas como en el algoritmo.
 * C04  Con un error de sintaxis no se dibuja nada y se informa la línea.
 * C06  Todos los algoritmos correctos del corpus de paridad se dibujan, sin
 *      cajas superpuestas, dentro del tamaño declarado y siempre igual.
 */
import { readFileSync, readdirSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { type Diagrama, type NodoDiagrama, construirDiagramas } from "../src/diagrama"

function uno(fuente: string): Diagrama {
  const r = construirDiagramas(fuente)
  expect(r.ok, JSON.stringify(r)).toBe(true)
  if (!r.ok) throw new Error("sin diagrama")
  expect(r.diagramas.length).toBeGreaterThanOrEqual(1)
  return r.diagramas[0]!
}

function nodosDe(d: Diagrama, tipo: NodoDiagrama["tipo"]): NodoDiagrama[] {
  return d.nodos.filter((n) => n.tipo === tipo)
}

function salidas(d: Diagrama, id: string) {
  return d.aristas.filter((a) => a.desde === id)
}

function alcanzables(d: Diagrama, desde: string): Set<string> {
  const vistos = new Set<string>([desde])
  const pila = [desde]
  while (pila.length) {
    const id = pila.pop()!
    for (const a of salidas(d, id)) {
      if (!vistos.has(a.hasta)) {
        vistos.add(a.hasta)
        pila.push(a.hasta)
      }
    }
  }
  return vistos
}

/** Propiedades que todo diagrama tiene que cumplir. */
function bienFormado(d: Diagrama, contexto: string) {
  const inicio = nodosDe(d, "inicio")
  const fin = nodosDe(d, "fin")
  expect(inicio.length, `${contexto}: un inicio`).toBe(1)
  expect(fin.length, `${contexto}: un fin`).toBe(1)
  const ids = new Set(d.nodos.map((n) => n.id))
  expect(ids.size, `${contexto}: ids únicos`).toBe(d.nodos.length)
  for (const a of d.aristas) {
    expect(ids.has(a.desde) && ids.has(a.hasta), `${contexto}: arista a un nodo que no existe`).toBe(true)
    expect(a.puntos.length, `${contexto}: arista sin trazo`).toBeGreaterThanOrEqual(2)
    for (const p of a.puntos) {
      expect(p.x >= 0 && p.y >= 0 && p.x <= d.ancho && p.y <= d.alto, `${contexto}: punto fuera`).toBe(true)
    }
  }
  const alcanzados = alcanzables(d, inicio[0]!.id)
  expect(alcanzados.size, `${contexto}: todo nodo se alcanza desde el inicio`).toBe(d.nodos.length)
  for (const n of d.nodos) {
    if (n.tipo !== "fin") expect(salidas(d, n.id).length, `${contexto}: ${n.etiqueta} sin salida`).toBeGreaterThan(0)
    expect(n.ancho > 0 && n.alto > 0, `${contexto}: caja vacía`).toBe(true)
    expect(n.x >= 0 && n.y >= 0 && n.x + n.ancho <= d.ancho && n.y + n.alto <= d.alto, `${contexto}: ${n.etiqueta} fuera`).toBe(
      true,
    )
    expect(n.etiqueta.trim().length, `${contexto}: forma sin texto`).toBeGreaterThan(0)
  }
  // Sin cajas superpuestas.
  for (let i = 0; i < d.nodos.length; i++) {
    for (let j = i + 1; j < d.nodos.length; j++) {
      const a = d.nodos[i]!
      const b = d.nodos[j]!
      const separadas = a.x + a.ancho <= b.x || b.x + b.ancho <= a.x || a.y + a.alto <= b.y || b.y + b.alto <= a.y
      expect(separadas, `${contexto}: "${a.etiqueta}" se superpone con "${b.etiqueta}"`).toBe(true)
    }
  }
}

describe("C02 formas y conexiones", () => {
  it("secuencial: inicio, Definir, Leer, asignación, Escribir y fin, en orden", () => {
    const d = uno(`Algoritmo doble
	Definir n Como Entero
	Leer n
	n <- n * 2
	Escribir "El doble es ", n
FinAlgoritmo
`)
    bienFormado(d, "secuencial")
    expect(d.nombre).toBe("doble")
    const tipos = d.nodos.map((n) => n.tipo)
    expect(tipos).toEqual(["inicio", "proceso", "entrada", "proceso", "salida", "fin"])
    const leer = nodosDe(d, "entrada")[0]!
    expect(leer.etiqueta).toContain("n")
    expect(leer.linea).toBe(3)
    expect(nodosDe(d, "salida")[0]!.etiqueta).toContain("El doble es")
    expect(d.aristas.length).toBe(5)
  })

  it("Si con SiNo: un rombo con salidas V y F que se vuelven a unir", () => {
    const d = uno(`Algoritmo paridad
	Definir n Como Entero
	Leer n
	Si n MOD 2 = 0 Entonces
		Escribir "par"
	SiNo
		Escribir "impar"
	FinSi
	Escribir "fin"
FinAlgoritmo
`)
    bienFormado(d, "si")
    const rombo = nodosDe(d, "decision")[0]!
    expect(rombo.etiqueta).toContain("MOD")
    const s = salidas(d, rombo.id)
    expect(s.map((a) => a.etiqueta).sort()).toEqual(["F", "V"])
    const par = d.nodos.find((n) => n.etiqueta.includes('"par"'))!
    const impar = d.nodos.find((n) => n.etiqueta.includes('"impar"'))!
    expect(s.find((a) => a.etiqueta === "V")!.hasta).toBe(par.id)
    expect(s.find((a) => a.etiqueta === "F")!.hasta).toBe(impar.id)
    // Las dos ramas llegan al mismo "fin" del texto.
    const despues = d.nodos.find((n) => n.etiqueta.includes('"fin"'))!
    expect(alcanzables(d, par.id).has(despues.id)).toBe(true)
    expect(alcanzables(d, impar.id).has(despues.id)).toBe(true)
  })

  it("Si sin SiNo: la salida F va directo a lo que sigue", () => {
    const d = uno(`Algoritmo positivo
	Definir n Como Entero
	Leer n
	Si n > 0 Entonces
		Escribir "positivo"
	FinSi
	Escribir "listo"
FinAlgoritmo
`)
    bienFormado(d, "si sin sino")
    const rombo = nodosDe(d, "decision")[0]!
    const listo = d.nodos.find((n) => n.etiqueta.includes('"listo"'))!
    expect(salidas(d, rombo.id).find((a) => a.etiqueta === "F")!.hasta).toBe(listo.id)
  })

  it("Mientras: el cuerpo vuelve al rombo y la F sale del bucle", () => {
    const d = uno(`Algoritmo cuenta
	Definir i Como Entero
	i <- 1
	Mientras i <= 5 Hacer
		Escribir i
		i <- i + 1
	FinMientras
	Escribir "fin"
FinAlgoritmo
`)
    bienFormado(d, "mientras")
    const rombo = nodosDe(d, "decision")[0]!
    expect(rombo.etiqueta).toContain("i <= 5")
    const s = salidas(d, rombo.id)
    expect(s.map((a) => a.etiqueta).sort()).toEqual(["F", "V"])
    const incremento = d.nodos.find((n) => n.etiqueta.includes("i + 1"))!
    expect(salidas(d, incremento.id).map((a) => a.hasta)).toContain(rombo.id)
    const fin = d.nodos.find((n) => n.etiqueta.includes('"fin"'))!
    expect(s.find((a) => a.etiqueta === "F")!.hasta).toBe(fin.id)
  })

  it("Repetir: el rombo va al final y vuelve al principio del cuerpo", () => {
    const d = uno(`Algoritmo validar
	Definir n Como Entero
	Repetir
		Leer n
	Hasta Que n > 0
	Escribir n
FinAlgoritmo
`)
    bienFormado(d, "repetir")
    const leer = nodosDe(d, "entrada")[0]!
    const rombo = nodosDe(d, "decision")[0]!
    expect(rombo.y).toBeGreaterThan(leer.y)
    const s = salidas(d, rombo.id)
    // Repetir…Hasta Que: con la condición FALSA se repite.
    expect(s.find((a) => a.etiqueta === "F")!.hasta).toBe(leer.id)
    expect(s.find((a) => a.etiqueta === "V")!.hasta).not.toBe(leer.id)
  })

  it("Para: un hexágono con la cabecera y el cuerpo que vuelve a él", () => {
    const d = uno(`Algoritmo tabla
	Definir i Como Entero
	Para i <- 1 Hasta 10 Con Paso 2 Hacer
		Escribir i
	FinPara
FinAlgoritmo
`)
    bienFormado(d, "para")
    const cab = nodosDe(d, "para")[0]!
    for (const parte of ["i", "1", "10", "2"]) expect(cab.etiqueta).toContain(parte)
    const cuerpo = nodosDe(d, "salida")[0]!
    expect(salidas(d, cuerpo.id).map((a) => a.hasta)).toContain(cab.id)
    expect(salidas(d, cab.id).length).toBe(2)
  })

  it("Segun: una salida por caso más De Otro Modo", () => {
    const d = uno(`Algoritmo dias
	Definir dia Como Entero
	Leer dia
	Segun dia Hacer
		1:
			Escribir "Lunes"
		2, 3:
			Escribir "Martes o miercoles"
		De Otro Modo:
			Escribir "Otro"
	FinSegun
FinAlgoritmo
`)
    bienFormado(d, "segun")
    const rombo = nodosDe(d, "decision")[0]!
    expect(rombo.etiqueta).toContain("dia")
    const etiquetas = salidas(d, rombo.id).map((a) => a.etiqueta)
    expect(etiquetas.length).toBe(3)
    expect(etiquetas).toContain("1")
    expect(etiquetas.some((e) => e.includes("2") && e.includes("3"))).toBe(true)
    expect(etiquetas.some((e) => /otro modo/i.test(e))).toBe(true)
  })

  it("funciones y subprocesos: un diagrama por cada uno, el principal primero", () => {
    const r = construirDiagramas(`Funcion r <- cuadrado(x)
	Definir r Como Real
	r <- x * x
FinFuncion

SubProceso saludar(nombre)
	Escribir "Hola ", nombre
FinSubProceso

Algoritmo principal
	saludar("Ana")
	Escribir cuadrado(3)
FinAlgoritmo
`)
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.diagramas.map((d) => d.nombre)).toEqual(["principal", "cuadrado", "saludar"])
    for (const d of r.diagramas) bienFormado(d, d.nombre)
    const principal = r.diagramas[0]!
    const llamada = nodosDe(principal, "llamada")
    expect(llamada.length).toBe(1)
    expect(llamada[0]!.etiqueta).toContain("saludar")
    // Una función usada dentro de una expresión no es una llamada aparte.
    expect(nodosDe(principal, "salida")[0]!.etiqueta).toContain("cuadrado")
  })

  it("los bloques anidados se dibujan sin superponerse", () => {
    const d = uno(`Algoritmo anidado
	Definir i, j Como Entero
	Para i <- 1 Hasta 3 Hacer
		Si i MOD 2 = 0 Entonces
			Para j <- 1 Hasta i Hacer
				Escribir i * j
			FinPara
		SiNo
			Mientras j < 10 Hacer
				j <- j + i
			FinMientras
		FinSi
	FinPara
FinAlgoritmo
`)
    bienFormado(d, "anidado")
  })
})

describe("C04 errores de sintaxis", () => {
  it("no dibuja nada y da la línea", () => {
    const r = construirDiagramas(`Algoritmo roto
	Escribir "hola
FinAlgoritmo
`)
    expect(r.ok).toBe(false)
    if (r.ok) return
    expect(r.error.linea).toBe(2)
    expect(r.error.mensaje.trim().length).toBeGreaterThan(0)
  })
})

describe("C06 corpus de paridad", () => {
  const dir = join(__dirname, "paridad")
  const esperados = JSON.parse(readFileSync(join(dir, "esperados.json"), "utf-8")) as Record<string, { tipo: string }>
  const correctos = readdirSync(join(dir, "casos"))
    .filter((f) => f.endsWith(".psc"))
    .map((f) => f.replace(/\.psc$/, ""))
    .filter((n) => esperados[n]?.tipo !== "error_sintaxis")
    .sort()

  it("hay al menos 28 algoritmos que dibujar", () => {
    expect(correctos.length).toBeGreaterThanOrEqual(28)
  })

  for (const nombre of correctos) {
    it(`${nombre}: se dibuja bien y siempre igual`, () => {
      const fuente = readFileSync(join(dir, "casos", `${nombre}.psc`), "utf-8")
      const r1 = construirDiagramas(fuente)
      const r2 = construirDiagramas(fuente)
      expect(r1.ok, nombre).toBe(true)
      if (!r1.ok) return
      expect(r1.diagramas.length).toBeGreaterThan(0)
      for (const d of r1.diagramas) bienFormado(d, `${nombre}/${d.nombre}`)
      expect(JSON.stringify(r2)).toBe(JSON.stringify(r1))
    })
  }
})
