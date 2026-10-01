/**
 * Change `alumno-ve-su-nota-sin-depender-del-listado`.
 *
 * El alumno pierde el acceso a su nota cuando el docente archiva la TP: la
 * unica puerta era `TareaSelector`, que itera TPs `published`. Esta pantalla
 * es la puerta nueva — lista las entregas directamente, sin pasar por la TP.
 *
 * `nota_final` llega YA en la entrega (mismo batch que codigo/titulo de TP,
 * `evaluation-service::_notas_metadata`) — correctivo de spec, no mio: el
 * shape original pedia la nota EN LA LISTA, no solo al abrir el detalle, y
 * la primera vuelta de esta change no lo habia resuelto asi. La version
 * anterior pedia `getCalificacion` por cada fila en paralelo (hasta 50
 * requests por carga de pantalla — costo real reportado en netbooks). Esa
 * version ya no existe: la lista NUNCA pide calificaciones, sea cual sea el
 * numero de entregas.
 *
 * Dos niveles de test, mismo criterio que el resto del repo:
 *   - `agruparEntregas` (pura) — unit, sin render.
 *   - `MisNotasList` (presentacional) — render directo, sin fetch ni router.
 *     Mismo patron que `HomeContent` en HomePage.test.tsx.
 *   - `MisNotasPage` (orquestador) — QA encontro un bloqueante acá: si
 *     `listMisMaterias` rechaza, `materias` queda `null` PARA SIEMPRE (el
 *     `.catch` solo setea `materiasError`), y `loading` se calculaba como
 *     `materias === null`, sin mirar el error. Resultado: skeleton eterno,
 *     el `ErrorPanel` (gateado por `!loading && error`) nunca se monta. El
 *     motivo real por el que esto no se vio: `MisNotasList` (presentacional)
 *     tenia tests, pero nadie montaba `MisNotasPage` — los dos `fetch`, el
 *     calculo de `loading`/`error`/`limitReached`, no tenian NINGUN test.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { Entrega, MateriaInscripta } from "../src/lib/api"
import { MisNotasList, MisNotasPage, agruparEntregas } from "../src/pages/MisNotasPage"
import { setupFetchMock } from "./_mocks"

// `MisNotasPage` usa `useNavigate` (sin `<Link>`) — sin RouterProvider,
// `useNavigate` real explota. Mismo patron que HomePage.test.tsx.
vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-router")>()
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  }
})

function makeEntrega(overrides: Partial<Entrega> = {}): Entrega {
  return {
    id: "e1",
    tenant_id: "t1",
    tarea_practica_id: "tp1",
    comision_id: "c1",
    student_pseudonym: "s1",
    estado: "graded",
    ejercicio_estados: [],
    submitted_at: "2026-09-12T10:00:00Z",
    created_at: "2026-09-12T09:00:00Z",
    updated_at: "2026-09-19T12:00:00Z",
    tarea_codigo: "TP2",
    tarea_titulo: "Agenda de turnos",
    nota_final: 8.5,
    ...overrides,
  }
}

describe("agruparEntregas", () => {
  it("separa graded/returned (con nota) de submitted (sin corregir), y excluye draft", () => {
    const graded = makeEntrega({ id: "e-graded", estado: "graded" })
    const returned = makeEntrega({ id: "e-returned", estado: "returned" })
    const submitted = makeEntrega({ id: "e-submitted", estado: "submitted", nota_final: null })
    const draft = makeEntrega({ id: "e-draft", estado: "draft", nota_final: null })

    const { conNota, sinCorregir } = agruparEntregas([graded, returned, submitted, draft])

    expect(conNota.map((e) => e.id).sort()).toEqual(["e-graded", "e-returned"])
    expect(sinCorregir.map((e) => e.id)).toEqual(["e-submitted"])
  })

  it("ordena por fecha de envio, la mas reciente arriba", () => {
    const vieja = makeEntrega({
      id: "vieja",
      estado: "graded",
      submitted_at: "2026-08-28T00:00:00Z",
    })
    const nueva = makeEntrega({
      id: "nueva",
      estado: "graded",
      submitted_at: "2026-09-12T00:00:00Z",
    })

    const { conNota } = agruparEntregas([vieja, nueva])

    expect(conNota.map((e) => e.id)).toEqual(["nueva", "vieja"])
  })
})

describe("MisNotasList", () => {
  it("muestra codigo, titulo y la nota tabular de una entrega calificada — sin pedir nada mas", () => {
    render(
      <MisNotasList
        conNota={[makeEntrega()]}
        sinCorregir={[]}
        limitReached={false}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByText(/TP2/)).toBeInTheDocument()
    expect(screen.getByText(/Agenda de turnos/)).toBeInTheDocument()
    expect(screen.getByTestId("mis-notas-nota").textContent).toBe("8.50")
  })

  it("muestra la fecha de correccion junto a la de entrega cuando hay calificacion", () => {
    render(
      <MisNotasList
        conNota={[
          makeEntrega({ submitted_at: "2026-09-12T10:00:00Z", graded_at: "2026-09-19T12:00:00Z" }),
        ]}
        sinCorregir={[]}
        limitReached={false}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByText(/entregado 12\/09/)).toBeInTheDocument()
    expect(screen.getByText(/corregido 19\/09/)).toBeInTheDocument()
  })

  it("sin fecha de correccion, NO muestra 'corregido' — sólo la de entrega", () => {
    render(
      <MisNotasList
        conNota={[]}
        sinCorregir={[
          makeEntrega({
            estado: "submitted",
            nota_final: null,
            graded_at: null,
            submitted_at: "2026-09-26T10:00:00Z",
          }),
        ]}
        limitReached={false}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByText(/entregado 26\/09/)).toBeInTheDocument()
    expect(screen.queryByText(/corregido/)).not.toBeInTheDocument()
  })

  it("una entrega sin calificar lo dice con palabras, no con un guion pelado", () => {
    render(
      <MisNotasList
        conNota={[]}
        sinCorregir={[makeEntrega({ estado: "submitted", nota_final: null })]}
        limitReached={false}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByText(/el docente no la corrigi[oó] todav[ií]a/i)).toBeInTheDocument()
  })

  it("la nota pendiente lleva texto accesible, no solo un simbolo de color", () => {
    render(
      <MisNotasList
        conNota={[]}
        sinCorregir={[makeEntrega({ estado: "submitted", nota_final: null })]}
        limitReached={false}
        onSelect={vi.fn()}
      />,
    )
    // El guion visual existe, pero el estado se anuncia con texto legible por
    // un lector de pantalla — no depende de un color para distinguirse.
    expect(screen.getByTestId("mis-notas-nota-pendiente").textContent).toMatch(/sin calificar/i)
  })

  it("cada fila es un boton enfocable: Enter la activa igual que el click", async () => {
    const onSelect = vi.fn()
    const entrega = makeEntrega()
    render(
      <MisNotasList
        conNota={[entrega]}
        sinCorregir={[]}
        limitReached={false}
        onSelect={onSelect}
      />,
    )
    const user = userEvent.setup()
    await user.tab()
    expect(screen.getByTestId("mis-notas-row")).toHaveFocus()
    await user.keyboard("{Enter}")
    expect(onSelect).toHaveBeenCalledWith(entrega)
  })

  it("al llegar al limite de 50 avisa en vez de truncar en silencio", () => {
    render(<MisNotasList conNota={[]} sinCorregir={[]} limitReached={true} onSelect={vi.fn()} />)
    expect(screen.getByTestId("mis-notas-limite")).toBeInTheDocument()
    expect(screen.getByTestId("mis-notas-limite").textContent).toMatch(/50/)
  })

  it("sin el limite, no muestra el aviso", () => {
    render(<MisNotasList conNota={[]} sinCorregir={[]} limitReached={false} onSelect={vi.fn()} />)
    expect(screen.queryByTestId("mis-notas-limite")).not.toBeInTheDocument()
  })

  it("click en una fila dispara onSelect con la entrega completa", () => {
    const onSelect = vi.fn()
    const entrega = makeEntrega({ id: "e-click" })
    render(
      <MisNotasList
        conNota={[entrega]}
        sinCorregir={[]}
        limitReached={false}
        onSelect={onSelect}
      />,
    )
    fireEvent.click(screen.getByTestId("mis-notas-row"))
    expect(onSelect).toHaveBeenCalledWith(entrega)
  })

  it("renderiza la lista SIN pedir calificaciones — la nota ya viene en la entrega", async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)

    render(
      <MisNotasList
        conNota={[makeEntrega(), makeEntrega({ id: "e2" })]}
        sinCorregir={[makeEntrega({ id: "e3", estado: "submitted", nota_final: null })]}
        limitReached={false}
        onSelect={vi.fn()}
      />,
    )
    // Deja correr cualquier microtask/efecto que pudiera disparar un fetch
    // al montar, antes de afirmar que no paso nada.
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(fetchSpy).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})

// ─── MisNotasPage: el orquestador, el que QA encontro sin tests ───────────

function makeMateriaInscripta(overrides: Partial<MateriaInscripta> = {}): MateriaInscripta {
  return {
    materia_id: "m1",
    codigo: "PROG1",
    nombre: "Programacion 1",
    comision_id: "c1",
    comision_codigo: "A",
    comision_nombre: "A-Manana",
    horario_resumen: null,
    periodo_id: "p1",
    periodo_codigo: "2026-S2",
    inscripcion_id: "insc1",
    fecha_inscripcion: "2026-03-01",
    ...overrides,
  }
}

describe("MisNotasPage (orquestador)", () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it("si listMisMaterias falla, aparece el panel de error y DESAPARECE el skeleton", async () => {
    setupFetchMock({
      "/api/v1/materias/mias": { ok: false, status: 500, body: () => ({ detail: "boom" }) },
    })

    render(<MisNotasPage />)

    // El bug que QA reporto: esto se quedaba en true para siempre.
    await waitFor(() => {
      expect(screen.getByTestId("mis-notas-error")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("mis-notas-loading")).not.toBeInTheDocument()
  })

  it("si listMisEntregas falla (materias OK), aparece el panel de error y DESAPARECE el skeleton", async () => {
    // Este camino QA dice que ya funcionaba (tiene su propio `loadingEntregas`
    // con `.finally()`) — se fija igual, con el mismo test que el anterior,
    // para que quede en la red y no vuelva a quedar sin cubrir.
    setupFetchMock({
      "/api/v1/materias/mias": () => ({ data: [makeMateriaInscripta()], meta: {} }),
      "/api/v1/entregas": { ok: false, status: 500, body: () => ({ detail: "boom" }) },
    })

    render(<MisNotasPage />)

    await waitFor(() => {
      expect(screen.getByTestId("mis-notas-error")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("mis-notas-loading")).not.toBeInTheDocument()
  })

  it("las dos resuelven vacio — estado vacio, NO un error", async () => {
    setupFetchMock({
      "/api/v1/materias/mias": () => ({ data: [makeMateriaInscripta()], meta: {} }),
      "/api/v1/entregas": () => ({ data: [], meta: { cursor_next: null } }),
    })

    render(<MisNotasPage />)

    await waitFor(() => {
      expect(screen.getByTestId("mis-notas-empty")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("mis-notas-error")).not.toBeInTheDocument()
  })

  it("50 entregas — limitReached se calcula y se muestra el aviso", async () => {
    const entregas = Array.from({ length: 50 }, (_, i) =>
      makeEntrega({ id: `e${i}`, estado: "graded", nota_final: 7 }),
    )
    setupFetchMock({
      "/api/v1/materias/mias": () => ({ data: [makeMateriaInscripta()], meta: {} }),
      "/api/v1/entregas": () => ({ data: entregas, meta: { cursor_next: null } }),
    })

    render(<MisNotasPage />)

    await waitFor(() => {
      expect(screen.getByTestId("mis-notas-limite")).toBeInTheDocument()
    })
  })
})
