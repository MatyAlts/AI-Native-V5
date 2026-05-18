import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { MarkdownRenderer } from "./MarkdownRenderer"

afterEach(() => {
  cleanup()
})

describe("MarkdownRenderer", () => {
  it("renderiza un heading H1 con el texto correcto", () => {
    render(<MarkdownRenderer content="# Titulo principal" />)
    const heading = screen.getByRole("heading", { level: 1 })
    expect(heading).toBeInTheDocument()
    expect(heading).toHaveTextContent("Titulo principal")
  })

  it("renderiza parrafos como elementos <p>", () => {
    render(<MarkdownRenderer content="Esto es un parrafo simple." />)
    expect(screen.getByText("Esto es un parrafo simple.")).toBeInTheDocument()
  })

  it("renderiza tablas GFM con thead y tbody", () => {
    const tableMd = [
      "| Columna A | Columna B |",
      "| --------- | --------- |",
      "| celda1    | celda2    |",
      "| celda3    | celda4    |",
    ].join("\n")
    render(<MarkdownRenderer content={tableMd} />)
    const table = screen.getByRole("table")
    expect(table).toBeInTheDocument()
    expect(screen.getByRole("columnheader", { name: "Columna A" })).toBeInTheDocument()
    expect(screen.getByRole("columnheader", { name: "Columna B" })).toBeInTheDocument()
    expect(screen.getByRole("cell", { name: "celda1" })).toBeInTheDocument()
    expect(screen.getByRole("cell", { name: "celda4" })).toBeInTheDocument()
  })

  it("renderiza links como elementos <a> con href correcto", () => {
    render(<MarkdownRenderer content="Visita [Anthropic](https://anthropic.com)." />)
    const link = screen.getByRole("link", { name: "Anthropic" })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute("href", "https://anthropic.com")
  })

  it("aplica className extra en el wrapper", () => {
    const { container } = render(
      <MarkdownRenderer content="texto" className="extra-class" />,
    )
    const wrapper = container.firstChild as HTMLElement
    expect(wrapper.className).toContain("extra-class")
  })

  it("escapa HTML embebido por default (XSS-safe)", () => {
    render(<MarkdownRenderer content={'<script>alert("xss")</script>'} />)
    // react-markdown escapea <script> por default — no debe existir el elemento
    expect(document.querySelector("script")).toBeNull()
  })
})
