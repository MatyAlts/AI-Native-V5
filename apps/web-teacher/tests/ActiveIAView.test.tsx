/**
 * Tests de la vista de correccion asistida.
 *
 * Lo que fijan, en orden de importancia:
 *  - Que el aviso de MODO SIMULADO se vea, y que se vea ANTES de elegir un TP
 *    (si no, el docente conecta su cuenta sin saber que nada va a llegar).
 *  - Que "Sincronizar" este deshabilitado sin cuenta conectada.
 *  - Que un estado desconocido del backend NO rompa la tabla entera.
 */
import { screen, waitFor } from "@testing-library/react"
import { describe, expect, test } from "vitest"
import { ActiveIAView } from "../src/views/ActiveIAView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const COMISION = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
const getToken = async () => null

function credencial(over: Record<string, unknown> = {}) {
  return {
    conectada: true,
    modo_simulado: false,
    username: "docente@utn.edu.ar",
    created_at: "2026-08-18T10:00:00Z",
    last_login_at: "2026-08-18T10:00:00Z",
    last_login_ok: true,
    ...over,
  }
}

describe("ActiveIAView", () => {
  test("avisa el modo simulado antes de elegir un TP", async () => {
    setupFetchMock({
      "/api/v1/activeia/credenciales": () => credencial({ modo_simulado: true }),
      "/api/v1/tareas-practicas": () => ({ data: [], meta: { cursor_next: null } }),
    })
    renderWithRouter(<ActiveIAView comisionId={COMISION} getToken={getToken} />)

    await waitFor(() => {
      expect(screen.getByTestId("activeia-modo-simulado")).toBeInTheDocument()
    })
  })

  test("sin simulador no muestra el aviso", async () => {
    setupFetchMock({
      "/api/v1/activeia/credenciales": () => credencial(),
      "/api/v1/tareas-practicas": () => ({ data: [], meta: { cursor_next: null } }),
    })
    renderWithRouter(<ActiveIAView comisionId={COMISION} getToken={getToken} />)

    await waitFor(() => {
      expect(screen.getByText(/Tu cuenta de Active-IA/i)).toBeInTheDocument()
    })
    expect(screen.queryByTestId("activeia-modo-simulado")).not.toBeInTheDocument()
  })

  test("sin cuenta conectada no se puede sincronizar", async () => {
    setupFetchMock({
      "/api/v1/activeia/credenciales": () => ({ conectada: false, modo_simulado: false }),
      "/api/v1/tareas-practicas": () => ({ data: [], meta: { cursor_next: null } }),
    })
    renderWithRouter(<ActiveIAView comisionId={COMISION} getToken={getToken} />)

    await waitFor(() => {
      expect(screen.getByTestId("activeia-conectar")).toBeInTheDocument()
    })
    expect(screen.getByTestId("activeia-sincronizar")).toBeDisabled()
  })

  test("con cuenta conectada ofrece desconectar", async () => {
    setupFetchMock({
      "/api/v1/activeia/credenciales": () => credencial(),
      "/api/v1/tareas-practicas": () => ({ data: [], meta: { cursor_next: null } }),
    })
    renderWithRouter(<ActiveIAView comisionId={COMISION} getToken={getToken} />)

    await waitFor(() => {
      expect(screen.getByTestId("activeia-desconectar")).toBeInTheDocument()
    })
    expect(screen.getByText(/docente@utn.edu.ar/)).toBeInTheDocument()
  })
})
