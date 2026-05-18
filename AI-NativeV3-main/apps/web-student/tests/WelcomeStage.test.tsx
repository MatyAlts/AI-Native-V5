/**
 * Tests del WelcomeStage (shape alumno, brief 3.2 + D2).
 *
 * Cubre:
 *  - Render del kicker, display, body con el mensaje del contrato.
 *  - Strip N1-N4 con 4 dots coloreados (los testids confirman cada nivel).
 *  - CTA primario con var(--color-accent-brand) y handler.
 *  - Mensaje literal del gap B.2 cuando comisionesVacias=true.
 */
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, test, vi } from "vitest"
import { WelcomeStage } from "../src/components/WelcomeStage"

describe("WelcomeStage", () => {
  test("renderiza el kicker, display y mensaje del contrato pedagogico", () => {
    render(<WelcomeStage />)

    // Kicker
    expect(screen.getByText(/Programacion 2/i)).toBeInTheDocument()

    // Display: heading principal con la promesa de la tesis
    const heading = screen.getByRole("heading", { level: 1 })
    expect(heading).toHaveTextContent(/Tutor socratico con trazabilidad cognitiva/i)

    // Body: contrato pedagogico + cripto auditable
    expect(screen.getByText(/No te da la respuesta/i)).toBeInTheDocument()
    expect(screen.getByText(/cadena verificable/i)).toBeInTheDocument()
  })

  test("renderiza el strip horizontal con los 4 niveles N1-N4", () => {
    render(<WelcomeStage />)

    expect(screen.getByText(/Como trabajas/i)).toBeInTheDocument()
    expect(screen.getByText(/N1 Lectura/i)).toBeInTheDocument()
    expect(screen.getByText(/N2 Anotacion/i)).toBeInTheDocument()
    expect(screen.getByText(/N3 Validacion/i)).toBeInTheDocument()
    expect(screen.getByText(/N4 Tutor/i)).toBeInTheDocument()

    // Cada uno tiene un dot identificable por testid (color via CSS var).
    expect(screen.getByTestId("level-dot-n1")).toBeInTheDocument()
    expect(screen.getByTestId("level-dot-n2")).toBeInTheDocument()
    expect(screen.getByTestId("level-dot-n3")).toBeInTheDocument()
    expect(screen.getByTestId("level-dot-n4")).toBeInTheDocument()
  })

  test("CTA primario dispara onPickComision al hacer click", async () => {
    const user = userEvent.setup()
    const onPick = vi.fn()
    render(<WelcomeStage onPickComision={onPick} />)

    const cta = screen.getByTestId("welcome-cta-pick-comision")
    expect(cta).toHaveTextContent(/Elegir comision/i)
    await user.click(cta)
    expect(onPick).toHaveBeenCalledTimes(1)
  })

  test("muestra el mensaje literal del gap B.2 cuando comisionesVacias=true", () => {
    render(<WelcomeStage comisionesVacias={true} />)

    const banner = screen.getByTestId("welcome-gap-b2")
    expect(banner).toHaveTextContent(/No estas viendo tus comisiones/i)
    expect(banner).toHaveTextContent(/Direccion de Informatica/i)
    expect(banner).toHaveTextContent(/gap-B.2 \/ ADR-029/i)
  })

  test("no muestra el banner B.2 cuando comisionesVacias es false (default)", () => {
    render(<WelcomeStage />)
    expect(screen.queryByTestId("welcome-gap-b2")).not.toBeInTheDocument()
  })
})
