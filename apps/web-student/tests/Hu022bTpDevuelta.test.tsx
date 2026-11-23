/**
 * HU-022 (vuelta 2), C05 c (F30): un TP devuelto (`returned`) no es "Listo ·
 * corregidas": el docente pidió que se rehaga. Va a la zona de trabajo activo
 * (Pendiente) con la marca "Devuelta" y un botón para abrirlo y re-entregar.
 * Una entrega `graded` sigue en Listo (guarda).
 * Prueba propia del constructor (sin aceptación congelada para este punto).
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { TareaSelector } from "../src/components/TareaSelector"
import type { AvailableTarea, Entrega } from "../src/lib/api"
import { setupFetchMock } from "./_mocks"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

function tarea(id: string, codigo: string): AvailableTarea {
  return {
    id,
    codigo,
    titulo: `TP ${codigo}`,
    enunciado: "x",
    fecha_inicio: null,
    fecha_fin: null,
    peso: "1.0",
    estado: "published",
    version: 1,
    inicial_codigo: null,
  }
}

function entrega(tareaId: string, estado: Entrega["estado"]): Entrega {
  return {
    id: `ent-${tareaId}`,
    tenant_id: "t1",
    tarea_practica_id: tareaId,
    comision_id: COMISION_ID,
    student_pseudonym: "b1b1b1b1-0001-0001-0001-000000000001",
    estado,
    ejercicio_estados: [],
    submitted_at: "2026-11-20T10:00:00Z",
    created_at: "2026-11-20T10:00:00Z",
    updated_at: "2026-11-21T10:00:00Z",
  }
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function montar(onSelect = vi.fn()) {
  const devuelta = tarea("tp-dev", "DEV")
  const calificada = tarea("tp-cal", "CAL")
  setupFetchMock({
    "/student/me/episodes": () => ({ episodes: [] }),
    "tarea_practica_id=tp-dev": () => ({ data: [entrega("tp-dev", "returned")], meta: {} }),
    "tarea_practica_id=tp-cal": () => ({ data: [entrega("tp-cal", "graded")], meta: {} }),
    "/api/v1/tareas-practicas": () => ({
      data: [devuelta, calificada],
      meta: { cursor_next: null },
    }),
  })
  render(<TareaSelector comisionId={COMISION_ID} onSelect={onSelect} />)
  return { devuelta, onSelect }
}

describe("C05 c · el TP devuelto no cae en Listo", () => {
  it("la entrega devuelta va a Pendiente con su marca y un botón para rehacer", async () => {
    const { devuelta, onSelect } = montar()
    await waitFor(() => expect(screen.getByTestId("entrega-badge-returned")).toBeDefined())
    const pendiente = screen.getByTestId("zone-pendiente")
    const card = within(pendiente).getByText("TP DEV").closest("[data-testid='tp-card']")
    expect(card, "el TP devuelto no está en Pendiente").not.toBeNull()
    expect(within(card as HTMLElement).getByTestId("entrega-badge-returned")).toBeDefined()
    const listo = screen.getByTestId("zone-listo")
    expect(within(listo).queryByText("TP DEV")).toBeNull()
    fireEvent.click(within(card as HTMLElement).getByRole("button", { name: /rehacer/i }))
    expect(onSelect).toHaveBeenCalledWith(devuelta)
  })

  it("una entrega calificada sigue en Listo", async () => {
    montar()
    await waitFor(() => expect(screen.getByTestId("zone-listo")).toBeDefined())
    expect(within(screen.getByTestId("zone-listo")).getByText("TP CAL")).toBeDefined()
  })
})
