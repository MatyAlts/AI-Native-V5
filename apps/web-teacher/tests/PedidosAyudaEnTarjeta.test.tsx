/**
 * La tarjeta de la comision avisa cuantos pedidos de ayuda pendientes hay
 * (change alumno-pide-ayuda-al-docente). Sin pendientes no muestra nada.
 */
import { screen } from "@testing-library/react"
import { describe, expect, test } from "vitest"
import { ComisionDelDocenteCard } from "../src/components/ComisionDelDocenteCard"
import type { Comision } from "../src/lib/api"
import { renderWithRouter } from "./_mocks"

const comision = {
  id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  codigo: "A",
  nombre: "A-Manana",
  horario: {},
} as unknown as Comision

const kpisBase = { alumnos: 5, episodiosSemana: 3, alertas: 0, adversosSemana: 0 }

describe("ComisionDelDocenteCard: pedidos de ayuda", () => {
  test("con 2 pendientes muestra 2 pedidos de ayuda con link a la vista", async () => {
    renderWithRouter(
      <ComisionDelDocenteCard
        comision={comision}
        displayName="A"
        kpis={{ ...kpisBase, pedidosAyudaPendientes: 2 }}
      />,
    )
    const link = await screen.findByRole("link", { name: /2 pedidos de ayuda/i })
    expect(link.getAttribute("href")).toContain("/pedidos-ayuda")
    expect(link.getAttribute("href")).toContain(`comisionId=${comision.id}`)
  })

  test("con 1 pendiente usa el singular", async () => {
    renderWithRouter(
      <ComisionDelDocenteCard
        comision={comision}
        displayName="A"
        kpis={{ ...kpisBase, pedidosAyudaPendientes: 1 }}
      />,
    )
    expect(await screen.findByRole("link", { name: /1 pedido de ayuda/i })).toBeTruthy()
  })

  test.each([0, null, undefined])("con %s no muestra nada", async (n) => {
    renderWithRouter(
      <ComisionDelDocenteCard
        comision={comision}
        displayName="A"
        kpis={{ ...kpisBase, pedidosAyudaPendientes: n as number | null | undefined }}
      />,
    )
    await screen.findByTestId("comision-card")
    expect(screen.queryByText(/pedido.* de ayuda/i)).toBeNull()
  })
})
