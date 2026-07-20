import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it } from "vitest"
import { PageContainer } from "./PageContainer"

afterEach(() => {
  cleanup()
})

describe("PageContainer", () => {
  it("renderiza title, description y children", () => {
    render(
      <PageContainer title="Mi Pagina" description="Descripcion breve" helpContent={<p>help</p>}>
        <div>contenido de la pagina</div>
      </PageContainer>,
    )
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Mi Pagina")
    expect(screen.getByText("Descripcion breve")).toBeInTheDocument()
    expect(screen.getByText("contenido de la pagina")).toBeInTheDocument()
  })

  it("siempre muestra el HelpButton (el skill lo exige)", () => {
    render(
      <PageContainer title="T" helpContent={<p>x</p>}>
        <div>x</div>
      </PageContainer>,
    )
    expect(screen.getByRole("button", { name: /ayuda/i })).toBeInTheDocument()
  })

  it("al click en el HelpButton abre el modal con el helpContent pasado", async () => {
    render(
      <PageContainer title="Periodos" helpContent={<p>ayuda de periodos</p>}>
        <div>body</div>
      </PageContainer>,
    )
    await userEvent.click(screen.getByRole("button", { name: /ayuda/i }))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByText("ayuda de periodos")).toBeInTheDocument()
  })

  it("omite el parrafo de description cuando no se pasa", () => {
    render(
      <PageContainer title="T" helpContent={<p>h</p>}>
        <div>c</div>
      </PageContainer>,
    )
    expect(screen.queryByTestId("page-description")).toBeNull()
  })
})
