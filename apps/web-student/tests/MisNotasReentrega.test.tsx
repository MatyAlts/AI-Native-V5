/**
 * Item 27 de MEJORAS-PLATAFORMA.md — "Mis notas" con una re-entrega se contradice.
 *
 * Visto en prod el 24/11 y otra vez el 25/11: el docente devuelve un TP ya
 * calificado y el alumno lo vuelve a entregar. Devolver no borra la
 * calificacion (memoria `reentrega-409-ya-calificada`), asi que la entrega
 * queda `submitted` pero sigue trayendo `nota_final` y `graded_at` de la
 * correccion vieja (`graded_at` 21:16 < `submitted_at` 21:18).
 *
 * Mis notas la listaba bajo "Sin corregir todavia" con "corregido 24/11" y el
 * 9.00 viejo a la derecha, como si fuera la nota vigente, mientras la pagina
 * del curso decia "Esperando correccion". Y al abrirla mostraba solo
 * "Pendiente de correccion": ni la nota anterior ni el feedback que dice que
 * rehacer.
 *
 * Lo que se pide:
 *   - en la lista, una entrega `submitted` NUNCA muestra una nota como
 *     vigente: la vieja aparece rotulada "nota anterior";
 *   - en el detalle, debajo del "Pendiente de correccion", la correccion
 *     anterior con su feedback, rotulada como anterior.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { GradeDetailView } from "../src/components/GradeDetailView"
import type { Entrega } from "../src/lib/api"
import { MisNotasList } from "../src/pages/MisNotasPage"
import { setupFetchMock } from "./_mocks"

function reentrega(overrides: Partial<Entrega> = {}): Entrega {
  return {
    id: "f4a8026a-1277-48cb-89b4-d3092d4c4138",
    tenant_id: "t1",
    tarea_practica_id: "tp1",
    comision_id: "c1",
    student_pseudonym: "s1",
    estado: "submitted",
    ejercicio_estados: [],
    submitted_at: "2026-11-24T21:18:43Z",
    created_at: "2026-11-24T20:48:16Z",
    updated_at: "2026-11-24T21:18:43Z",
    tarea_codigo: "TP3.1-U1-v2",
    tarea_titulo: "Secuenciales (prueba 2)",
    nota_final: 9,
    graded_at: "2026-11-24T21:16:45Z",
    ...overrides,
  }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("Item 27 — lista de Mis notas", () => {
  it("una re-entrega sin corregir no muestra la nota vieja como vigente", () => {
    render(
      <MisNotasList
        conNota={[]}
        sinCorregir={[reentrega()]}
        limitReached={false}
        onSelect={vi.fn()}
      />,
    )

    expect(screen.queryByTestId("mis-notas-nota")).not.toBeInTheDocument()
    expect(screen.getByTestId("mis-notas-nota-pendiente")).toBeInTheDocument()
    expect(screen.queryByText(/· corregido/)).not.toBeInTheDocument()
  })

  it("la nota vieja aparece rotulada como anterior", () => {
    render(
      <MisNotasList
        conNota={[]}
        sinCorregir={[reentrega()]}
        limitReached={false}
        onSelect={vi.fn()}
      />,
    )

    expect(screen.getByTestId("mis-notas-nota-anterior").textContent).toMatch(
      /nota anterior 9\.00/i,
    )
  })

  it("una entrega calificada sigue mostrando su nota y su fecha de correccion", () => {
    render(
      <MisNotasList
        conNota={[reentrega({ estado: "graded", submitted_at: "2026-11-24T21:10:00Z" })]}
        sinCorregir={[]}
        limitReached={false}
        onSelect={vi.fn()}
      />,
    )

    expect(screen.getByTestId("mis-notas-nota").textContent).toBe("9.00")
    expect(screen.getByText(/corregido 24\/11/)).toBeInTheDocument()
    expect(screen.queryByTestId("mis-notas-nota-anterior")).not.toBeInTheDocument()
  })
})

describe("Item 27 — detalle de la re-entrega", () => {
  it("muestra la correccion anterior con su feedback, rotulada como anterior", async () => {
    setupFetchMock({
      "/calificacion": () => ({
        id: "cal-1",
        entrega_id: "f4a8026a-1277-48cb-89b4-d3092d4c4138",
        nota_final: 9,
        feedback_general: "Rehace el ejercicio 6 sin bucles.",
        detalle_criterios: [],
        graded_at: "2026-11-24T21:16:45Z",
        graded_by: "docente-1",
      }),
    })

    render(<GradeDetailView entrega={reentrega()} onBack={vi.fn()} />)

    expect(screen.getByTestId("pending-correction-state")).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByTestId("correccion-anterior")).toBeInTheDocument()
    })
    expect(screen.getByText(/Rehace el ejercicio 6 sin bucles/)).toBeInTheDocument()
    expect(screen.getByTestId("correccion-anterior").textContent).toMatch(/anterior/i)
    // La nota vieja no se presenta como "NOTA FINAL" de esta entrega.
    expect(screen.queryByTestId("nota-final")).not.toBeInTheDocument()
  })

  it("una entrega submitted sin correccion previa no pide la calificacion", () => {
    setupFetchMock({})
    const fetchSpy = vi.mocked(globalThis.fetch)

    render(
      <GradeDetailView
        entrega={reentrega({ nota_final: null, graded_at: null })}
        onBack={vi.fn()}
      />,
    )

    expect(screen.getByTestId("pending-correction-state")).toBeInTheDocument()
    expect(screen.queryByTestId("correccion-anterior")).not.toBeInTheDocument()
    expect(fetchSpy.mock.calls.some(([url]) => String(url).includes("/calificacion"))).toBe(false)
  })
})
