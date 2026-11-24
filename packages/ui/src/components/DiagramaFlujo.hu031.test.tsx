/**
 * Aceptación HU-031 (orquestador, antes de construir; el constructor no la
 * modifica). Criterios acordados el 24/11/2026 (Juani delegó criterios y
 * aceptación).
 *
 * C01  Un bloque ```diagrama en la consigna se ve como diagrama de flujo.
 * C02  Cada forma lleva su tipo y su texto.
 * C04  Con un error de sintaxis se muestra un aviso con la línea, sin dibujo.
 * C07  Accesible: <svg role="img"> con nombre y una lista de pasos en texto.
 * N01  El alumno no ve el pseudocódigo del bloque como código (<pre>/<code>).
 * N02  Un bloque de otro lenguaje (```python) se sigue viendo como código.
 */
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { DiagramaFlujo } from "./DiagramaFlujo"
import { MarkdownRenderer } from "./MarkdownRenderer"

const DOBLE = `Algoritmo doble
	Definir n Como Entero
	Leer n
	Escribir "El doble es ", n * 2
FinAlgoritmo`

describe("DiagramaFlujo", () => {
  it("C02/C07 dibuja un svg accesible con una forma por instrucción", () => {
    const { container } = render(<DiagramaFlujo fuente={DOBLE} />)
    const svgs = container.querySelectorAll('svg[role="img"]')
    expect(svgs.length).toBe(1)
    expect(svgs[0]!.getAttribute("aria-label") ?? "").toMatch(/doble/)
    const tipos = [...container.querySelectorAll("g[data-tipo]")].map((g) =>
      g.getAttribute("data-tipo"),
    )
    expect(tipos).toEqual(["inicio", "proceso", "entrada", "salida", "fin"])
    const leer = container.querySelector('g[data-tipo="entrada"]')!
    expect(leer.textContent).toMatch(/n/)
    const pasos = [...container.querySelectorAll("ol li")].map((li) => li.textContent ?? "")
    expect(pasos.length).toBe(5)
    expect(pasos.some((p) => /Leer/.test(p))).toBe(true)
  })

  it("C02 un diagrama por función y subproceso", () => {
    const fuente = `Funcion r <- cuadrado(x)
	r <- x * x
FinFuncion
Algoritmo principal
	Escribir cuadrado(3)
FinAlgoritmo`
    const { container } = render(<DiagramaFlujo fuente={fuente} />)
    const svgs = [...container.querySelectorAll('svg[role="img"]')]
    expect(svgs.length).toBe(2)
    expect(svgs[0]!.getAttribute("aria-label")).toMatch(/principal/)
    expect(svgs[1]!.getAttribute("aria-label")).toMatch(/cuadrado/)
  })

  it("C04 con error de sintaxis avisa la línea y no dibuja", () => {
    const { container } = render(
      <DiagramaFlujo fuente={'Algoritmo roto\n\tEscribir "hola\nFinAlgoritmo'} />,
    )
    expect(container.querySelector("svg")).toBeNull()
    expect(screen.getByText(/l[ií]nea 2/i)).toBeTruthy()
  })
})

describe("MarkdownRenderer con diagramas", () => {
  it("C01/N01 un bloque ```diagrama se dibuja y no se muestra como código", () => {
    const md = `## Consigna\n\nMirá el diagrama y escribí el algoritmo.\n\n\`\`\`diagrama\n${DOBLE}\n\`\`\`\n`
    const { container } = render(<MarkdownRenderer content={md} />)
    expect(container.querySelectorAll('svg[role="img"]').length).toBe(1)
    expect(container.querySelector("pre")).toBeNull()
    expect(container.querySelector("code")).toBeNull()
    expect(screen.getByText(/Mirá el diagrama/)).toBeTruthy()
  })

  it("N02 un bloque de Python sigue siendo código", () => {
    const md = "```python\nprint(1)\n```\n"
    const { container } = render(<MarkdownRenderer content={md} />)
    expect(container.querySelector("pre")).not.toBeNull()
    expect(container.querySelector("svg")).toBeNull()
  })
})
